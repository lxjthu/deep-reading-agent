$ErrorActionPreference = "Stop"

$PYTHON_CMD = "python"

# Paths
$PDF_DIR = "d:\code\skill\pdf"
$RAW_MD_DIR = "d:\code\skill\pdf_raw_md"
$SEGMENTED_MD_DIR = "d:\code\skill\pdf_segmented_md"
$OUT_DIR = "d:\code\skill\social_science_results_v2"

# Scripts
$EXTRACT_SCRIPT = "d:\code\skill\anthropic_pdf_extract_raw.py"
$SEGMENT_SCRIPT = "d:\code\skill\deepseek_segment_raw_md.py"
$ANALYZE_SCRIPT = "d:\code\skill\social_science_analyzer.py"

Write-Host "=== Social Science Deep Reading Pipeline ==="

# 1. Extract Raw Text
Write-Host "[Step 1] Extracting PDF to Raw MD..."
if (-not (Test-Path $RAW_MD_DIR)) { New-Item -ItemType Directory -Path $RAW_MD_DIR }
& $PYTHON_CMD $EXTRACT_SCRIPT $PDF_DIR --out_dir $RAW_MD_DIR

# 2. Segment Text
Write-Host "[Step 2] Segmenting MD..."
if (-not (Test-Path $SEGMENTED_MD_DIR)) { New-Item -ItemType Directory -Path $SEGMENTED_MD_DIR }

# Process all MD files in raw directory
$raw_files = Get-ChildItem -Path $RAW_MD_DIR -Filter "*.md"
foreach ($file in $raw_files) {
    Write-Host "Segmenting: $($file.Name)"
    & $PYTHON_CMD $SEGMENT_SCRIPT $file.FullName --out_dir $SEGMENTED_MD_DIR
}

# 3. Deep Analysis (4-Layer)
Write-Host "[Step 3] Running 4-Layer Analysis..."
& $PYTHON_CMD $ANALYZE_SCRIPT $SEGMENTED_MD_DIR --out_dir $OUT_DIR

Write-Host "=== Pipeline Complete ==="
Write-Host "Results available in: $OUT_DIR"
