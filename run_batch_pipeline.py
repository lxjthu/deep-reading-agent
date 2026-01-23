import os
import sys
import argparse
import subprocess
import glob

def run_command(command):
    """Run a shell command."""
    print(f"Running: {command}")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        # Don't exit, just continue to next file
        pass

def main():
    parser = argparse.ArgumentParser(description="Batch Run Deep Reading Pipeline")
    parser.add_argument("pdf_dir", help="Directory containing PDF files")
    args = parser.parse_args()

    pdf_dir = os.path.abspath(args.pdf_dir)
    if not os.path.exists(pdf_dir):
        print(f"Directory not found: {pdf_dir}")
        return

    # Find all PDFs
    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        return
        
    print(f"Found {len(pdf_files)} PDF files in {pdf_dir}")
    
    cwd = os.getcwd()
    deep_reading_results_dir = os.path.join(cwd, "deep_reading_results")
    
    for pdf_path in pdf_files:
        basename = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Check if already processed
        # Expected output: deep_reading_results/{basename}/Final_Deep_Reading_Report.md
        expected_report = os.path.join(deep_reading_results_dir, basename, "Final_Deep_Reading_Report.md")
        
        print(f"\nProcessing: {basename}")
        
        if os.path.exists(expected_report):
            print(f"[SKIP] Report already exists: {expected_report}")
            continue
            
        print(f"[START] Processing {basename}...")
        # Call the existing single-file pipeline script
        # Assuming run_full_pipeline.py is in the current working directory
        script_path = os.path.join(cwd, "run_full_pipeline.py")
        
        run_command(f'python "{script_path}" "{pdf_path}"')
        
    print("\n--- Batch Processing Complete ---")

if __name__ == "__main__":
    main()
