# Arkadanta: Dynamic Big Data Intelligence Pipeline

**Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto Berbasis Lambda Architecture**

Panduan operasional Windows + Ubuntu WSL, termasuk startup HDFS/NiFi, dashboard, ML, dan troubleshooting: **[START.md](../START.md)**.

---

## Mode Penelitian: Data Nyata

Aplikasi tidak lagi membuat dataset sintetis saat startup, membaca data, atau ketika Binance gagal. Frontend menampilkan kegagalan API; grafik, metrik, prediksi, hasil unggah, dan status scheduler tidak mempunyai pengganti simulasi.

- Data aktif: `data/research/drop_zone/`.
- Model aktif: `data/research/models/`.
- Audit lengkap: `data/research/audit_logs.jsonl`; snapshot terbaru: `data/research/audit_logs.json`.
- Data, model, dan audit lama di `data/drop_zone/`, `data/models/`, dan `data/audit_logs.json` tetap disimpan tetapi tidak digunakan otomatis karena asal datanya belum terverifikasi.
- Cadangan lokal sebelum perubahan: `../backups/before-research-20261024-150944/data/`. Cadangan dan data penelitian tidak dimasukkan ke Git.
- `data/sample_generator.py` hanya menyediakan generator untuk tes eksplisit; tes backend menggunakan direktori sementara.

Setelah memperbarui kode, restart backend dan Vite. Pada awalnya status `NO_DATA` adalah normal. Buka tab **Data Ingestion**, pilih aset, lalu **Manual Sync Now**, atau unggah CSV/JSON nyata yang sumbernya sudah Anda periksa. Jangan unggah kembali dataset lama yang belum diverifikasi. Upload selalu **digabung** dengan histori yang ada (duplikat simbol + timestamp diganti versi terbaru), tidak pernah menimpa seluruh dataset.

**Manual Sync** mengambil candle terbaru. **Backfill Histori** (`POST /api/ingestion/backfill`, maks. 365 hari) menarik histori 5m per halaman 1000 candle. Jika Binance gagal, data aset yang gagal tidak diganti; aset yang sudah berhasil pada permintaan yang sama tetap tersimpan dan tercatat di audit. Berkas lokal dilaporkan sebagai `QUEUED_DROP_ZONE`, bukan bukti bahwa HDFS telah tersinkronisasi.

Pengujian pemisahan data (tanpa akses jaringan, memakai berkas sementara):

```bash
python -m unittest discover -s arkadanta/tests -p test_research_data.py -v
```

Dari folder `arkadanta/frontend`, jalankan pengujian layanan API dengan `node --test tests/api.test.mjs` dan build dengan `npm run build`.

---

## Harga Real-time di Dashboard React

Backend membuka satu Binance WebSocket publik untuk empat aset ketika dashboard React dibuka. Event candle 5 menit berjalan diterima sekitar setiap dua detik dan diteruskan ke browser melalui **Server-Sent Events**, endpoint `GET /api/market/stream`. Harga, OHLC, volume berjalan, umur data, dan status koneksi tampil pada panel live di atas dashboard. Ini bukan harga setiap transaksi dan bukan jaminan latensi tertentu.

Candle berjalan hanya ditampilkan. Saat Binance menyatakan candle 5 menit selesai, backend menyimpannya secara atomik, mencatat audit, lalu memberitahu dashboard untuk mengambil ulang analisis dan prediksi. Candle disimpan dengan deduplikasi simbol + timestamp. Upload, REST sync, dan stream berbagi penguncian penulisan dalam satu proses. Grafik analisis historis tetap mengikuti timeframe yang dipilih; grafik tersebut tidak diganti dengan harga candle berjalan.

Inferensi hanya memuat model yang sudah dilatih; request prediksi tidak pernah memicu training (respons 409 bila model belum ada). Siapkan histori nyata yang cukup dan latih model melalui Model Lab sebelum demonstrasi. Streaming tidak menggantikan pengambilan histori untuk pelatihan.

