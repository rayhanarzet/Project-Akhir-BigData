"""Inferensi kategori gejolak relatif T+1, periode target UTC, dan batas harga ilustratif."""

from datetime import datetime, timezone
import json
from typing import Any, Dict
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import BASE_CANDLE, TIMEFRAME_DURATION, aggregate_timeframe
from backend.ml.model_trainer import MODEL_VERSION, bundle_path, metrics_path, model_directory
from backend.schemas import DynamicConfig, PredictRequest
from data.storage import load_clean_ohlcv, ResearchDataError


def load_or_train_bundle(symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    """Memuat model terlatih untuk simbol & timeframe. Training hanya lewat Model Lab/batch, bukan request prediksi."""
    # Namespace versi baru membuat artefak lama tetap tersimpan dan tidak termuat.
    validated = DynamicConfig(symbol=symbol.upper(), timeframe=timeframe)
    specific_path = bundle_path(validated.symbol, validated.timeframe)
    # Bundle ditulis atomik (replace), jadi membaca tanpa training_lock aman dan tidak menunggu training.
    if not specific_path.exists():
        raise ResearchDataError(f"Model {validated.symbol} {validated.timeframe} belum dilatih. Latih melalui Model Lab atau batch HDFS.")
    bundle = joblib.load(specific_path)
    if bundle.get("model_version") != MODEL_VERSION:
        raise ResearchDataError("Versi model tidak cocok. Latih ulang GMM/HGB melalui Model Lab.")
    return bundle


def predict_next_period(req: PredictRequest) -> Dict[str, Any]:
    """Menghasilkan prediksi kategori/range T+1, dengan waktu target dan batas ilustratif."""
    symbol = req.symbol.upper()
    bundle = load_or_train_bundle(symbol=symbol, timeframe=req.timeframe)

    labeler = bundle["labeler"]
    classifier = bundle["classifier"]
    regressor = bundle["regressor"]
    meta = bundle["meta"]
    feature_cols = meta["features"]
    if req.target_horizon != meta["target_horizon"]:
        raise ResearchDataError(f"Model dilatih untuk horizon {meta['target_horizon']}. Pilih horizon yang sama atau latih ulang.")

    config = DynamicConfig(**bundle["config"])
    # Fitur pandas identik dengan fitur Spark (tests/test_spark_parity.py), jadi model hasil Spark
    # pun dilayani tanpa menyalakan Spark di setiap request prediksi.
    df_agg = aggregate_timeframe(load_clean_ohlcv(symbol), timeframe=req.timeframe)
    df_feat = compute_dynamic_features(df_agg, ma_period=config.ma_period,
                                      rsi_period=config.rsi_period, rolling_window=config.rolling_window)
    if df_feat.empty:
        raise ResearchDataError("Belum ada candle lengkap dalam 365 hari terakhir pada timeframe ini. Jalankan Backfill Histori.")
    latest_row = df_feat.sort_values("timestamp").iloc[-1].copy()
    # Candle lengkap terakhir normalnya selesai < 1 periode lalu; lebih tua berarti ada data yang terlewat.
    duration = TIMEFRAME_DURATION.get(req.timeframe, BASE_CANDLE)
    candle_end = pd.Timestamp(latest_row["timestamp"]) + duration
    clock = pd.Timestamp.now(tz="UTC")
    # Candle T harus merupakan bucket tertutup paling akhir, bukan sekadar "cukup baru".
    if clock >= candle_end + duration:
        raise ResearchDataError(
            f"Candle {req.timeframe} lengkap terakhir selesai {candle_end:%Y-%m-%d %H:%M} UTC; data setelahnya hilang. "
            "Jalankan Manual Sync atau Backfill Histori agar prediksi memakai data terbaru."
        )

    if req.custom_features:
        for k, v in req.custom_features.items():
            if k in latest_row.index:
                latest_row[k] = float(v)

    missing = set(feature_cols) - set(latest_row.index)
    if missing:
        raise ResearchDataError(f"Sumber fitur prediksi tidak tersedia: {sorted(missing)}. Lengkapi data atau latih ulang dengan fitur yang tersedia.")
    x_vec = np.array([[float(latest_row[col]) for col in feature_cols]])

    if not np.isfinite(x_vec).all():
        raise ResearchDataError("Fitur prediksi mengandung nilai tidak valid.")
    # Status rezim saat ini (waktu T) dari Gaussian Mixture Risk Labeler
    x_scaled = labeler.scaler.transform(x_vec)
    current_cluster = int(labeler.gmm.predict(x_scaled)[0])
    current_regime = labeler.cluster_to_label[current_cluster]

    # Prediksi T+1 dari HistGradientBoosting
    with threadpool_limits(limits=2):
        pred_regime_t1 = str(classifier.predict(x_vec)[0])
        proba_raw = classifier.predict_proba(x_vec)[0]
        pred_vol_ratio = max(float(regressor.predict(x_vec)[0]), 0.0)
    classes = list(classifier.classes_)

    probabilities = {"SAFE": 0.0, "WARNING": 0.0, "DANGER": 0.0}
    for cls_name, p_val in zip(classes, proba_raw):
        probabilities[str(cls_name)] = round(float(p_val), 4)

    current_price = float(req.current_price or latest_row["close"])

    # Estimasi volatilitas dalam satuan harga nominal
    estimated_volatility_price = current_price * pred_vol_ratio
    resistance_level = current_price + estimated_volatility_price
    stop_loss_level = max(current_price - estimated_volatility_price, 0.0)
    target_start = candle_end + duration * (req.target_horizon - 1)
    target_end = target_start + duration

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candle_timestamp": str(latest_row["timestamp"]),
        "target_start": target_start.isoformat(), "target_end": target_end.isoformat(),
        "model_trained_at": meta["trained_at"],
        "symbol": symbol,
        "timeframe": req.timeframe,
        "target_horizon": req.target_horizon,
        "current_price": round(current_price, 6),
        "current_component_id": current_cluster,
        "current_regime_t": current_regime,
        "predicted_regime_t_plus_1": pred_regime_t1,
        "probabilities_t_plus_1": probabilities,
        "predicted_volatility_pct": round(pred_vol_ratio * 100.0, 4),
        "estimated_volatility_nominal": round(estimated_volatility_price, 6),
        "resistance_level": round(resistance_level, 6),
        "stop_loss_level": round(stop_loss_level, 6),
        "illustrative_upper_bound": round(resistance_level, 6),
        "illustrative_lower_bound": round(stop_loss_level, 6),
        "bounds_definition": "Harga penutupan T +/- harga T x estimasi range target; batas ilustratif, tanpa jaminan cakupan harga.",
        "risk_label_definition": meta["risk_label_definition"],
        "feature_snapshot": {
            col: round(float(latest_row.get(col, 0.0)), 6) for col in feature_cols
        },
        "disclaimer": "Keluaran hanya untuk analitik akademik, bukan nasihat investasi.",
    }


def get_latest_metrics(symbol: str | None = None, timeframe: str | None = None) -> Dict[str, Any]:
    """Mengambil metrik evaluasi model terakhir."""
    config = DynamicConfig(symbol=symbol or "BTCUSDT", timeframe=timeframe or "1h")
    path = metrics_path(config.symbol, config.timeframe) if symbol or timeframe else model_directory() / "latest_metrics.json"
    if not path.exists():
        raise ResearchDataError("Belum ada model terlatih. Latih melalui Model Lab atau batch HDFS.")
    metrics = json.loads(path.read_text(encoding="utf-8"))
    if metrics.get("model_version") != MODEL_VERSION:
        raise ResearchDataError("Metrik model lama tidak digunakan. Latih ulang model GMM/HGB.")
    return metrics
