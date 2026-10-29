# Kontrak Integrasi Tim Arkadanta (Orang 1 <-> Orang 2)

Dokumen ini mendefinisikan titik temu (data, skema, dan API) antara **Orang 1 (Data Pipeline & Big Data)** dan **Orang 2 (Analytics, Machine Learning & Dashboard)**.

**Revisi ML v3:** label relatif memakai GaussianMixture; prediksi memakai HistGradientBoostingClassifier/Regressor. Konfigurasi: `gmm_components`, `gb_max_iter`, `gb_max_depth`, `gb_learning_rate`. Artefak berada di `data/research/models/gmm_hgb_v3/`. Semua jalur menggunakan histori maksimal 365 hari dan target dengan selisih timestamp tepat sesuai horizon. Spark memproses fitur; training GMM/HGB berlangsung di driver lokal dengan batas 500.000 baris.

**Pengiriman v3:** outbox berada di `data/research/nifi_outbox/v3/symbol=.../year=.../month=...`. Kolom tetap mengacu pada [skema NiFi](nifi/candle-v3.avsc), dengan `ingestion_version` integer 64 bit, `ingested_at` UTC, dan `source_name`. Replay memakai nama berkas event yang sama; PutHDFS harus `ignore`. HDFS bersih berada di `/user/arkadanta/data/clean/crypto/v3/`. Revisi terbesar menang; konflik isi dengan revisi sama ditolak. CSV tanpa simbol harus memiliki identitas dari nama file/partisi.

**Audit dan kualitas:** tidak ada imputasi OHLCV; baris non-finite, kosong, belum selesai, atau di luar grid 5m ditolak. `error_reasons` dapat memiliki kunci tambahan, dan `source_sha256` opsional. Audit lengkap JSONL tidak dibatasi; API baseline hanya mengirim 20 catatan terakhir. `LOCAL_DATA_READY` mengacu pada dataset lokal, bukan status HDFS. `integration` menyajikan pemeriksaan terpisah backend/stream/port NiFi/WebHDFS/antrean; tidak menjanjikan konfirmasi pengiriman tiap candle.

**Evaluasi dan keluaran:** `volatility_event_validation` menilai event range aktual > persentil 95 target latih; `walk_forward_volatility` memuat hingga tiga periode uji regressor. SAFE bukan jaminan aman. Prediksi menyertakan waktu `target_start` dan `target_end` UTC serta `illustrative_upper_bound`/`illustrative_lower_bound`; `resistance_level` dan `stop_loss_level` merupakan alias kompatibilitas untuk batas ilustratif, tanpa klaim resistance/stop loss tervalidasi. Korelasi tanpa pasangan cukup adalah `null`, disertai `paired_observations`, bukan diisi nol.

---

## 1. Kontrak Skema Data OHLCV Standar (Output Orang 1 -> Input Orang 2)

Setelah melalui *Dynamic Pipeline Controller* milik Orang 1, data yang disimpan di `data/research/drop_zone/`, HDFS (`/user/arkadanta/data/clean/crypto/v3/`), maupun hasil agregasi PySpark wajib mengikuti skema berikut:

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
| `quote_asset_volume` | `float64` / `double` | Opsional | Volume dalam USDT; tetap kosong bila sumber tidak menyediakan |
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
  "selected_pipeline": "CSVParser -> SchemaAliasMapper -> Closed5mFiniteValidator -> DedupSorter -> DurableOutbox",
  "column_mapping": {
    "open_time": "timestamp",
    "symbol": "coin_symbol",
    "vol": "volume"
  },
  "symbols_detected": ["BTCUSDT"],
  "rows_before": 1500,
  "rows_after": 1482,
  "duplicates_removed": 12,
  "imputed_ohlc_rows": 0,
  "imputed_volume_rows": 0,
  "rejected_rows": 6,
  "error_reasons": {
    "high_less_than_low": 4,
    "non_positive_price": 2,
    "negative_volume": 0,
    "invalid_timestamp": 0
  },
  "drop_zone_path": "data/drop_zone/BTCUSDT_clean.csv",
  "hdfs_target_path": "/user/arkadanta/data/clean/crypto/v3/symbol=BTCUSDT/",
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
| `/api/ml/predict` | `POST` | **Orang 2** | Inferensi kategori/volatilitas T+1, periode target UTC, batas gejolak ilustratif |
| `/api/models/metrics` | `GET` | **Orang 2** | Silhouette score, centroid table, Accuracy/Precision/Recall/F1, MAE/RMSE |
| `/api/live-monitor` | `GET` | **Orang 2** | Live Market Shield 5m + prediksi aktif $T+1$ |
