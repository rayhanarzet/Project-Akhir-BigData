# Script 1-Perintah PowerShell untuk Menjalankan Seluruh Layanan Arkadanta
# Cara pakai: .\run-all.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ArkadantaDir = Join-Path $RepoRoot "arkadanta"
$FrontendDir = Join-Path $ArkadantaDir "frontend"

$VenvRootPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$VenvSubPython = Join-Path $ArkadantaDir ".venv\Scripts\python.exe"
$VenvWindowsPython = Join-Path $ArkadantaDir ".venv-windows\Scripts\python.exe"

if (Test-Path $VenvRootPython) {
    $PythonExe = $VenvRootPython
} elseif (Test-Path $VenvSubPython) {
    $PythonExe = $VenvSubPython
} elseif (Test-Path $VenvWindowsPython) {
    $PythonExe = $VenvWindowsPython
} else {
    $PythonExe = "python"
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  ARKADANTA - Dynamic Big Data Intelligence Pipeline" -ForegroundColor Cyan
Write-Host "  Menjalankan FastAPI Backend + React Frontend + Streamlit Dashboard" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "[INFO] Python Interpreter : $PythonExe" -ForegroundColor Gray
Write-Host "[INFO] Working Directory  : $ArkadantaDir" -ForegroundColor Gray

Write-Host "[CLEANUP] Memastikan port 8000, 5173, dan 8501 bersih dari proses gantung..." -ForegroundColor Yellow
$conns = Get-NetTCPConnection -LocalPort 8000,5173,8501 -ErrorAction SilentlyContinue
if ($conns) {
    $conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[SETUP] Menginstal dependensi React Frontend (npm install)..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    npm install
    Pop-Location
}


Write-Host "[1/3] Menjalankan FastAPI Backend (http://localhost:8000)..." -ForegroundColor Green
Start-Process cmd.exe -WorkingDirectory $ArkadantaDir -ArgumentList "/k `"$PythonExe`" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

Write-Host "[2/3] Menjalankan React TypeScript Frontend (http://localhost:5173)..." -ForegroundColor Green
Start-Process cmd.exe -WorkingDirectory $FrontendDir -ArgumentList "/k npm run dev -- --host 127.0.0.1 --port 5173"

Write-Host "[3/3] Menjalankan Streamlit BI Dashboard (http://localhost:8501)..." -ForegroundColor Green
Start-Process cmd.exe -WorkingDirectory $ArkadantaDir -ArgumentList "/k `"$PythonExe`" -m streamlit run frontend/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false"

Write-Host ""
Write-Host "Seluruh layanan telah aktif:" -ForegroundColor Cyan
Write-Host "  -> FastAPI Swagger UI : http://localhost:8000/docs" -ForegroundColor White
Write-Host "  -> React Frontend     : http://localhost:5173" -ForegroundColor White
Write-Host "  -> Streamlit Dashboard: http://localhost:8501" -ForegroundColor White
