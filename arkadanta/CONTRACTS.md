# Kontrak Integrasi Tim Arkadanta (Orang 1 <-> Orang 2)

Dokumen ini mendefinisikan titik temu (data, skema, dan API) antara **Orang 1 (Data Pipeline & Big Data)** dan **Orang 2 (Analytics, Machine Learning & Dashboard)**.

**Revisi ML:** label risiko memakai GaussianMixture; prediksi memakai HistGradientBoostingClassifier/Regressor. Konfigurasi: `gmm_components`, `gb_max_iter`, `gb_max_depth`, `gb_learning_rate`. Respons metrik: `gmm_metrics` (silhouette nullable, BIC, AIC, mean komponen); respons prediksi: `current_component_id`. Model lama tidak dibaca, artefak baru berada di `data/research/models/gmm_hgb_v2/`. Spark memproses fitur; training GMM/HGB berlangsung di driver lokal dengan batas 500.000 baris.

---

## 1. Kontrak Skema Data OHLCV Standar (Output Orang 1 -> Input Orang 2)

Setelah melalui *Dynamic Pipeline Controller* milik Orang 1, data yang disimpan di `data/drop_zone/`, HDFS (`/user/arkadanta/data/clean/crypto/`), maupun hasil agregasi PySpark wajib mengikuti skema berikut:

### 1.1 Skema OHLCV Dasar (5 Menit)
| Nama Kolom | Tipe Data | Wajib? | Deskripsi |
|---|---|---|---|
| `timestamp` | `datetime64[ns, UTC]` / ISO-8601 / epoch ms | Ya | Waktu pembukaan candle (UTC) |
| `coin_symbol` | `string` | Ya | Simbol pasangan aset, misal: `BTCUSDT`, `ETHUSDT`, `BNBUSDT`, `ADAUSDT` |
| `open` | `float64` / `double` | Ya | Harga pembukaan (`> 0`) |
| `high` | `float64` / `double` | Ya | Harga tertinggi (`>= low`, `>= open`, `>= close`) |
| `low` | `float64` / `double` | Ya | Harga terendah (`> 0`, `<= high`) |
| `close` | `float64` / `double` | Ya | Harga penutupan (`> 0`) |
| `volume` | `float64` / `double` | Ya | Volume aset dasar (`>= 0.0`) |
| `quote_asset_volume` | `float64` / `double` | Opsional | Volume dalam USDT (default `volume * close` bila tidak tersedia) |
| `number_of_trades` | `int64` / `long` | Opsional | Jumlah transaksi dalam candle |
| `taker_buy_base_volume` | `float64` / `double` | Opsional | Volume pembelian agresif (taker buy) aset dasar |
| `taker_buy_quote_volume` | `float64` / `double` | Opsional | Volume pembelian agresif (taker buy) aset kuotasi |

### 1.2 Skema Hasil Agregasi Multi-Timeframe (`5m`, `15m`, `1h`, `4h`, `1d`, `1w`)
Selain kolom OHLCV di atas (dengan `open` pertama kronologis, `high` maksimum, `low` minimum, `close` terakhir kronologis, dan `volume` total), agregator menyediakan:
- `log_return` (`double`): $\ln(\text{close}_t / \text{close}_{t-1})$
- `max_volatility` (`double`): $(\text{high} - \text{low}) / \text{low}$ atau maksimum volatilitas intra-window
- `avg_volatility` (`double`): Rata-rata volatilitas intra-window

---

## 2. Kontrak Laporan Kualitas Data & Status Pipeline (Output Orang 1 -> UI Tab 1 Orang 2)

Endpoint `POST /api/ingestion/upload` dan `POST /api/ingestion/live-sync` mengembalikan JSON dengan struktur `IngestionAuditReport`:

```json
{
  "run_id": "ing_20261022_001",
  "timestamp": "2026-10-22T07:30:00Z",
  "source_name": "btcusdt_5m_sample.csv",
  "format_detected": "CSV",
  "selected_pipeline": "StandardCSVParser -> AliasMapper -> OHLCVSanityValidator -> ForwardFillImputer",
  "column_mapping": {
    "open_time": "timestamp",
    "symbol": "coin_symbol",
    "vol": "volume"
  },
  "symbols_detected": ["BTCUSDT"],
  "rows_before": 1500,
  "rows_after": 1482,
  "duplicates_removed": 12,
  "imputed_ohlc_rows": 5,
  "imputed_volume_rows": 3,
  "rejected_rows": 6,
  "error_reasons": {
    "high_less_than_low": 4,
    "non_positive_price": 2,
    "negative_volume": 0,
    "invalid_timestamp": 0
  },
  "drop_zone_path": "data/drop_zone/BTCUSDT_clean.csv",
  "hdfs_target_path": "/user/arkadanta/data/clean/crypto/symbol=BTCUSDT/",
  "nifi_hdfs_status": "QUEUED_DROP_ZONE",
  "quality_score_pct": 98.8
}
```

---

## 3. Pembagian Endpoint FastAPI (Bab 3.3)

| Endpoint | Method | Penanggung Jawab | Keterangan |
|---|---|---|---|
| `/api/ingestion/upload` | `POST` | Orang 1 (di-render di Tab 1 oleh Orang 2) | Upload CSV/JSON, validasi, normalisasi, simpan ke drop zone |
| `/api/ingestion/live-sync` | `POST` | Orang 1 & 2 | Tarik candle live dari Binance `/api/v3/klines` |
| `/api/historical-baseline` | `GET` | Orang 1 & 2 | Ringkasan ketersediaan data bersih & status audit terbaru |
| `/api/analytics/run` | `POST` | **Orang 2** | Agregasi timeframe, feature engineering dinamis, deteksi anomali |
| `/api/analytics/correlation` | `GET` | **Orang 2** | Korelasi Pearson, rolling correlation, lag correlation, market risk |
| `/api/ml/train` | `POST` | **Orang 2** | GMM component risk labeling (`SAFE`/`WARNING`/`DANGER`) + HistGradientBoosting $T+1$ |
| `/api/ml/predict` | `POST` | **Orang 2** | Inferensi risiko $T+1$, volatilitas $T+1$, Resistance & Stop Loss |
| `/api/models/metrics` | `GET` | **Orang 2** | Silhouette score, centroid table, Accuracy/Precision/Recall/F1, MAE/RMSE |
| `/api/live-monitor` | `GET` | **Orang 2** | Live Market Shield 5m + prediksi aktif $T+1$ |
