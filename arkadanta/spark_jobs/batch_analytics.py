"""Agregasi dan feature engineering Spark; training GMM/HGB di driver lokal."""
import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import DROP_ZONE_DIR
from backend.schemas import DynamicConfig
from backend.analytics.research_window import research_bounds
from data.storage import load_clean_ohlcv
from spark_jobs.locks import exclusive_spark
from spark_jobs.train_models import collect_model_features
from backend.ml.model_trainer import train_from_features


def prepare_spark_features(config: DynamicConfig):
    with exclusive_spark():
        return _prepare_spark_features(config)


def _prepare_spark_features(config: DynamicConfig):
    from pyspark.sql import SparkSession, functions as F
    from spark_jobs.dynamic_aggregation import spark_aggregate_timeframe
    from spark_jobs.feature_pipeline import spark_compute_features
    symbol = config.symbol.upper()
    load_clean_ohlcv(symbol)
    spark = (SparkSession.builder.appName(f"Arkadanta-GMM-HGB-{symbol}").master("local[*]")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
        raw = spark.read.csv(str(DROP_ZONE_DIR / f"{symbol}_5m_clean.csv"), header=True, inferSchema=True)
        raw = raw.withColumn("timestamp", F.to_timestamp("timestamp"))
        start, end = research_bounds(config.start_date, config.end_date)
        raw = raw.filter(F.col("timestamp").between(F.to_timestamp(F.lit(start.isoformat())), F.to_timestamp(F.lit(end.isoformat()))))
        raw = raw.filter(F.col("timestamp") + F.expr("INTERVAL 5 MINUTES") <= F.current_timestamp())
        aggregated = spark_aggregate_timeframe(raw, timeframe=config.timeframe)
        features = spark_compute_features(aggregated, ma_period=config.ma_period,
                                          rsi_period=config.rsi_period, rolling_window=config.rolling_window)
        return collect_model_features(features)
    finally:
        spark.stop()


def run_batch_job(config: DynamicConfig) -> dict:
    return train_from_features(prepare_spark_features(config), config, "PySpark Features + Scikit-Learn GMM/HGB (driver)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arkadanta Spark features + GMM/HGB driver training")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()
    print(json.dumps(run_batch_job(DynamicConfig(symbol=args.symbol, timeframe=args.timeframe, use_spark=True)), indent=2))
