"""[ORANG 2] Orkestrator Batch Layer PySpark (HDFS / Local Drop Zone -> Aggregation -> Features -> ML)."""

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pyspark.sql import SparkSession
from backend.config import DEFAULT_FEATURES, DROP_ZONE_DIR
from data.sample_generator import ensure_sample_data_exists
from spark_jobs.dynamic_aggregation import spark_aggregate_timeframe
from spark_jobs.feature_pipeline import spark_compute_features
from spark_jobs.train_models import spark_train_and_evaluate


def run_batch_job(symbol: str = "BTCUSDT", timeframe: str = "1h") -> dict:
    ensure_sample_data_exists([symbol])
    input_csv = str(DROP_ZONE_DIR / f"{symbol.upper()}_5m_clean.csv")

    spark = (
        SparkSession.builder.appName(f"Arkadanta-Batch-{symbol}-{timeframe}")
        .master("local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    try:
        df_raw = spark.read.csv(input_csv, header=True, inferSchema=True)
        df_agg = spark_aggregate_timeframe(df_raw, timeframe=timeframe)
        df_feat = spark_compute_features(df_agg)
        metrics = spark_train_and_evaluate(df_feat, feature_cols=DEFAULT_FEATURES)
        return metrics
    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arkadanta PySpark Batch Job")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()
    result = run_batch_job(symbol=args.symbol, timeframe=args.timeframe)
    print(json.dumps(result, indent=2))
