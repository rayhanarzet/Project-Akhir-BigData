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
from sklearn.base import clone
from sklearn.metrics import precision_recall_fscore_support, f1_score
from threadpoolctl import threadpool_limits

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe, TIMEFRAME_DURATION
from backend.analytics.research_window import filter_research_window
from backend.config import MODELS_DIR
from backend.ml.dynamic_feature_selector import select_and_prepare_features
from backend.ml.model_evaluator import evaluate_classification, evaluate_regression
from backend.ml.risk_labeler import DynamicRiskLabeler
from backend.schemas import DynamicConfig
from data.storage import load_clean_ohlcv

MODEL_VERSION = "gmm_hgb_v3"
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
        research_frame = filter_research_window(frame, config.start_date, config.end_date)
        data, feature_cols = select_and_prepare_features(research_frame, config.features)
        data = data.sort_values("timestamp").reset_index(drop=True)
        if data["timestamp"].duplicated().any():
            raise ValueError("Timestamp fitur training duplikat; periksa versi/deduplikasi data sumber.")
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
        data["target_timestamp"] = data["timestamp"].shift(-horizon)
        valid_target = data["target_timestamp"].eq(data["timestamp"] + TIMEFRAME_DURATION[config.timeframe] * horizon)
        train = data.iloc[:split - horizon].loc[valid_target].copy()
        test = data.iloc[split:len(data) - horizon].loc[valid_target].copy()
        if len(train) < 10 or len(test) < 5:
            raise ValueError("Terlalu sedikit pasangan waktu yang utuh setelah candle berlubang dibuang. Jalankan backfill atau tambah histori.")
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
        # Metrik di atas dari model holdout. Model yang disimpan untuk live dilatih ulang pada semua
        # baris bertarget (definisi label GMM tetap) agar periode uji terbaru ikut dipelajari.
        labeled = data.loc[valid_target]
        holdout_classifier, holdout_regressor = classifier, regressor
        classifier = HistGradientBoostingClassifier(class_weight="balanced", **parameters).fit(
            labeled[feature_cols].to_numpy(dtype=float), labeled["target_risk"].tolist())
        regressor = HistGradientBoostingRegressor(**parameters).fit(
            labeled[feature_cols].to_numpy(dtype=float), labeled["target_volatility"].to_numpy(dtype=float))
        counts = data["current_risk_label"].value_counts()
        metadata = {
            "model_version": MODEL_VERSION, "trained_at": datetime.now(timezone.utc).isoformat(),
            "execution_engine": execution_engine,
            "algorithms": {"labeler": "GaussianMixture", "classifier": "HistGradientBoostingClassifier", "regressor": "HistGradientBoostingRegressor"},
            "symbol": config.symbol.upper(), "timeframe": config.timeframe, "target_horizon": horizon,
            "features": feature_cols, "gmm_components": config.gmm_components, "train_ratio": config.train_ratio,
            "research_window": {"max_days": 365, "data_start": str(data["timestamp"].min()),
                                "data_end": str(data["timestamp"].max()), "excluded_rows": len(frame) - len(data)},
            "risk_label_definition": "Kategori gejolak relatif hasil GMM; SAFE bukan jaminan aman atau bebas kerugian.",
            "volatility_event_validation": _volatility_event_metrics(train, test, predicted_volatility),
            "walk_forward_volatility": _walk_forward_volatility(data, valid_target, feature_cols, regressor, horizon, split, test, predicted_volatility),
            "gb_max_iter": config.gb_max_iter, "gb_max_depth": config.gb_max_depth, "gb_learning_rate": config.gb_learning_rate,
            "temporal_split": {
                "total_samples": len(labeled), "train_samples": len(train), "test_samples": len(test),
                "embargo_samples": horizon, "train_start": str(train["timestamp"].iloc[0]),
                "train_end": str(train["timestamp"].iloc[-1]), "train_target_end": str(train["target_timestamp"].max()),
                "labeler_fit_end": str(data["timestamp"].iloc[split - 1]),
                "test_start": str(test["timestamp"].iloc[0]), "test_end": str(test["timestamp"].iloc[-1]),
                "deployed_model_fit_samples": len(labeled),
                "gap_targets_removed": int((~valid_target.iloc[:len(data) - horizon]).sum()),
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
            # Pembanding naif pada holdout yang sama: model berguna hanya jika mengalahkan angka ini.
            "baseline_metrics": {
                "majority_accuracy": round(float((test["target_risk"] == train["target_risk"].mode()[0]).mean()), 4),
                "persistence_accuracy": round(float((test["target_risk"] == test["current_risk_label"]).mean()), 4),
                "persistence_rmse": round(float(np.sqrt(np.mean(
                    (test["target_volatility"] - test["max_volatility"]).to_numpy(dtype=float) ** 2))), 6),
            },
            "feature_importance_method": "permutation_f1_macro_holdout", "feature_importances": importances,
            "test_predictions_preview": [{
                "timestamp": str(row["timestamp"]), "close": round(float(row["close"]), 4),
                "target_timestamp": str(row["target_timestamp"]),
                "actual_risk_t1": row["target_risk"], "predicted_risk_t1": predicted,
                "actual_vol_t1": round(float(row["target_volatility"]), 6), "predicted_vol_t1": round(float(volatility), 6),
            } for (_, row), predicted, volatility in list(zip(test.iterrows(), predicted_class, predicted_volatility))[-60:]],
        }
        bundle = {"model_version": MODEL_VERSION, "labeler": labeler, "classifier": classifier,
                  "regressor": regressor, "holdout_classifier": holdout_classifier,
                  "holdout_regressor": holdout_regressor, "config": config.model_dump(), "meta": metadata}
        model_directory().mkdir(parents=True, exist_ok=True)
        _save_bundle(bundle_path(config.symbol, config.timeframe), bundle)
        _save_metrics(metrics_path(config.symbol, config.timeframe), metadata)
        _save_metrics(model_directory() / "latest_metrics.json", metadata)
        return metadata


def _volatility_event_metrics(train, test, predicted):
    """Kejadian terukur: range candle mendatang melewati persentil 95 data latih, tanpa label GMM."""
    threshold = float(train["target_volatility"].quantile(0.95))
    actual = test["target_volatility"].to_numpy(float) > threshold
    estimated = np.asarray(predicted) > threshold
    precision, recall, f1, _ = precision_recall_fscore_support(actual, estimated, average="binary", zero_division=0)
    persistence = test["max_volatility"].to_numpy(float) > threshold
    return {"definition": "Range (high-low)/low candle target > persentil 95 target latih",
            "threshold": threshold, "threshold_quantile": 0.95, "test_samples": len(test),
            "actual_events": int(actual.sum()), "precision": float(precision), "recall": float(recall), "f1": float(f1),
            "persistence_f1": float(f1_score(actual, persistence, zero_division=0))}


def _walk_forward_volatility(data, valid, columns, regressor, horizon, main_split, main_test, main_prediction):
    results = []
    for ratio in (0.5, 0.65):
        split = int((len(data) - horizon) * ratio)
        stop = min(main_split, int((len(data) - horizon) * (ratio + 0.15)))
        train = data.iloc[:max(0, split - horizon)].loc[valid]
        test = data.iloc[split:stop].loc[valid]
        if len(train) < 20 or len(test) < 5:
            continue
        estimator = clone(regressor).fit(train[columns].to_numpy(float), train["target_volatility"].to_numpy(float))
        predicted = estimator.predict(test[columns].to_numpy(float))
        results.append({"train_target_end": str(train["target_timestamp"].max()), "test_start": str(test["timestamp"].min()),
                        "test_end": str(test["timestamp"].max()), "samples": len(test),
                        **evaluate_regression(test["target_volatility"].to_numpy(float), predicted),
                        "event_validation": _volatility_event_metrics(train, test, predicted)})
    train = data.iloc[:main_split - horizon].loc[valid]
    results.append({"train_target_end": str(train["target_timestamp"].max()), "test_start": str(main_test["timestamp"].min()),
                    "test_end": str(main_test["timestamp"].max()), "samples": len(main_test),
                    **evaluate_regression(main_test["target_volatility"].to_numpy(float), main_prediction),
                    "event_validation": _volatility_event_metrics(train, main_test, main_prediction)})
    return results
