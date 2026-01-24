import os
import subprocess
import sys
import glob

# Configuration
PYTHON = sys.executable
BASE_DIR = r"d:\code\skill"
RAW_MD_DIR = os.path.join(BASE_DIR, "pdf_raw_md")
SEG_MD_DIR = os.path.join(BASE_DIR, "pdf_segmented_md")
OUT_DIR = os.path.join(BASE_DIR, "social_science_results_v2")

# Scripts
SEGMENT_SCRIPT = os.path.join(BASE_DIR, "deepseek_segment_raw_md.py")
ANALYZE_SCRIPT = os.path.join(BASE_DIR, "social_science_analyzer.py")
LINK_SCRIPT = os.path.join(BASE_DIR, "link_social_science_docs.py")

# Target Keywords (The 3 specific papers)
KEYWORDS = ["含绿量", "中国生态产品", "组态视角"]

def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def main():
    print("=== Social Science Task Orchestrator (Python) ===")
    
    # 1. Segment specific files
    print("\n[Step 1] Segmenting Target Files...")
    os.makedirs(SEG_MD_DIR, exist_ok=True)
    
    raw_files = glob.glob(os.path.join(RAW_MD_DIR, "*.md"))
    for fpath in raw_files:
        fname = os.path.basename(fpath)
        if any(k in fname for k in KEYWORDS):
            print(f"Processing: {fname}")
            run_cmd([PYTHON, SEGMENT_SCRIPT, fpath, "--out_dir", SEG_MD_DIR])
            
    # 2. Analyze
    print("\n[Step 2] Analyzing Target Files...")
    # Pass keywords to analyzer to ensure it filters correctly too
    cmd = [PYTHON, ANALYZE_SCRIPT, SEG_MD_DIR, "--out_dir", OUT_DIR, "--filter"] + KEYWORDS
    run_cmd(cmd)
    
    # 3. Inject Links
    print("\n[Step 3] Injecting Bidirectional Links...")
    run_cmd([PYTHON, LINK_SCRIPT, OUT_DIR])
    
    print("\n=== Task Complete ===")

if __name__ == "__main__":
    main()
