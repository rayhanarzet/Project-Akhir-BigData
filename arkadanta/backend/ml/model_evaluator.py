"""[ORANG 2] Evaluasi model Gaussian Mixture, HistGradientBoosting Classifier, dan HistGradientBoosting Regressor (Bab 5.8)."""

from typing import Any, Dict, List
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)

CLASS_ORDER = ["SAFE", "WARNING", "DANGER"]


def evaluate_classification(
    y_true: List[str], y_pred: List[str]
) -> Dict[str, Any]:
    """Menghitung Accuracy, Precision, Recall, F1-Score makro & per kelas, serta Confusion Matrix."""
    present_labels = [lbl for lbl in CLASS_ORDER if lbl in set(y_true) | set(y_pred)]
    if not present_labels:
        present_labels = CLASS_ORDER

    acc = float(accuracy_score(y_true, y_pred))
    prec_macro = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    rec_macro = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1_macro = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    prec_arr, rec_arr, f1_arr, sup_arr = precision_recall_fscore_support(
        y_true, y_pred, labels=CLASS_ORDER, zero_division=0
    )

    per_class = {}
    for idx, cls_name in enumerate(CLASS_ORDER):
        per_class[cls_name] = {
            "precision": round(float(prec_arr[idx]), 4),
            "recall": round(float(rec_arr[idx]), 4),
            "f1_score": round(float(f1_arr[idx]), 4),
            "support": int(sup_arr[idx]),
        }

    cm = confusion_matrix(y_true, y_pred, labels=CLASS_ORDER).tolist()

    return {
        "accuracy": round(acc, 4),
        "precision_macro": round(prec_macro, 4),
        "recall_macro": round(rec_macro, 4),
        "f1_macro": round(f1_macro, 4),
        "per_class": per_class,
        "labels": CLASS_ORDER,
        "confusion_matrix": cm,
    }


def evaluate_regression(
    y_true: np.ndarray, y_pred: np.ndarray
) -> Dict[str, float]:
    """Menghitung MAE dan RMSE untuk prediksi volatilitas T+1."""
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
    }
