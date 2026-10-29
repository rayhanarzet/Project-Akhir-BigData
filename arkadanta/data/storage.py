"""Penyimpanan data penelitian. Tidak pernah membuat data simulasi."""
import json
import io
import errno
import os
from collections import deque
from pathlib import Path
import re
import threading
import time
import uuid
from typing import List
import pandas as pd
from backend.config import AUDIT_LOG_PATH, DROP_ZONE_DIR, NIFI_OUTBOX_DIR
from data.validation import validate_candles, OHLCV, OPTIONAL_NUMERIC

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
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                try:
                    os.fsync(descriptor)
                except OSError as exc:
                    # DrvFS/9p dapat mendukung fsync berkas tetapi tidak fsync direktori.
                    if exc.errno not in (errno.EINVAL, errno.ENOTSUP):
                        raise
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


class ResearchDataError(ValueError):
    """Dataset penelitian belum tersedia atau tidak dapat digunakan."""


def load_clean_ohlcv(symbol: str = "BTCUSDT") -> pd.DataFrame:
    """Membaca data 5m bersih untuk satu simbol dari drop_zone (tanpa membuat data pengganti)."""
    symbol = _symbol(symbol)
    with _write_lock:
        _replay_pending(symbol)
        return _load_clean_ohlcv(symbol)


def _load_clean_ohlcv(symbol: str) -> pd.DataFrame:
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
        df, errors = validate_candles(df)
        if errors["rejected_rows"] or not df["coin_symbol"].eq(symbol).all():
            raise ValueError(f"candle sumber tidak valid: {errors}")
    except (ValueError, KeyError, OSError) as exc:
        raise ResearchDataError(f"Data penelitian {symbol.upper()} tidak dapat dibaca: {exc}") from exc
    df = df.sort_values("timestamp").drop_duplicates(subset=["coin_symbol", "timestamp"]).reset_index(drop=True)
    _read_cache[file_path] = (version, df)
    return df.copy()


def load_audit_logs(limit: int | None = None) -> List[dict]:
    journal = AUDIT_LOG_PATH.with_suffix(".jsonl")
    if journal.exists():
        with _write_lock, journal.open(encoding="utf-8") as stream:
            records = deque(maxlen=limit)
            for line in stream:
                if line.strip():
                    records.append(json.loads(line))
        return list(reversed(records))
    if AUDIT_LOG_PATH.exists():
        try:
            records = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
            return records[:limit] if limit else records
        except (ValueError, OSError) as exc:
            raise ResearchDataError(f"Audit tidak dapat dibaca: {exc}") from exc
    return []


def save_audit_logs(logs: List[dict]) -> None:
    with _write_lock:
        _atomic_write(AUDIT_LOG_PATH, json.dumps(logs, indent=2))
        _atomic_write(AUDIT_LOG_PATH.with_suffix(".jsonl"), "".join(json.dumps(row) + "\n" for row in reversed(logs)))


def append_audit_logs(logs: List[dict]) -> None:
    with _write_lock:
        journal = AUDIT_LOG_PATH.with_suffix(".jsonl")
        if not journal.exists():
            legacy = load_audit_logs()
            _atomic_write(journal, "".join(json.dumps(row) + "\n" for row in reversed(legacy)))
        with journal.open("a", encoding="utf-8") as stream:
            for row in reversed(logs):
                stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Snapshot kompatibilitas; riwayat lengkap tetap ada di JSONL.
        _atomic_write(AUDIT_LOG_PATH, json.dumps(load_audit_logs(limit=50), indent=2))


