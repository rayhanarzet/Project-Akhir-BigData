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
from data.sample_generator import load_audit_logs, save_audit_logs


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

    # 1. Konversi timestamp ke UTC
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        max_ts = df["timestamp"].dropna().max()
        unit = "ms" if max_ts > 1e11 else "s"
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

    # 5. Sanity check (high < low, harga <= 0, volume < 0)
    bad_hl = df["high"] < df["low"]
    bad_price = (df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)
    bad_vol = df["volume"] < 0

    error_reasons["high_less_than_low"] = int(bad_hl.sum())
    error_reasons["non_positive_price"] = int(bad_price.sum())
    error_reasons["negative_volume"] = int(bad_vol.sum())

    invalid_mask = bad_hl | bad_price | bad_vol
    rejected_rows = int(invalid_mask.sum()) + invalid_ts
    df_clean = df[~invalid_mask].reset_index(drop=True)

    # Kolom opsional mikrostruktur
    if "quote_asset_volume" not in df_clean.columns:
        df_clean["quote_asset_volume"] = df_clean["volume"] * df_clean["close"]
    if "number_of_trades" not in df_clean.columns:
        df_clean["number_of_trades"] = (df_clean["volume"] * 15).astype(int)
    if "taker_buy_base_volume" not in df_clean.columns:
        df_clean["taker_buy_base_volume"] = df_clean["volume"] * 0.5
    if "taker_buy_quote_volume" not in df_clean.columns:
        df_clean["taker_buy_quote_volume"] = df_clean["quote_asset_volume"] * 0.5

    symbols_detected = sorted(df_clean["coin_symbol"].unique().tolist())
    primary_sym = symbols_detected[0] if symbols_detected else default_symbol.upper()

    out_path = DROP_ZONE_DIR / f"{primary_sym}_5m_clean.csv"
    df_clean.to_csv(out_path, index=False)

    rows_after = len(df_clean)
    quality_score = round((rows_after / max(rows_before, 1)) * 100.0, 2)

    report = IngestionAuditReport(
        run_id=f"ing_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source_name=filename,
        format_detected=fmt,
        selected_pipeline=f"{fmt}Parser -> SchemaAliasMapper -> DedupSorter -> ForwardFillImputer -> OHLCVSanityGuard",
        column_mapping=applied_mapping,
        symbols_detected=symbols_detected,
        rows_before=rows_before,
        rows_after=rows_after,
        duplicates_removed=duplicates_removed,
        imputed_ohlc_rows=imputed_ohlc_rows,
        imputed_volume_rows=imputed_volume_rows,
        rejected_rows=rejected_rows,
        error_reasons=error_reasons,
        drop_zone_path=f"data/drop_zone/{out_path.name}",
        hdfs_target_path=f"{HDFS_BASE_PATH}symbol={primary_sym}/",
        nifi_hdfs_status="QUEUED_DROP_ZONE",
        quality_score_pct=quality_score,
    )

    logs = load_audit_logs()
    logs.insert(0, report.model_dump())
    save_audit_logs(logs[:50])

    return df_clean, report
