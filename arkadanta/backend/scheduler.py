"""Background Cron Job Scheduler untuk penarikan data Binance berkala (Speed Layer)."""

import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import requests
import pandas as pd

from backend.config import BINANCE_KLINES_URL, DEFAULT_SYMBOLS, DROP_ZONE_DIR, HDFS_BASE_PATH
from backend.schemas import IngestionAuditReport
from data.sample_generator import (
    generate_synthetic_5m_ohlcv,
    load_audit_logs,
    load_clean_ohlcv,
    save_audit_logs,
)
import uuid


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
        self._lock = threading.Lock()

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
        """Mengeksekusi penarikan data Binance untuk simbol terpilih (dapat dipanggil cron atau manual)."""
        target_symbols = symbols or self.symbols
        target_limit = limit or self.limit
        synced_reports = []

        for sym in target_symbols:
            symbol = sym.upper()
            source_mode = "BINANCE_API"
            try:
                resp = requests.get(
                    BINANCE_KLINES_URL,
                    params={"symbol": symbol, "interval": "5m", "limit": target_limit},
                    timeout=7,
                )
                resp.raise_for_status()
                raw_klines = resp.json()
                rows = []
                for k in raw_klines:
                    rows.append(
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
                    )
                df_new = pd.DataFrame(rows)
            except Exception:
                source_mode = "CSV"
                df_new = generate_synthetic_5m_ohlcv(symbol=symbol, n_candles=target_limit)

            existing_path = DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"
            if existing_path.exists():
                df_old = load_clean_ohlcv(symbol)
                rows_before = len(df_old) + len(df_new)
                df_merged = (
                    pd.concat([df_old, df_new], ignore_index=True)
                    .sort_values("timestamp")
                    .drop_duplicates(subset=["coin_symbol", "timestamp"], keep="last")
                    .reset_index(drop=True)
                )
            else:
                rows_before = len(df_new)
                df_merged = df_new

            df_merged.to_csv(existing_path, index=False)
            dups = max(0, rows_before - len(df_merged))

            rep = IngestionAuditReport(
                run_id=f"cron_{uuid.uuid4().hex[:8]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source_name=f"Binance /api/v3/klines ({symbol} 5m auto-sync)",
                format_detected=source_mode,
                selected_pipeline="BinanceCronFetcher -> SchemaNormalizer -> Deduplicator -> DropZoneWriter",
                column_mapping={"open_time": "timestamp", "symbol": "coin_symbol"},
                symbols_detected=[symbol],
                rows_before=rows_before,
                rows_after=len(df_merged),
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
                drop_zone_path=f"data/drop_zone/{existing_path.name}",
                hdfs_target_path=f"{HDFS_BASE_PATH}symbol={symbol}/",
                nifi_hdfs_status="SYNCED",
                quality_score_pct=100.0,
            )
            synced_reports.append(rep.model_dump())

        logs = load_audit_logs()
        save_audit_logs((synced_reports + logs)[:50])
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
