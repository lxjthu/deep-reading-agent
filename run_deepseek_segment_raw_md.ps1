param (
    [Parameter(Mandatory=$true)]
    [string]$RawMdPath,
    [string]$OutDir = "pdf_segmented_md"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "deepseek_segment_raw_md.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

$cmdArgs = @()
$cmdArgs += $RawMdPath
$cmdArgs += "--out_dir"
$cmdArgs += $OutDir

& $VenvPython $ScriptPath $cmdArgs
