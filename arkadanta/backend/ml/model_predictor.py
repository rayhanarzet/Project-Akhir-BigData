"""[ORANG 2] Inferensi T+1 untuk kelas risiko (SAFE/WARNING/DANGER), estimasi volatilitas, Resistance, dan Stop Loss (Bab 5.6)."""

from datetime import datetime, timezone
import json
from typing import Any, Dict
import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
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
    """Menghasilkan prediksi rezim risiko T+1, probabilitas kelas, estimasi volatilitas T+1, Resistance, dan Stop Loss."""
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
    if config.use_spark:
        from spark_jobs.batch_analytics import prepare_spark_features
        df_feat = prepare_spark_features(config.model_copy(update={"start_date": None, "end_date": None}))
    else:
        df_5m = load_clean_ohlcv(symbol)
        df_agg = aggregate_timeframe(df_5m, timeframe=req.timeframe)
        df_feat = compute_dynamic_features(df_agg, ma_period=config.ma_period,
                                          rsi_period=config.rsi_period, rolling_window=config.rolling_window)
    latest_row = df_feat.sort_values("timestamp").iloc[-1].copy()

    if req.custom_features:
        for k, v in req.custom_features.items():
            if k in latest_row.index:
                latest_row[k] = float(v)

    x_vec = np.array([[float(latest_row.get(col, 0.0)) for col in feature_cols]])

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

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candle_timestamp": str(latest_row["timestamp"]),
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
