import pandas as pd

from src.schema import NUMERIC_COLUMNS


def validate_data(df):
    errors = []

    # Periksa nilai kosong
    if df.isnull().any().any():
        errors.append("Data mengandung nilai kosong")

    # Periksa nilai numerik
    for column in NUMERIC_COLUMNS:
        converted = pd.to_numeric(
            df[column], errors="coerce"
        )

        if converted.isnull().any():
            errors.append(
                f"Kolom {column} mengandung nilai nonnumerik"
            )
        elif not converted.map(
            lambda value: pd.notna(value)
            and abs(value) != float("inf")
        ).all():
            errors.append(
                f"Kolom {column} mengandung nilai tidak valid"
            )
        else:
            df[column] = converted

    if errors:
        return False, errors

    # Harga dan volume tidak boleh negatif
    if (df[NUMERIC_COLUMNS] < 0).any().any():
        errors.append("Harga atau volume bernilai negatif")

    # Validasi rentang harga candle
    if (
        (df["high"] < df["low"]).any()
        or (df["high"] < df["open"]).any()
        or (df["high"] < df["close"]).any()
        or (df["low"] > df["open"]).any()
        or (df["low"] > df["close"]).any()
    ):
        errors.append("Rentang harga candle tidak valid")

    if errors:
        return False, errors

    return True, ["Data valid"]