def save_clean_ohlcv(symbol: str, frame: pd.DataFrame, *, source: str = "ingestion") -> tuple[int, int]:
    """Serialisasi penulis upload/REST/stream dalam satu worker; pembaca melihat berkas utuh."""
    # shortcut: setiap simpan menulis ulang CSV aset (~10 MB/tahun 5m), O(n) per candle; cukup untuk
    # 4 aset x 1 tahun. Untuk multi-tahun, pindahkan speed layer ke berkas append per bulan/Parquet.
    symbol = _symbol(symbol)
    path = DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"
    with _write_lock:
        _replay_pending(symbol)
        frame, errors = validate_candles(frame)
        if errors["rejected_rows"] or frame.empty or not frame["coin_symbol"].eq(symbol).all():
            raise ResearchDataError(f"Candle {symbol} ditolak: {errors}. Wajib OHLCV nyata, angka terbatas, interval 5m, dan sudah selesai.")
        existing = _load_clean_ohlcv(symbol) if path.exists() else None
        rows_before = len(frame) + (len(existing) if existing is not None else 0)
        keys = ["coin_symbol", "timestamp"]
        incoming = frame.drop_duplicates(keys, keep="last").set_index(keys)
        old = existing.set_index(keys) if existing is not None else incoming.iloc[:0]
        output = incoming.combine_first(old)
        content_cols = [c for c in output if c not in ("ingestion_version", "ingested_at", "source_name")]
        previous = old.reindex(index=output.index, columns=content_cols)
        content = output[content_cols]
        changed = ~((content == previous) | (content.isna() & previous.isna())).all(axis=1)
        changed |= ~output.index.isin(old.index)
        # Backfill pertama v3 juga menerbitkan candle lokal lama yang belum memiliki versi.
        old_versions = pd.to_numeric(old.get("ingestion_version", pd.Series(0, index=old.index)), errors="coerce").reindex(output.index).fillna(0)
        changed |= output.index.isin(incoming.index) & old_versions.eq(0)
        delta = output.loc[changed].reset_index()
        if not delta.empty:
            previous_version = pd.to_numeric(old.get("ingestion_version", pd.Series(dtype=float)), errors="coerce").max()
            revision = max(time.time_ns(), int(previous_version) + 1 if pd.notna(previous_version) else 0)
            delta["ingestion_version"] = revision
            delta["ingested_at"] = pd.Timestamp.now(tz="UTC").isoformat()
            delta["source_name"] = source
            delta = delta.reindex(columns=["timestamp", "coin_symbol", *OHLCV, *OPTIONAL_NUMERIC,
                                           "ingestion_version", "ingested_at", "source_name"])
            pending = DROP_ZONE_DIR / ".pending"
            pending.mkdir(exist_ok=True)
            batch_id = f"{revision}_{uuid.uuid4().hex[:8]}"
            # Write-ahead journal: perubahan tetap dapat dipulihkan meskipun CSV/outbox gagal.
            _atomic_write(pending / f"{symbol}_{batch_id}.csv", delta.to_csv(index=False))
            _replay_pending(symbol)
        return rows_before, len(output)


def _write_nifi_outbox(symbol: str, new_rows: pd.DataFrame, batch_id: str | None = None) -> None:
    """Snapshot baris baru untuk NiFi GetFile -> PutHDFS dengan partisi symbol/year/month.

    Nama berkas unik dan ditulis atomik (berkas sementara diawali titik diabaikan GetFile),
    sehingga NiFi boleh memindahkan berkas tanpa menyentuh dataset penelitian aktif.
    """
    if new_rows.empty:
        return
    stamp = batch_id or f"{time.time_ns()}_{uuid.uuid4().hex[:8]}"
    # shortcut: satu berkas kecil per penyimpanan (candle live = per 5 menit); untuk volume besar,
    # gabungkan berkas kecil di HDFS (MergeRecord NiFi atau compaction Spark berkala).
    for (year, month), part in new_rows.groupby([new_rows["timestamp"].dt.year, new_rows["timestamp"].dt.month]):
        target = NIFI_OUTBOX_DIR / "v3" / f"symbol={symbol}" / f"year={year}" / f"month={month:02d}"
        target.mkdir(parents=True, exist_ok=True)
        _atomic_write(target / f"{symbol}_5m_{stamp}.csv", part.to_csv(index=False))


def _replay_pending(symbol: str) -> None:
    for journal in sorted((DROP_ZONE_DIR / ".pending").glob(f"{symbol}_*.csv")):
        delta = pd.read_csv(io.StringIO(journal.read_text(encoding="utf-8")))
        delta["timestamp"] = pd.to_datetime(delta["timestamp"], utc=True)
        path = DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"
        old = _load_clean_ohlcv(symbol) if path.exists() else delta.iloc[:0]
        old = old.copy()
        old["ingestion_version"] = pd.to_numeric(old.get("ingestion_version", pd.Series(0, index=old.index)), errors="coerce").fillna(0).astype("int64")
        output = pd.concat([old, delta], ignore_index=True)
        output["ingestion_version"] = pd.to_numeric(output["ingestion_version"], errors="coerce").fillna(0).astype("int64")
        output = output.sort_values("ingestion_version", kind="stable").drop_duplicates(["coin_symbol", "timestamp"], keep="last")
        _atomic_write(path, output.sort_values("timestamp").to_csv(index=False))
        batch_id = journal.stem[len(symbol) + 1:]
        _write_nifi_outbox(symbol, delta, batch_id)
        journal.unlink()


def recover_pending_writes() -> None:
    with _write_lock:
        symbols = {path.name.split("_", 1)[0] for path in (DROP_ZONE_DIR / ".pending").glob("*.csv")}
        for symbol in sorted(symbols):
            _replay_pending(_symbol(symbol))


def delivery_status() -> dict:
    return {
        "pending_recovery_batches": len(list((DROP_ZONE_DIR / ".pending").glob("*.csv"))),
        "queued_files": len(list(NIFI_OUTBOX_DIR.rglob("*.csv"))),
        "delivery_confirmed": False,
        "detail": "Antrean lokal bukan konfirmasi pengiriman HDFS. Periksa provenance NiFi dan hasil baca HDFS.",
    }
