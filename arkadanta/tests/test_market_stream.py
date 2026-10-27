"""Uji stream tanpa jaringan dan tanpa menyentuh data penelitian aktif."""
import asyncio
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import market_stream as module
from backend.api import market_routes
from data import storage
import pandas as pd


def message(*, closed=False, event_time=1767225601000):
    return {"data": {"s": "BTCUSDT", "E": event_time, "k": {
        "s": "BTCUSDT", "i": "5m", "t": 1767225600000, "T": 1767225899999,
        "x": closed, "o": "100", "h": "102", "l": "99", "c": "101",
        "v": "10", "q": "1010", "n": 4, "V": "5", "Q": "505",
    }}}


class MarketStreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(storage, "DROP_ZONE_DIR", self.directory))
        self.stack.enter_context(patch.object(storage, "AUDIT_LOG_PATH", self.directory / "audit.json"))
        self.stack.enter_context(patch.object(storage, "NIFI_OUTBOX_DIR", self.directory / "nifi_outbox"))
        self.stream = module.MarketStream()
        self.queue = asyncio.Queue(maxsize=64)
        self.stream.subscribers.add(self.queue)

    async def test_running_candle_is_visible_but_never_saved(self):
        await self.stream.handle_message(message())
        event = self.queue.get_nowait()
        self.assertEqual(event["type"], "quote")
        self.assertEqual(event["close"], 101)
        self.assertFalse(event["closed"])
        self.assertEqual(list(self.directory.iterdir()), [])

    async def test_closed_candle_is_deduplicated_and_acknowledged_after_save(self):
        await self.stream.handle_message(message(closed=True))
        await self.stream.handle_message(message(closed=True))
        self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 1)
        self.assertEqual(len(storage.load_audit_logs()), 1)
        events = []
        while not self.queue.empty():
            events.append(self.queue.get_nowait()["type"])
        self.assertEqual(events.count("candle_closed"), 1)
        self.assertEqual(storage.load_audit_logs()[0]["nifi_hdfs_status"], "QUEUED_DROP_ZONE")

    async def test_out_of_order_event_does_not_move_price_backwards(self):
        await self.stream.handle_message(message(event_time=2000))
        await self.stream.handle_message(message(event_time=1000))
        self.assertEqual(self.queue.qsize(), 1)
        self.assertEqual(self.stream.latest["BTCUSDT"]["event_time"], 2000)

    async def test_invalid_messages_never_reach_storage(self):
        for key, value in (("c", "NaN"), ("h", "90"), ("v", "-1"), ("x", "true"), ("s", "../escape")):
            invalid = deepcopy(message(closed=True))
            invalid["data"]["k"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                await self.stream.handle_message(invalid)
        self.assertEqual(list(self.directory.iterdir()), [])

    async def test_storage_failure_is_not_reported_as_success_and_can_retry(self):
        with patch.object(module, "persist_closed_candle", side_effect=OSError("disk full")):
            await self.stream.handle_message(message(closed=True))
        self.assertNotIn("BTCUSDT", self.stream.saved)
        self.assertEqual(self.queue.get_nowait()["type"], "quote")
        self.assertEqual(self.queue.get_nowait()["type"], "storage_error")
        await self.stream.handle_message(message(closed=True))
        self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 1)

    async def test_clients_share_one_task_and_last_disconnect_stops_it(self):
        stream = module.MarketStream()
        async def blocked():
            await asyncio.Event().wait()
        with patch.object(stream, "run", side_effect=blocked) as run:
            first = stream.subscribe()
            second = stream.subscribe()
            await asyncio.sleep(0)
            task = stream.task
            self.assertEqual(run.call_count, 1)
            await stream.unsubscribe(first)
            self.assertIs(stream.task, task)
            self.assertFalse(task.done())
            await stream.unsubscribe(second)
            self.assertTrue(task.cancelled())
            self.assertIsNone(stream.task)

    async def test_slow_consumer_reconnects_instead_of_silently_losing_close_event(self):
        queue = asyncio.Queue(maxsize=1)
        self.stream.subscribers = {queue}
        self.stream.publish({"type": "quote"})
        self.stream.publish({"type": "candle_closed"})
        self.assertEqual(queue.get_nowait()["type"], "overflow")

    async def test_sse_framing_and_disconnect_cleanup(self):
        queue = asyncio.Queue()
        queue.put_nowait({"type": "status", "connected": False, "message": "offline"})
        fake = Mock(subscribe=Mock(return_value=queue), unsubscribe=AsyncMock())
        request = Mock(is_disconnected=AsyncMock(return_value=False))
        with patch.object(market_routes, "market_stream", fake):
            response = await market_routes.stream_market(request)
            chunk = await anext(response.body_iterator)
            self.assertTrue(chunk.startswith('data: {'))
            self.assertTrue(chunk.endswith('\n\n'))
            await response.body_iterator.aclose()
        fake.unsubscribe.assert_awaited_once_with(queue)

    async def test_upstream_failure_reports_disconnect_without_fake_prices(self):
        with patch.object(module, "connect", side_effect=OSError("offline")):
            task = asyncio.create_task(self.stream.run())
            try:
                connecting = await asyncio.wait_for(self.queue.get(), 1)
                failure = await asyncio.wait_for(self.queue.get(), 1)
                self.assertFalse(connecting["connected"])
                self.assertFalse(failure["connected"])
                self.assertIn("offline", failure["message"])
                self.assertEqual(self.stream.latest, {})
                self.assertEqual(list(self.directory.iterdir()), [])
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

    async def test_concurrent_candle_writers_do_not_lose_rows(self):
        def write(index):
            frame = pd.DataFrame([{
                "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=5 * index),
                "coin_symbol": "BTCUSDT", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10,
            }])
            storage.save_clean_ohlcv("BTCUSDT", frame)
        def concurrent_write():
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write, range(8)))
        await asyncio.to_thread(concurrent_write)
        self.assertEqual(len(storage.load_clean_ohlcv("BTCUSDT")), 8)


if __name__ == "__main__":
    unittest.main()
