"""[ORANG 2] Analisis Korelasi Lintas Aset (Pearson, Rolling, Lag Correlation, dan Market-Wide Risk Score - Bab 5.4)."""

from typing import Any, Dict, List
import numpy as np
import pandas as pd


def analyze_cross_asset_correlation(
    df_multi: pd.DataFrame,
    base_symbol: str = "BTCUSDT",
    target_symbol: str = "ETHUSDT",
    value_col: str = "log_return",
    rolling_window: int = 30,
    max_lag: int = 6,
) -> Dict[str, Any]:
    """Menghitung Pearson correlation matrix, rolling correlation, lag correlation, dan market-wide risk score."""
    if df_multi.empty:
        return {}

    df = df_multi.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Pivot untuk menyamakan indeks timestamp lintas aset
    pivot_ret = (
        df.pivot_table(index="timestamp", columns="coin_symbol", values=value_col)
        .sort_index()
        .ffill()
        .fillna(0.0)
    )
    pivot_vol = (
        df.pivot_table(
            index="timestamp",
            columns="coin_symbol",
            values="max_volatility" if "max_volatility" in df.columns else value_col,
        )
        .sort_index()
        .ffill()
        .fillna(0.0)
    )

    symbols: List[str] = list(pivot_ret.columns)
    corr_matrix = pivot_ret.corr(method="pearson").round(4).fillna(0.0)

    if base_symbol not in symbols and symbols:
        base_symbol = symbols[0]
    if target_symbol not in symbols and len(symbols) > 1:
        target_symbol = [s for s in symbols if s != base_symbol][0]
    elif target_symbol not in symbols:
        target_symbol = base_symbol

    # Rolling correlation antara base_symbol dan target_symbol
    rolling_series = (
        pivot_ret[base_symbol]
        .rolling(window=rolling_window, min_periods=5)
        .corr(pivot_ret[target_symbol])
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
    )
    rolling_records = [
        {"timestamp": ts.isoformat(), "rolling_corr": round(float(val), 4)}
        for ts, val in rolling_series.tail(250).items()
    ]

    # Lag correlation: apakah pergerakan base_symbol pada t mendahului target_symbol pada t+lag?
    lag_records = []
    s_base = pivot_ret[base_symbol]
    s_targ = pivot_ret[target_symbol]
    for lag in range(-max_lag, max_lag + 1):
        c_val = s_base.corr(s_targ.shift(-lag))
        lag_records.append(
            {
                "lag": lag,
                "correlation": round(float(0.0 if pd.isna(c_val) else c_val), 4),
                "interpretation": (
                    f"{base_symbol} mendahului {target_symbol} {lag} periode"
                    if lag > 0
                    else (
                        f"{target_symbol} mendahului {base_symbol} {abs(lag)} periode"
                        if lag < 0
                        else "Simultan (Lag 0)"
                    )
                ),
            }
        )

    # Market-Wide Risk Score (0 - 100) berdasarkan persentil volatilitas gabungan seluruh aset
    z_vols = (pivot_vol - pivot_vol.mean()) / pivot_vol.std().replace(0, 1.0)
    composite_z = z_vols.mean(axis=1)
    market_risk_series = np.clip(50.0 + composite_z * 20.0, 0.0, 100.0)
    current_market_risk = round(float(market_risk_series.iloc[-1]), 2) if len(market_risk_series) else 0.0

    market_regime = (
        "DANGER"
        if current_market_risk >= 70.0
        else ("WARNING" if current_market_risk >= 45.0 else "SAFE")
    )

    return {
        "symbols": symbols,
        "base_symbol": base_symbol,
        "target_symbol": target_symbol,
        "pearson_matrix": corr_matrix.to_dict(),
        "rolling_correlation": rolling_records,
        "lag_correlation": lag_records,
        "market_wide_risk_score": current_market_risk,
        "market_wide_regime": market_regime,
        "market_risk_timeline": [
            {"timestamp": ts.isoformat(), "risk_score": round(float(val), 2)}
            for ts, val in market_risk_series.tail(200).items()
        ],
    }
