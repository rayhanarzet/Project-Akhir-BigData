# DOKUMEN RANCANGAN & SPESIFIKASI TEKNIS PROYEK AKHIR

## Mata Kuliah: Big Data & Analitik (Kelas A)

> Revisi implementasi ML: pengelompokan risiko menggunakan GaussianMixture (GMM) dengan inisialisasi acak dari data; prediksi menggunakan HistGradientBoostingClassifier dan HistGradientBoostingRegressor. Spark menjalankan pengolahan fitur, sedangkan training GMM/HGB berjalan pada driver lokal (bukan algoritma Spark MLlib). Model memakai validasi temporal dengan embargo sesuai horizon. Evaluasi GMM mencakup BIC/AIC dan silhouette; interpretasi fitur memakai permutation importance pada holdout.

**Judul Proyek:** **Arkadanta: Dynamic Big Data Intelligence Pipeline untuk Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto Berbasis Lambda Architecture**

---

# BAB 1: PENDAHULUAN

## 1.1 Latar Belakang Masalah

Pasar kripto beroperasi 24/7 tanpa *circuit breaker*, sehingga rentan terhadap lonjakan volatilitas, *flash crash*, *pump-and-dump*, dan aktivitas transaksi tidak normal. Data pasar memiliki karakteristik Big Data: volume multi-aset dan multi-tahun, pembaruan candle periodik, variasi format, serta masalah kualitas seperti timestamp duplikat, nilai hilang, dan candle tidak valid.

Data OHLCV tidak menyediakan label risiko pasar. Prediksi harga nominal sulit karena sifat *random walk*. Karena itu, Arkadanta berfokus pada volatilitas, volume, struktur candle, indikator teknikal, mikrostruktur transaksi, dan hubungan lintas aset untuk mendeteksi anomali, menentukan rezim risiko, serta memprediksi risiko periode berikutnya.

Arkadanta bersifat dinamis: pengguna dapat memilih aset, rentang tanggal, timeframe, fitur, metode deteksi anomali, target prediksi, dan parameter model melalui dashboard atau API tanpa mengubah kode inti pipeline.

## 1.2 Rumusan Masalah

1. Bagaimana membangun ingestion CSV/JSON yang mendeteksi format, memvalidasi skema, dan memilih preprocessing otomatis sebelum HDFS?
2. Bagaimana Dynamic Pipeline Controller menentukan parser, normalisasi, dan pemeriksaan kualitas berdasarkan dataset masuk?
3. Bagaimana mengagregasi OHLCV 5 menit menjadi 15 menit, 1 jam, 4 jam, 1 hari, atau 1 minggu dengan PySpark?
4. Bagaimana menyediakan feature engineering dinamis untuk fitur volatilitas, teknikal, mikrostruktur pasar, dan lintas aset?
5. Bagaimana mendeteksi anomali menggunakan *rolling Z-score*, IQR, *adaptive quantile*, atau Gaussian Mixture?
6. Bagaimana membuat label SAFE, WARNING, dan DANGER tanpa mengasumsikan ID cluster Gaussian Mixture sebagai label risiko?
7. Bagaimana melatih dan mengevaluasi prediksi T+1 dengan fitur, timeframe, target, dan parameter model yang dinamis?
8. Bagaimana menyajikan BI, anomali, korelasi lintas aset, metrik model, dan prediksi live melalui dashboard serta FastAPI?

## 1.3 Tujuan Proyek

1. Mengembangkan ingestion CSV/JSON dengan deteksi format, validasi skema, pembersihan, normalisasi OHLCV, dan laporan kualitas.
2. Mengimplementasikan Dynamic Pipeline Controller berbasis aturan.
3. Menyimpan data bersih melalui Apache NiFi ke HDFS dan memprosesnya dengan PySpark.
4. Menyediakan agregasi dinamis: 5m, 15m, 1h, 4h, 1d, dan 1w.
5. Menghasilkan fitur volatilitas, teknikal, mikrostruktur, dan korelasi lintas aset yang dapat dipilih pengguna.
6. Mendeteksi anomali dengan metode serta ambang adaptif yang dapat dikonfigurasi.
7. Melabeli hasil Gaussian Mixture berdasarkan urutan skor risiko centroid menjadi SAFE, WARNING, dan DANGER.
8. Memprediksi probabilitas rezim risiko dan volatilitas T+1 menggunakan HistGradientBoosting dengan validasi temporal.
9. Menyediakan dashboard BI dan live monitoring dengan konfigurasi analitik, prediksi, rentang harga, dan evaluasi model.

