"""Aturan candle sumber bersama untuk upload, REST, dan penyimpanan stream."""
import numpy as np
import pandas as pd

BASE_PERIOD = pd.Timedelta(minutes=5)
OHLCV = ("open", "high", "low", "close", "volume")
OPTIONAL_NUMERIC = ("quote_asset_volume", "number_of_trades", "taker_buy_base_volume", "taker_buy_quote_volume")


def validate_candles(frame: pd.DataFrame, now=None) -> tuple[pd.DataFrame, dict[str, int]]:
    missing = {"timestamp", "coin_symbol", *OHLCV} - set(frame.columns)
    if missing:
        raise ValueError(f"Kolom candle tidak lengkap: {sorted(missing)}")
    df = frame.copy()
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        maximum = pd.to_numeric(df["timestamp"], errors="coerce").max()
        unit = "ns" if maximum > 1e17 else "us" if maximum > 1e14 else "ms" if maximum > 1e11 else "s"
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit=unit, utc=True, errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="mixed")
    df["coin_symbol"] = df["coin_symbol"].astype("string").str.strip().str.upper()
    malformed_optional = pd.Series(False, index=df.index)
    for col in (*OHLCV, *OPTIONAL_NUMERIC):
        if col in df:
            numbers = pd.to_numeric(df[col], errors="coerce")
            if col in OPTIONAL_NUMERIC:
                malformed_optional |= df[col].notna() & numbers.isna()
            df[col] = numbers
    clock = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock.tz_convert("UTC")
    numeric = df[list(OHLCV)].to_numpy(dtype=float)
    reasons = {
        "invalid_timestamp": df["timestamp"].isna(),
        "invalid_symbol": ~df["coin_symbol"].str.fullmatch(r"[A-Z0-9]{2,30}", na=False),
        "non_finite_ohlcv": pd.Series(~np.isfinite(numeric).all(axis=1), index=df.index),
        "non_positive_price": (df[list(OHLCV[:4])] <= 0).any(axis=1),
        "negative_volume": df["volume"] < 0,
        "high_less_than_low": (df["high"] < df[["open", "close", "low"]].max(axis=1))
                              | (df["low"] > df[["open", "close", "high"]].min(axis=1)),
        "off_grid_timestamp": df["timestamp"].notna() & (df["timestamp"] != df["timestamp"].dt.floor("5min")),
        "unfinished_or_future_candle": df["timestamp"] + BASE_PERIOD > clock,
    }
    optional_bad = malformed_optional
    for col in OPTIONAL_NUMERIC:
        if col in df:
            values = df[col]
            optional_bad |= values.notna() & (~np.isfinite(values) | (values < 0))
            if col == "number_of_trades":
                optional_bad |= values.notna() & (values % 1 != 0)
    reasons["invalid_microstructure"] = optional_bad
    invalid = pd.DataFrame(reasons).fillna(True).any(axis=1)
    counts = {name: int(mask.fillna(True).sum()) for name, mask in reasons.items()}
    counts["rejected_rows"] = int(invalid.sum())
    return df.loc[~invalid].reset_index(drop=True), counts
