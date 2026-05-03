Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Deep Reading Agent - Build and Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1/6: Check Python version
Write-Host "[1/6] Checking Python version..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Python not found" }
    Write-Host "  Found: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Python is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# Step 2/6: Install PyInstaller
Write-Host "[2/6] Installing PyInstaller..." -ForegroundColor Yellow
pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to install PyInstaller." -ForegroundColor Red
    exit 1
}
Write-Host "  PyInstaller ready." -ForegroundColor Green

# Step 3/6: Clean previous builds
Write-Host "[3/6] Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build"; Write-Host "  Removed build/" -ForegroundColor Green }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist"; Write-Host "  Removed dist/" -ForegroundColor Green }
if (-not (Test-Path "build") -and -not (Test-Path "dist")) { Write-Host "  Clean." -ForegroundColor Green }

# Step 4/6: Run the build script
Write-Host "[4/6] Running build_windows.py..." -ForegroundColor Yellow
python build_windows.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Build script failed." -ForegroundColor Red
    exit 1
}
Write-Host "  Build script completed." -ForegroundColor Green

# Step 5/6: Test executable exists
Write-Host "[5/6] Checking executable..." -ForegroundColor Yellow
$exePath = "dist\DeepReadingAgent.exe"
if (Test-Path $exePath) {
    $sizeMB = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
    Write-Host "  Found: $exePath ($sizeMB MB)" -ForegroundColor Green
} else {
    Write-Host "  ERROR: $exePath not found." -ForegroundColor Red
    exit 1
}

# Step 6/6: Check ZIP package exists
Write-Host "[6/6] Checking ZIP package..." -ForegroundColor Yellow
$zipPath = "dist\DeepReadingAgent-Windows.zip"
if (Test-Path $zipPath) {
    $zipSizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
    Write-Host "  Found: $zipPath ($zipSizeMB MB)" -ForegroundColor Green
} else {
    Write-Host "  WARNING: $zipPath not found." -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Test the executable: dist\DeepReadingAgent.exe"
Write-Host "  2. Distribute the ZIP: dist\DeepReadingAgent-Windows.zip"
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
