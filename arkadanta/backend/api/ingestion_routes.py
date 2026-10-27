"""Endpoint Ingestion & Historical Baseline (Kontrak Orang 1 <-> Orang 2)."""

import asyncio
from datetime import datetime, timezone
import json
from typing import Optional
import uuid
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import pandas as pd
import requests

from backend.config import (
    BINANCE_KLINES_URL,
    DEFAULT_SYMBOLS,
    DROP_ZONE_DIR,
    HDFS_BASE_PATH,
    MAX_UPLOAD_BYTES,
)
from backend.ingestion.dynamic_pipeline import run_dynamic_ingestion_pipeline
from backend.schemas import (
    BackfillRequest,
    CronConfigRequest,
    CronStatusResponse,
    IngestionAuditReport,
    LiveSyncRequest,
)
from backend.scheduler import cron_scheduler
from data.storage import (
    load_audit_logs,
    load_clean_ohlcv,
    save_audit_logs,
)

router = APIRouter(tags=["Ingestion & Baseline"])


@router.post("/api/ingestion/upload", response_model=IngestionAuditReport)
async def upload_dataset(
    file: UploadFile = File(...),
    default_symbol: str = Form("BTCUSDT"),
    column_mapping_json: Optional[str] = Form(None),
):
    """Menerima unggahan CSV/JSON, menjalankan Dynamic Pipeline Controller, dan mengembalikan laporan audit."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Berkas melebihi {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Kirim data besar lewat NiFi ke HDFS.")
    try:
        custom_map = json.loads(column_mapping_json) if column_mapping_json else None
        # Parsing CPU-bound di thread agar stream live (event loop) tidak tertahan.
        _, report = await asyncio.to_thread(
            run_dynamic_ingestion_pipeline,
            filename=file.filename or "uploaded_data.csv",
            content=content,
            custom_mapping=custom_map,
            default_symbol=default_symbol,
        )
        return report
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/ingestion/cron-status", response_model=CronStatusResponse)
def get_cron_status():
    """Mengambil status background cron scheduler untuk sinkronisasi live data."""
    return cron_scheduler.get_status()


@router.post("/api/ingestion/cron-config", response_model=CronStatusResponse)
def configure_cron(req: CronConfigRequest):
    """Mengaktifkan/menonaktifkan atau mengatur interval waktu background cron job."""
    return cron_scheduler.configure(
        enabled=req.enabled,
        interval_minutes=req.interval_minutes,
        symbols=req.symbols,
        limit=req.limit,
    )


@router.post("/api/ingestion/live-sync")
def sync_live_binance(req: LiveSyncRequest):
    """Menarik candle 5 menit terbaru secara manual dari Binance API (/api/v3/klines)."""
    try:
        synced_reports = cron_scheduler.trigger_sync(symbols=req.symbols, limit=req.limit)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Sinkronisasi Binance gagal: {exc}. Data simulasi tidak digunakan.") from exc
    return {"status": "ok", "synced_assets": len(synced_reports), "reports": synced_reports}


@router.post("/api/ingestion/backfill")
def backfill_binance_history(req: BackfillRequest):
    """Menarik histori 5m Binance hingga 365 hari; baris baru ikut masuk NiFi outbox untuk HDFS."""
    try:
        reports = cron_scheduler.backfill(req.symbols, req.days)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Backfill Binance gagal: {exc}. Aset yang sudah selesai tetap tersimpan.") from exc
    return {"status": "ok", "synced_assets": len(reports), "reports": reports}


@router.get("/api/historical-baseline")
def get_historical_baseline():
    """Mengembalikan ringkasan dataset per aset, status HDFS/NiFi, dan log audit validasi Orang 1."""
    assets_summary = []
    for sym in DEFAULT_SYMBOLS:
        if not (DROP_ZONE_DIR / f"{sym}_5m_clean.csv").exists():
            continue
        df = load_clean_ohlcv(sym)
        assets_summary.append(
            {
                "symbol": sym,
                "rows_5m": len(df),
                "start_timestamp": str(df["timestamp"].min()),
                "end_timestamp": str(df["timestamp"].max()),
                "latest_close": round(float(df["close"].iloc[-1]), 6),
                "avg_volume_5m": round(float(df["volume"].mean()), 4),
                "hdfs_partition": f"{HDFS_BASE_PATH}symbol={sym}/",
                "status": "READY",
            }
        )
    logs = load_audit_logs()
    return {
        "pipeline_status": "ONLINE" if assets_summary else "NO_DATA",
        "hdfs_cluster_path": HDFS_BASE_PATH,
        "assets": assets_summary,
        "audit_logs": logs[:20],
    }
