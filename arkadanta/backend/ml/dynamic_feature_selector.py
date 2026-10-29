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
    unknown = [c for c in candidates if c not in AVAILABLE_FEATURES]
    if unknown:
        raise ValueError(f"Fitur tidak dikenal: {unknown}")
    # Jangan diam-diam mengganti fitur pilihan pengguna atau mengisi kolom sumber yang tidak ada dengan nol.
    unavailable = [c for c in candidates if c not in df.columns or df[c].isna().any()]
    if unavailable:
        raise ValueError(
            f"Fitur {unavailable} tidak tersedia lengkap dari data sumber "
            "(mis. CSV tanpa kolom taker/quote/trades). Hapus fitur tersebut atau gunakan data Binance lengkap."
        )
    valid_cols = list(candidates)

    clean_df = df.copy()
    for col in valid_cols:
        values = pd.to_numeric(clean_df[col], errors="coerce")
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError(f"Fitur {col} mengandung NaN/Inf atau nilai nonnumerik; periksa data sumber.")
        clean_df[col] = values

    return clean_df, valid_cols
