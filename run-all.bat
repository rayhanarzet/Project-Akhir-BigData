@echo off
setlocal
title Arkadanta - One-Command Launcher (FastAPI + React FE)

echo ======================================================================
echo   ARKADANTA - Dynamic Big Data Intelligence Pipeline
echo   Menjalankan Semua Layanan dalam 1 Perintah:
echo     [1] FastAPI Backend Server   : http://localhost:8000 (Swagger: /docs)
echo     [2] React TypeScript UI (FE) : http://localhost:5173
echo ======================================================================

REM Tentukan lokasi root project dan folder arkadanta
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%backend\main.py" (
    set "ARKADANTA_DIR=%SCRIPT_DIR%"
    for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
) else (
    set "REPO_ROOT=%SCRIPT_DIR%"
    set "ARKADANTA_DIR=%SCRIPT_DIR%arkadanta\"
)

REM Deteksi Python interpreter dari .venv (root atau arkadanta)
if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PY_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
) else if exist "%ARKADANTA_DIR%\.venv\Scripts\python.exe" (
    set "PY_EXE=%ARKADANTA_DIR%\.venv\Scripts\python.exe"
) else if exist "%ARKADANTA_DIR%\.venv-windows\Scripts\python.exe" (
    set "PY_EXE=%ARKADANTA_DIR%\.venv-windows\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

echo.
echo [INFO] Menggunakan Python: %PY_EXE%
echo [INFO] Direktori Kerja   : %ARKADANTA_DIR%

REM Bersihkan proses lama/zombie yang masih menahan port 8000 atau 5173
echo [CLEANUP] Memastikan port 8000 dan 5173 bersih dari proses gantung...
powershell -NoProfile -Command "$conns = Get-NetTCPConnection -LocalPort 8000,5173 -ErrorAction SilentlyContinue; if ($conns) { $conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }"

REM Cek apakah node_modules di frontend sudah terinstal
if not exist "%ARKADANTA_DIR%frontend\node_modules" (
    echo [SETUP] Menginstal dependensi React Frontend ^(npm install^)...
    pushd "%ARKADANTA_DIR%frontend"
    call npm install
    popd
)


REM 1. Jalankan FastAPI Backend (Port 8000) - tanpa --reload agar tidak terkena bug multiprocessing spawn di Windows Python 3.14
echo [1/2] Menjalankan FastAPI Backend di port 8000...
start "Arkadanta - FastAPI Backend (8000)" /D "%ARKADANTA_DIR%" cmd /k ""%PY_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

REM 2. Jalankan React + TypeScript Frontend (Port 5173)
echo [2/2] Menjalankan React TypeScript Frontend di port 5173...
start "Arkadanta - React Frontend (5173)" /D "%ARKADANTA_DIR%frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173"


echo.
echo ======================================================================
echo   Seluruh layanan Arkadanta berhasil dijalankan!
echo   - FastAPI Docs  : http://localhost:8000/docs
echo   - React UI (FE) : http://localhost:5173
echo ======================================================================
endlocal
