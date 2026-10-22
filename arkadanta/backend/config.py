"""Konfigurasi utama aplikasi Arkadanta."""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DROP_ZONE_DIR = DATA_DIR / "drop_zone"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
AUDIT_LOG_PATH = DATA_DIR / "audit_logs.json"

for directory in (DATA_DIR, DROP_ZONE_DIR, PROCESSED_DIR, MODELS_DIR):
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
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
