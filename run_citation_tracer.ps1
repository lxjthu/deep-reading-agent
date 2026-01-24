param (
    [string]$SegmentedMd,
    [string]$RefExcel
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ScriptDir "citation_tracer.py"

if (-not $SegmentedMd) {
    # Default to finding one
    $SegmentedMd = Get-ChildItem "pdf_segmented_md\*.md" | Select-Object -First 1 -ExpandProperty FullName
}

if (-not $RefExcel) {
    # Default to matching excel
    $BaseName = [System.IO.Path]::GetFileNameWithoutExtension($SegmentedMd)
    # Remove _segmented
    if ($BaseName.EndsWith("_segmented")) {
        $BaseName = $BaseName.Substring(0, $BaseName.Length - 10)
    }
    $RefExcel = Join-Path $ScriptDir "references\${BaseName}_references.xlsx"
}

Write-Host "Tracing Citations..."
Write-Host "MD: $SegmentedMd"
Write-Host "Excel: $RefExcel"

& $VenvPython $ScriptPath $SegmentedMd $RefExcel
