# Set encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"

# Define Scripts
$ScriptExtractRaw = Join-Path $ScriptDir "anthropic_pdf_extract_raw.py"
$ScriptSegment = Join-Path $ScriptDir "deepseek_segment_raw_md.py"
$ScriptRef = Join-Path $ScriptDir "extract_references.py"

# Define Dirs
$PdfDir = Join-Path $ScriptDir "pdf"
$RawMdDir = Join-Path $ScriptDir "pdf_raw_md"
$SegMdDir = Join-Path $ScriptDir "pdf_segmented_md"
$RefDir = Join-Path $ScriptDir "references"

# Ensure Dirs Exist
New-Item -ItemType Directory -Force -Path $RawMdDir | Out-Null
New-Item -ItemType Directory -Force -Path $SegMdDir | Out-Null
New-Item -ItemType Directory -Force -Path $RefDir | Out-Null

# Get PDFs
$Pdfs = Get-ChildItem -Path $PdfDir -Filter *.pdf

if ($Pdfs.Count -eq 0) {
    Write-Error "No PDFs found in $PdfDir"
    exit 1
}

Write-Host "Found $($Pdfs.Count) PDFs. Starting Pipeline..." -ForegroundColor Green

foreach ($Pdf in $Pdfs) {
    $BaseName = $Pdf.BaseName
    Write-Host "`n=== Processing: $BaseName ===" -ForegroundColor Cyan
    
    # --- Step 1: PDF -> Raw MD ---
    $RawMdPath = Join-Path $RawMdDir "$BaseName.md"
    if (-not (Test-Path $RawMdPath)) {
        Write-Host "[Step 1] Extracting Raw Text (Anthropic)..."
        & $VenvPython $ScriptExtractRaw $Pdf.FullName
    } else {
        Write-Host "[Step 1] Raw MD exists, skipping."
    }
    
    # --- Step 2: Raw MD -> Segmented MD ---
    $SegMdPath = Join-Path $SegMdDir "${BaseName}_segmented.md"
    # Always re-run segmentation if Raw MD exists, or check timestamp? For now, run if not exists or force
    if (-not (Test-Path $SegMdPath)) {
        Write-Host "[Step 2] Segmenting Text (DeepSeek)..."
        & $VenvPython $ScriptSegment $RawMdPath
    } else {
        Write-Host "[Step 2] Segmented MD exists, skipping."
    }
    
    # --- Step 3: Segmented MD -> References Excel ---
    $RefExcelPath = Join-Path $RefDir "${BaseName}_references.xlsx"
    Write-Host "[Step 3] Extracting References..."
    & $VenvPython $ScriptRef $SegMdPath
    
    Write-Host "Done: $BaseName" -ForegroundColor Green
}

Write-Host "`nAll tasks completed." -ForegroundColor Green
