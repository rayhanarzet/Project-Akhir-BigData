"""Konfigurasi utama aplikasi Arkadanta."""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
# Isolasi dari dataset, audit, dan model lama yang mungkin berasal dari simulasi.
DATA_DIR = BASE_DIR / "data" / "research"
DROP_ZONE_DIR = DATA_DIR / "drop_zone"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
AUDIT_LOG_PATH = DATA_DIR / "audit_logs.json"
# Antrean NiFi GetFile (Keep Source File=false). Terpisah dari drop_zone agar dataset aktif tidak dipindahkan NiFi.
NIFI_OUTBOX_DIR = Path(os.getenv("ARKADANTA_NIFI_OUTBOX", str(DATA_DIR / "nifi_outbox")))

for directory in (DATA_DIR, DROP_ZONE_DIR, PROCESSED_DIR, MODELS_DIR, NIFI_OUTBOX_DIR):
    directory.mkdir(parents=True, exist_ok=True)

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
SUPPORTED_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w"]

AVAILABLE_FEATURES = [
    # Volatilitas
    "max_volatility",
    "avg_volatility",
    "rolling_volatility",
    "spike_ratio",
    # Harga
    "log_return",
    "periodic_return",
    "hl_range",
    "co_change",
    # Teknikal
    "sma_20",
    "ema_20",
    "rsi_14",
    "bb_width",
    # Struktur Candle
    "upper_wick_ratio",
    "lower_wick_ratio",
    "body_ratio",
    # Mikrostruktur
    "volume",
    "quote_asset_volume",
    "number_of_trades",
    "buy_sell_pressure_ratio",
    "volume_zscore",
]

DEFAULT_FEATURES = [
    "max_volatility",
    "spike_ratio",
    "rsi_14",
    "volume_zscore",
    "bb_width",
    "hl_range",
]

HDFS_BASE_PATH = os.getenv(
    "ARKADANTA_HDFS_PATH", "/user/arkadanta/data/clean/crypto/"
)
HISTORICAL_HDFS_URI = os.getenv(
    "ARKADANTA_HISTORICAL_HDFS_URI", "hdfs://127.0.0.1:9000"
).rstrip("/")
HISTORICAL_HDFS_RAW_PATH = os.getenv(
    "ARKADANTA_HISTORICAL_HDFS_RAW_PATH",
    "/arkadanta/raw",
)
HISTORICAL_HDFS_OUTPUT_PATH = os.getenv(
    "ARKADANTA_HISTORICAL_HDFS_OUTPUT_PATH",
    "/tmp/arkadanta-historical/processed",
)
HISTORICAL_OUTPUT_MODE = os.getenv(
    "ARKADANTA_HISTORICAL_OUTPUT_MODE", "local"
).strip().lower()
HISTORICAL_LOCAL_OUTPUT_PATH = PROCESSED_DIR / "historical_hdfs"
# Mirror resmi Binance khusus data pasar publik; domain *.binance.com diblokir sebagian ISP Indonesia.
BINANCE_KLINES_URL = os.getenv(
    "ARKADANTA_BINANCE_KLINES_URL", "https://data-api.binance.vision/api/v3/klines"
)
BINANCE_STREAM_URL = os.getenv(
    "ARKADANTA_BINANCE_STREAM_URL", "wss://data-stream.binance.vision/stream"
)
CORS_ORIGINS = os.getenv(
    "ARKADANTA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
