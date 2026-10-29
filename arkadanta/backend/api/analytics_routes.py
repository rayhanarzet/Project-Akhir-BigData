"""[ORANG 2] Endpoint Analitik BI, Deteksi Anomali, dan Korelasi Lintas Aset (Bab 3.3 & Bab 5)."""

from fastapi import APIRouter, HTTPException, Query
import pandas as pd

from backend.analytics.anomaly_detector import detect_anomalies
from backend.analytics.correlation_analyzer import (
    analyze_cross_asset_correlation,
    compute_historical_factor_attribution,
)
from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe, TIMEFRAME_DURATION
from backend.config import DEFAULT_SYMBOLS, DROP_ZONE_DIR
from backend.schemas import DynamicConfig
from data.storage import ResearchDataError, load_clean_ohlcv

router = APIRouter(tags=["Analytics & BI (Orang 2)"])


@router.post("/api/analytics/run")
def run_dynamic_analytics(config: DynamicConfig):
    """Menjalankan agregasi timeframe, feature engineering dinamis, deteksi anomali, dan atribusi faktor lampau."""
    symbol = config.symbol.upper()
    execution_engine = "Pandas + Scikit-Learn (Speed Layer)"

    df_feat = None
    if config.use_spark:
        # Tidak ada fallback diam-diam: kegagalan Spark dilaporkan agar engine yang dipakai jelas.
        from spark_jobs.batch_analytics import prepare_spark_features
        try:
            df_feat = prepare_spark_features(config)
        except ResearchDataError:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"PySpark gagal: {exc}. Nonaktifkan use_spark untuk memakai pandas.") from exc
        execution_engine = "PySpark SQL (Batch Layer)"

    if df_feat is None:
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

    historical_attribution = compute_historical_factor_attribution(
        df_anom, feature_cols=config.features, max_lag=min(config.max_lag, 6), timeframe=config.timeframe
    )

    df_anom["timestamp"] = df_anom["timestamp"].astype(str)
    # JSON tidak menerima NaN; mikrostruktur yang tidak tersedia dikirim sebagai null.
    anomaly_mask = df_anom["is_anomaly"].astype(bool)
    df_anom = df_anom.astype(object).where(df_anom.notna(), None)
    anomalies_only = df_anom[anomaly_mask].tail(100).to_dict(orient="records")
    series_records = df_anom.tail(400).to_dict(orient="records")

    return {
        "symbol": symbol,
        "timeframe": config.timeframe,
        "execution_engine": execution_engine,
        "total_candles": len(df_anom),
        "selected_features": config.features,
        "anomaly_summary": anom_summary,
        "historical_factor_attribution": historical_attribution,
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
        if not (DROP_ZONE_DIR / f"{sym}_5m_clean.csv").exists():
            continue
        df_5m = load_clean_ohlcv(sym)
        df_agg = aggregate_timeframe(df_5m, timeframe=timeframe)
        df_feat = compute_dynamic_features(df_agg, rolling_window=rolling_window)
        if not df_feat.empty:
            df_feat.loc[df_feat["timestamp"].diff().ne(TIMEFRAME_DURATION[timeframe]), "log_return"] = float("nan")
        frames.append(df_feat)
    if not frames or base_symbol.upper() not in {str(f["coin_symbol"].iloc[0]) for f in frames if not f.empty} or target_symbol.upper() not in {str(f["coin_symbol"].iloc[0]) for f in frames if not f.empty}:
        raise ResearchDataError("Data kedua aset korelasi belum tersedia pada timeframe ini. Ambil histori kedua aset terlebih dahulu.")
    df_multi = pd.concat(frames, ignore_index=True)
    return analyze_cross_asset_correlation(
        df_multi,
        base_symbol=base_symbol.upper(),
        target_symbol=target_symbol.upper(),
        rolling_window=rolling_window,
        max_lag=max_lag,
        timeframe=timeframe,
    )
