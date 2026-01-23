param (
    [string]$InputPath = "pdf",
    [string]$OutDir = "pdf_raw_md",
    [ValidateSet("hybrid", "pypdf", "pdfplumber")]
    [string]$Method = "hybrid"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "anthropic_pdf_extract_raw.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

& $VenvPython $ScriptPath $InputPath --out_dir $OutDir --method $Method

