import pandas as pd

try:
    from src.schema import REQUIRED_COLUMNS, NUMERIC_COLUMNS
except ImportError:
    from schema import REQUIRED_COLUMNS, NUMERIC_COLUMNS


def validate_data(df):
    messages = []

    # Terima alias asset dari data sampel lama.
    if "coin_symbol" not in df.columns and "asset" in df.columns:
        df = df.copy()
        df["coin_symbol"] = df["asset"]

    missing_columns = [
        column for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        messages.append(
            f"Kolom wajib tidak tersedia: {missing_columns}"
        )
        return False, messages

    if df["timestamp"].isna().any():
        messages.append("Terdapat timestamp kosong.")
        return False, messages

    timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
    if timestamps.isna().any():
        messages.append("Format timestamp tidak valid.")
        return False, messages

    for column in NUMERIC_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")

        if values.isna().any():
            messages.append(
                f"Kolom {column} memiliki nilai kosong atau nonnumerik."
            )
            return False, messages

        if not values.map(lambda value: pd.notna(value) and abs(value) != float("inf")).all():
            messages.append(f"Kolom {column} memiliki nilai tidak valid.")
            return False, messages

    numeric_df = df[NUMERIC_COLUMNS].apply(
        pd.to_numeric, errors="coerce"
    )

    if (numeric_df[["open", "high", "low", "close"]] <= 0).any().any():
        messages.append("Harga OHLC harus lebih besar dari nol.")
        return False, messages

    if (numeric_df["volume"] < 0).any():
        messages.append("Volume tidak boleh negatif.")
        return False, messages

    invalid_ohlc = (
        (numeric_df["high"] < numeric_df[["open", "close", "low"]].max(axis=1))
        | (numeric_df["low"] > numeric_df[["open", "close", "high"]].min(axis=1))
    )

    if invalid_ohlc.any():
        messages.append("Terdapat candle dengan nilai OHLC tidak konsisten.")
        return False, messages

    messages.append("Data valid.")
    return True, messages
