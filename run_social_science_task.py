import os
import subprocess
import sys
import glob

# Configuration
PYTHON = sys.executable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directories - PaddleOCR primary, legacy fallback
PADDLEOCR_MD_DIR = os.path.join(BASE_DIR, "paddleocr_md")
RAW_MD_DIR = os.path.join(BASE_DIR, "pdf_raw_md")  # Legacy fallback
OUT_DIR = os.path.join(BASE_DIR, "social_science_results_v2")

# Scripts
ANALYZE_SCRIPT = os.path.join(BASE_DIR, "social_science_analyzer.py")
LINK_SCRIPT = os.path.join(BASE_DIR, "link_social_science_docs.py")

# Target Keywords (The 3 specific papers)
KEYWORDS = ["含绿量", "中国生态产品", "组态视角"]

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def main():
    print("=== Social Science Task Orchestrator (Python) ===")

    # Determine extraction directory (prefer PaddleOCR, fallback to legacy)
    paddleocr_files = glob.glob(os.path.join(PADDLEOCR_MD_DIR, "*.md"))
    raw_files = glob.glob(os.path.join(RAW_MD_DIR, "*.md"))

    # Check which directory has matching target files
    has_paddleocr = any(any(k in os.path.basename(f) for k in KEYWORDS) for f in paddleocr_files)
    has_raw = any(any(k in os.path.basename(f) for k in KEYWORDS) for f in raw_files)

    if has_paddleocr:
        extraction_dir = PADDLEOCR_MD_DIR
        print(f"Using PaddleOCR extraction directory: {extraction_dir}")
    elif has_raw:
        extraction_dir = RAW_MD_DIR
        print(f"Using legacy extraction directory: {extraction_dir}")
    else:
        print("No matching extraction files found. Run extraction first.")
        return

    # 1. Analyze (pass extraction directory directly, no segmentation needed)
    print("\n[Step 1] Analyzing Target Files...")
    cmd = [PYTHON, ANALYZE_SCRIPT, extraction_dir, "--out_dir", OUT_DIR, "--filter"] + KEYWORDS
    run_cmd(cmd)

    # 2. Inject Links
    print("\n[Step 2] Injecting Bidirectional Links...")
    run_cmd([PYTHON, LINK_SCRIPT, OUT_DIR])

    print("\n=== Task Complete ===")

if __name__ == "__main__":
    main()
