@echo off
setlocal
title Arkadanta - One-Command Launcher (FastAPI + React FE + Streamlit)

echo ======================================================================
echo   ARKADANTA - Dynamic Big Data Intelligence Pipeline
echo   Menjalankan Semua Layanan dalam 1 Perintah:
echo     [1] FastAPI Backend Server   : http://localhost:8000 (Swagger: /docs)
echo     [2] React TypeScript UI (FE) : http://localhost:5173
echo     [3] Streamlit BI Dashboard   : http://localhost:8501
echo ======================================================================

set "ARKADANTA_DIR=%~dp0"
for %%I in ("%ARKADANTA_DIR%..") do set "REPO_ROOT=%%~fI"

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PY_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
) else if exist "%ARKADANTA_DIR%.venv\Scripts\python.exe" (
    set "PY_EXE=%ARKADANTA_DIR%.venv\Scripts\python.exe"
) else if exist "%ARKADANTA_DIR%.venv-windows\Scripts\python.exe" (
    set "PY_EXE=%ARKADANTA_DIR%.venv-windows\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

echo.
echo [INFO] Menggunakan Python: %PY_EXE%
echo [INFO] Direktori Kerja   : %ARKADANTA_DIR%

echo [CLEANUP] Memastikan port 8000, 5173, dan 8501 bersih dari proses gantung...
powershell -NoProfile -Command "$conns = Get-NetTCPConnection -LocalPort 8000,5173,8501 -ErrorAction SilentlyContinue; if ($conns) { $conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }"

if not exist "%ARKADANTA_DIR%frontend\node_modules" (
    echo [SETUP] Menginstal dependensi React Frontend ^(npm install^)...
    pushd "%ARKADANTA_DIR%frontend"
    call npm install
    popd
)

"%PY_EXE%" -c "import sys; sys.path.insert(0, r'%ARKADANTA_DIR%'); from data.sample_generator import ensure_sample_data_exists; ensure_sample_data_exists()"

echo [1/3] Menjalankan FastAPI Backend di port 8000...
start "Arkadanta - FastAPI Backend (8000)" /D "%ARKADANTA_DIR%" cmd /k ""%PY_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo [2/3] Menjalankan React TypeScript Frontend di port 5173...
start "Arkadanta - React Frontend (5173)" /D "%ARKADANTA_DIR%frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173"

echo [3/3] Menjalankan Streamlit Dashboard di port 8501...
start "Arkadanta - Streamlit Dashboard (8501)" /D "%ARKADANTA_DIR%" cmd /k ""%PY_EXE%" -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false"

echo.
echo ======================================================================
echo   Seluruh layanan Arkadanta berhasil dijalankan!
echo   - FastAPI Docs  : http://localhost:8000/docs
echo   - React UI (FE) : http://localhost:5173
echo   - Streamlit UI  : http://localhost:8501
echo ======================================================================
endlocal
