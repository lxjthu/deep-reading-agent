param (
    [Parameter(Mandatory=$true)]
    [string]$SegmentedMdPath,
    [string]$OutDir = "deep_reading_results"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "deep_read_pipeline.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

& $VenvPython $ScriptPath $SegmentedMdPath --out_dir $OutDir
