"""[ORANG 2] Dynamic Feature Engineering untuk volatilitas, harga, teknikal, struktur candle, dan mikrostruktur (Bab 5.2)."""

import numpy as np
import pandas as pd


def compute_dynamic_features(
    df: pd.DataFrame,
    ma_period: int = 20,
    rsi_period: int = 14,
    rolling_window: int = 20,
) -> pd.DataFrame:
    """Menghasilkan seluruh fitur volatilitas, harga, indikator teknikal, struktur candle, dan mikrostruktur."""
    if df.empty:
        return df

    out_frames = []
    for sym, grp in df.groupby("coin_symbol", sort=False):
        g = grp.sort_values("timestamp").copy()

        # 1. Fitur Harga
        g["log_return"] = np.log(g["close"] / g["close"].shift(1)).replace(
            [np.inf, -np.inf], 0.0
        ).fillna(0.0)
        g["periodic_return"] = g["close"].pct_change().replace(
            [np.inf, -np.inf], 0.0
        ).fillna(0.0)
        g["hl_range"] = (g["high"] - g["low"]) / np.maximum(g["low"], 1e-8)
        g["co_change"] = (g["close"] - g["open"]) / np.maximum(g["open"], 1e-8)

        # 2. Fitur Volatilitas
        if "max_volatility" not in g.columns:
            g["max_volatility"] = g["hl_range"]
        if "avg_volatility" not in g.columns:
            g["avg_volatility"] = g["hl_range"].rolling(3, min_periods=1).mean()

        g["rolling_volatility"] = (
            g["log_return"]
            .rolling(window=rolling_window, min_periods=2)
            .std()
            .fillna(g["hl_range"])
        )
        rolling_vol_mean = (
            g["max_volatility"]
            .rolling(window=rolling_window, min_periods=1)
            .mean()
            .replace(0, 1e-8)
        )
        g["spike_ratio"] = g["max_volatility"] / np.maximum(rolling_vol_mean, 1e-8)

        # 3. Indikator Teknikal (SMA, EMA, RSI, Bollinger Bands Width)
        g["sma_20"] = g["close"].rolling(window=ma_period, min_periods=1).mean()
        g["ema_20"] = g["close"].ewm(span=ma_period, adjust=False).mean()

        # RSI rata-rata sederhana (Cutler), sama persis dengan spark_compute_features agar model
        # yang dilatih dari fitur Spark menerima skala fitur yang sama saat prediksi pandas.
        delta = g["close"].diff().fillna(0.0)
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.rolling(window=rsi_period, min_periods=1).mean()
        avg_loss = loss.rolling(window=rsi_period, min_periods=1).mean()
        rs = avg_gain / np.maximum(avg_loss, 1e-8)
        g["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
        g["rsi_14"] = g["rsi_14"].fillna(50.0)

        bb_std = g["close"].rolling(window=ma_period, min_periods=2).std().fillna(0.0)
        g["bb_upper"] = g["sma_20"] + 2.0 * bb_std
        g["bb_lower"] = g["sma_20"] - 2.0 * bb_std
        g["bb_width"] = (g["bb_upper"] - g["bb_lower"]) / np.maximum(g["sma_20"], 1e-8)

        # 4. Struktur Candle (Upper Wick, Lower Wick, Body Ratio)
        candle_span = np.maximum(g["high"] - g["low"], 1e-8)
        body_top = np.maximum(g["open"], g["close"])
        body_bottom = np.minimum(g["open"], g["close"])
        g["upper_wick_ratio"] = (g["high"] - body_top) / candle_span
        g["lower_wick_ratio"] = (body_bottom - g["low"]) / candle_span
        g["body_ratio"] = (body_top - body_bottom) / candle_span

        # 5. Mikrostruktur Pasar: hanya dari kolom sumber nyata; baris tanpa sumber tetap NaN.
        if "taker_buy_base_volume" in g.columns:
            g["buy_sell_pressure_ratio"] = g["taker_buy_base_volume"] / np.maximum(
                g["volume"], 1e-8
            )
        vol_mean = g["volume"].rolling(window=rolling_window, min_periods=1).mean()
        vol_std = (
            g["volume"]
            .rolling(window=rolling_window, min_periods=2)
            .std()
            .replace(0, 1.0)
            .fillna(1.0)
        )
        g["volume_zscore"] = (g["volume"] - vol_mean) / np.maximum(vol_std, 1e-8)

        out_frames.append(g)

    result = pd.concat(out_frames, ignore_index=True).replace([np.inf, -np.inf], 0.0)
    keep_missing = [c for c in MICROSTRUCTURE_SOURCE_COLUMNS if c in result.columns]
    return result.fillna({c: 0.0 for c in result.columns if c not in keep_missing})


# Nilai hilang di kolom ini berarti sumber tidak menyediakannya, bukan nol.
MICROSTRUCTURE_SOURCE_COLUMNS = (
    "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
    "taker_buy_quote_volume", "buy_sell_pressure_ratio",
)
