import pandas as pd
from pathlib import Path


def parse_file(file_path):
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".csv":
        df = pd.read_csv(path)
    elif extension == ".json":
        df = pd.read_json(path)
    else:
        raise ValueError(
            f"Format file tidak didukung: {extension}"
        )

    required_columns = [
        "timestamp", "open", "high", "low",
        "close", "volume", "asset", "interval"
    ]

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Kolom wajib tidak ditemukan: {missing_columns}"
        )

    return df[required_columns]
