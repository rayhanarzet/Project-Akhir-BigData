"""Skema Pydantic untuk request/response API dan kontrak integrasi Orang 1 & Orang 2."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class IngestionAuditReport(BaseModel):
    """Kontrak laporan hasil validasi & preprocessing dari Orang 1."""

    run_id: str
    timestamp: str
    source_name: str
    format_detected: Literal["CSV", "JSON", "BINANCE_API"]
    selected_pipeline: str
    column_mapping: Dict[str, str] = Field(default_factory=dict)
    symbols_detected: List[str] = Field(default_factory=list)
    rows_before: int
    rows_after: int
    duplicates_removed: int = 0
    imputed_ohlc_rows: int = 0
    imputed_volume_rows: int = 0
    rejected_rows: int = 0
    error_reasons: Dict[str, int] = Field(default_factory=dict)
    drop_zone_path: str
    hdfs_target_path: str
    nifi_hdfs_status: Literal["SYNCED", "QUEUED_DROP_ZONE", "LOCAL_FALLBACK"] = (
        "SYNCED"
    )
    quality_score_pct: float


class LiveSyncRequest(BaseModel):
    symbols: List[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
    )
    interval: str = "5m"
    limit: int = Field(default=300, ge=50, le=1000)


class CronConfigRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(default=5, ge=1, le=1440)
    symbols: List[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
    )
    limit: int = Field(default=60, ge=10, le=500)


class CronStatusResponse(BaseModel):
    enabled: bool
    interval_minutes: int
    symbols: List[str]
    limit: int
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    last_status: str
    last_synced_count: int
    total_runs: int


class DynamicConfig(BaseModel):
    """Konfigurasi dinamis sesuai Bab 5.7 Proposal Arkadanta."""

    symbols: List[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    )
    symbol: str = "BTCUSDT"
    timeframe: Literal["5m", "15m", "1h", "4h", "1d", "1w"] = "1h"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    features: List[str] = Field(
        default_factory=lambda: [
            "max_volatility",
            "spike_ratio",
            "rsi_14",
            "volume_zscore",
            "bb_width",
            "hl_range",
        ]
    )
    # Parameter indikator teknikal & rolling
    ma_period: int = Field(default=20, ge=5, le=200)
    rsi_period: int = Field(default=14, ge=5, le=100)
    rolling_window: int = Field(default=20, ge=5, le=200)
    # Parameter deteksi anomali
    anomaly_method: Literal[
        "rolling_zscore", "iqr", "adaptive_quantile", "kmeans"
    ] = "adaptive_quantile"
    anomaly_quantile: float = Field(default=0.95, ge=0.80, le=0.999)
    anomaly_z_threshold: float = Field(default=2.5, ge=1.5, le=5.0)
    anomaly_iqr_multiplier: float = Field(default=1.5, ge=1.0, le=4.0)
    # Parameter K-Means & Random Forest
    cluster_k: int = Field(default=3, ge=3, le=6)
    correlation_window: int = Field(default=30, ge=5, le=200)
    max_lag: int = Field(default=6, ge=1, le=24)
    train_ratio: float = Field(default=0.8, ge=0.5, le=0.95)
    rf_num_trees: int = Field(default=200, ge=20, le=500)
    rf_max_depth: int = Field(default=10, ge=3, le=30)
    target_horizon: int = Field(default=1, ge=1, le=12)
    use_spark: bool = False


class PredictRequest(BaseModel):
    symbol: str = "BTCUSDT"
    timeframe: Literal["5m", "15m", "1h", "4h", "1d", "1w"] = "1h"
    custom_features: Optional[Dict[str, float]] = None
    current_price: Optional[float] = None
    target_horizon: int = 1
