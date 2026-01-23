param (
    [Parameter(Mandatory=$true)]
    [string]$SourceMd,
    [Parameter(Mandatory=$true)]
    [string]$TargetDir,
    [string]$RawMd = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "inject_obsidian_meta.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

$cmdArgs = @()
$cmdArgs += $SourceMd
$cmdArgs += $TargetDir

if ($RawMd -and $RawMd.Trim() -ne "") {
    $cmdArgs += "--raw_md"
    $cmdArgs += $RawMd
}

& $VenvPython $ScriptPath $cmdArgs