---

# BAB 2: JUSTIFIKASI KARAKTERISTIK BIG DATA (4V)

| Dimensi | Implementasi Arkadanta | Solusi Infrastruktur |
|---|---|---|
| **Volume** | Data 5 menit menghasilkan 288 candle/hari atau hingga 105.120 baris/aset/tahun; multi-aset dan multi-tahun menghasilkan jutaan baris. | Hadoop HDFS dan Apache Spark. |
| **Velocity** | Candle baru dari Binance diambil berkala; 288 candle/hari/aset pada interval 5 menit. | FastAPI polling/scheduler, NiFi, Speed Layer. |
| **Variety** | Input CSV/JSON dapat memiliki variasi nama kolom, timestamp, atau JSON bertingkat. | Dynamic Pipeline Controller, PySpark DataFrame, FastAPI. |
| **Veracity** | Data dapat memiliki duplikasi, nilai hilang, tipe tidak sesuai, dan candle tidak valid. | Validasi skema, deduplikasi, imputasi, sanity check, audit log. |

Rentang historis mengikuti ketersediaan nyata masing-masing aset, bukan dipaksakan sama selama 15 tahun.

---

# BAB 3: ARSITEKTUR SISTEM (LAMBDA ARCHITECTURE)

## 3.1 Batch Layer

1. Pengguna mengunggah CSV atau JSON melalui Web UI.
2. Backend mendeteksi format, struktur, dan skema.
3. Dynamic Pipeline Controller memilih parser dan preprocessing.
4. Data dinormalisasi menjadi OHLCV standar.
5. Data bersih masuk *drop zone*, kemudian NiFi mengirimkannya ke HDFS.
6. PySpark menjalankan agregasi timeframe, feature engineering, BI, anomali, dan pelatihan model.

## 3.2 Speed Layer

1. FastAPI mengambil candle dari Binance `/api/v3/klines`.
2. Data terbaru divalidasi, dideduplikasi, dan dinormalisasi.
3. Fitur terbaru digabungkan dengan konteks historis.
4. Model aktif menghasilkan prediksi risiko dan volatilitas T+1.
5. Hasil tersedia pada dashboard live monitor.

## 3.3 Serving Layer

- `POST /api/ingestion/upload`
- `POST /api/ingestion/live-sync`
- `POST /api/analytics/run`
- `GET /api/analytics/correlation`
- `POST /api/ml/train`
- `POST /api/ml/predict`
- `GET /api/models/metrics`
- `GET /api/historical-baseline`
- `GET /api/live-monitor`

---

# BAB 4: MODUL 1 — INGESTION, PREPROCESSING, DAN HDFS

## 4.1 Skema OHLCV Standar

| Kolom | Tipe | Keterangan |
|---|---|---|
| `timestamp` | timestamp UTC / epoch ms | Waktu pembukaan candle |
| `coin_symbol` | string | Contoh: BTCUSDT |
| `open`, `high`, `low`, `close` | double | Harga OHLC |
| `volume` | double | Volume aset dasar |

Jika tersedia dari Binance, pipeline juga mempertahankan `quote_asset_volume`, `number_of_trades`, `taker_buy_base_volume`, dan `taker_buy_quote_volume`.

## 4.2 Dynamic Pipeline Controller

Controller berbasis aturan aplikasi, bukan ML:

1. Deteksi format CSV atau JSON.
2. Pilih parser, termasuk JSON bertingkat jika mapping tersedia.
3. Cocokkan alias kolom, seperti `open_time` ke `timestamp` atau `vol` ke `volume`.
4. Validasi kolom wajib, tipe data, timestamp, dan simbol aset.
5. Tentukan preprocessing: parsing timestamp, deduplikasi, imputasi, atau penolakan.
6. Normalisasi input valid ke skema OHLCV standar.
7. Catat format, mapping kolom, pipeline terpilih, jumlah baris sebelum/sesudah, dan alasan kegagalan.

