"""[ORANG 2] Inferensi T+1 untuk kelas risiko (SAFE/WARNING/DANGER), estimasi volatilitas, Resistance, dan Stop Loss (Bab 5.6)."""

from datetime import datetime, timezone
import json
from typing import Any, Dict
import joblib
import numpy as np

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.config import MODELS_DIR
from backend.ml.model_trainer import train_dynamic_models
from backend.schemas import DynamicConfig, PredictRequest
from data.sample_generator import load_clean_ohlcv


def load_or_train_bundle(symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    """Memuat model terlatih untuk simbol & timeframe, atau melatih otomatis jika belum ada."""
    specific_path = MODELS_DIR / f"model_{symbol.upper()}_{timeframe}.joblib"
    if specific_path.exists():
        return joblib.load(specific_path)

    default_cfg = DynamicConfig(symbol=symbol.upper(), timeframe=timeframe)
    train_dynamic_models(default_cfg)
    return joblib.load(specific_path)


def predict_next_period(req: PredictRequest) -> Dict[str, Any]:
    """Menghasilkan prediksi rezim risiko T+1, probabilitas kelas, estimasi volatilitas T+1, Resistance, dan Stop Loss."""
    symbol = req.symbol.upper()
    bundle = load_or_train_bundle(symbol=symbol, timeframe=req.timeframe)

    labeler = bundle["labeler"]
    rf_clf = bundle["rf_clf"]
    rf_reg = bundle["rf_reg"]
    meta = bundle["meta"]
    feature_cols = meta["features"]

    df_5m = load_clean_ohlcv(symbol)
    df_agg = aggregate_timeframe(df_5m, timeframe=req.timeframe)
    df_feat = compute_dynamic_features(df_agg)
    latest_row = df_feat.sort_values("timestamp").iloc[-1].copy()

    if req.custom_features:
        for k, v in req.custom_features.items():
            if k in latest_row.index:
                latest_row[k] = float(v)

    x_vec = np.array([[float(latest_row.get(col, 0.0)) for col in feature_cols]])

    # Status rezim saat ini (waktu T) dari K-Means Risk Labeler
    x_scaled = labeler.scaler.transform(x_vec)
    current_cluster = int(labeler.kmeans.predict(x_scaled)[0])
    current_regime = labeler.cluster_to_label[current_cluster]

    # Prediksi T+1 dari Random Forest
    pred_regime_t1 = str(rf_clf.predict(x_vec)[0])
    proba_raw = rf_clf.predict_proba(x_vec)[0]
    classes = list(rf_clf.classes_)

    probabilities = {"SAFE": 0.0, "WARNING": 0.0, "DANGER": 0.0}
    for cls_name, p_val in zip(classes, proba_raw):
        probabilities[str(cls_name)] = round(float(p_val), 4)

    pred_vol_ratio = max(float(rf_reg.predict(x_vec)[0]), 0.0005)
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
        "current_cluster_id": current_cluster,
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


def get_latest_metrics() -> Dict[str, Any]:
    """Mengambil metrik evaluasi model terakhir (atau memicu pelatihan default jika belum ada)."""
    metrics_path = MODELS_DIR / "latest_metrics.json"
    if not metrics_path.exists():
        train_dynamic_models(DynamicConfig())
    return json.loads(metrics_path.read_text(encoding="utf-8"))
