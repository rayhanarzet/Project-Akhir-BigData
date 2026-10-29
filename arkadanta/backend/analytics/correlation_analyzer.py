"""[ORANG 2] Analisis Korelasi Lintas Aset (Pearson, Rolling, Lag Correlation, dan Market-Wide Risk Score - Bab 5.4)."""

from typing import Any, Dict, List
import numpy as np
import pandas as pd
from backend.analytics.timeframe_aggregator import TIMEFRAME_DURATION, TIMEFRAME_PANDAS_MAP


def _number(value):
    return round(float(value), 4) if pd.notna(value) and np.isfinite(value) else None


def analyze_cross_asset_correlation(
    df_multi: pd.DataFrame,
    base_symbol: str = "BTCUSDT",
    target_symbol: str = "ETHUSDT",
    value_col: str = "log_return",
    rolling_window: int = 30,
    max_lag: int = 6,
    timeframe: str = "1h",
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
        .asfreq(TIMEFRAME_PANDAS_MAP[timeframe])
    )
    pivot_vol = (
        df.pivot_table(
            index="timestamp",
            columns="coin_symbol",
            values="max_volatility" if "max_volatility" in df.columns else value_col,
        )
        .sort_index()
        .reindex(pivot_ret.index)
    )

    symbols: List[str] = list(pivot_ret.columns)
    corr_matrix = pivot_ret.corr(method="pearson", min_periods=5).round(4)
    observations = pivot_ret.notna().astype(int)
    pair_counts = observations.T.dot(observations)

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
        .replace([np.inf, -np.inf], np.nan)
    )
    rolling_records = [
        {"timestamp": ts.isoformat(), "rolling_corr": _number(val)}
        for ts, val in rolling_series.tail(250).items()
    ]

    # Lag correlation: apakah pergerakan base_symbol pada t mendahului target_symbol pada t+lag?
    lag_records = []
    s_base = pivot_ret[base_symbol]
    s_targ = pivot_ret[target_symbol]
    for lag in range(-max_lag, max_lag + 1):
        paired_samples = int((s_base.notna() & s_targ.shift(-lag).notna()).sum())
        c_val = s_base.corr(s_targ.shift(-lag)) if paired_samples >= 5 else np.nan
        lag_records.append(
            {
                "lag": lag,
                "correlation": _number(c_val) if paired_samples >= 5 else None,
                "paired_samples": paired_samples,
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
    past = pivot_vol.shift(1).rolling(rolling_window, min_periods=5)
    z_vols = (pivot_vol - past.mean()) / past.std().replace(0, np.nan)
    composite_z = z_vols.mean(axis=1, skipna=False)
    market_risk_series = np.clip(50.0 + composite_z * 20.0, 0.0, 100.0)
    latest = pivot_ret.index[-1]
    fresh = pd.Timestamp.now(tz="UTC") < latest + TIMEFRAME_DURATION[timeframe] * 2
    current_market_risk = _number(market_risk_series.iloc[-1]) if fresh else None

    market_regime = (
        None if current_market_risk is None else "DANGER"
        if current_market_risk >= 70.0
        else ("WARNING" if current_market_risk >= 45.0 else "SAFE")
    )

    return {
        "symbols": symbols,
        "base_symbol": base_symbol,
        "target_symbol": target_symbol,
        "pearson_matrix": {col: {row: _number(value) for row, value in values.items()} for col, values in corr_matrix.to_dict().items()},
        "paired_observations": pair_counts.to_dict(),
        "observation_policy": "Hanya pasangan timestamp nyata; nilai hilang tidak diisi. Skor pasar memakai statistik periode lampau.",
        "asset_freshness": {sym: {"last_timestamp": str(pivot_vol[sym].last_valid_index()),
                                  "latest_observed": bool(pd.notna(pivot_vol[sym].iloc[-1]))} for sym in symbols},
        "market_timestamp": latest.isoformat(),
        "rolling_correlation": rolling_records,
        "lag_correlation": lag_records,
        "market_wide_risk_score": current_market_risk,
        "market_wide_regime": market_regime,
        "market_risk_timeline": [
            {"timestamp": ts.isoformat(), "risk_score": _number(val)}
            for ts, val in market_risk_series.tail(200).items()
        ],
    }


def compute_historical_factor_attribution(
    df: pd.DataFrame,
    feature_cols: List[str] | None = None,
    max_lag: int = 5,
    timeframe: str = "1h",
) -> List[Dict[str, Any]]:
    """Menganalisis faktor historis pada periode/hari lampau (T-1 s.d. T-max_lag) yang paling mempengaruhi volatilitas hari ini (T)."""
    if df.empty or "max_volatility" not in df.columns:
        return []

    candidate_cols = [
        c
        for c in (
            feature_cols
            or [
                "max_volatility",
                "rolling_volatility",
                "spike_ratio",
                "volume_zscore",
                "bb_width",
                "rsi_14",
                "buy_sell_pressure_ratio",
                "hl_range",
            ]
        )
        if c in df.columns
    ]

    df = df.sort_values("timestamp").set_index(pd.to_datetime(df["timestamp"], utc=True))
    target_today = df["max_volatility"].astype(float)
    records: List[Dict[str, Any]] = []

    for col in candidate_cols:
        s_col = df[col].astype(float)
        best_lag = 1
        best_corr = 0.0
        lag_profile: Dict[str, float] = {}

        for lag in range(1, max_lag + 1):
            past = s_col.reindex(s_col.index - TIMEFRAME_DURATION[timeframe] * lag)
            past.index = s_col.index
            c_val = target_today.corr(past)
            c_clean = 0.0 if pd.isna(c_val) else float(c_val)
            lag_profile[f"T-{lag}"] = round(c_clean, 4)
            if abs(c_clean) >= abs(best_corr):
                best_corr = c_clean
                best_lag = lag

        records.append(
            {
                "feature": col,
                "dominant_lag": f"T-{best_lag}",
                "lag_periods": best_lag,
                "correlation_to_today": round(best_corr, 4),
                "abs_impact_score": round(abs(best_corr) * 100.0, 2),
                "lag_profile": lag_profile,
                "bi_insight": (
                    f"Perubahan {col} pada {best_lag} periode lalu (T-{best_lag}) berkorelasi "
                    f"{'positif' if best_corr >= 0 else 'negatif'} ({best_corr:+.3f}) terhadap lonjakan risiko saat ini (T)."
                ),
            }
        )

    records.sort(key=lambda item: item["abs_impact_score"], reverse=True)
    return records
