"""Regresi untuk perbaikan audit: bucket parsial, minggu Senin, mikrostruktur palsu, ambang kausal, prediksi tanpa model."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from backend.analytics.anomaly_detector import detect_anomalies
from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.ml import model_predictor, model_trainer
from backend.ml.dynamic_feature_selector import select_and_prepare_features
from backend.schemas import PredictRequest
from data.storage import ResearchDataError


def candles(start: str, count: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=count, freq="5min", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "coin_symbol": "BTCUSDT", "open": 1.0,
                         "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0})


class AuditFixTests(unittest.TestCase):
    def test_partial_last_bucket_is_dropped(self):
        hourly = aggregate_timeframe(candles("2026-10-05 00:00", 12 * 3 + 3), "1h")
        self.assertEqual(len(hourly), 3)
        self.assertTrue((hourly["volume"] == 12).all())

    def test_weekly_buckets_start_on_monday_utc(self):
        # 2026-10-01 adalah Kamis; minggu pertama yang lengkap dimulai Senin 2026-10-05.
        weekly = aggregate_timeframe(candles("2026-10-01 00:00", 12 * 24 * 14), "1w")
        self.assertEqual(weekly["timestamp"].iloc[-1], pd.Timestamp("2026-10-05", tz="UTC"))
        self.assertEqual(weekly["volume"].iloc[-1], 12 * 24 * 7)
        self.assertTrue((weekly["timestamp"].dt.dayofweek == 0).all())

    def test_microstructure_is_not_invented(self):
        features = compute_dynamic_features(candles("2026-10-05", 50))
        self.assertTrue(features["buy_sell_pressure_ratio"].isna().all() if "buy_sell_pressure_ratio" in features else True)
        self.assertNotIn("number_of_trades", features.columns)
        with self.assertRaises(ValueError):
            select_and_prepare_features(features, ["max_volatility", "buy_sell_pressure_ratio"])

    def test_causal_thresholds_do_not_change_when_future_data_arrives(self):
        base = candles("2026-10-05", 200)
        base["high"] = 1.6 + (base.index % 17) / 10.0
        features = compute_dynamic_features(base)
        extended = pd.concat([features, features.tail(50).assign(
            timestamp=features["timestamp"].iloc[-1] + pd.to_timedelta(range(5, 255, 5), unit="min"),
            max_volatility=50.0)], ignore_index=True)
        for method in ("adaptive_quantile", "iqr", "rolling_zscore"):
            before, _ = detect_anomalies(features, method=method)
            after, _ = detect_anomalies(extended, method=method)
            pd.testing.assert_series_equal(before["is_anomaly"], after["is_anomaly"].iloc[:len(before)], check_names=False)

    def test_predict_without_model_does_not_train_inside_request(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(model_trainer, "MODELS_DIR", Path(root)), \
                patch.object(model_trainer, "train_dynamic_models") as train:
            with self.assertRaises(ResearchDataError):
                model_predictor.predict_next_period(PredictRequest(timeframe="1h"))
            train.assert_not_called()


if __name__ == "__main__":
    unittest.main()
