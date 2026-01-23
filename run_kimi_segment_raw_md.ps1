param (
    [Parameter(Mandatory=$true)]
    [string]$RawMdPath,
    [string]$OutDir = "pdf_segmented_md",
    [string]$Model = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "kimi_segment_raw_md.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

$cmdArgs = @()
$cmdArgs += $RawMdPath
$cmdArgs += "--out_dir"
$cmdArgs += $OutDir

if ($Model -and $Model.Trim() -ne "") {
    $cmdArgs += "--model"
    $cmdArgs += $Model
}

& $VenvPython $ScriptPath $cmdArgs

