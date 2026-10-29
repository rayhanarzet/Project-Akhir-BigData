"""[ORANG 1 - KONTRAK & STUB] Dynamic Pipeline Controller berbasis aturan (Bab 4.2 & 4.3)."""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import hashlib
import uuid
import pandas as pd

from backend.config import DROP_ZONE_DIR, HDFS_BASE_PATH
from backend.ingestion.format_detector import detect_format
from backend.ingestion.processors.csv_processor import parse_csv_bytes
from backend.ingestion.processors.json_processor import parse_json_bytes
from backend.ingestion.schema_validator import map_and_validate_schema
from backend.schemas import IngestionAuditReport
from data.storage import append_audit_logs, save_clean_ohlcv
from data.validation import validate_candles


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

    df, error_reasons = validate_candles(df)
    rejected_rows = error_reasons.pop("rejected_rows")
    # Baris tidak lengkap ditolak; data penelitian tidak diisi dari harga/volume tebakan.
    before_dedup = len(df)
    df = df.sort_values(["coin_symbol", "timestamp"]).drop_duplicates(
        subset=["coin_symbol", "timestamp"], keep="last"
    )
    duplicates_removed = before_dedup - len(df)

    df_clean = df.reset_index(drop=True)

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
        save_clean_ohlcv(sym, sym_clean, source=filename)
        saved_paths.append(f"data/research/drop_zone/{sym_path.name}")

    rows_after = len(df_clean)
    quality_score = round((rows_after / max(rows_before, 1)) * 100.0, 2)

    report = IngestionAuditReport(
        run_id=f"ing_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source_name=filename,
        source_sha256=hashlib.sha256(content).hexdigest(),
        format_detected=fmt,
        selected_pipeline=f"{fmt}Parser -> SchemaAliasMapper -> Closed5mFiniteValidator -> DedupSorter -> DurableOutbox",
        column_mapping=applied_mapping,
        symbols_detected=symbols_detected or [primary_sym],
        rows_before=rows_before,
        rows_after=rows_after,
        duplicates_removed=duplicates_removed,
        imputed_ohlc_rows=0,
        imputed_volume_rows=0,
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