Koneksi terputus ditampilkan secara jelas dan dicoba kembali dengan jeda bertahap. Harga tanpa pembaruan selama 15 detik ditandai sebagai data terakhir, bukan LIVE. Tidak ada data simulasi. Stream hanya aktif selama ada browser yang berlangganan; saat dashboard ditutup, koneksi dihentikan. Untuk mengisi candle yang terlewat saat dashboard/backend mati atau koneksi terputus, jalankan Manual Sync atau Backfill Histori. Setiap candle baru juga masuk ke `data/research/nifi_outbox/` untuk dikirim NiFi ke HDFS.

Jalankan **satu worker backend** untuk aplikasi lokal ini. Jangan menjalankan backend Windows dan WSL bersamaan pada dataset yang sama. Panel stream ada di dashboard React.

Setelah perubahan kode, pada terminal **WSL**, dari direktori `arkadanta`:

```bash
source ~/venvs/arkadanta/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Jalankan React dengan `npm run dev` di Windows, buka `http://localhost:5173`, lalu tunggu label **LIVE** pada panel harga. Vite meneruskan stream ke backend port 8000; `VITE_API_URL` dapat digunakan jika backend berada di alamat lain. Akses internet ke Binance WebSocket diperlukan. Endpoint streaming tidak ditampilkan sebagai data JSON biasa di Swagger; pengujian manual dapat menggunakan `curl -N http://localhost:8000/api/market/stream`.

Pengujian stream tanpa jaringan:

```bash
python -m unittest discover -s arkadanta/tests -p test_market_stream.py -v
```

---

## Machine Learning: GMM + HistGradientBoosting

- **GaussianMixture (GMM)** menggantikan pengelompokan risiko. Mean setiap komponen dinilai dengan skor risiko, lalu diurutkan menjadi SAFE/WARNING/DANGER. Inisialisasi memakai `random_from_data`, bukan K-Means.
- **HistGradientBoostingClassifier** memprediksi kelas risiko T+horizon dan probabilitasnya; **HistGradientBoostingRegressor** memprediksi volatilitas T+horizon. Early stopping acak dinonaktifkan untuk menjaga urutan waktu.
- Train/test dibagi kronologis dengan embargo sepanjang horizon. Target latih terakhir serta fitting scaler/GMM selalu mendahului fitur uji pertama. Metrik berasal dari model holdout; model yang dipakai live dilatih ulang pada seluruh data berlabel (`deployed_model_fit_samples`).
- Agregasi timeframe hanya memakai bucket dengan candle 5m lengkap (mis. 12 untuk `1h`). Bucket berjalan atau berlubang dibuang, sehingga prediksi tidak memakai candle parsial. Minggu (`1w`) dimulai Senin 00:00 UTC pada pandas maupun Spark.
- Metrik selalu disertai pembanding naif (`baseline_metrics`): akurasi bila menebak kelas terbanyak, akurasi bila menebak "rezim tetap sama", dan RMSE bila menebak volatilitas tetap sama.
- Fitur mikrostruktur (`buy_sell_pressure_ratio`, dsb.) hanya dihitung dari kolom sumber nyata. Jika CSV tidak memiliki kolom taker/trades, fitur tersebut ditolak, tidak diisi tebakan.
- Ambang anomali `adaptive_quantile`, `iqr`, dan `rolling_zscore` hanya memakai data sebelum candle yang dinilai, sehingga label lama tidak berubah saat data baru masuk. Metode `gmm` di-fit pada seluruh rentang (analisis retrospektif, `causal: false`).
- Evaluasi GMM memuat BIC, AIC, konvergensi, dan silhouette (dapat `null` jika komponen terisi tidak cukup). Klasifikasi/regresi tetap memakai Accuracy, Precision, Recall, F1, MAE, dan RMSE.
- Grafik kepentingan fitur memakai **permutation importance terhadap macro F1 pada holdout**, maksimal 500 baris dan tiga pengulangan. Nilai negatif mungkin terjadi; grafik bukan bukti hubungan sebab-akibat dan tidak dipakai untuk memilih fitur/model.

