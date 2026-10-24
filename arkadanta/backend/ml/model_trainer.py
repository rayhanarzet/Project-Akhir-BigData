"""GMM risk labels dan HistGradientBoosting T+horizon dengan pemisahan temporal."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from threadpoolctl import threadpool_limits

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.config import MODELS_DIR
from backend.ml.dynamic_feature_selector import select_and_prepare_features
from backend.ml.model_evaluator import evaluate_classification, evaluate_regression
from backend.ml.risk_labeler import DynamicRiskLabeler
from backend.schemas import DynamicConfig
from data.storage import load_clean_ohlcv

MODEL_VERSION = "gmm_hgb_v1"
training_lock = threading.RLock()


def model_directory() -> Path:
    return MODELS_DIR / MODEL_VERSION


def bundle_path(symbol: str, timeframe: str) -> Path:
    return model_directory() / f"model_{symbol.upper()}_{timeframe}.joblib"


def metrics_path(symbol: str, timeframe: str) -> Path:
    return model_directory() / f"metrics_{symbol.upper()}_{timeframe}.json"


def _save_bundle(path: Path, bundle: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        joblib.dump(bundle, temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _save_metrics(path: Path, metrics: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def train_dynamic_models(config: DynamicConfig) -> dict[str, Any]:
    with training_lock:
        if config.use_spark:
            from spark_jobs.batch_analytics import run_batch_job
            return run_batch_job(config)
        frame = aggregate_timeframe(load_clean_ohlcv(config.symbol.upper()), timeframe=config.timeframe,
                                    start_date=config.start_date, end_date=config.end_date)
        features = compute_dynamic_features(frame, ma_period=config.ma_period,
                                            rsi_period=config.rsi_period, rolling_window=config.rolling_window)
        return train_from_features(features, config, "Pandas + Scikit-Learn GMM/HGB")


def train_from_features(frame: pd.DataFrame, config: DynamicConfig, execution_engine: str) -> dict[str, Any]:
    """Trainer bersama: Spark mengolah fitur; GMM/HGB selalu dilatih di driver lokal."""
    with training_lock, threadpool_limits(limits=2):
        data, feature_cols = select_and_prepare_features(frame, config.features)
        data = data.sort_values("timestamp").reset_index(drop=True)
        horizon = config.target_horizon
        if len(data) < 30 + horizon:
            raise ValueError(f"Data ({len(data)} candle) terlalu sedikit; minimal {30 + horizon} untuk horizon {horizon}.")
        # Terdapat embargo sepanjang horizon: target latih terakhir mendahului fitur uji pertama.
        split = int((len(data) - horizon) * config.train_ratio)
        if split - horizon < max(10, config.gmm_components * 2) or len(data) - horizon - split < 5:
            raise ValueError("Pembagian temporal menghasilkan data latih/uji terlalu sedikit. Tambah data atau ubah train_ratio/horizon.")
        labeler = DynamicRiskLabeler(n_clusters=config.gmm_components)
        labeler.fit(data.iloc[:split], feature_cols)
        component_ids, labels = labeler.transform(data)
        data["component_id"] = component_ids
        data["current_risk_label"] = labels
        data["target_risk"] = data["current_risk_label"].shift(-horizon)
        data["target_volatility"] = data["max_volatility"].shift(-horizon)
        train = data.iloc[:split - horizon].copy()
        test = data.iloc[split:len(data) - horizon].copy()
        if train["target_risk"].nunique() < 2:
            raise ValueError("Data latih hanya memiliki satu kelas risiko. Tambah rentang data atau ubah fitur/komponen GMM.")
        x_train = train[feature_cols].to_numpy(dtype=float)
        x_test = test[feature_cols].to_numpy(dtype=float)
        parameters = dict(max_iter=config.gb_max_iter, max_depth=config.gb_max_depth,
                          learning_rate=config.gb_learning_rate, min_samples_leaf=10,
                          early_stopping=False, random_state=42)
        classifier = HistGradientBoostingClassifier(class_weight="balanced", **parameters)
        regressor = HistGradientBoostingRegressor(**parameters)
        classifier.fit(x_train, train["target_risk"].tolist())
        regressor.fit(x_train, train["target_volatility"].to_numpy(dtype=float))
        predicted_class = classifier.predict(x_test).tolist()
        predicted_volatility = regressor.predict(x_test)
        # Interpretasi pada holdout; tidak digunakan untuk memilih fitur atau melatih ulang model.
        sample = np.linspace(0, len(test) - 1, min(len(test), 500), dtype=int)
        importance = permutation_importance(classifier, x_test[sample], test["target_risk"].iloc[sample].tolist(),
                                           scoring="f1_macro", n_repeats=3, random_state=42, n_jobs=1)
        importances = sorted([
            {"feature": name, "importance": round(float(mean), 6), "std": round(float(std), 6)}
            for name, mean, std in zip(feature_cols, importance.importances_mean, importance.importances_std)
        ], key=lambda record: record["importance"], reverse=True)
        counts = data["current_risk_label"].value_counts()
        metadata = {
            "model_version": MODEL_VERSION, "trained_at": datetime.now(timezone.utc).isoformat(),
            "execution_engine": execution_engine,
            "algorithms": {"labeler": "GaussianMixture", "classifier": "HistGradientBoostingClassifier", "regressor": "HistGradientBoostingRegressor"},
            "symbol": config.symbol.upper(), "timeframe": config.timeframe, "target_horizon": horizon,
            "features": feature_cols, "gmm_components": config.gmm_components, "train_ratio": config.train_ratio,
            "gb_max_iter": config.gb_max_iter, "gb_max_depth": config.gb_max_depth, "gb_learning_rate": config.gb_learning_rate,
            "temporal_split": {
                "total_samples": len(data) - horizon, "train_samples": len(train), "test_samples": len(test),
                "embargo_samples": horizon, "train_start": str(train["timestamp"].iloc[0]),
                "train_end": str(train["timestamp"].iloc[-1]), "train_target_end": str(data["timestamp"].iloc[split - 1]),
                "labeler_fit_end": str(data["timestamp"].iloc[split - 1]),
                "test_start": str(test["timestamp"].iloc[0]), "test_end": str(test["timestamp"].iloc[-1]),
            },
            "gmm_metrics": {
                "silhouette_score": round(labeler.silhouette, 4) if labeler.silhouette is not None else None,
                "bic": labeler.bic, "aic": labeler.aic, "converged": bool(labeler.gmm.converged_),
                "cluster_to_label": {str(key): value for key, value in labeler.cluster_to_label.items()},
                "centroids": labeler.centroid_table,
                "regime_distribution": {label: int(counts.get(label, 0)) for label in ("SAFE", "WARNING", "DANGER")},
            },
            "classification_metrics": evaluate_classification(test["target_risk"].tolist(), predicted_class),
            "regression_metrics": evaluate_regression(test["target_volatility"].to_numpy(dtype=float), predicted_volatility),
            "feature_importance_method": "permutation_f1_macro_holdout", "feature_importances": importances,
            "test_predictions_preview": [{
                "timestamp": str(row["timestamp"]), "close": round(float(row["close"]), 4),
                "actual_risk_t1": row["target_risk"], "predicted_risk_t1": predicted,
                "actual_vol_t1": round(float(row["target_volatility"]), 6), "predicted_vol_t1": round(float(volatility), 6),
            } for (_, row), predicted, volatility in list(zip(test.iterrows(), predicted_class, predicted_volatility))[-60:]],
        }
        bundle = {"model_version": MODEL_VERSION, "labeler": labeler, "classifier": classifier,
                  "regressor": regressor, "config": config.model_dump(), "meta": metadata}
        model_directory().mkdir(parents=True, exist_ok=True)
        _save_bundle(bundle_path(config.symbol, config.timeframe), bundle)
        _save_metrics(metrics_path(config.symbol, config.timeframe), metadata)
        _save_metrics(model_directory() / "latest_metrics.json", metadata)
        return metadata