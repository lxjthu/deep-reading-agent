param (
    [string]$InputPath,
    [string]$Output = "results.xlsx",
    [switch]$Force
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$MainScript = Join-Path $ScriptDir "main.py"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found. Please run setup first."
    exit 1
}

# When using Splatting (@pyArgs), PowerShell might be passing empty strings if variables are null
# Let's construct the command string explicitly to be safe
$cmdArgs = @()
$cmdArgs += $InputPath
$cmdArgs += "--output"
$cmdArgs += $Output

if ($Force) {
    $cmdArgs += "--force"
}

# Use Start-Process or direct invocation
& $VenvPython $MainScript $cmdArgs
