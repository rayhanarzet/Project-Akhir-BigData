"""Satu koneksi Binance untuk semua dashboard; hanya candle selesai masuk penelitian."""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import math

import pandas as pd
from websockets.asyncio.client import connect

from backend.config import BINANCE_STREAM_URL, DEFAULT_SYMBOLS, HDFS_BASE_PATH
from backend.scheduler import cron_scheduler
from data.storage import append_audit_logs, save_clean_ohlcv


def parse_kline(message: dict) -> dict:
    data = message.get("data", message)
    candle = data["k"]
    symbol = data["s"]
    if symbol not in DEFAULT_SYMBOLS or candle["s"] != symbol or candle["i"] != "5m":
        raise ValueError("Simbol atau interval stream tidak valid")
    if not isinstance(candle["x"], bool):
        raise ValueError("Status penutupan candle tidak valid")
    values = {name: float(candle[key]) for name, key in (
        ("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"),
        ("volume", "v"), ("quote_asset_volume", "q"),
        ("taker_buy_base_volume", "V"), ("taker_buy_quote_volume", "Q"),
    )}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Angka candle tidak valid")
    if min(values[key] for key in ("open", "high", "low", "close")) <= 0:
        raise ValueError("Harga candle harus positif")
    if values["high"] < max(values["open"], values["close"], values["low"]) or values["low"] > min(values["open"], values["close"]):
        raise ValueError("Rentang OHLC tidak valid")
    if any(values[key] < 0 for key in ("volume", "quote_asset_volume", "taker_buy_base_volume", "taker_buy_quote_volume")):
        raise ValueError("Volume tidak valid")
    trades = int(candle["n"])
    if trades < 0 or int(candle["T"]) < int(candle["t"]):
        raise ValueError("Jumlah transaksi atau waktu candle tidak valid")
    return {
        "symbol": symbol,
        "event_time": int(data["E"]),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "candle_time": int(candle["t"]),
        "closed": candle["x"],
        "number_of_trades": trades,
        **values,
    }


def persist_closed_candle(quote: dict) -> None:
    if not quote["closed"]:
        raise ValueError("Candle berjalan tidak boleh disimpan sebagai candle selesai")
    row = {name: quote[name] for name in (
        "open", "high", "low", "close", "volume", "quote_asset_volume",
        "number_of_trades", "taker_buy_base_volume", "taker_buy_quote_volume",
    )}
    row.update(timestamp=pd.to_datetime(quote["candle_time"], unit="ms", utc=True), coin_symbol=quote["symbol"])
    before, after = save_clean_ohlcv(quote["symbol"], pd.DataFrame([row]))
    append_audit_logs([{
        "run_id": f"ws_{quote['symbol']}_{quote['candle_time']}",
        "timestamp": quote["received_at"],
        "source_name": f"Binance WebSocket {quote['symbol']} kline_5m (closed)",
        "format_detected": "BINANCE_API",
        "selected_pipeline": "BinanceWebSocket -> ClosedCandleValidator -> Deduplicator -> DropZoneWriter",
        "column_mapping": {}, "symbols_detected": [quote["symbol"]],
        "rows_before": before, "rows_after": after, "duplicates_removed": before - after,
        "imputed_ohlc_rows": 0, "imputed_volume_rows": 0, "rejected_rows": 0,
        "error_reasons": {},
        "drop_zone_path": f"data/research/drop_zone/{quote['symbol']}_5m_clean.csv",
        "hdfs_target_path": f"{HDFS_BASE_PATH}symbol={quote['symbol']}/",
        "nifi_hdfs_status": "QUEUED_DROP_ZONE", "quality_score_pct": 100.0,
    }])


class MarketStream:
    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()
        self.latest: dict[str, dict] = {}
        self.saved: dict[str, int] = {}
        self.status = {"type": "status", "connected": False, "message": "Menghubungkan ke Binance..."}
        self.task: asyncio.Task | None = None

    def publish(self, event: dict) -> None:
        for queue in self.subscribers:
            # Klien lambat diputus dan tersambung lagi; jangan hilangkan event candle selesai.
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "overflow"})
            else:
                queue.put_nowait(event)

    def set_status(self, connected: bool, message: str) -> None:
        self.status = {"type": "status", "connected": connected, "message": message}
        self.publish(self.status)

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=64)
        self.subscribers.add(queue)
        queue.put_nowait(self.status)
        for quote in self.latest.values():
            queue.put_nowait({"type": "quote", "snapshot": True, **quote})
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)
        if not self.subscribers:
            await self.stop()

    async def stop(self) -> None:
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if not self.subscribers:
            self.status = {"type": "status", "connected": False, "message": "Stream berhenti"}

    async def handle_message(self, message: dict) -> None:
        quote = parse_kline(message)
        previous = self.latest.get(quote["symbol"])
        if previous and quote["event_time"] < previous["event_time"]:
            return
        self.latest[quote["symbol"]] = quote
        self.publish({"type": "quote", "snapshot": False, **quote})
        if quote["closed"] and quote["candle_time"] > self.saved.get(quote["symbol"], -1):
            try:
                await asyncio.to_thread(persist_closed_candle, quote)
            except Exception as exc:
                self.publish({"type": "storage_error", "message": f"Candle gagal disimpan: {exc}"})
                return
            self.saved[quote["symbol"]] = quote["candle_time"]
            self.publish({"type": "candle_closed", "symbol": quote["symbol"], "candle_time": quote["candle_time"]})

    async def fill_gaps(self) -> None:
        """Isi candle yang terlewat saat backend/stream mati, agar analisis & prediksi tidak memakai data basi."""
        for symbol in DEFAULT_SYMBOLS:
            try:
                added = await asyncio.to_thread(cron_scheduler.fill_gap, symbol)
            except Exception as exc:  # REST gagal tidak boleh memutus stream harga live
                self.publish({"type": "storage_error", "message": f"Candle terlewat {symbol} gagal diambil: {exc}"})
                continue
            if added:
                self.publish({"type": "candle_closed", "symbol": symbol, "candle_time": None})

    async def run(self) -> None:
        streams = "/".join(f"{symbol.lower()}@kline_5m" for symbol in DEFAULT_SYMBOLS)
        url = f"{BINANCE_STREAM_URL}?streams={streams}"
        delay = 1
        while True:
            self.set_status(False, "Menghubungkan ke Binance...")
            try:
                async with connect(url, open_timeout=10, ping_interval=20, ping_timeout=20, max_size=65536) as socket:
                    self.set_status(True, "Terhubung ke Binance WebSocket")
                    # Sebelum membaca event: candle yang tersimpan setelah ini akan menggeser titik awal celah.
                    await self.fill_gaps()
                    async for raw in socket:
                        await self.handle_message(json.loads(raw))
                        delay = 1
                self.set_status(False, "Koneksi Binance ditutup; mencoba kembali...")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.set_status(False, f"Stream Binance terputus: {str(exc)[:200]}. Mencoba kembali...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


market_stream = MarketStream()