## 4.3 Pembersihan dan Validasi

1. Konversi timestamp ke UTC atau epoch millisecond konsisten.
2. Konversi harga dan volume ke numerik.
3. Hapus duplikasi berdasarkan `coin_symbol` dan `timestamp`.
4. Urutkan data berdasarkan aset dan timestamp.
5. Lakukan *forward-fill* per aset pada OHLC; baris awal yang tetap kosong ditandai atau dibuang.
6. Isi volume kosong dengan `0.0`.
7. Tandai/tolak baris dengan `high < low`, harga tidak positif, atau `volume < 0`.
8. Hasilkan laporan kualitas data yang dapat diaudit.

## 4.4 NiFi ke HDFS

NiFi menggunakan `GetFile` atau `InvokeHTTP`, lalu `PutHDFS` ke contoh path:

`/user/arkadanta/data/clean/crypto/`

Data dapat dipartisi menurut `symbol`, `year`, `month`, dan `timeframe`.

---

# BAB 5: MODUL 2 — ANALITIK PYSPARK DAN MACHINE LEARNING DINAMIS

## 5.1 Dynamic Multi-Timeframe Aggregation

Timeframe: `5m`, `15m`, `1h`, `4h`, `1d`, `1w`.

Untuk setiap window, PySpark menghitung open pertama, high maksimum, low minimum, close terakhir secara kronologis, total volume, quote volume, jumlah transaksi, log return, volatilitas maksimum, dan volatilitas rata-rata. Close terakhir harus memakai urutan timestamp eksplisit agar hasil Spark deterministik.

## 5.2 Dynamic Feature Engineering

| Kategori | Fitur |
|---|---|
| Volatilitas | max/average/rolling volatility, spike ratio |
| Harga | log return, return periodik, high-low range, close-open change |
| Teknikal | SMA, EMA, RSI, Bollinger Bands width |
| Struktur candle | upper wick ratio, lower wick ratio, body ratio |
| Mikrostruktur | volume, quote volume, number of trades, taker buy/sell pressure ratio |
| Lintas aset | Pearson correlation, rolling correlation, lag correlation, market-wide risk score |

Pengguna dapat memilih subset fitur. Periode RSI, moving average, rolling window, dan korelasi berasal dari konfigurasi analitik.

## 5.3 Dynamic Anomaly Detection

Metode yang tersedia:

1. *Rolling Z-score* untuk lonjakan volatilitas/volume dari rata-rata bergerak.
2. IQR untuk outlier berbasis kuartil.
3. *Adaptive quantile* untuk nilai di atas persentil historis, misalnya 0,95.
4. Gaussian Mixture untuk rezim pasar berdasarkan kombinasi fitur.

Ambang dihitung per aset, timeframe, dan rentang historis, bukan nilai global tetap.

## 5.4 Business Intelligence dan Analisis Lintas Aset

Dashboard menyajikan tren harga, volume, volatilitas, SMA/EMA, RSI, dan Bollinger width; scatter plot dan log anomali; distribusi rezim risiko; perbandingan volatilitas antar-aset; Pearson/rolling correlation; lag correlation; serta *market-wide risk score* dari aset terpilih.

Hubungan lintas aset harus disajikan sebagai hasil perhitungan, bukan asumsi bahwa selalu berlaku.

## 5.5 Gaussian Mixture dan Pelabelan Risiko Dinamis

1. Pengguna memilih fitur dan nilai `k` (default 3).
2. Fitur valid dinormalisasi dengan `StandardScaler`.
3. Gaussian Mixture dilatih pada data pelatihan.
4. Centroid dinilai memakai skor risiko gabungan dari volatilitas, spike ratio, dan volume terstandarisasi.
5. Cluster diurutkan dari skor terendah ke tertinggi sebagai SAFE, WARNING, dan DANGER.

ID cluster 0, 1, atau 2 tidak langsung menjadi label karena bersifat arbitrer.

## 5.6 Prediksi T+1 dengan HistGradientBoosting

- `RandomForestClassifier`: fitur waktu T memprediksi probabilitas SAFE, WARNING, dan DANGER pada T+1.
- `RandomForestRegressor`: fitur waktu T memprediksi `max_volatility` atau target numerik lain pada T+1.

