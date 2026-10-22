"""[ORANG 2] Pemilihan fitur dinamis sesuai konfigurasi pengguna (Bab 5.2 & 5.7)."""

from typing import List, Tuple
import numpy as np
import pandas as pd

from backend.config import AVAILABLE_FEATURES, DEFAULT_FEATURES


def select_and_prepare_features(
    df: pd.DataFrame, requested_features: List[str] | None = None
) -> Tuple[pd.DataFrame, List[str]]:
    """Memvalidasi daftar fitur pilihan pengguna dan menyiapkan matriks fitur bersih tanpa nilai NaN/Inf."""
    candidates = requested_features or DEFAULT_FEATURES
    valid_cols = [c for c in candidates if c in df.columns]

    if not valid_cols:
        valid_cols = [c for c in DEFAULT_FEATURES if c in df.columns]
    if not valid_cols:
        valid_cols = [c for c in AVAILABLE_FEATURES if c in df.columns][:4]

    clean_df = df.copy()
    for col in valid_cols:
        clean_df[col] = (
            pd.to_numeric(clean_df[col], errors="coerce")
            .replace([np.inf, -np.inf], 0.0)
            .fillna(0.0)
        )

    return clean_df, valid_cols
