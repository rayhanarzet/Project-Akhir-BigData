"""Fitur Spark (Tab 4 / use_spark) harus identik dengan fitur pandas (prediksi live), atau model menerima skala lain."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from data.sample_generator import generate_synthetic_5m_ohlcv

try:
    from pyspark.sql import SparkSession
    from spark_jobs.dynamic_aggregation import spark_aggregate_timeframe
    from spark_jobs.feature_pipeline import spark_compute_features
    from spark_jobs.locks import check_java_home
except ImportError:
    SparkSession = None

# ema_20 tidak dihitung Spark (EWM rekursif); Tab 4 menolak fitur itu secara eksplisit.
COMPARED = ["max_volatility", "avg_volatility", "rolling_volatility", "spike_ratio", "log_return",
            "periodic_return", "hl_range", "co_change", "sma_20", "rsi_14", "bb_width",
            "upper_wick_ratio", "lower_wick_ratio", "body_ratio", "buy_sell_pressure_ratio", "volume_zscore"]


@unittest.skipIf(SparkSession is None, "pyspark tidak terpasang")
class SparkPandasParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            check_java_home()
            cls.spark = (SparkSession.builder.master("local[1]")
                         .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        except Exception as exc:  # Java/JAVA_HOME tidak tersedia di mesin ini
            raise unittest.SkipTest(f"Spark tidak bisa start: {exc}")
        cls.spark.sparkContext.setLogLevel("ERROR")
        raw = generate_synthetic_5m_ohlcv(n_candles=12 * 24 * 20)
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
        raw = raw.drop(index=[500, 501, 502])  # lubang data: bucket 1h ini harus dibuang di kedua engine
        cls.raw = raw
        cls.sdf = cls.spark.createDataFrame(raw.assign(timestamp=raw["timestamp"].dt.tz_localize(None)))

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_features_identical_per_timeframe(self):
        for timeframe in ("15m", "1h", "4h", "1d"):
            with self.subTest(timeframe=timeframe):
                expected = compute_dynamic_features(aggregate_timeframe(self.raw, timeframe))
                actual = spark_compute_features(spark_aggregate_timeframe(self.sdf, timeframe)).toPandas()
                actual = actual.sort_values("timestamp").reset_index(drop=True)
                self.assertEqual(len(expected), len(actual))
                np.testing.assert_array_equal(
                    expected["timestamp"].dt.tz_localize(None).to_numpy(), pd.to_datetime(actual["timestamp"]).to_numpy())
                for column in COMPARED:
                    np.testing.assert_allclose(actual[column].to_numpy(float), expected[column].to_numpy(float),
                                               rtol=1e-6, atol=1e-9, err_msg=f"{timeframe} {column}")


if __name__ == "__main__":
    unittest.main()