Parameter API/UI sekarang: `gmm_components`, `gb_max_iter`, `gb_max_depth`, `gb_learning_rate`, dan `target_horizon`. Nama lama `cluster_k`, `rf_num_trees`, `rf_max_depth`, serta metode anomali `kmeans` ditolak agar tidak diabaikan diam-diam. Metode anomali pengganti adalah `gmm` dengan skor negative log-likelihood. Metrik kelompok dikirim sebagai `gmm_metrics`; prediksi memakai `current_component_id`.

Artefak baru disimpan di `data/research/models/gmm_hgb_v3/`, terpisah dari model lama. Setelah restart backend, latih ulang melalui **Model Lab → Train & Evaluate Models**. Pilih timeframe dengan data nyata yang cukup; minimal 30 + horizon candle dan setidaknya dua kelas pada data latih. Model/matriks fitur disimpan bersama konfigurasi indikator agar inferensi menggunakan parameter yang sama. Hanya satu training berjalan sekaligus; permintaan kedua mendapat 429.

**Integritas v3:** perubahan candle dijurnal sebelum CSV/outbox diperbarui dan dipulihkan saat startup/read/write berikutnya. Koreksi timestamp lama juga dikirim dengan `ingestion_version` baru. Outbox memakai skema tetap di `nifi_outbox/v3/`; NiFi wajib memakai PutHDFS `Conflict Resolution Strategy = ignore` agar replay berkas event yang sama aman. Riwayat audit lengkap berada di `audit_logs.jsonl`; JSON lama tetap menjadi snapshot kompatibilitas. Lihat [migrasi dan startup](../START.md) serta [penggabungan berkas NiFi](nifi/README.md).

Upload/REST/stream hanya menyimpan OHLCV finite, lengkap, di grid 5 menit, dan sudah selesai. Tidak ada forward-fill OHLC atau penggantian volume hilang dengan nol. Semua jalur analisis/training membatasi penelitian pada 365 hari terakhir tanpa menghapus arsip. Target training harus tepat T+horizon menurut timestamp; pasangan yang melewati celah dibuang. Prediksi menolak candle yang bukan bucket tertutup terakhir dan menyertakan `target_start`/`target_end` UTC.

SAFE/WARNING/DANGER adalah kategori relatif GMM. Metrik klasifikasi bukan ukuran keamanan investasi. Evaluasi tambahan `volatility_event_validation` memakai kejadian range aktual candle target di atas persentil 95 target latih; `walk_forward_volatility` mengevaluasi regressor pada hingga tiga periode uji kronologis. Batas harga pada dashboard adalah ilustrasi harga ± estimasi range, bukan resistance teknikal atau stop loss tervalidasi; field API `resistance_level`/`stop_loss_level` dipertahankan sebagai alias kompatibilitas.

**Jalur Spark:** agregasi/feature engineering memakai PySpark, kemudian fitur dikumpulkan ke driver untuk trainer GMM/HGB yang sama, dengan batas 500.000 baris. HistGradientBoosting tidak tersedia di Spark MLlib; pelatihan ini **bukan training terdistribusi**. Rumus fitur Spark dan pandas identik (diuji `tests/test_spark_parity.py`; RSI memakai rata-rata sederhana di keduanya, `ema_20` hanya tersedia di pandas), sehingga model hasil Spark dilayani dengan fitur pandas tanpa menyalakan Spark per prediksi. Hanya satu job Spark berjalan per backend; job kedua ditolak (429/400). Memilih Spark membutuhkan Java/PySpark yang berfungsi; `JAVA_HOME` yang salah langsung ditolak, bukan menggantung.

Pengujian migrasi (semua data sintetis dibuat eksplisit di direktori sementara):

```bash
python -m unittest discover -s arkadanta/tests -p test_ml_models.py -v
```

## Struktur Modul (`arkadanta/`)

