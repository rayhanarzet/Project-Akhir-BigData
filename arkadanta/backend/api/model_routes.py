"""[ORANG 2] Endpoint Machine Learning Training & Evaluasi Model (Bab 3.3 & 5.5-5.8)."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Query

from backend.ml.model_predictor import get_latest_metrics
from backend.ml.model_trainer import train_dynamic_models, training_lock
from backend.schemas import DynamicConfig

router = APIRouter(tags=["Machine Learning & Evaluation (Orang 2)"])


@router.post("/api/ml/train")
def train_model_endpoint(config: DynamicConfig):
    """Melatih Gaussian Mixture Risk Labeler (SAFE/WARNING/DANGER) dan HistGradientBoosting T+1 dengan validasi temporal."""
    # Tolak training paralel daripada mengantre; mencegah request berulang menghabiskan CPU.
    if not training_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Training lain sedang berjalan. Coba lagi setelah selesai.")
    try:
        return train_dynamic_models(config)
    except ValueError as exc:
        # Kesalahan data/konfigurasi; bug internal tetap 500 agar tidak tersamar sebagai input salah.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        training_lock.release()


@router.get("/api/models/metrics")
def get_model_metrics_endpoint(
    symbol: str | None = Query(None, pattern=r"^[A-Za-z0-9]{2,30}$"),
    timeframe: Literal["5m", "15m", "1h", "4h", "1d", "1w"] | None = None,
):
    """Mengambil metrik evaluasi model aktif (Silhouette, Centroid, Accuracy, Precision, Recall, F1, MAE, RMSE)."""
    return get_latest_metrics(symbol, timeframe)
