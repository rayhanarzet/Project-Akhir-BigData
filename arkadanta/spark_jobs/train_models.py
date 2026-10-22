"""[ORANG 2] PySpark MLlib K-Means Centroid Risk Labeling & Random Forest T+1 Trainer (Bab 5.5 - 5.8)."""

from typing import Any, Dict, List
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


def spark_train_and_evaluate(
    df_features: DataFrame,
    feature_cols: List[str],
    cluster_k: int = 3,
    train_ratio: float = 0.8,
    rf_num_trees: int = 100,
    rf_max_depth: int = 10,
) -> Dict[str, Any]:
    """Melatih K-Means + Random Forest di PySpark MLlib dengan pengurutan skor risiko centroid."""
    assembler = VectorAssembler(
        inputCols=feature_cols, outputCol="raw_features", handleInvalid="keep"
    )
    assembled = assembler.transform(df_features)

    scaler = SparkScaler(
        inputCol="raw_features",
        outputCol="scaled_features",
        withStd=True,
        withMean=True,
    )
    scaler_model = scaler.fit(assembled)
    scaled_df = scaler_model.transform(assembled)

    kmeans = SparkKMeans(
        featuresCol="scaled_features",
        predictionCol="cluster_id",
        k=cluster_k,
        seed=42,
    )
    km_model = kmeans.fit(scaled_df)
    clustered_df = km_model.transform(scaled_df)

    evaluator_clust = ClusteringEvaluator(
        featuresCol="scaled_features", predictionCol="cluster_id"
    )
    silhouette = float(evaluator_clust.evaluate(clustered_df))

    # Urutkan centroid berdasarkan skor risiko gabungan (bukan ID mentah 0/1/2)
    centers = km_model.clusterCenters()
    scored = [(cid, float(sum(centers[cid]))) for cid in range(cluster_k)]
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

    # Temporal split berdasarkan persentil timestamp
    ts_bounds = labeled_df.selectExpr(
        f"percentile_approx(unix_timestamp(timestamp), {train_ratio}) as split_ts"
    ).collect()[0]["split_ts"]

    train_df = labeled_df.filter(F.unix_timestamp("timestamp") <= ts_bounds)
    test_df = labeled_df.filter(F.unix_timestamp("timestamp") > ts_bounds)

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

    return {
        "engine": "PySpark MLlib",
        "silhouette_score": round(silhouette, 4),
        "cluster_rank_map": rank_map,
        "accuracy": round(float(acc), 4),
        "f1_score": round(float(f1), 4),
        "rmse": round(float(rmse), 6),
        "mae": round(float(mae), 6),
    }
