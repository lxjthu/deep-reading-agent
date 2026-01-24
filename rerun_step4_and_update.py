import os
import sys
import argparse
from dotenv import load_dotenv

# Add current directory to path so we can import modules
sys.path.append(os.getcwd())

from deep_reading_steps import step_4_vars
from deep_reading_steps.common import load_segmented_md
import run_supplemental_reading

def main():
    # Hardcoded for the user's specific case, but could be argumentized
    segmented_md_path = r"d:\code\skill\pdf_segmented_md\1-QJE-原神论文_segmented.md"
    output_dir = r"d:\code\skill\deep_reading_results\1-QJE-原神论文"
    
    # 1. Setup Environment
    os.environ["DEEP_READING_OUTPUT_DIR"] = output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"Loading segmented MD: {segmented_md_path}")
    sections = load_segmented_md(segmented_md_path)
    if not sections:
        print("Error: Could not load sections.")
        return

    # 2. Rerun Step 4
    print("--- Re-running Step 4: Variables ---")
    step_4_vars.run(sections)
    print("Step 4 completed.")

    # 3. Update Final Report
    print("--- Updating Final Report ---")
    report_path = os.path.join(output_dir, "Final_Deep_Reading_Report.md")
    
    # run_supplemental_reading.main() expects args, so we mock them or call the logic directly
    # Easier to call run_supplemental_reading via subprocess to avoid argument parsing mess,
    # OR just import the specific function if possible.
    # But run_supplemental_reading.main() is designed as CLI entry point.
    # Let's use subprocess for the final update to ensure clean env state.
    
    cmd = f'python run_supplemental_reading.py "{report_path}" --regenerate'
    print(f"Running: {cmd}")
    os.system(cmd)
    
    print("Done.")

if __name__ == "__main__":
    main()