Indikator rentang harga:

- Resistance = harga saat ini + estimasi volatilitas
- Stop Loss = harga saat ini - estimasi volatilitas

Keluaran hanya untuk analitik akademik, bukan nasihat investasi.

## 5.7 Konfigurasi Dinamis

```json
{
  "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
  "timeframe": "4h",
  "features": ["max_volatility", "spike_ratio", "rsi_14", "volume_zscore"],
  "anomaly_method": "adaptive_quantile",
  "anomaly_quantile": 0.95,
  "gmm_components": 3,
  "correlation_window": 30,
  "train_ratio": 0.8,
  "gb_max_iter": 200,
  "gb_max_depth": 10,
  "target_horizon": 1
}
```

## 5.8 Evaluasi dan Validasi Temporal

Data dibagi secara kronologis: data awal untuk pelatihan dan data berikutnya untuk pengujian. Pembagian acak tidak digunakan agar tidak terjadi kebocoran data masa depan.

| Komponen | Metrik |
|---|---|
| Gaussian Mixture | Silhouette Score dan interpretasi centroid |
| Klasifikasi | Accuracy, Precision, Recall, F1-Score per kelas |
| Regresi | MAE dan RMSE |
| Anomali | Jumlah anomali, tingkat anomali per periode, dan inspeksi sampel kejadian |

---

# BAB 6: STRUKTUR MODUL APLIKASI

```text
arkadanta/
  backend/
    main.py
    api/
      ingestion_routes.py
      analytics_routes.py
      prediction_routes.py
      model_routes.py
    ingestion/
      format_detector.py
      schema_validator.py
      dynamic_pipeline.py
      processors/
        csv_processor.py
        json_processor.py
    analytics/
      timeframe_aggregator.py
      feature_engineering.py
      anomaly_detector.py
      correlation_analyzer.py
    ml/
      dynamic_feature_selector.py
      risk_labeler.py
      model_trainer.py
      model_predictor.py
      model_evaluator.py
  spark_jobs/
    batch_analytics.py
    dynamic_aggregation.py
    feature_pipeline.py
    train_models.py
  frontend/
  data/drop_zone/
```

---

# BAB 7: RENCANA ANTARMUKA WEB

## Tab 1 — Data Ingestion & Preprocessing Manager

- Upload CSV atau JSON.
- Mapping kolom bila skema belum sesuai.
- Sinkronisasi Binance API.
- Status pipeline dan HDFS.
- Laporan kualitas data serta audit preprocessing.

## Tab 2 — Dynamic BI & Historical Explorer

- Pilihan aset, tanggal, timeframe, fitur, dan indikator.
- Grafik harga, volume, volatilitas, SMA/EMA, RSI, dan Bollinger width.
- Konfigurasi metode dan threshold anomali.
- Log anomali, korelasi, rolling correlation, dan lag correlation lintas aset.

## Tab 3 — Model Lab & Live Market Shield

- Konfigurasi fitur, Gaussian Mixture, HistGradientBoosting, horizon, dan split temporal.
- Centroid serta mapping SAFE/WARNING/DANGER.
- Metrik model.
- Candle live 5 menit.
- Status risiko, probabilitas T+1, estimasi volatilitas, resistance, dan stop loss.

---

# BAB 8: BATASAN DAN KRITERIA KEBERHASILAN

1. Aset awal: BTCUSDT, ETHUSDT, BNBUSDT, dan ADAUSDT; rentang historis mengikuti ketersediaan nyata tiap aset.
2. Data dasar menggunakan interval 5 menit; timeframe lain berasal dari agregasi pipeline.
3. Input awal mendukung CSV dan JSON; Parquet adalah pengembangan lanjutan.
4. Pipeline berhasil bila menolak data tidak valid, menormalisasi data valid, dan menghasilkan laporan kualitas yang dapat diaudit.
5. Analitik dinamis bila aset, timeframe, fitur, metode anomali, dan parameter model dapat diubah dari konfigurasi/API tanpa memodifikasi kode inti.
6. Model dievaluasi dengan data uji yang secara temporal lebih baru dari data latih.
7. Semua keluaran prediksi hanya untuk analitik akademik, bukan rekomendasi investasi.
