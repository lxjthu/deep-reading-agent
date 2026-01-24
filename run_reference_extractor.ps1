param (
    [Parameter(Mandatory=$true)]
    [string]$SegmentedMdPath,
    [string]$OutFile = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "extract_references.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

$cmdArgs = @()
$cmdArgs += $SegmentedMdPath

if ($OutFile -ne "") {
    $cmdArgs += "--out_file"
    $cmdArgs += $OutFile
}

& $VenvPython $ScriptPath $cmdArgs
