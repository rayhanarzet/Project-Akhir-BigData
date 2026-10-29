"""[ORANG 1 & 2] PySpark Dynamic Multi-Timeframe Aggregation dengan urutan timestamp eksplisit (Bab 5.1)."""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


SPARK_WINDOW_MAP = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day",
    "1w": "1 week",
}
# Jumlah candle 5m dalam satu bucket lengkap (sama dengan aggregate_timeframe pandas).
CANDLES_PER_BUCKET = {"5m": 1, "15m": 3, "1h": 12, "4h": 48, "1d": 288, "1w": 2016}
OPTIONAL_SUM_COLUMNS = (
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)


def spark_aggregate_timeframe(df_5m: DataFrame, timeframe: str = "1h") -> DataFrame:
    """Mengagregasi OHLCV 5 menit menjadi timeframe target menggunakan PySpark secara deterministik."""
    df = df_5m.withColumn("timestamp", F.to_timestamp("timestamp"))
    df = df.withColumn(
        "candle_volatility",
        (F.col("high") - F.col("low")) / F.greatest(F.col("low"), F.lit(1e-8)),
    )

    win_duration = SPARK_WINDOW_MAP.get(timeframe, "1 hour")
    # Epoch 1970-01-01 adalah Kamis; geser 4 hari agar minggu mulai Senin seperti pandas W-MON.
    start_time = "4 days" if timeframe == "1w" else "0 seconds"
    df_bucketed = df.withColumn("time_bucket", F.window("timestamp", win_duration, win_duration, start_time))

    # Urutan timestamp eksplisit dalam setiap bucket agar open pertama & close terakhir deterministik
    w_asc = (
        Window.partitionBy("coin_symbol", "time_bucket")
        .orderBy(F.col("timestamp").asc())
        .rowsBetween(Window.unboundedPreceding, Window.unboundedFollowing)
    )

    df_with_oc = df_bucketed.withColumn(
        "first_open", F.first("open").over(w_asc)
    ).withColumn("last_close", F.last("close").over(w_asc))

    optional = [F.when(F.count(c) == F.count("*"), F.sum(c)).alias(c)
                for c in OPTIONAL_SUM_COLUMNS if c in df.columns]
    agg_df = (
        df_with_oc.groupBy("coin_symbol", "time_bucket")
        .agg(
            F.first("first_open").alias("open"),
            F.max("high").alias("high"),
            F.min("low").alias("low"),
            F.first("last_close").alias("close"),
            F.sum("volume").alias("volume"),
            F.max("candle_volatility").alias("max_candle_volatility"),
            F.avg("candle_volatility").alias("avg_volatility"),
            F.count("*").alias("candle_count"),
            *optional,
        )
        # Hanya bucket lengkap: bucket berjalan atau berlubang bias rendah pada volume/volatilitas.
        .filter(F.col("candle_count") == CANDLES_PER_BUCKET[timeframe])
        # Sama dengan pandas: range seluruh bucket ikut dihitung, bukan hanya candle 5m terbesar.
        .withColumn(
            "max_volatility",
            F.greatest(
                F.col("max_candle_volatility"),
                (F.col("high") - F.col("low")) / F.greatest(F.col("low"), F.lit(1e-8)),
            ),
        )
        .withColumn("timestamp", F.col("time_bucket.start"))
        .drop("time_bucket", "candle_count", "max_candle_volatility")
    )

    w_sym = Window.partitionBy("coin_symbol").orderBy("timestamp")
    agg_df = agg_df.withColumn(
        "prev_close", F.lag("close", 1).over(w_sym)
    ).withColumn(
        "log_return",
        F.when(
            F.col("prev_close").isNotNull() & (F.col("prev_close") > 0),
            F.log(F.col("close") / F.col("prev_close")),
        ).otherwise(F.lit(0.0)),
    ).drop("prev_close")

    return agg_df.orderBy("coin_symbol", "timestamp")
