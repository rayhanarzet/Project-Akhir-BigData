"""[ORANG 2] Pelatihan model K-Means + Random Forest Classifier & Regressor dengan Temporal Split (Bab 5.5 - 5.8)."""

from datetime import datetime, timezone
import json
from typing import Any, Dict
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.config import MODELS_DIR
from backend.ml.dynamic_feature_selector import select_and_prepare_features
from backend.ml.model_evaluator import evaluate_classification, evaluate_regression
from backend.ml.risk_labeler import DynamicRiskLabeler
from backend.schemas import DynamicConfig
from data.sample_generator import load_clean_ohlcv


def train_dynamic_models(config: DynamicConfig) -> Dict[str, Any]:
    """Melatih K-Means Risk Labeler dan Random Forest T+1 dengan pembagian data kronologis (temporal split)."""
    symbol = config.symbol.upper()
    df_5m = load_clean_ohlcv(symbol)
    df_agg = aggregate_timeframe(
        df_5m,
        timeframe=config.timeframe,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    df_feat = compute_dynamic_features(
        df_agg,
        ma_period=config.ma_period,
        rsi_period=config.rsi_period,
        rolling_window=config.rolling_window,
    )
    df_clean, feature_cols = select_and_prepare_features(df_feat, config.features)
    df_clean = df_clean.sort_values("timestamp").reset_index(drop=True)

    if len(df_clean) < 30:
        raise ValueError(
            f"Jumlah baris data ({len(df_clean)}) terlalu sedikit untuk pelatihan model pada timeframe {config.timeframe}."
        )

    # Split kronologis awal untuk fit K-Means (mencegah data leakage dari masa depan)
    split_idx_raw = int(len(df_clean) * config.train_ratio)
    split_idx_raw = max(15, min(split_idx_raw, len(df_clean) - 5))

    labeler = DynamicRiskLabeler(n_clusters=config.cluster_k, random_state=42)
    labeler.fit(df_clean.iloc[:split_idx_raw], feature_cols)

    cluster_ids, risk_labels = labeler.transform(df_clean)
    df_clean["cluster_id"] = cluster_ids
    df_clean["current_risk_label"] = risk_labels

    # Buat target T+horizon (fitur waktu T memprediksi risiko & max_volatility pada T+horizon)
    horizon = max(1, config.target_horizon)
    df_clean["target_risk_t_plus_1"] = df_clean["current_risk_label"].shift(-horizon)
    df_clean["target_volatility_t_plus_1"] = df_clean["max_volatility"].shift(-horizon)

    df_supervised = df_clean.dropna(
        subset=["target_risk_t_plus_1", "target_volatility_t_plus_1"]
    ).reset_index(drop=True)

    # Temporal split untuk supervised learning T+1
    split_idx = int(len(df_supervised) * config.train_ratio)
    split_idx = max(10, min(split_idx, len(df_supervised) - 5))

    train_df = df_supervised.iloc[:split_idx].copy()
    test_df = df_supervised.iloc[split_idx:].copy()

    X_train = train_df[feature_cols].values.astype(float)
    y_train_cls = train_df["target_risk_t_plus_1"].tolist()
    y_train_reg = train_df["target_volatility_t_plus_1"].values.astype(float)

    X_test = test_df[feature_cols].values.astype(float)
    y_test_cls = test_df["target_risk_t_plus_1"].tolist()
    y_test_reg = test_df["target_volatility_t_plus_1"].values.astype(float)

    # Latih Random Forest Classifier (probabilitas SAFE / WARNING / DANGER pada T+1)
    rf_clf = RandomForestClassifier(
        n_estimators=config.rf_num_trees,
        max_depth=config.rf_max_depth,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    rf_clf.fit(X_train, y_train_cls)
    y_pred_cls = rf_clf.predict(X_test).tolist()

    # Latih Random Forest Regressor (estimasi max_volatility pada T+1)
    rf_reg = RandomForestRegressor(
        n_estimators=config.rf_num_trees,
        max_depth=config.rf_max_depth,
        random_state=42,
        n_jobs=-1,
    )
    rf_reg.fit(X_train, y_train_reg)
    y_pred_reg = rf_reg.predict(X_test)

    cls_metrics = evaluate_classification(y_test_cls, y_pred_cls)
    reg_metrics = evaluate_regression(y_test_reg, y_pred_reg)

    importances = [
        {"feature": feat, "importance": round(float(imp), 4)}
        for feat, imp in sorted(
            zip(feature_cols, rf_clf.feature_importances_),
            key=lambda x: x[1],
            reverse=True,
        )
    ]

    regime_counts = df_clean["current_risk_label"].value_counts().to_dict()

    artifact_meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": config.timeframe,
        "target_horizon": horizon,
        "features": feature_cols,
        "cluster_k": config.cluster_k,
        "train_ratio": config.train_ratio,
        "rf_num_trees": config.rf_num_trees,
        "rf_max_depth": config.rf_max_depth,
        "temporal_split": {
            "total_samples": len(df_supervised),
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "train_start": str(train_df["timestamp"].iloc[0]),
            "train_end": str(train_df["timestamp"].iloc[-1]),
            "test_start": str(test_df["timestamp"].iloc[0]),
            "test_end": str(test_df["timestamp"].iloc[-1]),
        },
        "kmeans_metrics": {
            "silhouette_score": round(labeler.silhouette, 4),
            "cluster_to_label": {str(k): v for k, v in labeler.cluster_to_label.items()},
            "centroids": labeler.centroid_table,
            "regime_distribution": {
                "SAFE": int(regime_counts.get("SAFE", 0)),
                "WARNING": int(regime_counts.get("WARNING", 0)),
                "DANGER": int(regime_counts.get("DANGER", 0)),
            },
        },
        "classification_metrics": cls_metrics,
        "regression_metrics": reg_metrics,
        "feature_importances": importances,
        "test_predictions_preview": [
            {
                "timestamp": str(row["timestamp"]),
                "close": round(float(row["close"]), 4),
                "actual_risk_t1": row["target_risk_t_plus_1"],
                "predicted_risk_t1": pred_c,
                "actual_vol_t1": round(float(row["target_volatility_t_plus_1"]), 6),
                "predicted_vol_t1": round(float(pred_r), 6),
            }
            for (_, row), pred_c, pred_r in list(
                zip(test_df.iterrows(), y_pred_cls, y_pred_reg)
            )[-60:]
        ],
    }

    # Simpan bundle model & file metrik terbaru
    bundle_path = MODELS_DIR / f"model_{symbol}_{config.timeframe}.joblib"
    latest_bundle_path = MODELS_DIR / "latest_model.joblib"
    metrics_path = MODELS_DIR / "latest_metrics.json"

    bundle_obj = {
        "labeler": labeler,
        "rf_clf": rf_clf,
        "rf_reg": rf_reg,
        "config": config.model_dump(),
        "meta": artifact_meta,
    }
    joblib.dump(bundle_obj, bundle_path)
    joblib.dump(bundle_obj, latest_bundle_path)
    metrics_path.write_text(json.dumps(artifact_meta, indent=2), encoding="utf-8")

    return artifact_meta
