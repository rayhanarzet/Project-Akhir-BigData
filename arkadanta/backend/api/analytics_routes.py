"""[ORANG 2] Endpoint Analitik BI, Deteksi Anomali, dan Korelasi Lintas Aset (Bab 3.3 & Bab 5)."""

from fastapi import APIRouter, Query
import pandas as pd

from backend.analytics.anomaly_detector import detect_anomalies
from backend.analytics.correlation_analyzer import analyze_cross_asset_correlation
from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.config import DEFAULT_SYMBOLS
from backend.schemas import DynamicConfig
from data.sample_generator import load_clean_ohlcv

router = APIRouter(tags=["Analytics & BI (Orang 2)"])


@router.post("/api/analytics/run")
def run_dynamic_analytics(config: DynamicConfig):
    """Menjalankan agregasi timeframe, feature engineering dinamis, dan deteksi anomali."""
    symbol = config.symbol.upper()
    df_5m = load_clean_ohlcv(symbol)
    df_agg = aggregate_timeframe(
        df_5m,
        timeframe=config.timeframe,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    df_feat = compute_dynamic_features(
        df_agg,
        ma_period=config.ma_period,
        rsi_period=config.rsi_period,
        rolling_window=config.rolling_window,
    )
    df_anom, anom_summary = detect_anomalies(
        df_feat,
        method=config.anomaly_method,
        quantile=config.anomaly_quantile,
        z_threshold=config.anomaly_z_threshold,
        iqr_multiplier=config.anomaly_iqr_multiplier,
        rolling_window=config.rolling_window,
        feature_cols=config.features,
    )

    df_anom["timestamp"] = df_anom["timestamp"].astype(str)
    anomalies_only = df_anom[df_anom["is_anomaly"]].tail(100).to_dict(orient="records")
    series_records = df_anom.tail(400).to_dict(orient="records")

    return {
        "symbol": symbol,
        "timeframe": config.timeframe,
        "total_candles": len(df_anom),
        "selected_features": config.features,
        "anomaly_summary": anom_summary,
        "anomalies_log": anomalies_only,
        "series": series_records,
    }


@router.get("/api/analytics/correlation")
def get_cross_asset_correlation(
    timeframe: str = Query("1h", pattern="^(5m|15m|1h|4h|1d|1w)$"),
    base_symbol: str = Query("BTCUSDT"),
    target_symbol: str = Query("ETHUSDT"),
    rolling_window: int = Query(30, ge=5, le=200),
    max_lag: int = Query(6, ge=1, le=24),
):
    """Menghitung korelasi Pearson, rolling correlation, lag correlation, dan market-wide risk score."""
    frames = []
    for sym in DEFAULT_SYMBOLS:
        df_5m = load_clean_ohlcv(sym)
        df_agg = aggregate_timeframe(df_5m, timeframe=timeframe)
        df_feat = compute_dynamic_features(df_agg, rolling_window=rolling_window)
        frames.append(df_feat)

    df_multi = pd.concat(frames, ignore_index=True)
    return analyze_cross_asset_correlation(
        df_multi,
        base_symbol=base_symbol.upper(),
        target_symbol=target_symbol.upper(),
        rolling_window=rolling_window,
        max_lag=max_lag,
    )
