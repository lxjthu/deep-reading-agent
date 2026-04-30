# Deep Reading Agent - One-click Dev Launcher
# Usage: .\start-dev.ps1

$projectRoot = $PSScriptRoot
$venvPython = "$projectRoot\.venv\Scripts\python.exe"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Deep Reading Agent - Dev Launcher" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Virtual environment not found!" -ForegroundColor Red
    exit 1
}

Write-Host "[1/2] Starting backend (port 8000)..." -ForegroundColor Yellow
$backendCmd = "Set-Location '$projectRoot\backend'; & '$venvPython' -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

Write-Host "[2/2] Starting frontend (port 5173)..." -ForegroundColor Yellow
$frontendCmd = "Set-Location '$projectRoot\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host ""
Write-Host "Waiting for services..." -ForegroundColor Gray
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor Cyan
Write-Host "  Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

Start-Process "http://localhost:5173"
