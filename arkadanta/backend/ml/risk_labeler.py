"""[ORANG 2] Clustering Risiko Gaussian Mixture & Pelabelan Centroid Dinamis SAFE / WARNING / DANGER (Bab 5.5)."""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

RISK_LABELS_3 = ["SAFE", "WARNING", "DANGER"]


class DynamicRiskLabeler:
    """Melatih StandardScaler + Gaussian Mixture dan mengurutkan centroid berdasarkan skor risiko gabungan."""

    def __init__(self, n_clusters: int = 3, random_state: int = 42):
        self.n_clusters = max(3, n_clusters)
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.gmm = GaussianMixture(
            n_components=self.n_clusters, random_state=self.random_state,
            covariance_type="full", reg_covar=1e-4, n_init=5,
            init_params="random_from_data", max_iter=200,
        )
        self.feature_cols: List[str] = []
        self.cluster_to_label: Dict[int, str] = {}
        self.cluster_to_rank: Dict[int, int] = {}
        self.centroid_table: List[Dict[str, Any]] = []
        self.silhouette: float | None = None
        self.bic: float = 0.0
        self.aic: float = 0.0

    def _compute_centroid_risk_score(
        self, centroid_z: np.ndarray, feature_cols: List[str]
    ) -> float:
        """Menghitung skor risiko gabungan dari fitur volatilitas, spike ratio, dan volume terstandarisasi."""
        weights = []
        for idx, col in enumerate(feature_cols):
            if col in ("max_volatility", "avg_volatility", "rolling_volatility", "hl_range", "bb_width"):
                weights.append((idx, 1.5))
            elif col in ("spike_ratio", "volume_zscore"):
                weights.append((idx, 1.2))
            elif col == "rsi_14":
                # Deviasi RSI dari 50 menandakan kondisi ekstrem overbought/oversold
                weights.append((idx, 0.6))
            else:
                weights.append((idx, 0.8))

        score = 0.0
        total_w = 0.0
        for idx, w in weights:
            col_name = feature_cols[idx]
            val = (
                abs(float(centroid_z[idx]))
                if col_name in ("rsi_14", "log_return", "periodic_return", "co_change")
                else float(centroid_z[idx])
            )
            score += val * w
            total_w += w
        return score / max(total_w, 1e-8)

    def fit(self, df_train: pd.DataFrame, feature_cols: List[str]) -> "DynamicRiskLabeler":
        self.feature_cols = list(feature_cols)
        X_train = df_train[self.feature_cols].values.astype(float)
        X_scaled = self.scaler.fit_transform(X_train)
        if len(X_scaled) < self.n_clusters:
            raise ValueError("Data pelatihan lebih sedikit dari jumlah komponen GMM.")
        cluster_ids = self.gmm.fit_predict(X_scaled)
        if not self.gmm.converged_:
            raise ValueError("GMM belum konvergen. Kurangi jumlah komponen atau ubah fitur/data.")
        self.bic = float(self.gmm.bic(X_scaled))
        self.aic = float(self.gmm.aic(X_scaled))

        # Silhouette score (gunakan sampel maks 2000 baris agar cepat)
        sample = np.random.default_rng(self.random_state).choice(len(X_scaled), min(len(X_scaled), 1500), replace=False)
        if 1 < len(np.unique(cluster_ids[sample])) < len(sample):
            self.silhouette = float(silhouette_score(X_scaled[sample], cluster_ids[sample]))

        centroids_z = self.gmm.means_
        centroids_orig = self.scaler.inverse_transform(centroids_z)

        scored_clusters = []
        for cid in range(self.n_clusters):
            r_score = self._compute_centroid_risk_score(
                centroids_z[cid], self.feature_cols
            )
            scored_clusters.append((cid, r_score))

        # Urutkan dari skor risiko terendah ke tertinggi (SAFE -> WARNING -> DANGER)
        scored_clusters.sort(key=lambda item: item[1])

        self.cluster_to_label = {}
        self.cluster_to_rank = {}
        self.centroid_table = []

        for rank_idx, (cid, r_score) in enumerate(scored_clusters):
            if self.n_clusters == 3:
                label = RISK_LABELS_3[rank_idx]
            else:
                if rank_idx == 0:
                    label = "SAFE"
                elif rank_idx == self.n_clusters - 1:
                    label = "DANGER"
                else:
                    label = "WARNING"

            self.cluster_to_label[int(cid)] = label
            self.cluster_to_rank[int(cid)] = rank_idx
            count_in_train = int(np.sum(cluster_ids == cid))

            row_info: Dict[str, Any] = {
                "cluster_id": int(cid),
                "risk_rank": rank_idx + 1,
                "assigned_risk_label": label,
                "composite_risk_score": round(float(r_score), 4),
                "train_sample_count": count_in_train,
                "mixture_weight": round(float(self.gmm.weights_[cid]), 6),
            }
            for f_idx, f_name in enumerate(self.feature_cols):
                row_info[f"centroid_{f_name}"] = round(
                    float(centroids_orig[cid, f_idx]), 6
                )
                row_info[f"z_{f_name}"] = round(float(centroids_z[cid, f_idx]), 4)

            self.centroid_table.append(row_info)

        return self

    def transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
        """Memetakan baris data ke cluster_id dan label risiko (SAFE/WARNING/DANGER)."""
        X = df[self.feature_cols].values.astype(float)
        X_scaled = self.scaler.transform(X)
        cids = self.gmm.predict(X_scaled)
        labels = [self.cluster_to_label[int(c)] for c in cids]
        return cids, labels
