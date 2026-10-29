"""Regresi kegagalan yang ditemukan audit; seluruh penyimpanan berada di direktori sementara."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import storage
from data.validation import validate_candles
from backend.analytics.research_window import filter_research_window, research_bounds
from backend.analytics.correlation_analyzer import analyze_cross_asset_correlation
from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.ingestion import dynamic_pipeline
from backend.ml import model_trainer, model_predictor
from backend.schemas import DynamicConfig, PredictRequest
from backend import integration_status
from data.sample_generator import generate_synthetic_5m_ohlcv


def candle(close=101.0):
    return pd.DataFrame({"timestamp": [pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=5)],
                         "coin_symbol": ["BTCUSDT"], "open": [100.0], "high": [102.0],
                         "low": [99.0], "close": [close], "volume": [10.0]})


class DataIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for module in (storage, dynamic_pipeline):
            self.stack.enter_context(patch.object(module, "DROP_ZONE_DIR", self.root))
        self.stack.enter_context(patch.object(storage, "NIFI_OUTBOX_DIR", self.root / "outbox"))
        self.stack.enter_context(patch.object(storage, "AUDIT_LOG_PATH", self.root / "audit.json"))
        self.stack.enter_context(patch.object(model_trainer, "MODELS_DIR", self.root / "models"))

    def queued(self):
        files = list((self.root / "outbox").rglob("*.csv"))
        return pd.concat([pd.read_csv(path) for path in files], ignore_index=True) if files else pd.DataFrame()

    def test_outbox_failure_recovers_without_losing_committed_candle(self):
        frame = candle()
        with patch.object(storage, "_write_nifi_outbox", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                storage.save_clean_ohlcv("BTCUSDT", frame)
        self.assertTrue(list((self.root / ".pending").glob("*.csv")))
        storage.recover_pending_writes()
        storage.save_clean_ohlcv("BTCUSDT", frame)
        self.assertEqual(len(self.queued()), 1)
        self.assertEqual(len(storage.load_clean_ohlcv()), 1)
        self.assertFalse(list((self.root / ".pending").glob("*.csv")))

    def test_local_write_failure_recovers_on_next_read(self):
        write = storage._atomic_write
        def fail_csv(path, text):
            if path.name == "BTCUSDT_5m_clean.csv":
                raise OSError("local write failed")
            return write(path, text)
        with patch.object(storage, "_atomic_write", side_effect=fail_csv):
            with self.assertRaises(OSError):
                storage.save_clean_ohlcv("BTCUSDT", candle())
        self.assertEqual(len(storage.load_clean_ohlcv()), 1)
        self.assertEqual(len(self.queued()), 1)

    def test_retry_after_publish_uses_identical_delivery_filename(self):
        real_publish = storage._write_nifi_outbox
        def published_then_crash(*args):
            real_publish(*args)
            raise OSError("crash before journal acknowledgement")
        with patch.object(storage, "_write_nifi_outbox", side_effect=published_then_crash):
            with self.assertRaises(OSError):
                storage.save_clean_ohlcv("BTCUSDT", candle())
        before = {path.name for path in (self.root / "outbox").rglob("*.csv")}
        storage.recover_pending_writes()
        self.assertEqual(before, {path.name for path in (self.root / "outbox").rglob("*.csv")})
        self.assertEqual(len(self.queued()), 1)

    def test_correction_is_republished_with_strictly_newer_integer_revision(self):
        frame = candle()
        storage.save_clean_ohlcv("BTCUSDT", frame)
        frame.loc[0, "close"] = 101.5
        storage.save_clean_ohlcv("BTCUSDT", frame)
        rows = self.queued().sort_values("ingestion_version")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows["close"].tolist(), [101, 101.5])
        self.assertGreater(int(rows.iloc[-1]["ingestion_version"]), int(rows.iloc[0]["ingestion_version"]))
        self.assertEqual(storage.load_clean_ohlcv().iloc[-1]["close"], 101.5)

    def test_legacy_migration_preserves_exact_revision_and_canonical_columns(self):
        legacy = candle()
        legacy["timestamp"] -= pd.Timedelta(minutes=5)
        legacy.to_csv(self.root / "BTCUSDT_5m_clean.csv", index=False)
        revision = 1780000000000000001
        with patch.object(storage.time, "time_ns", return_value=revision):
            storage.save_clean_ohlcv("BTCUSDT", candle())
            self.assertEqual(storage.load_clean_ohlcv()["ingestion_version"].tolist(), [0, revision])
            storage.save_clean_ohlcv("BTCUSDT", legacy)
        self.assertEqual(storage.load_clean_ohlcv()["ingestion_version"].tolist(), [revision + 1, revision])
        files = list((self.root / "outbox" / "v3").rglob("*.csv"))
        self.assertEqual(len(files), 2)
        expected = ["timestamp", "coin_symbol", *storage.OHLCV, *storage.OPTIONAL_NUMERIC,
                    "ingestion_version", "ingested_at", "source_name"]
        for path in files:
            self.assertEqual(pd.read_csv(path).columns.tolist(), expected)

    def test_upload_rejects_infinity_missing_values_and_non_5m_time(self):
        frame = pd.concat([candle()] * 4, ignore_index=True)
        frame.loc[1, "high"] = float("inf")
        frame.loc[2, "volume"] = float("nan")
        frame.loc[3, "timestamp"] += pd.Timedelta(minutes=1)
        cleaned, report = dynamic_pipeline.run_dynamic_ingestion_pipeline("invalid.csv", frame.to_csv(index=False).encode())
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(report.rejected_rows, 3)
        self.assertEqual(report.quality_score_pct, 25)
        self.assertEqual(report.imputed_volume_rows, 0)
        self.assertEqual(len(report.source_sha256), 64)

    def test_unfinished_candle_is_rejected_by_storage(self):
        frame = candle()
        frame["timestamp"] = pd.Timestamp.now(tz="UTC").floor("5min")
        with self.assertRaises(storage.ResearchDataError):
            storage.save_clean_ohlcv("BTCUSDT", frame)
        self.assertFalse((self.root / "BTCUSDT_5m_clean.csv").exists())

    def test_optional_microstructure_rejects_malformed_values_but_allows_missing(self):
        frame = pd.concat([candle()] * 6, ignore_index=True)
        frame["number_of_trades"] = ["broken", float("inf"), -1, 1.5, None, "25"]
        valid, errors = validate_candles(frame)
        self.assertEqual(errors["invalid_microstructure"], 4)
        self.assertEqual(errors["rejected_rows"], 4)
        self.assertEqual(len(valid), 2)
        self.assertTrue(pd.isna(valid.iloc[0]["number_of_trades"]))
        self.assertEqual(valid.iloc[1]["number_of_trades"], 25)

    def test_aggregation_preserves_missing_microstructure_in_partial_and_empty_buckets(self):
        raw = generate_synthetic_5m_ohlcv(n_candles=240)
        bucket = raw["timestamp"].dt.floor("15min")
        complete = bucket.value_counts().loc[lambda counts: counts.eq(3)].index.sort_values()
        raw.loc[bucket.eq(complete[1]), "number_of_trades"] = np.nan
        raw.loc[bucket.eq(complete[2]).idxmax(), "taker_buy_base_volume"] = np.nan
        aggregated = aggregate_timeframe(raw, "15m").set_index("timestamp")
        self.assertTrue(pd.isna(aggregated.loc[complete[1], "number_of_trades"]))
        self.assertTrue(pd.isna(aggregated.loc[complete[2], "taker_buy_base_volume"]))
        self.assertGreater(aggregated.loc[complete[0], "number_of_trades"], 0)

    def test_prediction_reports_missing_complete_buckets(self):
        bundle = {"labeler": None, "classifier": None, "regressor": None,
                  "meta": {"features": [], "target_horizon": 1}, "config": DynamicConfig(timeframe="1h").model_dump()}
        with patch.object(model_predictor, "load_or_train_bundle", return_value=bundle), \
             patch.object(model_predictor, "load_clean_ohlcv", return_value=candle()):
            with self.assertRaisesRegex(storage.ResearchDataError, "candle lengkap"):
                model_predictor.predict_next_period(PredictRequest(timeframe="1h"))

    def test_audit_history_is_not_limited_to_fifty_records(self):
        for i in range(61):
            storage.append_audit_logs([{"run_id": str(i)}])
        self.assertEqual(len(storage.load_audit_logs()), 61)
        self.assertEqual([r["run_id"] for r in storage.load_audit_logs(limit=2)], ["60", "59"])

    def test_research_window_filters_archive_without_deleting_it(self):
        now = pd.Timestamp.now(tz="UTC")
        frame = pd.concat([candle(), candle()], ignore_index=True)
        frame.loc[0, "timestamp"] = (now - pd.Timedelta(days=366)).floor("5min")
        storage.save_clean_ohlcv("BTCUSDT", frame)
        self.assertEqual(len(filter_research_window(storage.load_clean_ohlcv())), 1)
        self.assertEqual(len(storage.load_clean_ohlcv()), 2)
        with self.assertRaisesRegex(ValueError, "365"):
            research_bounds(start_date=(now - pd.Timedelta(days=366)).isoformat())

    def test_gap_pairs_are_removed_and_preview_target_is_exactly_one_period(self):
        raw = generate_synthetic_5m_ohlcv(n_candles=240).drop(index=[50, 51, 100])
        storage.save_clean_ohlcv("BTCUSDT", raw)
        config = DynamicConfig(timeframe="5m", gb_max_iter=20)
        metrics = model_trainer.train_dynamic_models(config)
        self.assertEqual(metrics["temporal_split"]["gap_targets_removed"], 2)
        for point in metrics["test_predictions_preview"]:
            self.assertEqual(pd.Timestamp(point["target_timestamp"]) - pd.Timestamp(point["timestamp"]), pd.Timedelta(minutes=5))
        for fold in metrics["walk_forward_volatility"]:
            self.assertLess(pd.Timestamp(fold["train_target_end"]), pd.Timestamp(fold["test_start"]))
        self.assertIn("persentil 95", metrics["volatility_event_validation"]["definition"])

    def test_prediction_refuses_a_target_period_that_has_already_passed(self):
        raw = generate_synthetic_5m_ohlcv(n_candles=240)
        raw["timestamp"] -= pd.Timedelta(minutes=10)
        storage.save_clean_ohlcv("BTCUSDT", raw)
        model_trainer.train_dynamic_models(DynamicConfig(timeframe="5m", gb_max_iter=20))
        with self.assertRaisesRegex(storage.ResearchDataError, "Backfill"):
            model_predictor.predict_next_period(PredictRequest(timeframe="5m"))

    def test_missing_asset_observations_are_not_forward_filled(self):
        stamp = pd.date_range("2026-10-05", periods=10, freq="1h", tz="UTC")
        data = pd.DataFrame({"timestamp": list(stamp) + list(stamp[:6]), "coin_symbol": ["BTCUSDT"] * 10 + ["ETHUSDT"] * 6,
                             "log_return": list(range(10)) + list(range(6)), "max_volatility": list(range(10)) + list(range(6))})
        result = analyze_cross_asset_correlation(data)
        self.assertEqual(result["paired_observations"]["BTCUSDT"]["ETHUSDT"], 6)
        self.assertIsNone(result["market_wide_risk_score"])
        self.assertFalse(result["asset_freshness"]["ETHUSDT"]["latest_observed"])

    def test_integration_does_not_claim_delivery_when_ports_respond(self):
        response = Mock()
        response.json.return_value = {"ContentSummary": {"fileCount": 12, "length": 1000}}
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        with patch.object(integration_status.socket, "create_connection", return_value=connection), patch.object(integration_status.requests, "get", return_value=response):
            result = integration_status._probe_infrastructure()
        self.assertEqual(result["nifi"]["status"], "PORT_REACHABLE")
        self.assertEqual(result["hdfs"]["status"], "READABLE")
        self.assertFalse(storage.delivery_status()["delivery_confirmed"])


if __name__ == "__main__":
    unittest.main()
