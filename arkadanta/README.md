# Arkadanta: Dynamic Big Data Intelligence Pipeline

**Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto Berbasis Lambda Architecture**

Panduan operasional Windows + Ubuntu WSL, termasuk startup HDFS/NiFi, dashboard, ML, dan troubleshooting: **[START.md](../START.md)**.

---

## Mode Penelitian: Data Nyata

Aplikasi tidak lagi membuat dataset sintetis saat startup, membaca data, atau ketika Binance gagal. Frontend menampilkan kegagalan API; grafik, metrik, prediksi, hasil unggah, dan status scheduler tidak mempunyai pengganti simulasi.

- Data aktif: `data/research/drop_zone/`.
- Model aktif: `data/research/models/`.
- Audit aktif: `data/research/audit_logs.json`.
- Data, model, dan audit lama di `data/drop_zone/`, `data/models/`, dan `data/audit_logs.json` tetap disimpan tetapi tidak digunakan otomatis karena asal datanya belum terverifikasi.
- Cadangan lokal sebelum perubahan: `../backups/before-research-20261024-150944/data/`. Cadangan dan data penelitian tidak dimasukkan ke Git.
- `data/sample_generator.py` hanya menyediakan generator untuk tes eksplisit; tes backend menggunakan direktori sementara.

Setelah memperbarui kode, restart backend, Vite, dan Streamlit. Pada awalnya status `NO_DATA` adalah normal. Buka tab **Data Ingestion**, pilih aset, lalu **Manual Sync Now**, atau unggah CSV/JSON nyata yang sumbernya sudah Anda periksa. Jangan unggah kembali dataset lama yang belum diverifikasi. Streamlit menyediakan panel ambil/unggah data sebelum analisis.

Sinkronisasi mengambil candle terbaru, belum histori satu tahun. Jika Binance gagal, data aset yang gagal tidak diganti; aset yang sudah berhasil pada permintaan yang sama tetap tersimpan dan tercatat di audit. Berkas lokal dilaporkan sebagai `QUEUED_DROP_ZONE`, bukan bukti bahwa HDFS telah tersinkronisasi.

Pengujian pemisahan data (tanpa akses jaringan, memakai berkas sementara):

```bash
python -m unittest discover -s arkadanta/tests -p test_research_data.py -v
```

Dari folder `arkadanta/frontend`, jalankan pengujian layanan API dengan `node --test tests/api.test.mjs` dan build dengan `npm run build`.

---

## Harga Real-time di Dashboard React

Backend membuka satu Binance WebSocket publik untuk empat aset ketika dashboard React dibuka. Event candle 5 menit berjalan diterima sekitar setiap dua detik dan diteruskan ke browser melalui **Server-Sent Events**, endpoint `GET /api/market/stream`. Harga, OHLC, volume berjalan, umur data, dan status koneksi tampil pada panel live di atas dashboard. Ini bukan harga setiap transaksi dan bukan jaminan latensi tertentu.

Candle berjalan hanya ditampilkan. Saat Binance menyatakan candle 5 menit selesai, backend menyimpannya secara atomik, mencatat audit, lalu memberitahu dashboard untuk mengambil ulang analisis dan prediksi. Candle disimpan dengan deduplikasi simbol + timestamp. Upload, REST sync, dan stream berbagi penguncian penulisan dalam satu proses. Grafik analisis historis tetap mengikuti timeframe yang dipilih; grafik tersebut tidak diganti dengan harga candle berjalan.

Model yang sudah tersedia digunakan kembali saat inferensi; kode lama masih dapat melatih model ketika model belum tersedia. Siapkan histori nyata yang cukup dan latih model melalui Model Lab sebelum demonstrasi. Streaming tidak menggantikan pengambilan histori untuk pelatihan.

Koneksi terputus ditampilkan secara jelas dan dicoba kembali dengan jeda bertahap. Harga tanpa pembaruan selama 15 detik ditandai sebagai data terakhir, bukan LIVE. Tidak ada data simulasi. Stream hanya aktif selama ada browser yang berlangganan; saat dashboard ditutup, koneksi dihentikan. Untuk mengisi candle yang terlewat saat dashboard/backend mati atau koneksi terputus, jalankan Manual Sync; mekanisme backfill histori panjang belum ditambahkan. NiFi/HDFS/Spark belum terhubung otomatis dengan stream ini.

Jalankan **satu worker backend** untuk aplikasi lokal ini. Jangan menjalankan backend Windows dan WSL bersamaan pada dataset yang sama. Panel stream ada di React; dashboard Streamlit tetap menggunakan alur pengambilan data sebelumnya.

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
- Train/test dibagi kronologis dengan embargo sepanjang horizon. Target latih terakhir serta fitting scaler/GMM selalu mendahului fitur uji pertama.
- Evaluasi GMM memuat BIC, AIC, konvergensi, dan silhouette (dapat `null` jika komponen terisi tidak cukup). Klasifikasi/regresi tetap memakai Accuracy, Precision, Recall, F1, MAE, dan RMSE.
- Grafik kepentingan fitur memakai **permutation importance terhadap macro F1 pada holdout**, maksimal 500 baris dan tiga pengulangan. Nilai negatif mungkin terjadi; grafik bukan bukti hubungan sebab-akibat dan tidak dipakai untuk memilih fitur/model.