```text
arkadanta/
  CONTRACTS.md                  # Kontrak integrasi Orang 1 <-> Orang 2
  requirements.txt              # Dependensi Backend Python (FastAPI + Scikit-learn + Pandas)
  requirements-spark.txt        # Dependensi PySpark khusus Batch Layer Orang 1
  backend/
    main.py                     # FastAPI Server utama (Serving Layer)
    config.py                   # Konfigurasi path, fitur, simbol, dan HDFS
    schemas.py                  # Skema Pydantic request/response & audit log
    api/
      ingestion_routes.py       # /api/ingestion/upload, /api/ingestion/live-sync, /api/historical-baseline
      analytics_routes.py       # [ORANG 2] /api/analytics/run, /api/analytics/correlation
      model_routes.py           # [ORANG 2] /api/ml/train, /api/models/metrics
      prediction_routes.py      # [ORANG 2] /api/ml/predict, /api/live-monitor
    ingestion/                  # [ORANG 1 - dilengkapi stub fungsional]
      format_detector.py
      schema_validator.py
      dynamic_pipeline.py
      processors/
        csv_processor.py
        json_processor.py
    analytics/                  # [ORANG 2]
      timeframe_aggregator.py   # Agregasi deterministik 5m -> 15m, 1h, 4h, 1d, 1w
      feature_engineering.py    # Fitur volatilitas, teknikal (SMA/EMA/RSI/BB), struktur candle, mikrostruktur
      anomaly_detector.py       # Deteksi anomali: rolling_zscore, iqr, adaptive_quantile, gmm
      correlation_analyzer.py   # Pearson, rolling correlation, lag correlation, market-wide risk score
    ml/                         # [ORANG 2]
      dynamic_feature_selector.py
      risk_labeler.py           # StandardScaler + Gaussian Mixture + pengurutan skor risiko centroid (SAFE/WARNING/DANGER)
      model_trainer.py          # Temporal split + HistGradientBoosting Classifier & Regressor (T+1)
      model_evaluator.py        # Silhouette, Accuracy, Precision, Recall, F1, Confusion Matrix, MAE, RMSE
      model_predictor.py        # Inferensi T+1 + periode target UTC dan batas ilustratif
  spark_jobs/                   # PySpark Batch Layer
    batch_analytics.py
    dynamic_aggregation.py
    feature_pipeline.py
    train_models.py
  frontend/                     # [ORANG 2] React 18 + TypeScript + Vite + TailwindCSS + Recharts
    package.json
    vite.config.ts
    src/
      App.tsx
      types/arkadanta.ts
      services/api.ts
      components/
        Tab1Ingestion.tsx
        Tab2AnalyticsBI.tsx
        Tab3ModelLabShield.tsx
  data/
    storage.py                  # Pembacaan data penelitian & penyimpanan audit
    sample_generator.py         # Generator sintetis untuk tes eksplisit
    research/
      drop_zone/                # Data OHLCV penelitian aktif
      models/                   # Model penelitian aktif
      audit_logs.jsonl          # Riwayat audit penelitian lengkap
      audit_logs.json           # Snapshot 50 catatan terbaru
    drop_zone/                  # Data lama, tidak dibaca otomatis
```

---

## Cara Menjalankan

### Jalur tambahan untuk data historis NiFi dan HDFS

Batch layer membaca HDFS dari salah satu dari dua sumber:

- **raw** (`/arkadanta/raw/symbol=<S>/`): dump histori Binance, terpisah per aset.
- **clean** (`/user/arkadanta/data/clean/crypto/v3/symbol=<S>/year=<Y>/month=<M>/`):
  setiap baris baru aplikasi (upload, sync, backfill, candle live) ditulis ke
  `data/research/nifi_outbox/`, lalu NiFi `GetFile → UpdateAttribute → PutHDFS`
  mengirimnya (lihat `START.md` bagian B). Spark memilih revisi terbesar per simbol/timestamp, menolak konflik pada revisi sama, dan memisahkan data v3 dari skema lama.

