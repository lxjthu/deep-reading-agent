param (
    [string]$InputPath,
    [string]$Output = "results.xlsx"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$MainScript = Join-Path $ScriptDir "main.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

& $VenvPython $MainScript $InputPath --output $Output
