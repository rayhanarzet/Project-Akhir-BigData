# Arkadanta: Dynamic Big Data Intelligence Pipeline

**Analisis, Deteksi Anomali, dan Prediksi Risiko Volatilitas Pasar Kripto Berbasis Lambda Architecture**

---

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
      anomaly_detector.py       # Deteksi anomali: rolling_zscore, iqr, adaptive_quantile, kmeans
      correlation_analyzer.py   # Pearson, rolling correlation, lag correlation, market-wide risk score
    ml/                         # [ORANG 2]
      dynamic_feature_selector.py
      risk_labeler.py           # StandardScaler + K-Means + pengurutan skor risiko centroid (SAFE/WARNING/DANGER)
      model_trainer.py          # Temporal split + Random Forest Classifier & Regressor (T+1)
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
    sample_generator.py         # Generator data sampel 5m & audit log otomatis untuk pengujian mandiri
    drop_zone/                  # Lokasi penyimpanan data OHLCV bersih
```

---

## Cara Menjalankan

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
