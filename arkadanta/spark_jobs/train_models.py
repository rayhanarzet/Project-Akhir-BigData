"""Spark DataFrame -> koleksi terbatas -> trainer GMM/HGB bersama di driver."""
from backend.ml.model_trainer import train_from_features
from backend.schemas import DynamicConfig

MAX_DRIVER_ROWS = 500_000


def collect_model_features(df_features):
    # HGB tidak tersedia di Spark MLlib. Jangan mengklaim training terdistribusi.
    bounded = df_features.limit(MAX_DRIVER_ROWS + 1)
    if "timestamp" in df_features.columns:
        from pyspark.sql import functions as F
        # Konversi eksplisit UTC menghindari ketergantungan zona waktu lokal driver dan
        # bug konversi timestamp PySpark pada pandas 3 tanpa Arrow.
        bounded = bounded.withColumn("timestamp", F.date_format("timestamp", "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"))
    frame = bounded.toPandas()
    if len(frame) > MAX_DRIVER_ROWS:
        raise ValueError(f"Training GMM/HGB lokal dibatasi {MAX_DRIVER_ROWS} baris. Persempit aset/rentang/timeframe.")
    if "timestamp" in frame.columns:
        import pandas as pd
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def spark_train_and_evaluate(df_features, config: DynamicConfig) -> dict:
    return train_from_features(collect_model_features(df_features), config, "PySpark Features + Scikit-Learn GMM/HGB (driver)")
