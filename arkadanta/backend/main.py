"""FastAPI Server Utama Arkadanta (Serving Layer - Bab 3.3)."""

import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

# Pastikan direktori arkadanta ada di sys.path untuk reloader spawn process
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from data.storage import ResearchDataError, recover_pending_writes

from backend.api.analytics_routes import router as analytics_router
from backend.api.ingestion_routes import router as ingestion_router
from backend.api.historical_hdfs_routes import router as historical_hdfs_router
from backend.api.model_routes import router as model_router
from backend.api.prediction_routes import router as prediction_router
from backend.api.market_routes import router as market_router
from backend.market_stream import market_stream
from backend.config import AVAILABLE_FEATURES, CORS_ORIGINS, DEFAULT_SYMBOLS, SUPPORTED_TIMEFRAMES

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(recover_pending_writes)
    yield
    await market_stream.stop()


app = FastAPI(
    title="Arkadanta Big Data Intelligence API",
    description="Dynamic Big Data Intelligence Pipeline untuk Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto Berbasis Lambda Architecture",
    version="1.0.0",
    lifespan=lifespan,
)

# Dashboard memakai proxy Vite (same-origin); CORS hanya untuk origin dashboard lokal.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(ResearchDataError)
async def research_data_error_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


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
app.include_router(historical_hdfs_router)
app.include_router(analytics_router)
app.include_router(model_router)
app.include_router(prediction_router)
app.include_router(market_router)
