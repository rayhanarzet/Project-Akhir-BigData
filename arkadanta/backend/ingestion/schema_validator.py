"""[ORANG 1 - KONTRAK & STUB] Validasi skema OHLCV, pencocokan alias kolom, dan sanity check."""

from typing import Dict, Tuple
import pandas as pd

COLUMN_ALIASES: Dict[str, str] = {
    "open_time": "timestamp",
    "time": "timestamp",
    "date": "timestamp",
    "datetime": "timestamp",
    "symbol": "coin_symbol",
    "pair": "coin_symbol",
    "ticker": "coin_symbol",
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "vol": "volume",
    "base_volume": "volume",
    "quote_vol": "quote_asset_volume",
    "trades": "number_of_trades",
}

REQUIRED_COLUMNS = ["timestamp", "coin_symbol", "open", "high", "low", "close", "volume"]


def map_and_validate_schema(
    df: pd.DataFrame,
    custom_mapping: Dict[str, str] | None = None,
    default_symbol: str = "BTCUSDT",
) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, int]]:
    """Memetakan alias kolom ke skema OHLCV standar dan menjalankan pemeriksaan kualitas data."""
    applied_mapping: Dict[str, str] = {}
    rename_dict: Dict[str, str] = {}

    effective_aliases = {**COLUMN_ALIASES, **(custom_mapping or {})}
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if col_clean in effective_aliases and effective_aliases[col_clean] not in df.columns:
            target = effective_aliases[col_clean]
            rename_dict[col] = target
            applied_mapping[col] = target
        elif col_clean in REQUIRED_COLUMNS and col != col_clean:
            rename_dict[col] = col_clean

    df = df.rename(columns=rename_dict).copy()

    if "coin_symbol" not in df.columns:
        df["coin_symbol"] = default_symbol.upper()
        applied_mapping["<default>"] = f"coin_symbol={default_symbol.upper()}"

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Kolom wajib OHLCV tidak ditemukan: {missing}")

    return df, applied_mapping, {
        "high_less_than_low": 0,
        "non_positive_price": 0,
        "negative_volume": 0,
        "invalid_timestamp": 0,
    }
