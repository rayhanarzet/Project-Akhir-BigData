"""[ORANG 1 - KONTRAK & STUB] Parser CSV ke DataFrame."""

import io
import pandas as pd


def parse_csv_bytes(content: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(content))
