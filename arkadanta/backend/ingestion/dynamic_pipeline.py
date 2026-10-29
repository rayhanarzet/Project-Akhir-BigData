"""[ORANG 1 - KONTRAK & STUB] Dynamic Pipeline Controller berbasis aturan (Bab 4.2 & 4.3)."""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import uuid
import pandas as pd

from backend.config import DROP_ZONE_DIR, HDFS_BASE_PATH
from backend.ingestion.format_detector import detect_format
from backend.ingestion.processors.csv_processor import parse_csv_bytes
from backend.ingestion.processors.json_processor import parse_json_bytes
from backend.ingestion.schema_validator import map_and_validate_schema
from backend.schemas import IngestionAuditReport
from data.storage import append_audit_logs, save_clean_ohlcv


def run_dynamic_ingestion_pipeline(
    filename: str,
    content: bytes,
    custom_mapping: Optional[Dict[str, str]] = None,
    default_symbol: str = "BTCUSDT",
) -> Tuple[pd.DataFrame, IngestionAuditReport]:
    """Menjalankan aturan Dynamic Pipeline Controller dan menghasilkan data bersih + laporan audit."""
    fmt = detect_format(filename, content[:512])
    df_raw = parse_json_bytes(content) if fmt == "JSON" else parse_csv_bytes(content)
    rows_before = len(df_raw)

    df, applied_mapping, error_reasons = map_and_validate_schema(
        df_raw, custom_mapping=custom_mapping, default_symbol=default_symbol
    )

    # 1. Konversi timestamp ke UTC (mendukung epoch s, ms, us, ns maupun string ISO)
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        max_ts = float(df["timestamp"].dropna().max()) if not df["timestamp"].dropna().empty else 0.0
        if max_ts > 1e17:
            unit = "ns"
        elif max_ts > 1e14:
            unit = "us"
        elif max_ts > 1e11:
            unit = "ms"
        else:
            unit = "s"
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit=unit, utc=True, errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    invalid_ts = int(df["timestamp"].isna().sum())
    error_reasons["invalid_timestamp"] = invalid_ts
    df = df.dropna(subset=["timestamp"]).copy()

    # 2. Konversi harga & volume ke numerik
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["coin_symbol"] = df["coin_symbol"].astype(str).str.upper().str.strip()

    # 3. Hapus duplikasi berdasarkan coin_symbol dan timestamp & urutkan
    before_dedup = len(df)
    df = df.sort_values(["coin_symbol", "timestamp"]).drop_duplicates(
        subset=["coin_symbol", "timestamp"], keep="last"
    )
    duplicates_removed = before_dedup - len(df)

    # 4. Forward-fill per aset pada OHLC & isi volume kosong dengan 0.0
    imputed_ohlc_rows = int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    df[["open", "high", "low", "close"]] = df.groupby("coin_symbol")[
        ["open", "high", "low", "close"]
    ].ffill()
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()

    imputed_volume_rows = int(df["volume"].isna().sum())
    df["volume"] = df["volume"].fillna(0.0)

    # 5. Sanity check (high < low, harga <= 0, volume < 0, atau high/low tidak konsisten terhadap open/close)
    bad_hl = (
        (df["high"] < df["low"])
        | (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
    )
    bad_price = (df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)
    bad_vol = df["volume"] < 0

    error_reasons["high_less_than_low"] = int(bad_hl.sum())
    error_reasons["non_positive_price"] = int(bad_price.sum())
    error_reasons["negative_volume"] = int(bad_vol.sum())

    invalid_mask = bad_hl | bad_price | bad_vol
    rejected_rows = int(invalid_mask.sum()) + invalid_ts
    df_clean = df[~invalid_mask].reset_index(drop=True)

    # Kolom mikrostruktur opsional tidak diisi tebakan; fitur turunannya ditolak bila sumbernya tidak ada.
    symbols_detected = sorted(df_clean["coin_symbol"].unique().tolist())
    primary_sym = symbols_detected[0] if symbols_detected else default_symbol.upper()

    # 6. Simpan/gabungkan secara terpisah per coin_symbol ke Drop Zone (mendukung file multi-aset)
    # Baris baru ikut ditulis ke NiFi outbox oleh save_clean_ohlcv; NiFi yang mengirim ke HDFS.
    saved_paths = []
    hdfs_status = "QUEUED_DROP_ZONE"
    for sym, sym_df in df_clean.groupby("coin_symbol"):
        sym_path = DROP_ZONE_DIR / f"{sym}_5m_clean.csv"
        sym_clean = sym_df.sort_values("timestamp").reset_index(drop=True)
        save_clean_ohlcv(sym, sym_clean)
        saved_paths.append(f"data/research/drop_zone/{sym_path.name}")

    if not saved_paths:
        out_path = DROP_ZONE_DIR / f"{primary_sym}_5m_clean.csv"
        save_clean_ohlcv(primary_sym, df_clean)
        saved_paths.append(f"data/research/drop_zone/{out_path.name}")

    rows_after = len(df_clean)
    quality_score = round((rows_after / max(rows_before, 1)) * 100.0, 2)

    report = IngestionAuditReport(
        run_id=f"ing_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source_name=filename,
        format_detected=fmt,
        selected_pipeline=f"{fmt}Parser -> SchemaAliasMapper -> DedupSorter -> ForwardFillImputer -> OHLCVSanityGuard",
        column_mapping=applied_mapping,
        symbols_detected=symbols_detected or [primary_sym],
        rows_before=rows_before,
        rows_after=rows_after,
        duplicates_removed=duplicates_removed,
        imputed_ohlc_rows=imputed_ohlc_rows,
        imputed_volume_rows=imputed_volume_rows,
        rejected_rows=rejected_rows,
        error_reasons=error_reasons,
        drop_zone_path=", ".join(saved_paths),
        hdfs_target_path=(
            f"{HDFS_BASE_PATH}symbol={primary_sym}/"
            if len(symbols_detected) <= 1
            else f"{HDFS_BASE_PATH}symbol={{multi:{','.join(symbols_detected)}}}/"
        ),
        nifi_hdfs_status=hdfs_status,
        quality_score_pct=quality_score,
    )

    append_audit_logs([report.model_dump()])

    return df_clean, report
