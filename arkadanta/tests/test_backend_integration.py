"""Pengujian terintegrasi untuk Backend Ingestion, Analytics, dan Machine Learning Arkadanta."""

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.analytics.anomaly_detector import detect_anomalies
from backend.analytics.correlation_analyzer import compute_historical_factor_attribution
from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.ingestion.dynamic_pipeline import run_dynamic_ingestion_pipeline
from backend.ml.model_predictor import predict_next_period
from backend.ml.model_trainer import train_dynamic_models
from backend.schemas import DynamicConfig, PredictRequest
from backend.ml.risk_labeler import DynamicRiskLabeler


def test_multi_symbol_ingestion_and_audit():
    csv_bytes = (
        b"open_time,symbol,open,high,low,close,vol\n"
        b"2026-01-01T00:00:00Z,BTCUSDT,92000,92500,91800,92300,120.5\n"
        b"2026-01-01T00:05:00Z,BTCUSDT,92300,92600,92100,92450,95.2\n"
        b"2026-01-01T00:00:00Z,ETHUSDT,3300,3350,3280,3320,850.0\n"
        b"2026-01-01T00:05:00Z,ETHUSDT,3320,3100,3250,3310,410.0\n"  # Baris invalid: high < low
    )
    df_clean, report = run_dynamic_ingestion_pipeline(
        filename="multi_test.csv", content=csv_bytes, default_symbol="BTCUSDT"
    )
    assert len(df_clean) == 3
    assert report.rejected_rows == 1
    assert report.error_reasons["high_less_than_low"] == 1
    assert set(report.symbols_detected) == {"BTCUSDT", "ETHUSDT"}
    assert "BTCUSDT_5m_clean.csv" in report.drop_zone_path
    assert "ETHUSDT_5m_clean.csv" in report.drop_zone_path


def test_raw_binance_vision_headerless_csv():
    # Format ekspor data.binance.vision: 12 kolom tanpa header, open_time dalam milidetik.
    start = 1735689600000  # 2025-01-01 00:00 UTC
    sample_lines = "\n".join(
        f"{start + i * 300_000},100,102,99,101,10,{start + i * 300_000 + 299_999},1010,25,4,404,0"
        for i in range(25)
    ).encode()
    df_clean, report = run_dynamic_ingestion_pipeline(
        filename="BTCUSDT-5m-2025-01.csv",
        content=sample_lines,
        default_symbol="BTCUSDT",
    )
    assert len(df_clean) == 25
    assert report.quality_score_pct == 100.0
    assert df_clean["timestamp"].iloc[0] == pd.Timestamp("2025-01-01", tz="UTC")
    assert df_clean["taker_buy_base_volume"].iloc[0] == 4


def test_analytics_ml_and_component_risk_ordering():
    from data.sample_generator import generate_synthetic_5m_ohlcv
    from backend.config import DROP_ZONE_DIR

    # Pastikan file drop_zone BTCUSDT punya cukup baris setelah test multi_symbol
    df_btc = generate_synthetic_5m_ohlcv("BTCUSDT", n_candles=600)
    (DROP_ZONE_DIR / "BTCUSDT_5m_clean.csv").write_text(
        df_btc.to_csv(index=False), encoding="utf-8"
    )
    df_eth = generate_synthetic_5m_ohlcv("ETHUSDT", n_candles=600)
    (DROP_ZONE_DIR / "ETHUSDT_5m_clean.csv").write_text(
        df_eth.to_csv(index=False), encoding="utf-8"
    )

    df_agg = aggregate_timeframe(df_btc, timeframe="1h")
    df_feat = compute_dynamic_features(df_agg)
    df_anom, summary = detect_anomalies(df_feat, method="adaptive_quantile", quantile=0.95)
    assert "is_anomaly" in df_anom.columns
    assert summary["total_observations"] == len(df_feat)

    attr = compute_historical_factor_attribution(df_anom, max_lag=4)
    assert len(attr) > 0
    assert "dominant_lag" in attr[0]

    # Jalur Pandas/Spark memakai satu pemilik aturan skor risiko komponen.
    features = ["max_volatility", "spike_ratio", "rsi_14", "log_return"]
    dummy_centroid = [1.2, 0.8, -1.5, -2.0]
    spark_score = DynamicRiskLabeler()._compute_centroid_risk_score(dummy_centroid, features)
    assert spark_score > 0

    cfg = DynamicConfig(symbol="BTCUSDT", timeframe="1h", gb_max_iter=30, use_spark=False)
    metrics = train_dynamic_models(cfg)
    assert "execution_engine" in metrics
    assert metrics["gmm_metrics"][" regime_distribution" if False else "regime_distribution"] is not None

    pred = predict_next_period(PredictRequest(symbol="BTCUSDT", timeframe="1h"))
    assert pred["predicted_regime_t_plus_1"] in ("SAFE", "WARNING", "DANGER")
    assert pred["resistance_level"] > pred["current_price"] > pred["stop_loss_level"]
