"""Penyimpanan data penelitian. Tidak pernah membuat data simulasi."""
import json
from pathlib import Path
import re
import threading
import uuid
from typing import List
import pandas as pd
from backend.config import AUDIT_LOG_PATH, DROP_ZONE_DIR, NIFI_OUTBOX_DIR

_write_lock = threading.RLock()
_read_cache: dict[Path, tuple[tuple[int, int], pd.DataFrame]] = {}


def _symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if not re.fullmatch(r"[A-Z0-9]{2,30}", symbol):
        raise ResearchDataError("Simbol aset tidak valid.")
    return symbol


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ResearchDataError(ValueError):
    """Dataset penelitian belum tersedia atau tidak dapat digunakan."""


def load_clean_ohlcv(symbol: str = "BTCUSDT") -> pd.DataFrame:
    """Membaca data 5m bersih untuk satu simbol dari drop_zone (tanpa membuat data pengganti)."""
    symbol = _symbol(symbol)
    file_path = DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"
    if not file_path.exists():
        raise ResearchDataError(f"Data penelitian {symbol.upper()} belum tersedia. Unggah data nyata atau jalankan sinkronisasi Binance.")
    # CSV setahun ~10 MB; baca ulang hanya bila berkas berubah (penulisan atomik mengganti mtime).
    stat = file_path.stat()
    version = (stat.st_mtime_ns, stat.st_size)
    cached = _read_cache.get(file_path)
    if cached is not None and cached[0] == version:
        return cached[1].copy()
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            raise ValueError("dataset kosong")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
        required = {"coin_symbol", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns) or df["timestamp"].isna().any():
            raise ValueError("skema atau timestamp tidak valid")
    except (ValueError, KeyError, OSError) as exc:
        raise ResearchDataError(f"Data penelitian {symbol.upper()} tidak dapat dibaca: {exc}") from exc
    df = df.sort_values("timestamp").drop_duplicates(subset=["coin_symbol", "timestamp"]).reset_index(drop=True)
    _read_cache[file_path] = (version, df)
    return df.copy()


def load_audit_logs() -> List[dict]:
    if AUDIT_LOG_PATH.exists():
        try:
            return json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_audit_logs(logs: List[dict]) -> None:
    with _write_lock:
        _atomic_write(AUDIT_LOG_PATH, json.dumps(logs, indent=2))


def append_audit_logs(logs: List[dict]) -> None:
    with _write_lock:
        save_audit_logs((logs + load_audit_logs())[:50])


def save_clean_ohlcv(symbol: str, frame: pd.DataFrame) -> tuple[int, int]:
    """Serialisasi penulis upload/REST/stream dalam satu worker; pembaca melihat berkas utuh."""
    # shortcut: setiap simpan menulis ulang CSV aset (~10 MB/tahun 5m), O(n) per candle; cukup untuk
    # 4 aset x 1 tahun. Untuk multi-tahun, pindahkan speed layer ke berkas append per bulan/Parquet.
    symbol = _symbol(symbol)
    path = DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"
    with _write_lock:
        # Selalu gabung: data baru tidak pernah menghapus histori yang sudah ada.
        existing = load_clean_ohlcv(symbol) if path.exists() else None
        rows_before = len(frame) + (len(existing) if existing is not None else 0)
        output = pd.concat([existing, frame], ignore_index=True) if existing is not None else frame.copy()
        output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
        output = output.sort_values("timestamp").drop_duplicates(["coin_symbol", "timestamp"], keep="last")
        _atomic_write(path, output.to_csv(index=False))
        known = set(existing["timestamp"]) if existing is not None else set()
        _write_nifi_outbox(symbol, output[~output["timestamp"].isin(known)])
        return rows_before, len(output)


def _write_nifi_outbox(symbol: str, new_rows: pd.DataFrame) -> None:
    """Snapshot baris baru untuk NiFi GetFile -> PutHDFS dengan partisi symbol/year/month.

    Nama berkas unik dan ditulis atomik (berkas sementara diawali titik diabaikan GetFile),
    sehingga NiFi boleh memindahkan berkas tanpa menyentuh dataset penelitian aktif.
    """
    if new_rows.empty:
        return
    stamp = f"{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    # shortcut: satu berkas kecil per penyimpanan (candle live = per 5 menit); untuk volume besar,
    # gabungkan berkas kecil di HDFS (MergeContent NiFi atau compaction Spark berkala).
    for (year, month), part in new_rows.groupby([new_rows["timestamp"].dt.year, new_rows["timestamp"].dt.month]):
        target = NIFI_OUTBOX_DIR / f"symbol={symbol}" / f"year={year}" / f"month={month:02d}"
        target.mkdir(parents=True, exist_ok=True)
        _atomic_write(target / f"{symbol}_5m_{stamp}.csv", part.to_csv(index=False))
