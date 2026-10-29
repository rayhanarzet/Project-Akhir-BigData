"""Setiap baris baru di dataset penelitian tepat sekali masuk ke NiFi outbox berpartisi."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import storage


def rows(start: str, count: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=count, freq="5min", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "coin_symbol": "BTCUSDT", "open": 1.0,
                         "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0})


def outbox_rows() -> pd.DataFrame:
    files = sorted(storage.NIFI_OUTBOX_DIR.rglob("*.csv"))
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def test_new_rows_only_and_partitioned_by_month():
    # Melewati batas bulan: harus terpecah ke month=09 dan month=10.
    storage.save_clean_ohlcv("BTCUSDT", rows("2026-09-30 23:50", 4))
    storage.save_clean_ohlcv("BTCUSDT", rows("2026-10-01 00:00", 3))  # 2 duplikat + 1 baru

    out = outbox_rows()
    assert len(out) == 5
    assert out["timestamp"].is_unique
    partitions = {p.parent.relative_to(storage.NIFI_OUTBOX_DIR).as_posix() for p in storage.NIFI_OUTBOX_DIR.rglob("*.csv")}
    assert partitions == {"v3/symbol=BTCUSDT/year=2026/month=09", "v3/symbol=BTCUSDT/year=2026/month=10"}
    assert not list(storage.NIFI_OUTBOX_DIR.rglob(".*"))  # tidak ada berkas sementara tertinggal
