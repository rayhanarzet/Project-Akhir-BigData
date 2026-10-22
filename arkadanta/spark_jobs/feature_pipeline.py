"""[ORANG 2] PySpark Dynamic Feature Engineering Pipeline (Bab 5.2)."""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


def spark_compute_features(
    df: DataFrame,
    ma_period: int = 20,
    rsi_period: int = 14,
    rolling_window: int = 20,
) -> DataFrame:
    """Menghitung fitur volatilitas, indikator teknikal, struktur candle, dan mikrostruktur di PySpark."""
    w_order = Window.partitionBy("coin_symbol").orderBy("timestamp")
    w_roll = w_order.rowsBetween(-(rolling_window - 1), 0)
    w_ma = w_order.rowsBetween(-(ma_period - 1), 0)
    w_rsi = w_order.rowsBetween(-(rsi_period - 1), 0)

    feat = (
        df.withColumn(
            "hl_range",
            (F.col("high") - F.col("low")) / F.greatest(F.col("low"), F.lit(1e-8)),
        )
        .withColumn(
            "co_change",
            (F.col("close") - F.col("open")) / F.greatest(F.col("open"), F.lit(1e-8)),
        )
        .withColumn(
            "rolling_volatility",
            F.coalesce(F.stddev("log_return").over(w_roll), F.col("hl_range")),
        )
        .withColumn(
            "rolling_vol_mean",
            F.greatest(F.avg("max_volatility").over(w_roll), F.lit(1e-8)),
        )
        .withColumn(
            "spike_ratio", F.col("max_volatility") / F.col("rolling_vol_mean")
        )
        .withColumn("sma_20", F.avg("close").over(w_ma))
        .withColumn("bb_std", F.coalesce(F.stddev("close").over(w_ma), F.lit(0.0)))
        .withColumn(
            "bb_width",
            (F.lit(4.0) * F.col("bb_std")) / F.greatest(F.col("sma_20"), F.lit(1e-8)),
        )
    )

    # RSI di PySpark
    feat = (
        feat.withColumn(
            "price_diff",
            F.coalesce(F.col("close") - F.lag("close", 1).over(w_order), F.lit(0.0)),
        )
        .withColumn(
            "gain",
            F.when(F.col("price_diff") > 0, F.col("price_diff")).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "loss",
            F.when(F.col("price_diff") < 0, -F.col("price_diff")).otherwise(F.lit(0.0)),
        )
        .withColumn("avg_gain", F.avg("gain").over(w_rsi))
        .withColumn(
            "avg_loss", F.greatest(F.avg("loss").over(w_rsi), F.lit(1e-8))
        )
        .withColumn(
            "rsi_14",
            F.lit(100.0) - (F.lit(100.0) / (F.lit(1.0) + (F.col("avg_gain") / F.col("avg_loss")))),
        )
    )

    # Struktur Candle & Volume Z-Score
    span = F.greatest(F.col("high") - F.col("low"), F.lit(1e-8))
    body_top = F.greatest(F.col("open"), F.col("close"))
    body_bot = F.least(F.col("open"), F.col("close"))

    feat = (
        feat.withColumn("upper_wick_ratio", (F.col("high") - body_top) / span)
        .withColumn("lower_wick_ratio", (body_bot - F.col("low")) / span)
        .withColumn("body_ratio", (body_top - body_bot) / span)
        .withColumn("vol_mean", F.avg("volume").over(w_roll))
        .withColumn(
            "vol_std", F.greatest(F.coalesce(F.stddev("volume").over(w_roll), F.lit(1.0)), F.lit(1e-8))
        )
        .withColumn("volume_zscore", (F.col("volume") - F.col("vol_mean")) / F.col("vol_std"))
    )

    return feat.drop(
        "rolling_vol_mean", "bb_std", "price_diff", "gain", "loss", "avg_gain", "avg_loss", "vol_mean", "vol_std"
    )
