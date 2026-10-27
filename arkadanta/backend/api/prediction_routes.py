"""[ORANG 2] Endpoint Inferensi Prediksi T+1 dan Live Market Monitor (Bab 3.2, 3.3 & 5.6)."""

from fastapi import APIRouter, Query

from backend.analytics.feature_engineering import compute_dynamic_features
from backend.ml.model_predictor import predict_next_period
from backend.schemas import PredictRequest
from data.storage import load_clean_ohlcv

router = APIRouter(tags=["Prediction & Live Monitor (Orang 2)"])


@router.post("/api/ml/predict")
def predict_endpoint(req: PredictRequest):
    """Menghasilkan prediksi kelas risiko T+1, probabilitas, estimasi volatilitas, Resistance, dan Stop Loss."""
    return predict_next_period(req)


@router.get("/api/live-monitor")
def live_monitor_endpoint(
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("5m", pattern="^(5m|15m|1h|4h|1d|1w)$"),
):
    """Menyajikan candle live terbaru beserta prediksi T+1 dari model aktif (Speed Layer)."""
    sym = symbol.upper()
    df_5m = load_clean_ohlcv(sym)
    df_feat_5m = compute_dynamic_features(df_5m.tail(120))
    df_feat_5m["timestamp"] = df_feat_5m["timestamp"].astype(str)
    df_feat_5m = df_feat_5m.astype(object).where(df_feat_5m.notna(), None)

    prediction = predict_next_period(
        PredictRequest(symbol=sym, timeframe=timeframe, target_horizon=1)
    )

    return {
        "symbol": sym,
        "timeframe": timeframe,
        "live_prediction": prediction,
        "recent_5m_candles": df_feat_5m.tail(60).to_dict(orient="records"),
    }
