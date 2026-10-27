# Penjelasan Detail Project Arkadanta

> Dokumen ini menjelaskan **apa yang dilakukan project**, **bagaimana alur kerjanya**, dan **file mana yang bertanggung jawab** untuk setiap langkah. Untuk cara menjalankan layanan (HDFS, NiFi, backend, dashboard), lihat `START.md`.

---

## Daftar isi

1. [Ringkasan satu paragraf](#1-ringkasan-satu-paragraf)
2. [Istilah dasar yang perlu dipahami](#2-istilah-dasar-yang-perlu-dipahami)
3. [Gambaran arsitektur](#3-gambaran-arsitektur)
4. [Struktur folder](#4-struktur-folder)
5. [Alur 1 — Data masuk (Ingestion)](#5-alur-1--data-masuk-ingestion)
6. [Alur 2 — Penyimpanan](#6-alur-2--penyimpanan)
7. [Alur 3 — Agregasi timeframe](#7-alur-3--agregasi-timeframe)
8. [Alur 4 — Feature engineering](#8-alur-4--feature-engineering)
9. [Alur 5 — Deteksi anomali](#9-alur-5--deteksi-anomali)
10. [Alur 6 — Korelasi lintas aset](#10-alur-6--korelasi-lintas-aset)
11. [Alur 7 — Machine Learning](#11-alur-7--machine-learning)
12. [Alur 8 — Prediksi live](#12-alur-8--prediksi-live)
13. [Batch layer: Spark, NiFi, HDFS](#13-batch-layer-spark-nifi-hdfs)
14. [Daftar endpoint API](#14-daftar-endpoint-api)
15. [Dashboard (frontend)](#15-dashboard-frontend)
16. [Konfigurasi dinamis (`DynamicConfig`)](#16-konfigurasi-dinamis-dynamicconfig)
17. [Testing](#17-testing)
18. [Yang sudah dan belum tersedia](#18-yang-sudah-dan-belum-tersedia)
19. [Urutan demo yang disarankan](#19-urutan-demo-yang-disarankan)

---

## 1. Ringkasan satu paragraf

**Arkadanta** adalah pipeline Big Data yang mengambil data harga kripto (BTCUSDT, ETHUSDT, BNBUSDT, ADAUSDT), membersihkannya, menghitung indikator pasar, mendeteksi kejadian tidak normal (anomali), lalu memakai machine learning untuk **menilai kondisi pasar sebagai SAFE, WARNING, atau DANGER** dan **memprediksi kondisi serta volatilitas pada periode berikutnya (T+1)**. Project ini **tidak memprediksi harga** naik atau turun. Yang diprediksi adalah tingkat risiko/gejolak, karena harga kripto mendekati *random walk* dan hampir tidak bisa ditebak, sedangkan volatilitas memiliki pola yang lebih stabil.

---

## 2. Istilah dasar yang perlu dipahami

| Istilah | Arti sederhana |
|---|---|
| **Candle / kline** | Ringkasan perdagangan dalam satu interval waktu (di sini dasar 5 menit). |
| **OHLCV** | *Open, High, Low, Close, Volume*: harga awal, tertinggi, terendah, akhir, dan jumlah koin yang diperdagangkan dalam satu candle. |
| **Timeframe** | Ukuran candle: `5m`, `15m`, `1h`, `4h`, `1d`, `1w`. Candle besar dibuat dengan menggabungkan candle 5 menit. |
| **Volatilitas** | Seberapa besar harga bergerak naik-turun. Di project ini dihitung terutama dari `(high - low) / low`. |
| **Fitur** | Angka turunan dari OHLCV yang dipakai analisis/ML, misalnya RSI dan Bollinger Band. |
| **Anomali** | Candle yang perilakunya jauh dari biasanya, misalnya lonjakan volatilitas ekstrem. |
| **Rezim risiko** | Status pasar: **SAFE** (tenang), **WARNING** (mulai bergejolak), **DANGER** (sangat bergejolak). |
| **T dan T+1** | T = periode sekarang, T+1 = satu periode berikutnya (bisa juga T+horizon). |
| **Lambda Architecture** | Desain data dengan dua jalur: *speed layer* (cepat, data terbaru) dan *batch layer* (lambat, data historis besar). |
| **HDFS** | *Hadoop Distributed File System*, penyimpanan file terdistribusi untuk data besar. |
| **NiFi** | Alat untuk memindahkan dan mengalirkan data antar sistem (misalnya dari folder lokal ke HDFS). |
| **PySpark** | Versi Python dari Apache Spark, mesin pemrosesan data besar secara paralel. |

---

## 3. Gambaran arsitektur

```
                         ┌────────────────────────────────────────────┐
                         │                SUMBER DATA                 │
                         │  Binance WebSocket · Binance REST · Upload │
                         └───────────────┬────────────────────────────┘
                                         │
                       ┌─────────────────▼─────────────────┐
                       │   INGESTION (backend/ingestion/)  │
                       │ deteksi format → mapping kolom →  │
                       │ validasi → dedup → imputasi →     │
                       │ sanity check → laporan audit      │
                       └─────────────────┬─────────────────┘
                                         │
                       ┌─────────────────▼─────────────────┐
                       │ PENYIMPANAN data/research/        │
                       │ drop_zone/{SYMBOL}_5m_clean.csv   │──── (opsional) NiFi ──► HDFS
                       └───────┬───────────────────┬───────┘
                               │                   │
          SPEED LAYER          │                   │          BATCH LAYER
       (pandas + sklearn)      │                   │      (PySpark, spark_jobs/)
                               ▼                   ▼
                ┌──────────────────────┐   ┌──────────────────────────┐
                │ Agregasi timeframe   │   │ Baca CSV dari HDFS       │
                │ Feature engineering  │   │ Agregasi + fitur (Spark) │
                │ Deteksi anomali      │   │ Training model           │
                │ Korelasi lintas aset │   │ Simpan hasil + metrik    │
                │ GMM + HGB (train)    │   └────────────┬─────────────┘
                │ Prediksi T+1         │                │
                └──────────┬───────────┘                │
                           │                            │
                    ┌──────▼────────────────────────────▼──────┐
                    │     FastAPI (backend/main.py, port 8000) │
                    └──────────────────┬───────────────────────┘
                                       │ REST + SSE
                    ┌──────────────────▼───────────────────────┐
                    │ Dashboard React (frontend/, port 5173)   │
                    │ Tab1 Ingestion · Tab2 Analytics · Tab3 ML│
                    │ Tab4 Historis HDFS · Panel Live Market   │
                    └──────────────────────────────────────────┘
```

---

## 4. Struktur folder

```
Project-Akhir-BigData/
├── START.md                    panduan menjalankan (Windows + WSL)
├── Konteks/                    proposal proyek (spesifikasi resmi)
├── run-all.ps1 / run-all.bat   launcher Windows (jangan dipakai untuk susunan WSL)
└── arkadanta/
    ├── backend/
    │   ├── main.py             aplikasi FastAPI, daftar router, lifespan
    │   ├── config.py           path data, simbol, timeframe, daftar fitur, path HDFS
    │   ├── schemas.py          kontrak request/response (Pydantic)
    │   ├── market_stream.py    WebSocket Binance → harga live + simpan candle selesai
    │   ├── scheduler.py        cron penarik data Binance REST berkala
    │   ├── ingestion/          upload CSV/JSON → data bersih + audit
    │   ├── analytics/          agregasi, fitur, anomali, korelasi
    │   ├── ml/                 pelabelan GMM, training HGB, evaluasi, prediksi
    │   └── api/                endpoint REST per domain
    ├── data/
    │   ├── storage.py          baca/tulis dataset & audit log (atomik, thread-safe)
    │   └── research/           dataset aktif, model, audit log (dibuat otomatis)
    ├── spark_jobs/             versi PySpark: agregasi, fitur, batch, job historis HDFS
    ├── src/                    pipeline lama/alternatif (parser, cleaner, upload_to_hdfs)
    ├── frontend/               dashboard React + TypeScript + Vite + Tailwind
    └── tests/                  pytest backend
```

---

## 5. Alur 1 — Data masuk (Ingestion)

Ada **tiga pintu masuk** data. Semua berakhir di penyimpanan yang sama.

### 5.1 Upload file CSV/JSON (Tab 1)

Endpoint `POST /api/ingestion/upload` → `backend/ingestion/dynamic_pipeline.py::run_dynamic_ingestion_pipeline`.

Langkah-langkahnya:

1. **Deteksi format** (`format_detector.py`): CSV atau JSON, dari nama file dan 512 byte pertama isi file.
2. **Parsing** (`processors/csv_processor.py` atau `processors/json_processor.py`). JSON bertingkat diratakan.
3. **Mapping & validasi skema** (`schema_validator.py`). Nama kolom yang berbeda-beda disamakan lewat alias, misalnya:
   - `open_time`, `time`, `date`, `datetime` → `timestamp`
   - `symbol`, `pair`, `ticker` → `coin_symbol`
   - `o/h/l/c` → `open/high/low/close`, `vol` → `volume`

   Kolom wajib: `timestamp, coin_symbol, open, high, low, close, volume`. Pengguna juga bisa mengirim mapping kustom dalam JSON.
4. **Normalisasi timestamp ke UTC.** Epoch otomatis dikenali satuannya (detik, milidetik, mikrodetik, nanodetik) dari besarnya angka. Timestamp yang tidak bisa dibaca dibuang dan dicatat sebagai `invalid_timestamp`.
5. **Konversi numerik** untuk harga dan volume.
6. **Deduplikasi** berdasarkan `(coin_symbol, timestamp)`; yang terakhir dipertahankan.
7. **Imputasi:** OHLC yang kosong diisi *forward-fill* per aset; volume kosong diisi `0`.
8. **Sanity check.** Baris ditolak jika:
   - `high < low`, atau `high` lebih kecil dari open/close, atau `low` lebih besar dari open/close;
   - ada harga `<= 0`;
   - volume negatif.
9. **Simpan per simbol** ke `data/research/drop_zone/{SYMBOL}_5m_clean.csv`.
10. **Sinkron ke HDFS (opsional):** hanya jika env `ARKADANTA_ENABLE_HDFS=1` dan perintah `hdfs` tersedia. Statusnya `SYNCED`, `QUEUED_DROP_ZONE`, atau `LOCAL_FALLBACK`.
11. **Laporan audit** (`IngestionAuditReport`) disimpan ke `audit_logs.json`. Isinya antara lain: jumlah baris sebelum/sesudah, duplikat dibuang, baris diimputasi, baris ditolak beserta alasannya, dan `quality_score_pct = rows_after / rows_before × 100`.

### 5.2 Binance WebSocket live (panel Live Market)

File: `backend/market_stream.py`.

- Satu koneksi ke `wss://stream.binance.com:9443` untuk stream `kline_5m` keempat simbol, dipakai bersama oleh semua tab dashboard yang terbuka.
- Setiap pesan divalidasi (`parse_kline`): simbol dan interval benar, angka finite, harga positif, rentang OHLC konsisten, volume tidak negatif.
- Harga terbaru diteruskan ke dashboard lewat **Server-Sent Events** (`GET /api/market/stream`).
- **Hanya candle yang sudah selesai** (`x = true`) yang disimpan (`persist_closed_candle`). Candle yang masih berjalan tidak disimpan, supaya data penelitian tidak berisi candle setengah jadi.
- Jika koneksi putus, sistem mencoba lagi dengan jeda yang naik bertahap (1, 2, 4, … maksimal 30 detik).
- Klien yang lambat menerima event `overflow` dan tersambung ulang, bukan membuat server menumpuk antrean.
- Stream berhenti otomatis ketika tidak ada lagi dashboard yang terhubung.

### 5.3 Binance REST: sync manual dan cron

- `POST /api/ingestion/live-sync`: menarik `N` candle terakhir dari `https://api.binance.com/api/v3/klines` sekali jalan.
- `backend/scheduler.py::BinanceCronScheduler`: thread latar yang menarik data secara berkala. Diatur lewat `POST /api/ingestion/cron-config` (aktif/nonaktif, interval menit, simbol, limit), statusnya dibaca lewat `GET /api/ingestion/cron-status`.

---

## 6. Alur 2 — Penyimpanan

File: `data/storage.py`. Lokasi dasar: `arkadanta/data/research/` (diatur di `backend/config.py`).

| Path | Isi |
|---|---|
| `data/research/drop_zone/{SYMBOL}_5m_clean.csv` | Dataset bersih 5 menit per simbol |
| `data/research/audit_logs.json` | Riwayat laporan audit ingestion |
| `data/research/models/gmm_hgb_v1/` | Model terlatih (`.joblib`) dan metrik (`.json`) |
| `data/research/processed/historical_hdfs/` | Output job historis HDFS (mode lokal) |

Prinsip penting:

- **Tidak ada data simulasi.** Jika data belum ada, API melempar `ResearchDataError` dan dashboard menampilkan pesan error, bukan angka palsu.
- **Penulisan atomik:** file ditulis ke file sementara lalu di-*rename*, sehingga file tidak pernah setengah tertulis kalau proses mati di tengah jalan.
- **Thread-safe:** penulisan dikunci dengan `RLock`, karena WebSocket, cron, dan upload bisa menulis bersamaan.
- **Merge + dedup:** candle baru digabung dengan dataset lama tanpa duplikasi.

---

## 7. Alur 3 — Agregasi timeframe

File: `backend/analytics/timeframe_aggregator.py::aggregate_timeframe` (versi Spark: `spark_jobs/dynamic_aggregation.py`).

Candle 5 menit digabung menjadi timeframe yang lebih besar:

| Kolom hasil | Cara menghitung |
|---|---|
| `open` | open candle 5m **pertama** dalam bucket |
| `high` | **maksimum** high |
| `low` | **minimum** low |
| `close` | close candle 5m **terakhir** |
| `volume`, `quote_asset_volume`, `number_of_trades`, `taker_buy_*` | **jumlah** |
| `max_volatility` | volatilitas candle 5m **tertinggi** di dalam bucket |
| `avg_volatility` | **rata-rata** volatilitas candle 5m di dalam bucket |

Detail penting:

- Volatilitas per candle 5m = `(high - low) / low`.
- Minggu (`1w`) dimulai Senin 00:00 UTC, sama seperti Binance.
- **Bucket terakhir yang belum lengkap dibuang.** Contoh: jika sekarang pukul 10:20, candle 1 jam 10:00–11:00 belum selesai; volume dan volatilitasnya akan tampak terlalu rendah, jadi tidak dipakai.
- Filter `start_date` / `end_date` diterapkan sebelum agregasi.

---

## 8. Alur 4 — Feature engineering

File: `backend/analytics/feature_engineering.py::compute_dynamic_features` (versi Spark: `spark_jobs/feature_pipeline.py`). Dihitung **per simbol**, berurutan menurut waktu.

### Volatilitas

| Fitur | Rumus / arti |
|---|---|
| `max_volatility` | Volatilitas 5m tertinggi di dalam candle (dari agregasi) |
| `avg_volatility` | Rata-rata volatilitas 5m di dalam candle |
| `rolling_volatility` | Standar deviasi `log_return` dalam jendela `rolling_window` |
| `spike_ratio` | `max_volatility / rata-rata max_volatility` jendela terakhir. Nilai > 1 berarti lebih bergejolak dari biasanya. |

### Harga

| Fitur | Rumus |
|---|---|
| `log_return` | `ln(close_t / close_{t-1})` |
| `periodic_return` | `close_t / close_{t-1} - 1` |
| `hl_range` | `(high - low) / low` |
| `co_change` | `(close - open) / open` |

### Teknikal

| Fitur | Arti |
|---|---|
| `sma_20` | Rata-rata close sederhana `ma_period` candle |
| `ema_20` | Rata-rata close eksponensial `ma_period` candle |
| `rsi_14` | *Relative Strength Index* (0–100). > 70 cenderung *overbought*, < 30 *oversold* |
| `bb_width` | Lebar Bollinger Band `(upper - lower) / sma`. Makin lebar, makin volatil |

### Struktur candle

| Fitur | Arti |
|---|---|
| `upper_wick_ratio` | Panjang sumbu atas / rentang candle |
| `lower_wick_ratio` | Panjang sumbu bawah / rentang candle |
| `body_ratio` | Panjang badan candle / rentang candle |

### Mikrostruktur pasar

| Fitur | Arti |
|---|---|
| `volume` | Volume koin |
| `quote_asset_volume` | Volume dalam USDT |
| `number_of_trades` | Jumlah transaksi |
| `buy_sell_pressure_ratio` | `taker_buy_base_volume / volume`. > 0.5 berarti pembeli agresif lebih dominan |
| `volume_zscore` | Seberapa jauh volume dari rata-ratanya, dalam satuan standar deviasi |

> **Catatan:** fitur mikrostruktur hanya ada jika sumber data menyediakan kolomnya (data Binance lengkap). CSV sederhana yang hanya berisi OHLCV tidak punya kolom ini. Sistem **tidak mengisinya dengan nol**; fitur tersebut akan ditolak dengan pesan error jika dipilih.

Fitur default untuk ML: `max_volatility, spike_ratio, rsi_14, volume_zscore, bb_width, hl_range`.

---

## 9. Alur 5 — Deteksi anomali

File: `backend/analytics/anomaly_detector.py::detect_anomalies`. Dipanggil dari `POST /api/analytics/run`. Target utama: `max_volatility`.

| Metode | Cara kerja | Kausal? |
|---|---|---|
| `adaptive_quantile` (default) | Anomali jika `max_volatility` ≥ kuantil (mis. 95%) dari **semua data sebelumnya** | Ya |
| `rolling_zscore` | Hitung z-score terhadap rata-rata dan std `rolling_window` candle sebelumnya. Anomali jika \|z\| ≥ ambang, atau \|`volume_zscore`\| ≥ ambang + 0.5 | Ya |
| `iqr` | Batas atas = Q3 + k × IQR dari data sebelumnya. Anomali jika melewati batas | Ya |
| `gmm` | Gaussian Mixture 3 komponen di-*fit* pada seluruh data; candle dengan *likelihood* paling rendah (kuantil teratas) dianggap anomali | Tidak |

**Kausal** artinya ambang hanya memakai data **sampai t-1** (`shift(1)`). Akibatnya, label anomali candle lama tidak berubah ketika data baru masuk, dan tidak ada "mengintip masa depan". Metode `gmm` sengaja ditandai tidak kausal karena dipakai untuk analisis retrospektif, bukan alarm real-time.

Endpoint ini juga mengembalikan **historical factor attribution** (`compute_historical_factor_attribution`): untuk setiap fitur, lag mana (T-1, T-2, …) yang paling berkorelasi dengan risiko saat ini.

---

## 10. Alur 6 — Korelasi lintas aset

File: `backend/analytics/correlation_analyzer.py`. Endpoint: `GET /api/analytics/correlation`.

Menghasilkan:

- **Matriks korelasi Pearson** antar keempat aset.
- **Rolling correlation** antara dua aset (`base_symbol` vs `target_symbol`) dalam jendela bergerak.
- **Lag correlation**, untuk menjawab pertanyaan seperti "apakah BTC bergerak duluan, lalu ETH menyusul N periode kemudian?".
- **Market-wide risk score** dan rezimnya: skor risiko gabungan seluruh pasar dari waktu ke waktu.

---

## 11. Alur 7 — Machine Learning

File utama: `backend/ml/model_trainer.py::train_from_features`. Endpoint: `POST /api/ml/train` (Tab 3).

### 11.1 Masalah yang diselesaikan

Data OHLCV **tidak punya label** "aman" atau "bahaya". Model klasifikasi biasa butuh label. Solusinya adalah dua tahap:

```
 fitur ──► [Tahap 1] GMM (tanpa label)  ──► label SAFE/WARNING/DANGER saat T
                                                    │
                                                    ▼ geser ke depan (shift -horizon)
 fitur ──► [Tahap 2] HistGradientBoosting ──► prediksi label & volatilitas saat T+1
```

### 11.2 Tahap 1 — Pelabelan dengan Gaussian Mixture

File: `backend/ml/risk_labeler.py::DynamicRiskLabeler`.

1. Fitur distandarisasi dengan `StandardScaler` (rata-rata 0, std 1).
2. `GaussianMixture` (default 3 komponen, `covariance_type="full"`, `n_init=5`, inisialisasi `random_from_data`) mengelompokkan candle yang mirip.
3. **Masalahnya:** ID cluster dari GMM (0, 1, 2) acak dan tidak bermakna. Cluster 0 belum tentu "aman".
4. **Solusinya:** untuk setiap pusat cluster (centroid) dihitung **skor risiko gabungan** berbobot:
   - fitur volatilitas (`max_volatility`, `avg_volatility`, `rolling_volatility`, `hl_range`, `bb_width`): bobot **1.5**
   - `spike_ratio`, `volume_zscore`: bobot **1.2**
   - `rsi_14`: bobot **0.6**, memakai nilai absolut karena RSI ekstrem ke atas maupun ke bawah sama-sama berisiko
   - fitur lain: bobot **0.8**
5. Cluster diurutkan dari skor terendah ke tertinggi: **SAFE → WARNING → DANGER**. Jika komponen lebih dari 3, yang terendah SAFE, tertinggi DANGER, sisanya WARNING.
6. Metrik kualitas yang dicatat: **BIC**, **AIC** (makin kecil makin baik), dan **silhouette score** (−1 sampai 1; makin tinggi, cluster makin terpisah).

### 11.3 Tahap 2 — Prediksi T+horizon dengan HistGradientBoosting

1. Target dibuat dengan menggeser label dan volatilitas ke belakang:
   - `target_risk = label pada T + horizon`
   - `target_volatility = max_volatility pada T + horizon`
2. Dua model dilatih:
   - `HistGradientBoostingClassifier` (dengan `class_weight="balanced"`, karena DANGER biasanya jarang) → memprediksi rezim.
   - `HistGradientBoostingRegressor` → memprediksi volatilitas.
3. Parameter yang bisa diatur: `gb_max_iter`, `gb_max_depth`, `gb_learning_rate`.

### 11.4 Validasi temporal dan embargo (mencegah kebocoran data)

Data **tidak diacak**. Data latih selalu dari masa lalu, data uji dari masa sesudahnya:

```
|──────────── data latih ────────────|─ embargo ─|────── data uji ──────|
 waktu lama                            (horizon)               waktu baru
```

- `split = (jumlah_data - horizon) × train_ratio`.
- GMM hanya di-*fit* pada bagian latih, sehingga definisi SAFE/WARNING/DANGER tidak dipengaruhi data uji.
- **Embargo** sepanjang `horizon`: target baris latih terakhir berada pada waktu sebelum fitur baris uji pertama. Tanpa embargo, label latih bisa "melihat" periode uji.
- Validasi minimum: data harus ≥ 30 + horizon candle, dan data latih harus memiliki minimal 2 kelas risiko. Jika tidak, training dibatalkan dengan pesan yang jelas.

### 11.5 Evaluasi

File: `backend/ml/model_evaluator.py`.

| Jenis | Metrik |
|---|---|
| Klasifikasi | accuracy, precision/recall/F1 macro, metrik per kelas, confusion matrix |
| Regresi | MAE, RMSE |
| Clustering | silhouette, BIC, AIC, distribusi rezim |
| Interpretasi | **permutation importance** pada data uji (skor F1 macro): seberapa besar F1 turun jika satu fitur diacak |

### 11.6 Model yang disimpan

Setelah evaluasi, model **dilatih ulang pada semua data yang punya target** (definisi label GMM tetap sama), supaya periode paling baru ikut dipelajari untuk prediksi live. Metrik yang dilaporkan tetap berasal dari model holdout.

Bundle disimpan di `data/research/models/gmm_hgb_v1/model_{SYMBOL}_{TIMEFRAME}.joblib`, berisi labeler, classifier, regressor, model holdout, konfigurasi, dan metadata. Metrik disimpan di `metrics_{SYMBOL}_{TIMEFRAME}.json` dan `latest_metrics.json`. Model versi lain tidak akan dimuat.

---

## 12. Alur 8 — Prediksi live

File: `backend/ml/model_predictor.py::predict_next_period`. Endpoint: `POST /api/ml/predict` dan `GET /api/live-monitor`.

1. Memuat bundle model untuk simbol + timeframe. **Prediksi tidak pernah melatih model**; jika model belum ada, API meminta pengguna melatih lewat Model Lab.
2. Menghitung fitur terbaru dari dataset (pipeline yang sama dengan training).
3. Mengambil candle terakhir, lalu:
   - GMM → **rezim saat ini (T)**.
   - Classifier → **rezim T+1** dan **probabilitas** SAFE/WARNING/DANGER.
   - Regressor → **volatilitas T+1** (rasio).
4. Menghitung level harga dari volatilitas prediksi:
   - `estimasi_volatilitas_nominal = harga_sekarang × volatilitas_prediksi`
   - `resistance_level = harga + estimasi`
   - `stop_loss_level = harga − estimasi`
5. Mengembalikan juga *snapshot* fitur dan disclaimer bahwa hasil hanya untuk analitik akademik, bukan nasihat investasi.

---

## 13. Batch layer: Spark, NiFi, HDFS

### 13.1 Spark di speed path (opsional)

Jika `use_spark=true` di konfigurasi, analytics dan training memakai `spark_jobs/batch_analytics.py`:

- Spark (`local[*]`) menjalankan **agregasi dan feature engineering**.
- Training GMM/HGB **tetap di driver lokal** dengan scikit-learn, karena HistGradientBoosting tidak tersedia di Spark MLlib. Data dikumpulkan ke driver dengan batas `MAX_DRIVER_ROWS = 500.000` baris.
- Jika Spark gagal, API mengembalikan error 503. Tidak ada *fallback* diam-diam ke pandas, supaya jelas engine mana yang benar-benar dipakai.

### 13.2 Job historis HDFS (Tab 4)

File: `spark_jobs/historical_hdfs_job.py`, endpoint `backend/api/historical_hdfs_routes.py` (`POST /api/historical-hdfs/run`).

1. Membaca CSV mentah dari HDFS (`hdfs://127.0.0.1:9000/arkadanta/raw` secara default), yang dikirim ke sana lewat NiFi.
2. Menyamakan nama kolom, membersihkan, dan membuang duplikat dengan Spark.
3. Mengagregasi ke timeframe yang dipilih dan menghitung fitur (minimal 30 candle).
4. Melatih dan mengevaluasi model.
5. Menyimpan `curated_features.csv` dan `metrics.json`:
   - mode `local` (default): ke `data/research/processed/historical_hdfs/symbol=.../timeframe=.../hist_<waktu>_<id>/`;
   - mode HDFS: Parquet + metrik ke path output HDFS.

Konfigurasi lewat env: `ARKADANTA_HISTORICAL_HDFS_URI`, `ARKADANTA_HISTORICAL_HDFS_RAW_PATH`, `ARKADANTA_HISTORICAL_HDFS_OUTPUT_PATH`, `ARKADANTA_HISTORICAL_OUTPUT_MODE`.

> **Status merge:** cabang `main` mengimplementasikan training job ini dengan Spark MLlib (K-Means + Random Forest), sedangkan cabang `Syafi` memakai GMM + HistGradientBoosting sesuai revisi proposal. Konflik di `spark_jobs/train_models.py` perlu diputuskan agar Tab 4 memakai algoritma yang konsisten.

### 13.3 Spark UI

Selama job Spark berjalan, UI tersedia di port **4040** (atau 4041, 4042 jika port terpakai). Buka dari Windows melalui `http://localhost:4040`. UI mati ketika job selesai karena kode memanggil `spark.stop()`.

---

## 14. Daftar endpoint API

Base URL: `http://localhost:8000`. Dokumentasi interaktif: `http://localhost:8000/docs`.

| Method | Path | Fungsi |
|---|---|---|
| GET | `/` | Status backend |
| POST | `/api/ingestion/upload` | Upload CSV/JSON → data bersih + laporan audit |
| POST | `/api/ingestion/live-sync` | Tarik candle terbaru dari Binance REST |
| GET | `/api/ingestion/cron-status` | Status cron sinkronisasi |
| POST | `/api/ingestion/cron-config` | Atur cron (aktif, interval, simbol, limit) |
| GET | `/api/historical-baseline` | Ringkasan dataset per aset + audit log |
| GET | `/api/market/stream` | SSE harga live dan event candle selesai |
| POST | `/api/analytics/run` | Agregasi + fitur + anomali + atribusi faktor |
| GET | `/api/analytics/correlation` | Korelasi Pearson, rolling, lag, risiko pasar |
| POST | `/api/ml/train` | Latih GMM + HGB dan kembalikan metrik |
| GET | `/api/models/metrics` | Metrik model terakhir |
| POST | `/api/ml/predict` | Prediksi rezim & volatilitas T+horizon |
| GET | `/api/live-monitor` | Prediksi untuk monitoring live |
| POST | `/api/historical-hdfs/run` | Jalankan job Spark historis dari HDFS |

Kesalahan data (misalnya dataset atau model belum ada) dikembalikan sebagai `ResearchDataError` dengan pesan berbahasa Indonesia di field `detail`.

---

## 15. Dashboard (frontend)

Stack: React + TypeScript + Vite + Tailwind. Jalan di `http://localhost:5173`. Semua panggilan API ada di `frontend/src/services/api.ts`; tipe data ada di `frontend/src/types/arkadanta.ts`.

| Komponen | Isi |
|---|---|
| `App.tsx` | Layout, sidebar, pemilihan tab, konfigurasi bersama |
| `LiveMarketPanel.tsx` | Harga live 4 aset dari SSE; memicu refresh saat candle selesai |
| `Tab1Ingestion.tsx` | Upload file, mapping kolom kustom, sync Binance, cron, tabel audit |
| `Tab2AnalyticsBI.tsx` | Grafik harga dan fitur, anomali, atribusi faktor, korelasi lintas aset |
| `Tab3ModelLabShield.tsx` | Konfigurasi & training model, metrik, confusion matrix, prediksi T+1 |
| `Tab4HistoricalHdfs.tsx` | Menjalankan job Spark historis dari HDFS dan menampilkan hasilnya |

Jika backend tidak bisa dihubungi, dashboard menampilkan **pesan error**, bukan data contoh.

---

## 16. Konfigurasi dinamis (`DynamicConfig`)

Didefinisikan di `backend/schemas.py`. Inilah yang membuat pipeline "dinamis": pengguna mengubah perilaku analisis dari dashboard tanpa mengubah kode. Field yang tidak dikenal ditolak (`extra="forbid"`).

| Kelompok | Field |
|---|---|
| Data | `symbol`, `symbols`, `timeframe`, `start_date`, `end_date` |
| Fitur | `features`, `ma_period`, `rsi_period`, `rolling_window` |
| Anomali | `anomaly_method`, `anomaly_quantile`, `anomaly_z_threshold`, `anomaly_iqr_multiplier` |
| Atribusi | `max_lag` |
| Model | `gmm_components`, `train_ratio`, `target_horizon`, `gb_max_iter`, `gb_max_depth`, `gb_learning_rate` |
| Engine | `use_spark` |

---

## 17. Testing

Backend (dari folder `arkadanta/`):

```bash
python -m pytest tests
```

| File | Yang diuji |
|---|---|
| `test_parser.py`, `test_validator.py`, `test_pipeline.py` | Parsing, validasi skema, pipeline ingestion |
| `test_invalid_data.py` | Penolakan data rusak |
| `test_research_data.py` | Penyimpanan dataset penelitian |
| `test_market_stream.py` | Validasi kline dan penyimpanan candle selesai |
| `test_ml_models.py` | Pelabelan GMM, training, batas data Spark |
| `test_backend_integration.py` | Endpoint API end-to-end |

Frontend: `frontend/tests/api.test.mjs`, dan pemeriksaan tipe dengan `npx tsc --noEmit`.

---

## 18. Yang sudah dan belum tersedia

| Bagian | Status |
|---|---|
| Upload CSV/JSON + validasi + audit | Tersedia |
| Harga live Binance (WebSocket → SSE) | Tersedia |
| Penyimpanan candle 5m selesai | Tersedia |
| Agregasi, fitur, anomali, korelasi | Tersedia |
| GMM + HistGradientBoosting + prediksi T+1 | Tersedia (butuh data cukup) |
| Fitur & agregasi dengan Spark | Tersedia (butuh Java + PySpark) |
| Job historis HDFS → Spark (Tab 4) | Tersedia di `main`; algoritma training masih konflik merge |
| Pengiriman otomatis setiap candle → NiFi → HDFS | Belum |
| Pengambilan histori 1 tahun + retensi otomatis | Belum |

Catatan: folder `arkadanta/src/` berisi pipeline lama/alternatif (parser, cleaner, validator, `upload_to_hdfs`) yang fungsinya tumpang tindih dengan `backend/ingestion/`.

---

## 19. Urutan demo yang disarankan

1. Jalankan HDFS dan NiFi di WSL (opsional; lihat `START.md`).
2. Jalankan backend di WSL dan dashboard di Windows.
3. Perhatikan **panel Live Market**: harga bergerak real-time.
4. **Tab 1:** sync data Binance atau upload CSV, lalu tunjukkan laporan audit (baris dibuang, alasan, skor kualitas).
5. **Tab 2:** pilih timeframe dan metode anomali, jalankan analytics, tunjukkan grafik, daftar anomali, dan korelasi BTC–ETH.
6. **Tab 3:** pilih fitur dan parameter, latih model, jelaskan centroid GMM → SAFE/WARNING/DANGER, metrik, confusion matrix, dan feature importance. Lalu jalankan prediksi T+1 dan tunjukkan resistance/stop loss.
7. **Tab 4:** jalankan job historis dari HDFS dan buka Spark UI di `http://localhost:4040` selama job berjalan.
