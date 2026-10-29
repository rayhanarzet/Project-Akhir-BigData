"""Background Cron Job Scheduler untuk penarikan data Binance berkala (Speed Layer)."""

import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import requests
import pandas as pd

from backend.config import BINANCE_KLINES_URL, DEFAULT_SYMBOLS, DROP_ZONE_DIR, HDFS_BASE_PATH
from backend.schemas import IngestionAuditReport
from data.storage import (
    ResearchDataError,
    append_audit_logs,
    load_clean_ohlcv,
    save_clean_ohlcv,
)
import uuid


FIVE_MINUTES_MS = 5 * 60 * 1000


def _fetch_closed_klines(symbol: str, limit: int, start_time_ms: Optional[int] = None) -> pd.DataFrame:
    """Satu permintaan /api/v3/klines 5m; candle yang belum selesai dibuang."""
    params = {"symbol": symbol, "interval": "5m", "limit": limit}
    if start_time_ms is not None:
        params["startTime"] = start_time_ms
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=7)
    resp.raise_for_status()
    raw_klines = resp.json()
    if not isinstance(raw_klines, list):
        raise ValueError(f"Respons Binance untuk {symbol} tidak valid")
    if not raw_klines and start_time_ms is None:
        raise ValueError(f"Binance tidak mengembalikan candle untuk {symbol}")
    now_ms = int(time.time() * 1000)
    rows = [
        {
            "timestamp": pd.to_datetime(int(k[0]), unit="ms", utc=True),
            "coin_symbol": symbol,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "quote_asset_volume": float(k[7]),
            "number_of_trades": int(k[8]),
            "taker_buy_base_volume": float(k[9]),
            "taker_buy_quote_volume": float(k[10]),
        }
        # Candle berjalan hanya ditampilkan live; dataset ML memakai candle selesai.
        for k in raw_klines
        if int(k[6]) < now_ms
    ]
    return pd.DataFrame(rows)


