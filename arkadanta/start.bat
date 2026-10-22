@echo off
echo ========================================================
echo   ARKADANTA - Dynamic Big Data Intelligence Pipeline
echo   Menjalankan FastAPI Backend (8000) & React UI (5173)
echo ========================================================

cd /d "%~dp0"
start "Arkadanta FastAPI Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000"
cd /d "%~dp0frontend"
start "Arkadanta React TypeScript Frontend" cmd /k "npm run dev"
