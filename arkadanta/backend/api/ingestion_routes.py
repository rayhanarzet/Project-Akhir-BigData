"""Endpoint Ingestion & Historical Baseline (Kontrak Orang 1 <-> Orang 2)."""

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
)
from backend.ingestion.dynamic_pipeline import run_dynamic_ingestion_pipeline
from backend.schemas import (
    CronConfigRequest,
    CronStatusResponse,
    IngestionAuditReport,
    LiveSyncRequest,
)
from backend.scheduler import cron_scheduler
from data.sample_generator import (
    ensure_sample_data_exists,
    generate_synthetic_5m_ohlcv,
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
    try:
        content = await file.read()
        custom_map = json.loads(column_mapping_json) if column_mapping_json else None
        _, report = run_dynamic_ingestion_pipeline(
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
    synced_reports = cron_scheduler.trigger_sync(symbols=req.symbols, limit=req.limit)
    return {"status": "ok", "synced_assets": len(synced_reports), "reports": synced_reports}


@router.get("/api/historical-baseline")
def get_historical_baseline():
    """Mengembalikan ringkasan dataset per aset, status HDFS/NiFi, dan log audit validasi Orang 1."""
    ensure_sample_data_exists(DEFAULT_SYMBOLS)
    assets_summary = []
    for sym in DEFAULT_SYMBOLS:
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
        "pipeline_status": "ONLINE",
        "hdfs_cluster_path": HDFS_BASE_PATH,
        "assets": assets_summary,
        "audit_logs": logs[:20],
    }
