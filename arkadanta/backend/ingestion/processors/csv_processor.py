"""[ORANG 1 - KONTRAK & STUB] Parser CSV ke DataFrame (mendukung CSV berheader & Raw Binance Vision 12-kolom)."""

import io
import pandas as pd

BINANCE_VISION_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]


def parse_csv_bytes(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content))
    if len(df.columns) in (11, 12):
        first_col = str(df.columns[0]).strip()
        if first_col.isdigit() and len(first_col) >= 10:
            df = pd.read_csv(
                io.BytesIO(content),
                header=None,
                names=BINANCE_VISION_COLUMNS[: len(df.columns)],
            )
    return df
