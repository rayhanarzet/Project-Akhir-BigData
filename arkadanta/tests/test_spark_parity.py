"""Fitur Spark (Tab 4 / use_spark) harus identik dengan fitur pandas (prediksi live), atau model menerima skala lain."""
from pathlib import Path
import sys
import unittest
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from data.sample_generator import generate_synthetic_5m_ohlcv

try:
    from pyspark.sql import SparkSession, functions as F
    from spark_jobs.dynamic_aggregation import spark_aggregate_timeframe
    from spark_jobs.feature_pipeline import spark_compute_features
    from spark_jobs.locks import check_java_home
    from spark_jobs.train_models import collect_model_features
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
        # Masuk seperti CSV produksi: waktu ISO UTC, bukan datetime naive yang ditafsirkan
        # createDataFrame menggunakan zona waktu lokal Python/WSL.
        cls.sdf = cls.spark.createDataFrame(
            raw.assign(timestamp=raw["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
        ).withColumn("timestamp", F.to_timestamp("timestamp"))

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_features_identical_per_timeframe(self):
        for timeframe in ("15m", "1h", "4h", "1d"):
            with self.subTest(timeframe=timeframe):
                expected = compute_dynamic_features(aggregate_timeframe(self.raw, timeframe))
                actual = collect_model_features(spark_compute_features(spark_aggregate_timeframe(self.sdf, timeframe)))
                actual = actual.sort_values("timestamp").reset_index(drop=True)
                self.assertEqual(len(expected), len(actual))
                np.testing.assert_array_equal(
                    expected["timestamp"].dt.tz_localize(None).to_numpy(), pd.to_datetime(actual["timestamp"], utc=True).dt.tz_localize(None).to_numpy())
                for column in COMPARED:
                    np.testing.assert_allclose(actual[column].to_numpy(float), expected[column].to_numpy(float),
                                               rtol=1e-6, atol=1e-9, err_msg=f"{timeframe} {column}")

    def test_raw_files_keep_their_own_asset_identity(self):
        from spark_jobs.historical_hdfs_job import _normalise_ohlcv
        with tempfile.TemporaryDirectory() as tmp:
            stamp = int((pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=10)).timestamp() * 1000)
            for symbol, price in (("BTCUSDT", 100), ("ETHUSDT", 10)):
                folder = Path(tmp) / f"symbol={symbol}"
                folder.mkdir()
                (folder / f"{symbol}-5m-test.csv").write_text(f"{stamp},{price},{price+2},{price-1},{price+1},10,{stamp+299999},1010,25,4,404,0\n")
            clean, _ = _normalise_ohlcv(self.spark, tmp, "BTCUSDT", "2020-01-01", "2099-01-01")
            records = clean.collect()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["coin_symbol"], "BTCUSDT")
            self.assertEqual(records[0]["close"], 101)

    def test_aggregation_preserves_missing_microstructure_like_pandas(self):
        raw = self.raw.copy()
        bucket = raw["timestamp"].dt.floor("15min")
        complete = bucket.value_counts().loc[lambda counts: counts.eq(3)].index.sort_values()
        raw.loc[bucket.eq(complete[1]), "number_of_trades"] = np.nan
        stamp = raw.loc[bucket.eq(complete[2]), "timestamp"].iloc[0]
        raw.loc[raw["timestamp"].eq(stamp), "taker_buy_base_volume"] = np.nan
        sdf = self.sdf.withColumn("number_of_trades", F.when(
            F.window("timestamp", "15 minutes").getField("start") != F.to_timestamp(F.lit(complete[1].isoformat())),
            F.col("number_of_trades")))
        sdf = sdf.withColumn("taker_buy_base_volume", F.when(
            F.col("timestamp") != F.to_timestamp(F.lit(stamp.isoformat())), F.col("taker_buy_base_volume")))
        expected = aggregate_timeframe(raw, "15m").sort_values("timestamp")
        actual = collect_model_features(spark_aggregate_timeframe(sdf, "15m")).sort_values("timestamp")
        for column in ("number_of_trades", "taker_buy_base_volume"):
            self.assertEqual(int(expected[column].isna().sum()), 1)
            np.testing.assert_allclose(actual[column].to_numpy(float), expected[column].to_numpy(float), equal_nan=True)

    def test_latest_revision_wins_and_replays_are_deduplicated(self):
        from spark_jobs.historical_hdfs_job import _normalise_ohlcv
        stamp = (pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=10)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revisions.csv"
            path.write_text("timestamp,coin_symbol,open,high,low,close,volume,ingestion_version\n"
                            f"{stamp},BTCUSDT,100,102,99,101,10,1780000000000000001\n"
                            f"{stamp},BTCUSDT,100,102,99,101.5,10,1780000000000000002\n"
                            f"{stamp},BTCUSDT,100,102,99,101.5,10,1780000000000000002\n")
            clean, before = _normalise_ohlcv(self.spark, str(path), "BTCUSDT", "2020-01-01", "2099-01-01")
            self.assertEqual(before, 3)
            self.assertEqual(clean.first()["close"], 101.5)
            self.assertEqual(clean.count(), 1)

    def test_raw_without_asset_identity_is_rejected(self):
        from spark_jobs.historical_hdfs_job import _normalise_ohlcv
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unknown.csv"
            path.write_text("1767225600000,100,102,99,101,10,1767225899999,1010,25,4,404,0\n")
            with self.assertRaisesRegex(ValueError, "simbol"):
                _normalise_ohlcv(self.spark, str(path), "BTCUSDT", "2020-01-01", "2099-01-01")

    def test_conflicting_equal_revisions_are_rejected(self):
        from spark_jobs.historical_hdfs_job import _normalise_ohlcv
        stamp = (pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=10)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conflict.csv"
            path.write_text("timestamp,coin_symbol,open,high,low,close,volume,ingestion_version\n"
                            f"{stamp},BTCUSDT,100,102,99,101,10,7\n"
                            f"{stamp},BTCUSDT,100,102,99,101.5,10,7\n")
            with self.assertRaisesRegex(ValueError, "versi sama"):
                _normalise_ohlcv(self.spark, str(path), "BTCUSDT", "2020-01-01", "2099-01-01")


if __name__ == "__main__":
    unittest.main()
