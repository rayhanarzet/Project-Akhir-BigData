"""Regresi pemisahan data. Semua berkas tes berada di direktori sementara."""
import asyncio
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from fastapi import HTTPException
from backend import scheduler
from backend.api import ingestion_routes
from backend.ingestion import dynamic_pipeline
from backend.main import research_data_error_handler
from backend.schemas import LiveSyncRequest
from data import storage


class ResearchDataTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.drop_zone = self.directory / "drop_zone"
        self.drop_zone.mkdir()
        for module in (storage, scheduler, ingestion_routes, dynamic_pipeline):
            self.stack.enter_context(patch.object(module, "DROP_ZONE_DIR", self.drop_zone))
        self.stack.enter_context(patch.object(storage, "AUDIT_LOG_PATH", self.directory / "audit.json"))
        self.stack.enter_context(patch.object(dynamic_pipeline, "_try_sync_to_hdfs", return_value="QUEUED_DROP_ZONE"))
        self.worker = scheduler.BinanceCronScheduler()
        self.stack.enter_context(patch.object(ingestion_routes, "cron_scheduler", self.worker))

    def write_csv(self):
        path = self.drop_zone / "BTCUSDT_5m_clean.csv"
        path.write_text(
            "timestamp,coin_symbol,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,BTCUSDT,100,102,99,101,10\n",
            encoding="utf-8",
        )
        return path

    def test_missing_data_does_not_generate_samples(self):
        with self.assertRaisesRegex(storage.ResearchDataError, "belum tersedia"):
            storage.load_clean_ohlcv("BTCUSDT")
        self.assertEqual(list(self.drop_zone.iterdir()), [])
        self.assertFalse(storage.AUDIT_LOG_PATH.exists())

    def test_small_dataset_is_never_replaced_with_samples(self):
        path = self.write_csv()
        before = path.read_bytes()
        self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_data_is_not_regenerated(self):
        path = self.write_csv()
        path.write_text("broken", encoding="utf-8")
        with self.assertRaises(storage.ResearchDataError):
            storage.load_clean_ohlcv("BTCUSDT")
        self.assertEqual(path.read_text(), "broken")

    def test_empty_baseline_has_no_fabricated_assets_or_audits(self):
        baseline = ingestion_routes.get_historical_baseline()
        self.assertEqual(baseline["pipeline_status"], "NO_DATA")
        self.assertEqual(baseline["assets"], [])
        self.assertEqual(baseline["audit_logs"], [])
        self.assertEqual(list(self.drop_zone.iterdir()), [])

    def test_binance_failure_preserves_existing_data_and_returns_502(self):
        path = self.write_csv()
        before = path.read_bytes()
        with patch.object(scheduler.requests, "get", side_effect=requests.ConnectionError("offline")):
            with self.assertRaises(HTTPException) as caught:
                ingestion_routes.sync_live_binance(LiveSyncRequest(symbols=["BTCUSDT"]))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("Data simulasi tidak digunakan", caught.exception.detail)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(storage.AUDIT_LOG_PATH.exists())
        self.assertTrue(self.worker.last_status.startswith("ERROR"))

    def test_success_saves_only_received_candles_and_actual_storage_status(self):
        response = Mock()
        response.json.return_value = [[1767225600000, "100", "102", "99", "101", "10", 0, "1010", 4, "5", "505"]]
        with patch.object(scheduler.requests, "get", return_value=response):
            result = ingestion_routes.sync_live_binance(LiveSyncRequest(symbols=["BTCUSDT"]))
        frame = storage.load_clean_ohlcv("BTCUSDT")
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["close"], 101)
        self.assertEqual(result["reports"][0]["nifi_hdfs_status"], "QUEUED_DROP_ZONE")
        self.assertEqual(storage.load_audit_logs()[0]["format_detected"], "BINANCE_API")

    def test_partial_sync_failure_keeps_audit_for_successful_asset(self):
        response = Mock()
        response.json.return_value = [[1767225600000, "100", "102", "99", "101", "10", 0, "1010", 4, "5", "505"]]
        with patch.object(scheduler.requests, "get", side_effect=[response, requests.Timeout("timeout")]):
            with self.assertRaises(ValueError):
                self.worker.trigger_sync(["BTCUSDT", "ETHUSDT"])
        self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 1)
        self.assertFalse((self.drop_zone / "ETHUSDT_5m_clean.csv").exists())
        self.assertEqual(len(storage.load_audit_logs()), 1)

    def test_empty_binance_response_is_failure_without_files(self):
        response = Mock()
        response.json.return_value = []
        with patch.object(scheduler.requests, "get", return_value=response):
            with self.assertRaises(ValueError):
                self.worker.trigger_sync(["BTCUSDT"])
        self.assertEqual(list(self.drop_zone.iterdir()), [])

    def test_data_error_is_returned_as_actionable_json(self):
        response = asyncio.run(research_data_error_handler(None, storage.ResearchDataError("Data belum tersedia")))
        self.assertEqual(response.status_code, 409)
        self.assertIn(b"Data belum tersedia", response.body)

    def test_upload_and_baseline_do_not_create_other_assets(self):
        content = self.write_csv().read_bytes()
        dynamic_pipeline.run_dynamic_ingestion_pipeline("real.csv", content)
        baseline = ingestion_routes.get_historical_baseline()
        self.assertEqual([asset["symbol"] for asset in baseline["assets"]], ["BTCUSDT"])
        self.assertEqual(len(list(self.drop_zone.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
