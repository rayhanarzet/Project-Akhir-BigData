"""[ORANG 2] Endpoint Machine Learning Training & Evaluasi Model (Bab 3.3 & 5.5-5.8)."""

from fastapi import APIRouter, HTTPException

from backend.ml.model_predictor import get_latest_metrics
from backend.ml.model_trainer import train_dynamic_models
from backend.schemas import DynamicConfig

router = APIRouter(tags=["Machine Learning & Evaluation (Orang 2)"])


@router.post("/api/ml/train")
def train_model_endpoint(config: DynamicConfig):
    """Melatih K-Means Risk Labeler (SAFE/WARNING/DANGER) dan Random Forest T+1 dengan validasi temporal."""
    try:
        metrics = train_dynamic_models(config)
        return metrics
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/models/metrics")
def get_model_metrics_endpoint():
    """Mengambil metrik evaluasi model aktif (Silhouette, Centroid, Accuracy, Precision, Recall, F1, MAE, RMSE)."""
    return get_latest_metrics()