PySpark mengolah agregasi dan fitur. GMM + HistGradientBoosting dilatih di driver
dengan trainer yang sama seperti Model Lab, dan bundle-nya disimpan ke
`data/research/models/` sehingga langsung dipakai `/api/ml/predict`.

Atur konfigurasi sebelum menyalakan FastAPI:

```powershell
$env:ARKADANTA_HISTORICAL_HDFS_URI = "hdfs://127.0.0.1:9000"
$env:ARKADANTA_HISTORICAL_HDFS_RAW_PATH = "/arkadanta/raw"
$env:ARKADANTA_HISTORICAL_OUTPUT_MODE = "local"
```

Kemudian buka dashboard React dan pilih **Historical HDFS Batch**, atau gunakan
`POST /api/historical-hdfs/run`. Endpoint menerima aset, timeframe, dan rentang
tanggal (maksimum 365 hari), serta `source` (`raw` atau `clean`). Job menerima format Binance
Kline standar 12 kolom tanpa header maupun CSV ber-header
`timestamp, open, high, low, close, volume`. `coin_symbol` opsional untuk file
yang hanya berisi satu aset; jika tidak ada, identitas wajib berasal dari partisi `symbol=<S>` atau nama file `<S>-5m-*.csv`, bukan diberikan dari pilihan dashboard.
Hasil API menunjukkan path input, rentang timestamp yang benar-benar terbaca,
metrik evaluasi, serta lokasi output dan model.

Secara default, input dibaca dari HDFS sedangkan fitur (CSV) dan metrik (JSON)
disimpan melalui filesystem Python di `data/processed/historical_hdfs/` pada
mesin backend. Ini menghindari kebutuhan izin tulis HDFS dan `winutils.exe` pada
Windows. Jika admin memberi hak tulis pada direktori output HDFS, set
`ARKADANTA_HISTORICAL_OUTPUT_MODE=hdfs` dan atur
`ARKADANTA_HISTORICAL_HDFS_OUTPUT_PATH`; mode itu menyimpan fitur sebagai Parquet
dan metrik sebagai JSON di HDFS. Bundle model selalu disimpan lokal untuk serving.

Spark perlu dapat menjangkau NameNode dan memakai konfigurasi Hadoop lokal.
Jika distribusi Hadoop memerlukan `HADOOP_CONF_DIR`, set environment itu sebelum
menyalakan backend. Jalur HDFS historis terpisah dari endpoint lokal yang sudah
ada; NiFi mengirim file, sedangkan endpoint baru menjalankan pembacaan dan batch.
Pastikan dependensi Spark terpasang (`pip install -r requirements-spark.txt`) dan
konfigurasi NiFi menulis header OHLCV serta tidak mencampur simbol ke direktori
aset yang berbeda.

### Opsi 1: Menjalankan Semua Layanan dalam 1 Perintah (Otomatis)
Dari direktori root `E:\GIT\Project-Akhir-BigData`, cukup jalankan satu perintah berikut di PowerShell atau Command Prompt:
```powershell
.\run-all.bat
```
*(atau `.\run-all.ps1` / `.\arkadanta\start.bat`)*

Script tersebut secara otomatis mendeteksi environment `.venv`, memeriksa dependensi `node_modules`, dan menyalakan kedua layanan sekaligus:
1. **FastAPI Backend Server**: `http://localhost:8000` (Swagger Docs: `http://localhost:8000/docs`)
2. **React + TypeScript Frontend (FE)**: `http://localhost:5173`

---

### Opsi 2: Menjalankan Secara Manual per Komponen

#### 1. Menjalankan Frontend Dashboard (React + TypeScript + TailwindCSS)
```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta\frontend
npm run dev
```
Buka `http://localhost:5173` di browser.

#### 2. Menjalankan Backend API (FastAPI Python)
```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta
..\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```
Dokumentasi Swagger UI tersedia di `http://localhost:8000/docs`.
