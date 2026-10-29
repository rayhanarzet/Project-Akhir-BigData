"""Regresi untuk perbaikan audit: bucket parsial, minggu Senin, mikrostruktur palsu, ambang kausal, prediksi tanpa model."""
from contextlib import contextmanager
import os
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
from backend.ingestion.dynamic_pipeline import run_dynamic_ingestion_pipeline
from backend.schemas import DynamicConfig, PredictRequest
from data import storage
from data.sample_generator import generate_synthetic_5m_ohlcv
from data.storage import ResearchDataError
from spark_jobs.locks import SparkBusyError, exclusive_spark


def candles(start: str, count: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=count, freq="5min", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "coin_symbol": "BTCUSDT", "open": 1.0,
                         "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0})


class AuditFixTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def _without_java_home():
        # Uji lock tanpa bergantung pada JAVA_HOME mesin ini (dipulihkan oleh patch.dict pemanggil).
        os.environ.pop("JAVA_HOME", None)
        yield

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

    def test_bucket_with_missing_candle_is_dropped(self):
        frame = candles("2026-10-05 00:00", 12 * 3).drop(index=15)  # jam kedua kehilangan satu candle
        hourly = aggregate_timeframe(frame, "1h")
        self.assertEqual(list(hourly["timestamp"].dt.hour), [0, 2])

    def test_upload_merges_with_existing_history(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(storage, "DROP_ZONE_DIR", Path(root)), \
                patch.object(storage, "NIFI_OUTBOX_DIR", Path(root) / "outbox"), \
                patch.object(storage, "AUDIT_LOG_PATH", Path(root) / "audit.json"):
            storage.save_clean_ohlcv("BTCUSDT", candles("2026-10-05 00:00", 100))
            upload = candles("2026-10-05 08:20", 5).assign(timestamp=lambda d: d["timestamp"].astype(str))
            run_dynamic_ingestion_pipeline("kecil.csv", upload.to_csv(index=False).encode(), default_symbol="BTCUSDT")
            self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 105)

    def test_cached_read_returns_fresh_data_after_write(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(storage, "DROP_ZONE_DIR", Path(root)), \
                patch.object(storage, "NIFI_OUTBOX_DIR", Path(root) / "outbox"):
            storage.save_clean_ohlcv("BTCUSDT", candles("2026-10-05", 10))
            first = storage.load_clean_ohlcv("BTCUSDT")
            first.loc[0, "close"] = -1  # pemanggil mengubah salinan, bukan cache
            self.assertEqual(storage.load_clean_ohlcv("BTCUSDT").loc[0, "close"], 1.5)
            storage.save_clean_ohlcv("BTCUSDT", candles("2026-10-05 00:50", 1))
            self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 11)

    def test_second_spark_job_is_rejected_not_interleaved(self):
        with patch.dict("os.environ"), self._without_java_home(), exclusive_spark():
            with self.assertRaises(SparkBusyError):
                with exclusive_spark():
                    pass
        with patch.dict("os.environ"), self._without_java_home(), exclusive_spark():
            pass  # lock dilepas setelah job pertama selesai

    def test_broken_java_home_fails_fast_instead_of_hanging(self):
        with patch.dict("os.environ", {"JAVA_HOME": str(Path(tempfile.gettempdir()) / "tidak-ada-jdk")}):
            with self.assertRaisesRegex(ValueError, "JAVA_HOME"):
                with exclusive_spark():
                    pass
        with patch.dict("os.environ"), self._without_java_home(), exclusive_spark():
            pass  # pemeriksaan gagal tidak menahan lock

    def test_training_reports_naive_baselines(self):
        raw = generate_synthetic_5m_ohlcv(n_candles=600)
        features = compute_dynamic_features(aggregate_timeframe(raw, "5m"))
        with tempfile.TemporaryDirectory() as root, patch.object(model_trainer, "MODELS_DIR", Path(root)):
            metrics = model_trainer.train_from_features(features, DynamicConfig(timeframe="5m", gb_max_iter=20), "test")
        baseline = metrics["baseline_metrics"]
        self.assertTrue(0 <= baseline["majority_accuracy"] <= 1)
        self.assertTrue(0 <= baseline["persistence_accuracy"] <= 1)
        self.assertGreater(baseline["persistence_rmse"], 0)

    def test_prediction_refuses_stale_candles(self):
        raw = generate_synthetic_5m_ohlcv(n_candles=600)
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True) - pd.Timedelta(days=2)  # backend mati 2 hari
        with tempfile.TemporaryDirectory() as root, \
                patch.object(storage, "DROP_ZONE_DIR", Path(root)), \
                patch.object(storage, "NIFI_OUTBOX_DIR", Path(root) / "outbox"), \
                patch.object(model_trainer, "MODELS_DIR", Path(root) / "models"):
            storage.save_clean_ohlcv("BTCUSDT", raw)
            model_trainer.train_dynamic_models(DynamicConfig(timeframe="5m", gb_max_iter=20))
            with self.assertRaisesRegex(ResearchDataError, "Backfill"):
                model_predictor.predict_next_period(PredictRequest(timeframe="5m"))

    def test_predict_without_model_does_not_train_inside_request(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(model_trainer, "MODELS_DIR", Path(root)), \
                patch.object(model_trainer, "train_dynamic_models") as train:
            with self.assertRaises(ResearchDataError):
                model_predictor.predict_next_period(PredictRequest(timeframe="1h"))
            train.assert_not_called()


if __name__ == "__main__":
    unittest.main()
