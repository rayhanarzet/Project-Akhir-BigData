"""[ORANG 2] Dynamic Anomaly Detection per aset & timeframe (Bab 5.3)."""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler


def detect_anomalies(
    df: pd.DataFrame,
    method: str = "adaptive_quantile",
    quantile: float = 0.95,
    z_threshold: float = 2.5,
    iqr_multiplier: float = 1.5,
    rolling_window: int = 20,
    feature_cols: List[str] | None = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Mendeteksi anomali dengan metode Rolling Z-Score, IQR, Adaptive Quantile, atau Gaussian Mixture."""
    if df.empty:
        return df, {"total_anomalies": 0, "anomaly_rate_pct": 0.0, "threshold_info": {}}

    data = df.copy()
    target_col = "max_volatility" if "max_volatility" in data.columns else "hl_range"
    # GMM di-fit pada seluruh rentang: analisis rezim retrospektif, bukan alarm real-time.
    threshold_info: Dict[str, Any] = {"method": method, "per_symbol_threshold": {}, "causal": method != "gmm"}

    data["is_anomaly"] = False
    data["anomaly_score"] = 0.0
    data["anomaly_reason"] = "NORMAL"

    for sym, grp in data.groupby("coin_symbol"):
        idx = grp.index
        s = grp[target_col].astype(float)

        # Ambang rolling/IQR/quantile hanya memakai data sampai t-1 (shift) agar label lama
        # tidak berubah saat data baru masuk. Candle sebelum riwayat cukup tidak dinilai.
        if method == "rolling_zscore":
            past = s.shift(1).rolling(window=rolling_window, min_periods=3)
            r_mean, r_std = past.mean(), past.std().replace(0, 1e-8)
            z_scores = ((s - r_mean) / np.maximum(r_std, 1e-8)).fillna(0.0)
            is_anom = (z_scores.abs() >= z_threshold) | (grp.get("volume_zscore", 0).abs() >= z_threshold + 0.5)
            data.loc[idx, "anomaly_score"] = z_scores.round(4)
            data.loc[idx, "is_anomaly"] = is_anom
            threshold_info["per_symbol_threshold"][sym] = float(z_threshold)

        elif method == "iqr":
            past = s.shift(1).expanding(min_periods=rolling_window)
            q1, q3 = past.quantile(0.25), past.quantile(0.75)
            iqr = np.maximum(q3 - q1, 1e-8)
            upper_bound = q3 + iqr_multiplier * iqr
            scores = ((s - upper_bound) / iqr).fillna(0.0)
            is_anom = (s > upper_bound).fillna(False)
            data.loc[idx, "anomaly_score"] = scores.round(4)
            data.loc[idx, "is_anomaly"] = is_anom
            threshold_info["per_symbol_threshold"][sym] = round(float(upper_bound.iloc[-1]), 6) if upper_bound.notna().any() else None

        elif method == "gmm":
            cols = [
                c
                for c in (feature_cols or ["max_volatility", "spike_ratio", "volume_zscore"])
                if c in grp.columns and grp[c].notna().all()
            ]
            if not cols:
                cols = [target_col]
            X = StandardScaler().fit_transform(grp[cols].fillna(0.0).values)
            if len(X) < 3:
                raise ValueError("Deteksi anomali GMM membutuhkan minimal tiga candle.")
            mixture = GaussianMixture(n_components=3, random_state=42, n_init=3,
                                      init_params="random_from_data", reg_covar=1e-4, max_iter=200)
            mixture.fit(X)
            if not mixture.converged_:
                raise ValueError("GMM deteksi anomali belum konvergen.")
            scores = -mixture.score_samples(X)
            dist_thresh = float(np.quantile(scores, quantile))
            is_anom = scores >= dist_thresh
            data.loc[idx, "anomaly_score"] = np.round(scores, 4)
            data.loc[idx, "is_anomaly"] = is_anom
            threshold_info["per_symbol_threshold"][sym] = round(dist_thresh, 4)

        else:  # adaptive_quantile (default)
            thresh = s.shift(1).expanding(min_periods=rolling_window).quantile(quantile)
            scores = (s / np.maximum(thresh, 1e-8)).fillna(0.0)
            is_anom = (s >= thresh).fillna(False)
            data.loc[idx, "anomaly_score"] = scores.round(4)
            data.loc[idx, "is_anomaly"] = is_anom
            threshold_info["per_symbol_threshold"][sym] = round(float(thresh.iloc[-1]), 6) if thresh.notna().any() else None

        anom_idx = idx[data.loc[idx, "is_anomaly"]]
        data.loc[anom_idx, "anomaly_reason"] = (
            f"Lonjakan {target_col} ({method})"
        )

    total_anom = int(data["is_anomaly"].sum())
    rate_pct = round((total_anom / max(len(data), 1)) * 100.0, 2)

    summary = {
        "method": method,
        "total_observations": len(data),
        "total_anomalies": total_anom,
        "anomaly_rate_pct": rate_pct,
        "threshold_info": threshold_info,
    }
    return data, summary
