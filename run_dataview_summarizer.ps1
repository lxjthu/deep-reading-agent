$ErrorActionPreference = "Stop"

$PYTHON_CMD = "python"
$SCRIPT_PATH = "d:\code\skill\inject_dataview_summaries.py"

# Argument: target directory
if ($args.Count -gt 0) {
    $TARGET_DIR = $args[0]
} else {
    $TARGET_DIR = "d:\code\skill\deep_reading_results"
}

& $PYTHON_CMD $SCRIPT_PATH $TARGET_DIR
