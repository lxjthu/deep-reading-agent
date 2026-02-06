import os
import sys
import subprocess
import shutil
import argparse

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PADDLEOCR_MD_DIR = os.path.join(BASE_DIR, "paddleocr_md")
PDF_RAW_MD_DIR = os.path.join(BASE_DIR, "pdf_raw_md")


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
    parser.add_argument("--use-paddleocr", action="store_true",
                        help="Use PaddleOCR for extraction (default: legacy pdfplumber)")
    args = parser.parse_args()

    pdf_path = os.path.abspath(args.pdf_path)
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        return

    # Basic info
    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    cwd = os.getcwd()

    # Output to a specific folder named after the article
    final_output_dir = os.path.join(cwd, "deep_reading_results", basename)

    print(f"--- Pipeline Start for: {basename} ---")
    print(f"Output Directory: {final_output_dir}")

    # Choose extraction method
    use_paddleocr = args.use_paddleocr

    if use_paddleocr:
        # PaddleOCR path
        paddleocr_md_dir = os.path.join(cwd, "paddleocr_md")
        extraction_md_file = os.path.join(paddleocr_md_dir, f"{basename}_paddleocr.md")
        source_md_file = extraction_md_file

        # 1. Extract Text (PDF -> PaddleOCR MD)
        print("\n[Step 1] Extracting PDF text (PaddleOCR)...")
        run_command(f'python paddleocr_pipeline.py "{pdf_path}" --out_dir "{paddleocr_md_dir}"')

    else:
        # Legacy path
        raw_md_dir = os.path.join(cwd, "pdf_raw_md")
        extraction_md_file = os.path.join(raw_md_dir, f"{basename}_raw.md")
        source_md_file = extraction_md_file

        # 1. Extract Text (PDF -> Raw MD)
        print("\n[Step 1] Extracting PDF text (legacy pdfplumber)...")
        run_command(f'python anthropic_pdf_extract_raw.py "{pdf_path}" --out_dir "{raw_md_dir}"')

    # 2. Deep Reading (Extraction MD -> Analysis)
    print("\n[Step 2] Running Deep Reading Agent...")
    env = {"DEEP_READING_OUTPUT_DIR": final_output_dir}
    run_command(f'python deep_read_pipeline.py "{extraction_md_file}" --out_dir "{final_output_dir}"', env=env)

    # 3. Supplemental Check & Fix
    print("\n[Step 3] Checking for missing sections and fixing...")
    report_path = os.path.join(final_output_dir, "Final_Deep_Reading_Report.md")
    run_command(f'python run_supplemental_reading.py "{report_path}" --regenerate', env=env)

    # 4. Dataview Summaries
    print("\n[Step 4] Injecting Dataview Summaries...")
    run_command(f'python inject_dataview_summaries.py "{final_output_dir}"')

    # 5. Obsidian Metadata
    print("\n[Step 5] Injecting Obsidian Metadata & Links...")
    # Check if QWEN_API_KEY is available for PDF vision extraction
    if os.getenv("QWEN_API_KEY"):
        run_command(f'python inject_obsidian_meta.py "{source_md_file}" "{final_output_dir}" --use_pdf_vision --pdf_path "{pdf_path}"')
    else:
        run_command(f'python inject_obsidian_meta.py "{source_md_file}" "{final_output_dir}"')

    print(f"\n--- Pipeline Complete! ---")
    print(f"Results are in: {final_output_dir}")

if __name__ == "__main__":
    main()
