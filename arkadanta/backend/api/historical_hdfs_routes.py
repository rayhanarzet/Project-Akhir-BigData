"""Dedicated API routes for historical CSV data delivered to HDFS by NiFi."""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.schemas import DynamicConfig

from backend.config import (
    DEFAULT_FEATURES,
    HDFS_BASE_PATH,
    HISTORICAL_LOCAL_OUTPUT_PATH,
    HISTORICAL_OUTPUT_MODE,
    HISTORICAL_HDFS_OUTPUT_PATH,
    HISTORICAL_HDFS_RAW_PATH,
    HISTORICAL_HDFS_URI,
)
router = APIRouter(prefix="/api/historical-hdfs", tags=["Historical HDFS Batch"])


class HistoricalHdfsRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(default="BTCUSDT", pattern=r"^[A-Za-z0-9]{2,30}$")
    timeframe: Literal["5m", "15m", "1h", "4h", "1d", "1w"] = "1h"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    features: list[str] = Field(default_factory=lambda: list(DEFAULT_FEATURES))
    gmm_components: int = Field(default=3, ge=3, le=6)
    train_ratio: float = Field(default=0.8, ge=0.5, le=0.95)
    gb_max_iter: int = Field(default=200, ge=20, le=500)
    gb_max_depth: int = Field(default=10, ge=3, le=30)
    # raw: dump historis Binance yang dimasukkan NiFi; clean: data aplikasi dari NiFi outbox (berpartisi).
    source: Literal["raw", "clean"] = "clean"


@router.get("/config")
def get_historical_hdfs_config():
    """Show the default HDFS input convention for the NiFi historical flow."""
    return {
        "hdfs_uri": HISTORICAL_HDFS_URI,
        "raw_root": HISTORICAL_HDFS_RAW_PATH,
        "output_mode": HISTORICAL_OUTPUT_MODE,
        "output_root": (
            HISTORICAL_HDFS_OUTPUT_PATH
            if HISTORICAL_OUTPUT_MODE == "hdfs"
            else str(HISTORICAL_LOCAL_OUTPUT_PATH)
        ),
        "default_input_pattern": f"{HISTORICAL_HDFS_URI}{HISTORICAL_HDFS_RAW_PATH}/symbol=<SYMBOL>",
        "clean_input_pattern": f"{HISTORICAL_HDFS_URI}{HDFS_BASE_PATH}symbol=<SYMBOL>/year=<YYYY>/month=<MM>/",
        "expected_format": "CSV with OHLCV header row and 5m candles",
        "default_features": DEFAULT_FEATURES,
        "max_history_days": 365,
    }


@router.post("/run")
def run_historical_hdfs(req: HistoricalHdfsRunRequest):
    """Read NiFi-delivered CSV from HDFS, process it, train Spark ML, and persist outputs."""
    from spark_jobs.locks import SparkBusyError

    try:
        from spark_jobs.historical_hdfs_job import run_historical_hdfs_job

        params = req.model_dump(exclude={"source"})
        input_path = f"{HDFS_BASE_PATH.rstrip('/')}/symbol={req.symbol.upper()}" if req.source == "clean" else None
        return run_historical_hdfs_job(DynamicConfig(**params), input_path=input_path)
    except SparkBusyError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        error_text = str(exc)
        if "10061" in error_text or "actively refused" in error_text.lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    "NameNode menolak koneksi. Backend mencoba menghubungi "
                    f"'{HISTORICAL_HDFS_URI}', tetapi tidak ada layanan RPC yang menerima koneksi "
                    "di alamat tersebut. Jalankan NameNode atau atur "
                    "ARKADANTA_HISTORICAL_HDFS_URI ke host:port RPC NameNode yang dapat dijangkau "
                    "backend, lalu mulai ulang backend. Path NiFi belum diperiksa karena koneksi "
                    f"belum terbentuk. Detail: {error_text}"
                ),
            ) from exc
        if HISTORICAL_OUTPUT_MODE == "hdfs" and (
            "AccessControlException" in error_text or "Permission denied" in error_text
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Spark berhasil membaca dan mengolah input, tetapi tidak memiliki izin tulis "
                    f"ke output HDFS '{HISTORICAL_HDFS_OUTPUT_PATH}'. Gunakan direktori yang "
                    "dapat ditulis oleh user Hadoop yang menjalankan FastAPI, atau minta admin "
                    "HDFS memberi izin pada direktori output tersebut."
                ),
            ) from exc
        raise HTTPException(
            status_code=503,
            detail=f"Pipeline historis HDFS gagal. Periksa koneksi NameNode dan path NiFi. Detail: {error_text}",
        ) from exc
