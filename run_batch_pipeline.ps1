$ErrorActionPreference = "Stop"

$PYTHON_CMD = "python"
$SCRIPT_PATH = "d:\code\skill\run_batch_pipeline.py"

# Argument: pdf directory
if ($args.Count -gt 0) {
    $PDF_DIR = $args[0]
} else {
    $PDF_DIR = "d:\code\skill\pdf"
}

& $PYTHON_CMD $SCRIPT_PATH $PDF_DIR