Parameter API/UI sekarang: `gmm_components`, `gb_max_iter`, `gb_max_depth`, `gb_learning_rate`, dan `target_horizon`. Nama lama `cluster_k`, `rf_num_trees`, `rf_max_depth`, serta metode anomali `kmeans` ditolak agar tidak diabaikan diam-diam. Metode anomali pengganti adalah `gmm` dengan skor negative log-likelihood. Metrik kelompok dikirim sebagai `gmm_metrics`; prediksi memakai `current_component_id`.

Artefak baru disimpan di `data/research/models/gmm_hgb_v1/`, terpisah dari model lama. Setelah restart backend, latih ulang melalui **Model Lab → Train & Evaluate Models**. Pilih timeframe dengan data nyata yang cukup; minimal 30 + horizon candle dan setidaknya dua kelas pada data latih. Model/matriks fitur disimpan bersama konfigurasi indikator agar inferensi menggunakan parameter yang sama. Aplikasi dapat melatih default secara otomatis jika artefak baru belum tersedia.

**Jalur Spark:** agregasi/feature engineering memakai PySpark, kemudian fitur dikumpulkan ke driver untuk trainer GMM/HGB yang sama, dengan batas 500.000 baris. HistGradientBoosting tidak tersedia di Spark MLlib; pelatihan ini **bukan training terdistribusi**. Inferensi model yang dilatih dengan Spark juga memakai persiapan fitur Spark yang sama. Memilih Spark membutuhkan Java/PySpark yang berfungsi; kegagalan training Spark ditampilkan, tanpa penggantian engine diam-diam.

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
      model_predictor.py        # Inferensi T+1 + estimasi Resistance & Stop Loss
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
      audit_logs.json           # Audit penelitian aktif
    drop_zone/                  # Data lama, tidak dibaca otomatis
```

---

## Cara Menjalankan

### Jalur tambahan untuk data historis NiFi dan HDFS

Alur lokal Arkadanta tetap sama. Untuk demo batch historis, jalankan NiFi secara
terpisah dan arahkan file CSV OHLCV 5 menit ke `/arkadanta/raw`. Pipeline membaca
CSV dari direktori tersebut dan memfilter simbol yang dipilih sebelum memproses
data dengan PySpark dan melatih model Spark MLlib. Path input ini ditetapkan di
konfigurasi backend sehingga tidak perlu diisi setiap kali menjalankan pipeline.

Atur konfigurasi sebelum menyalakan FastAPI:

```powershell
$env:ARKADANTA_HISTORICAL_HDFS_URI = "hdfs://127.0.0.1:9000"
$env:ARKADANTA_HISTORICAL_HDFS_RAW_PATH = "/arkadanta/raw"
$env:ARKADANTA_HISTORICAL_OUTPUT_MODE = "local"
```

Kemudian buka dashboard React dan pilih **Historical HDFS Batch**, atau gunakan
`POST /api/historical-hdfs/run`. Endpoint menerima aset, timeframe, dan rentang
tanggal (maksimum 365 hari); sumber input tetap `/arkadanta/raw`. Job menerima format Binance
Kline standar 12 kolom tanpa header maupun CSV ber-header
`timestamp, open, high, low, close, volume`. `coin_symbol` opsional untuk file
yang hanya berisi satu aset; jika tidak ada, simbol diambil dari pilihan aset.
Hasil API menunjukkan path input, rentang timestamp yang benar-benar terbaca,
metrik evaluasi, serta lokasi output dan model.

Secara default, input dibaca dari HDFS sedangkan fitur (CSV) dan metrik (JSON)
disimpan melalui filesystem Python di `data/processed/historical_hdfs/` pada
mesin backend. Ini menghindari kebutuhan izin tulis HDFS dan `winutils.exe` pada
Windows. Model MLlib dilatih dan dievaluasi pada run tersebut, tetapi tidak
disimpan sebagai artefak dalam mode lokal. Jika admin memberi hak tulis pada
direktori output HDFS, set `ARKADANTA_HISTORICAL_OUTPUT_MODE=hdfs` dan atur
`ARKADANTA_HISTORICAL_HDFS_OUTPUT_PATH`; mode itu menyimpan Parquet dan artefak
model di HDFS.

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

Script tersebut secara otomatis mendeteksi environment `.venv`, memeriksa dependensi `node_modules`, dan menyalakan ketiga layanan sekaligus:
1. **FastAPI Backend Server**: `http://localhost:8000` (Swagger Docs: `http://localhost:8000/docs`)
2. **React + TypeScript Frontend (FE)**: `http://localhost:5173`
3. **Streamlit + Plotly Interactive Dashboard**: `http://localhost:8501`

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

#### 3. Menjalankan Streamlit Dashboard
```powershell
cd E:\GIT\Project-Akhir-BigData\arkadanta
..\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.port 8501
```
Buka `http://localhost:8501` di browser.