def _fetch_since(symbol: str, start_time_ms: int) -> pd.DataFrame:
    """Semua candle 5m selesai sejak start_time_ms, per halaman 1000 (batas Binance)."""
    pages = []
    while True:
        page = _fetch_closed_klines(symbol, 1000, start_time_ms=start_time_ms)
        if page.empty:
            break
        pages.append(page)
        start_time_ms = int(page["timestamp"].iloc[-1].value // 1_000_000) + FIVE_MINUTES_MS
        if len(page) < 1000:
            break
        time.sleep(0.2)  # di bawah batas bobot Binance (6000/menit)
    return pd.concat(pages, ignore_index=True) if pages else pd.DataFrame()


class BinanceCronScheduler:
    """Pengelola background cron scheduler untuk sinkronisasi live data otomatis."""

    def __init__(self):
        self.enabled: bool = False
        self.interval_minutes: int = 5
        self.symbols: List[str] = list(DEFAULT_SYMBOLS)
        self.limit: int = 60
        self.last_run: Optional[str] = None
        self.next_run: Optional[str] = None
        self.last_status: str = "IDLE"
        self.last_synced_count: int = 0
        self.total_runs: int = 0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._sync_lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "interval_minutes": self.interval_minutes,
                "symbols": self.symbols,
                "limit": self.limit,
                "last_run": self.last_run,
                "next_run": self.next_run,
                "last_status": self.last_status,
                "last_synced_count": self.last_synced_count,
                "total_runs": self.total_runs,
            }

    def configure(
        self,
        enabled: bool,
        interval_minutes: int = 5,
        symbols: Optional[List[str]] = None,
        limit: int = 60,
    ) -> Dict[str, Any]:
        with self._lock:
            self.interval_minutes = max(1, interval_minutes)
            if symbols:
                self.symbols = [s.upper() for s in symbols]
            self.limit = min(max(10, limit), 1000)

            if enabled and not self.enabled:
                self.enabled = True
                self._stop_event.clear()
                self._compute_next_run()
                if self._thread is None or not self._thread.is_alive():
                    self._thread = threading.Thread(target=self._run_loop, daemon=True)
                    self._thread.start()
            elif not enabled and self.enabled:
                self.enabled = False
                self._stop_event.set()
                self.next_run = None
                self.last_status = "STOPPED"

            return self.get_status()

    def _compute_next_run(self):
        now = datetime.now(timezone.utc)
        nxt = now + timedelta(minutes=self.interval_minutes)
        self.next_run = nxt.isoformat()

    def trigger_sync(self, symbols: Optional[List[str]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        # Jangan biarkan sinkronisasi manual dan cron menimpa file bersamaan.
        with self._sync_lock:
            return self._trigger_sync(symbols, limit)

    def backfill(self, symbols: List[str], days: int) -> List[Dict[str, Any]]:
        """Menarik histori 5m hingga `days` hari ke belakang per halaman 1000 candle (startTime)."""
        with self._sync_lock:
            reports = []
            for sym in symbols:
                symbol = sym.upper()
                frame = _fetch_since(symbol, int((time.time() - days * 86400) * 1000))
                if frame.empty:
                    raise ValueError(f"Binance tidak mengembalikan histori untuk {symbol}")
                rows_before, rows_after = save_clean_ohlcv(symbol, frame)
                reports.append(IngestionAuditReport(
                    run_id=f"backfill_{uuid.uuid4().hex[:8]}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    source_name=f"Binance /api/v3/klines ({symbol} 5m backfill {days} hari)",
                    format_detected="BINANCE_API",
                    selected_pipeline="BinanceBackfillPager -> SchemaNormalizer -> Deduplicator -> DropZoneWriter -> NiFiOutbox",
                    column_mapping={"open_time": "timestamp", "symbol": "coin_symbol"},
                    symbols_detected=[symbol], rows_before=rows_before, rows_after=rows_after,
                    duplicates_removed=max(0, rows_before - rows_after),
                    imputed_ohlc_rows=0, imputed_volume_rows=0, rejected_rows=0,
                    error_reasons={"high_less_than_low": 0, "non_positive_price": 0, "negative_volume": 0, "invalid_timestamp": 0},
                    drop_zone_path=f"data/research/drop_zone/{symbol}_5m_clean.csv",
                    hdfs_target_path=f"{HDFS_BASE_PATH}symbol={symbol}/",
                    nifi_hdfs_status="QUEUED_DROP_ZONE", quality_score_pct=100.0,
                ).model_dump())
                # Simpan audit per aset agar aset yang sudah selesai tetap tercatat bila aset berikutnya gagal.
                append_audit_logs(reports[-1:])
            return reports

    def fill_gap(self, symbol: str) -> int:
        """Menarik candle yang terlewat sejak candle terakhir tersimpan (mis. laptop/backend mati)."""
        with self._sync_lock:
            try:
                last = load_clean_ohlcv(symbol)["timestamp"].max()
            except ResearchDataError:
                return 0  # belum ada histori sama sekali: itu tugas Backfill Histori, bukan pengisian celah
            frame = _fetch_since(symbol, int(last.value // 1_000_000) + FIVE_MINUTES_MS)
            if not frame.empty:
                save_clean_ohlcv(symbol, frame)
            return len(frame)

    def _trigger_sync(self, symbols: Optional[List[str]], limit: Optional[int]) -> List[Dict[str, Any]]:
        """Mengeksekusi penarikan data Binance untuk simbol terpilih (dapat dipanggil cron atau manual)."""
        target_symbols = symbols or self.symbols
        target_limit = limit or self.limit
        synced_reports = []

        for sym in target_symbols:
            symbol = sym.upper()
            source_mode = "BINANCE_API"
            try:
                df_new = _fetch_closed_klines(symbol, target_limit)
                if df_new.empty:
                    raise ValueError("Belum ada candle selesai pada respons Binance")
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                # Simpan bukti aset yang sudah selesai apabila aset berikutnya gagal.
                if synced_reports:
                    append_audit_logs(synced_reports)
                with self._lock:
                    self.last_status = f"ERROR: Binance {symbol}: {exc}"
                    self.last_synced_count = len(synced_reports)
                raise ValueError(f"Binance {symbol}: {exc}. {len(synced_reports)} aset sudah tersimpan; aset yang gagal tidak diubah") from exc

            existing_path = DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"
            rows_before, rows_after = save_clean_ohlcv(symbol, df_new)
            dups = max(0, rows_before - rows_after)

            rep = IngestionAuditReport(
                run_id=f"cron_{uuid.uuid4().hex[:8]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_name=f"Binance /api/v3/klines ({symbol} 5m auto-sync)",
                format_detected=source_mode,
                selected_pipeline="BinanceCronFetcher -> SchemaNormalizer -> Deduplicator -> DropZoneWriter",
                column_mapping={"open_time": "timestamp", "symbol": "coin_symbol"},
                symbols_detected=[symbol],
                rows_before=rows_before,
                rows_after=rows_after,
                duplicates_removed=dups,
                imputed_ohlc_rows=0,
                imputed_volume_rows=0,
                rejected_rows=0,
                error_reasons={
                    "high_less_than_low": 0,
                    "non_positive_price": 0,
                    "negative_volume": 0,
                    "invalid_timestamp": 0,
                },
                drop_zone_path=f"data/research/drop_zone/{existing_path.name}",
                hdfs_target_path=f"{HDFS_BASE_PATH}symbol={symbol}/",
                nifi_hdfs_status="QUEUED_DROP_ZONE",
                quality_score_pct=100.0,
            )
            synced_reports.append(rep.model_dump())

        append_audit_logs(synced_reports)
        return synced_reports

    def _run_loop(self):
        """Loop thread latar belakang yang berjalan sesuai interval waktu yang ditentukan."""
        while not self._stop_event.is_set():
            # Tunggu interval dalam potongan kecil 1 detik agar responsif saat dimatikan/diubah
            interval_seconds = self.interval_minutes * 60
            for _ in range(interval_seconds):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            if self._stop_event.is_set():
                return

            try:
                reports = self.trigger_sync()
                with self._lock:
                    self.last_run = datetime.now(timezone.utc).isoformat()
                    self.last_synced_count = len(reports)
                    self.total_runs += 1
                    self.last_status = "SUCCESS"
                    self._compute_next_run()
            except Exception as exc:
                with self._lock:
                    self.last_status = f"ERROR: {str(exc)}"
                    self._compute_next_run()


# Instansi global tunggal
cron_scheduler = BinanceCronScheduler()
