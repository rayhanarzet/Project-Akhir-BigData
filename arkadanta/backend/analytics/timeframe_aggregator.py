"""Agregasi Multi-Timeframe deterministik (5m -> 15m, 1h, 4h, 1d, 1w) sesuai Bab 5.1."""

from typing import Optional
import numpy as np
import pandas as pd
from backend.analytics.research_window import filter_research_window


TIMEFRAME_PANDAS_MAP = {
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    # Minggu Senin 00:00 UTC seperti Binance; sama dengan window Spark startTime="4 days".
    "1w": "W-MON",
}
TIMEFRAME_DURATION = {
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
    "1w": pd.Timedelta(weeks=1),
}
BASE_CANDLE = pd.Timedelta(minutes=5)


def aggregate_timeframe(
    df_5m: pd.DataFrame,
    timeframe: str = "1h",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Mengagregasi data 5 menit menjadi timeframe target dengan urutan timestamp eksplisit."""
    df = filter_research_window(df_5m, start_date, end_date)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["coin_symbol", "timestamp"]).reset_index(drop=True)

    if df.empty:
        return df

    # Volatilitas dasar tingkat 5m sebelum agregasi
    df["candle_volatility"] = (df["high"] - df["low"]) / np.maximum(df["low"], 1e-8)

    if timeframe == "5m":
        out = df.copy()
        out["max_volatility"] = out["candle_volatility"]
        out["avg_volatility"] = out["candle_volatility"]
        out["log_return"] = np.log(
            out["close"] / out.groupby("coin_symbol")["close"].shift(1)
        ).fillna(0.0)
        return out.drop(columns=["candle_volatility"]).reset_index(drop=True)

    freq = TIMEFRAME_PANDAS_MAP.get(timeframe, "1h")
    results = []

    for sym, grp in df.groupby("coin_symbol", sort=False):
        grp = grp.sort_values("timestamp").set_index("timestamp")
        expected = int(TIMEFRAME_DURATION[timeframe] / BASE_CANDLE)
        agg_dict = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "candle_volatility": ["max", "mean", "count"],
        }
        optional_cols = [col for col in (
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ) if col in grp.columns]
        agg_dict.update(dict.fromkeys(optional_cols, "sum"))

        res = grp.resample(freq, label="left", closed="left").agg(agg_dict)
        res.columns = [
            f"{c[0]}_{c[1]}" if c[0] == "candle_volatility" else c[0]
            for c in res.columns
        ]
        if optional_cols:
            # Total hanya bermakna bila sumber seluruh candle dalam bucket tersedia.
            counts = grp[optional_cols].resample(freq, label="left", closed="left").count()
            res[optional_cols] = res[optional_cols].where(counts.eq(expected))
        res = res.dropna(subset=["open", "high", "low", "close"]).reset_index()
        # Hanya bucket dengan candle 5m lengkap: bucket berjalan (terakhir) atau berlubang (data hilang)
        # akan bias rendah pada volume/volatilitas.
        res = res[res["candle_volatility_count"] == expected].reset_index(drop=True)
        res["coin_symbol"] = sym
        res["max_volatility"] = np.maximum(
            res["candle_volatility_max"],
            (res["high"] - res["low"]) / np.maximum(res["low"], 1e-8),
        )
        res["avg_volatility"] = res["candle_volatility_mean"]
        res["log_return"] = np.log(res["close"] / res["close"].shift(1)).fillna(0.0)
        res = res.drop(columns=["candle_volatility_max", "candle_volatility_mean", "candle_volatility_count"])
        results.append(res)

    return pd.concat(results, ignore_index=True)
