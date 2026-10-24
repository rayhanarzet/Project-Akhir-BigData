"""FastAPI Server Utama Arkadanta (Serving Layer - Bab 3.3)."""

import sys
from pathlib import Path

# Pastikan direktori arkadanta ada di sys.path untuk reloader spawn process
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analytics_routes import router as analytics_router
from backend.api.ingestion_routes import router as ingestion_router
from backend.api.model_routes import router as model_router
from backend.api.prediction_routes import router as prediction_router
from backend.config import AVAILABLE_FEATURES, DEFAULT_SYMBOLS, SUPPORTED_TIMEFRAMES
from data.sample_generator import ensure_sample_data_exists

app = FastAPI(
    title="Arkadanta Big Data Intelligence API",
    description="Dynamic Big Data Intelligence Pipeline untuk Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto Berbasis Lambda Architecture",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    ensure_sample_data_exists(DEFAULT_SYMBOLS)


@app.get("/")
def root():
    return {
        "project": "Arkadanta",
        "architecture": "Lambda Architecture (Batch + Speed + Serving Layer)",
        "supported_symbols": DEFAULT_SYMBOLS,
        "supported_timeframes": SUPPORTED_TIMEFRAMES,
        "available_features": AVAILABLE_FEATURES,
    }


app.include_router(ingestion_router)
app.include_router(analytics_router)
app.include_router(model_router)
app.include_router(prediction_router)
