import os
import sys
import subprocess
import shutil
import argparse

def run_command(command, env=None):
    """Run a shell command and print output."""
    print(f"Running: {command}")
    # Merge current env with passed env
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
        
    try:
        # Using shell=True for simpler command string handling on Windows
        # checking return code
        subprocess.run(command, shell=True, check=True, env=full_env)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run Full Deep Reading Pipeline")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    args = parser.parse_args()

    pdf_path = os.path.abspath(args.pdf_path)
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        return

    # Basic info
    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    cwd = os.getcwd()
    
    # Paths
    raw_md_dir = os.path.join(cwd, "pdf_raw_md")
    raw_md_file = os.path.join(raw_md_dir, f"{basename}_raw.md")
    
    segmented_md_dir = os.path.join(cwd, "pdf_segmented_md")
    segmented_md_file = os.path.join(segmented_md_dir, f"{basename}_segmented.md")
    
    # NEW: Output to a specific folder named after the article
    # We use "deep_reading_results/{basename}"
    final_output_dir = os.path.join(cwd, "deep_reading_results", basename)
    
    print(f"--- Pipeline Start for: {basename} ---")
    print(f"Output Directory: {final_output_dir}")

    # 1. Extract Text (PDF -> Raw MD)
    print("\n[Step 1] Extracting PDF text...")
    run_command(f'python anthropic_pdf_extract_raw.py "{pdf_path}" --out_dir "{raw_md_dir}"')

    # 2. Segment (Raw MD -> Segmented MD)
    print("\n[Step 2] Segmenting text (DeepSeek)...")
    run_command(f'python deepseek_segment_raw_md.py "{raw_md_file}" --out_dir "{segmented_md_dir}"')

    # 3. Deep Reading (Segmented MD -> Analysis)
    print("\n[Step 3] Running Deep Reading Agent...")
    # Pass the output directory via environment variable so common.py picks it up
    env = {"DEEP_READING_OUTPUT_DIR": final_output_dir}
    run_command(f'python deep_read_pipeline.py "{segmented_md_file}" --out_dir "{final_output_dir}"', env=env)

    # 4. Supplemental Check & Fix
    print("\n[Step 4] Checking for missing sections and fixing...")
    report_path = os.path.join(final_output_dir, "Final_Deep_Reading_Report.md")
    # This script also needs the env var to know where sub-files are located
    run_command(f'python run_supplemental_reading.py "{report_path}" --regenerate', env=env)

    # 5. Dataview Summaries
    print("\n[Step 5] Injecting Dataview Summaries...")
    run_command(f'python inject_dataview_summaries.py "{final_output_dir}"')

    # 6. Obsidian Metadata
    print("\n[Step 6] Injecting Obsidian Metadata & Links...")
    # We use the raw_md_file as source for metadata extraction
    run_command(f'python inject_obsidian_meta.py "{raw_md_file}" "{final_output_dir}" --raw_md "{raw_md_file}"')

    print(f"\n--- Pipeline Complete! ---")
    print(f"Results are in: {final_output_dir}")

if __name__ == "__main__":
    main()
