$ErrorActionPreference = "Stop"

$PYTHON_CMD = "python"
$SCRIPT_PATH = "d:\code\skill\social_science_scholar.py"

$PDF_DIR = "d:\code\skill\pdf"
$RAW_MD_DIR = "d:\code\skill\pdf_raw_md"
$OUT_DIR = "d:\code\skill\social_science_results"

Write-Host "Starting Social Science Scholar Analysis..."
& $PYTHON_CMD $SCRIPT_PATH $PDF_DIR $RAW_MD_DIR --out_dir $OUT_DIR
Write-Host "Analysis Complete. Check $OUT_DIR"
