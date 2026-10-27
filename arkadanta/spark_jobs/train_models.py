"""[ORANG 2] PySpark MLlib K-Means Centroid Risk Labeling & Random Forest T+1 Trainer (Bab 5.5 - 5.8)."""

from typing import Any, Dict, List

try:
    from pyspark.ml.clustering import KMeans as SparkKMeans
    from pyspark.ml.evaluation import (
        ClusteringEvaluator,
        MulticlassClassificationEvaluator,
        RegressionEvaluator,
    )
    from pyspark.ml.feature import StandardScaler as SparkScaler, VectorAssembler
    from pyspark.ml.classification import RandomForestClassifier as SparkRFClassifier
    from pyspark.ml.regression import RandomForestRegressor as SparkRFRegressor
    from pyspark.sql import DataFrame, Window
    from pyspark.sql import functions as F
except ImportError:
    DataFrame = Any  # type: ignore


def _compute_spark_centroid_risk_score(
    centroid_z: Any, feature_cols: List[str]
) -> float:
    """Menghitung skor risiko gabungan centroid yang identik dengan DynamicRiskLabeler (Scikit-Learn)."""
    weights = []
    for idx, col in enumerate(feature_cols):
        if col in ("max_volatility", "avg_volatility", "rolling_volatility", "hl_range", "bb_width"):
            weights.append((idx, 1.5))
        elif col in ("spike_ratio", "volume_zscore"):
            weights.append((idx, 1.2))
        elif col == "rsi_14":
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


def spark_train_and_evaluate(
    df_features: DataFrame,
    feature_cols: List[str],
    cluster_k: int = 3,
    train_ratio: float = 0.8,
    rf_num_trees: int = 100,
    rf_max_depth: int = 10,
    model_output_path: str | None = None,
) -> Dict[str, Any]:
    """Melatih K-Means + Random Forest di PySpark MLlib dengan pengurutan skor risiko centroid & temporal split."""
    assembler = VectorAssembler(
        inputCols=feature_cols, outputCol="raw_features", handleInvalid="keep"
    )
    assembled = assembler.transform(df_features)

    # Temporal split terlebih dahulu sebelum fit StandardScaler & K-Means (mencegah data leakage)
    ts_bounds_init = assembled.selectExpr(
        f"percentile_approx(unix_timestamp(timestamp), {train_ratio}) as split_ts"
    ).collect()[0]["split_ts"]

    train_raw = assembled.filter(F.unix_timestamp("timestamp") <= ts_bounds_init)

    scaler = SparkScaler(
        inputCol="raw_features",
        outputCol="scaled_features",
        withStd=True,
        withMean=True,
    )
    scaler_model = scaler.fit(train_raw)
    scaled_train = scaler_model.transform(train_raw)
    scaled_df = scaler_model.transform(assembled)

    kmeans = SparkKMeans(
        featuresCol="scaled_features",
        predictionCol="cluster_id",
        k=cluster_k,
        seed=42,
    )
    km_model = kmeans.fit(scaled_train)
    clustered_df = km_model.transform(scaled_df)

    evaluator_clust = ClusteringEvaluator(
        featuresCol="scaled_features", predictionCol="cluster_id"
    )
    silhouette = float(evaluator_clust.evaluate(km_model.transform(scaled_train)))

    # Urutkan centroid berdasarkan skor risiko gabungan berbobot (SAFE -> WARNING -> DANGER)
    centers = km_model.clusterCenters()
    scored = [
        (cid, _compute_spark_centroid_risk_score(centers[cid], feature_cols))
        for cid in range(cluster_k)
    ]
    scored.sort(key=lambda x: x[1])

    rank_map = {cid: idx for idx, (cid, _) in enumerate(scored)}
    mapping_expr = F.create_map([F.lit(x) for pair in rank_map.items() for x in pair])

    w_time = Window.partitionBy("coin_symbol").orderBy("timestamp")
    labeled_df = (
        clustered_df.withColumn("risk_label_idx", mapping_expr[F.col("cluster_id")].cast("double"))
        .withColumn("target_risk_t1", F.lead("risk_label_idx", 1).over(w_time))
        .withColumn("target_vol_t1", F.lead("max_volatility", 1).over(w_time))
        .dropna(subset=["target_risk_t1", "target_vol_t1"])
    )

    train_df = labeled_df.filter(F.unix_timestamp("timestamp") <= ts_bounds_init)
    test_df = labeled_df.filter(F.unix_timestamp("timestamp") > ts_bounds_init)

    rf_clf = SparkRFClassifier(
        featuresCol="scaled_features",
        labelCol="target_risk_t1",
        numTrees=rf_num_trees,
        maxDepth=rf_max_depth,
        seed=42,
    )
    clf_model = rf_clf.fit(train_df)
    pred_cls = clf_model.transform(test_df)

    rf_reg = SparkRFRegressor(
        featuresCol="scaled_features",
        labelCol="target_vol_t1",
        numTrees=rf_num_trees,
        maxDepth=rf_max_depth,
        seed=42,
    )
    reg_model = rf_reg.fit(train_df)
    pred_reg = reg_model.transform(test_df)

    acc = MulticlassClassificationEvaluator(
        labelCol="target_risk_t1", predictionCol="prediction", metricName="accuracy"
    ).evaluate(pred_cls)
    f1 = MulticlassClassificationEvaluator(
        labelCol="target_risk_t1", predictionCol="prediction", metricName="f1"
    ).evaluate(pred_cls)
    rmse = RegressionEvaluator(
        labelCol="target_vol_t1", predictionCol="prediction", metricName="rmse"
    ).evaluate(pred_reg)
    mae = RegressionEvaluator(
        labelCol="target_vol_t1", predictionCol="prediction", metricName="mae"
    ).evaluate(pred_reg)

    if model_output_path:
        # Persist all fitted MLlib stages needed to reproduce inference later.
        scaler_model.write().overwrite().save(f"{model_output_path}/scaler")
        km_model.write().overwrite().save(f"{model_output_path}/kmeans")
        clf_model.write().overwrite().save(f"{model_output_path}/classifier")
        reg_model.write().overwrite().save(f"{model_output_path}/regressor")

    return {
        "engine": "PySpark MLlib (Batch Layer)",
        "silhouette_score": round(silhouette, 4),
        "cluster_rank_map": rank_map,
        "features": feature_cols,
        "accuracy": round(float(acc), 4),
        "f1_score": round(float(f1), 4),
        "rmse": round(float(rmse), 6),
        "mae": round(float(mae), 6),
    }
