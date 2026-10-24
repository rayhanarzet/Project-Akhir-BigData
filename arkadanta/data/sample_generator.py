"""Generator sintetis untuk pengujian eksplisit. Tidak menulis ke penyimpanan penelitian."""

from datetime import datetime, timedelta, timezone
from typing import Dict
import numpy as np
import pandas as pd

ASSET_BASE_PRICES: Dict[str, float] = {
    "BTCUSDT": 68500.0,
    "ETHUSDT": 3450.0,
    "BNBUSDT": 595.0,
    "ADAUSDT": 0.62,
}


def generate_synthetic_5m_ohlcv(
    symbol: str = "BTCUSDT",
    n_candles: int = 2000,
    seed: int = 42,
) -> pd.DataFrame:
    """Menghasilkan data candle 5 menit realistis dengan rezim volatilitas SAFE, WARNING, dan DANGER."""
    rng = np.random.default_rng(seed + sum(ord(c) for c in symbol))
    base_price = ASSET_BASE_PRICES.get(symbol, 100.0)

    end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end_minute = (end_time.minute // 5) * 5
    end_time = end_time.replace(minute=end_minute)
    timestamps = [
        end_time - timedelta(minutes=5 * (n_candles - 1 - i))
        for i in range(n_candles)
    ]

    # Simulasi rezim pasar (Markov-like switching) + faktor bersama lintas aset
    common_rng = np.random.default_rng(seed)
    market_factor = common_rng.normal(0, 0.0018, size=n_candles)

    regimes = np.zeros(n_candles, dtype=int)
    current_regime = 0
    for i in range(1, n_candles):
        p = rng.random()
        if current_regime == 0:  # SAFE
            current_regime = 0 if p < 0.93 else (1 if p < 0.985 else 2)
        elif current_regime == 1:  # WARNING
            current_regime = 1 if p < 0.82 else (0 if p < 0.94 else 2)
        else:  # DANGER (flash crash / spike)
            current_regime = 2 if p < 0.65 else 1
        regimes[i] = current_regime

    vol_scale = np.where(regimes == 0, 0.0018, np.where(regimes == 1, 0.0055, 0.0155))
    idiosyncratic = rng.normal(0, vol_scale)
    returns = 0.65 * market_factor * (vol_scale / 0.0025) + idiosyncratic

    close_prices = base_price * np.exp(np.cumsum(returns))
    open_prices = np.empty_like(close_prices)
    open_prices[0] = base_price
    open_prices[1:] = close_prices[:-1]

    intra_spread = np.abs(rng.normal(vol_scale * 0.85, vol_scale * 0.45))
    upper_wicks = np.abs(rng.normal(vol_scale * 0.45, vol_scale * 0.35))
    lower_wicks = np.abs(rng.normal(vol_scale * 0.45, vol_scale * 0.35))

    body_high = np.maximum(open_prices, close_prices)
    body_low = np.minimum(open_prices, close_prices)
    high_prices = body_high * (1.0 + intra_spread * 0.5 + upper_wicks)
    low_prices = np.maximum(
        body_low * (1.0 - intra_spread * 0.5 - lower_wicks), 1e-6
    )

    base_vol = 45.0 if symbol == "BTCUSDT" else (420.0 if symbol == "ETHUSDT" else 1800.0)
    vol_multiplier = np.where(regimes == 0, 1.0, np.where(regimes == 1, 2.6, 6.8))
    volumes = np.abs(rng.lognormal(mean=np.log(base_vol), sigma=0.45, size=n_candles)) * vol_multiplier
    quote_volumes = volumes * close_prices
    trades = (volumes * rng.uniform(12, 28, size=n_candles)).astype(int)
    buy_ratio = np.clip(0.5 + rng.normal(0, 0.12, size=n_candles) + np.sign(returns) * 0.08, 0.15, 0.88)
    taker_buy_base = volumes * buy_ratio
    taker_buy_quote = quote_volumes * buy_ratio

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, utc=True),
            "coin_symbol": symbol,
            "open": np.round(open_prices, 6),
            "high": np.round(high_prices, 6),
            "low": np.round(low_prices, 6),
            "close": np.round(close_prices, 6),
            "volume": np.round(volumes, 4),
            "quote_asset_volume": np.round(quote_volumes, 4),
            "number_of_trades": trades,
            "taker_buy_base_volume": np.round(taker_buy_base, 4),
            "taker_buy_quote_volume": np.round(taker_buy_quote, 4),
        }
    )
    return df
