$ErrorActionPreference = "Stop"

$PYTHON_CMD = "python"
$SCRIPT_PATH = "d:\code\skill\run_supplemental_reading.py"

# Optional argument: path to report
if ($args.Count -gt 0) {
    $REPORT_PATH = $args[0]
    & $PYTHON_CMD $SCRIPT_PATH $REPORT_PATH
} else {
    & $PYTHON_CMD $SCRIPT_PATH
}
