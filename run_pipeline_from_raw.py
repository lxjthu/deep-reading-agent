import os
import sys
import subprocess
import argparse

def run_command(command, env=None):
    """Run a shell command and print output."""
    print(f"Running: {command}")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
        
    try:
        subprocess.run(command, shell=True, check=True, env=full_env)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run Deep Reading Pipeline starting from Raw Markdown")
    parser.add_argument("raw_md_path", help="Path to the raw markdown file (e.g. *_raw.md)")
    args = parser.parse_args()

    raw_md_path = os.path.abspath(args.raw_md_path)
    if not os.path.exists(raw_md_path):
        print(f"Raw MD not found: {raw_md_path}")
        return

    # Infer basename: "xxx_raw.md" -> "xxx"
    filename = os.path.basename(raw_md_path)
    if filename.endswith("_raw.md"):
        basename = filename[:-7]
    else:
        basename = os.path.splitext(filename)[0]

    cwd = os.getcwd()
    
    # Paths
    # Output segmented md to default folder
    segmented_md_dir = os.path.join(cwd, "pdf_segmented_md")
    segmented_md_file = os.path.join(segmented_md_dir, f"{basename}_segmented.md")
    
    # Final results
    final_output_dir = os.path.join(cwd, "deep_reading_results", basename)
    
    print(f"--- Pipeline Start (from Raw MD) for: {basename} ---")
    print(f"Input: {raw_md_path}")
    print(f"Output Directory: {final_output_dir}")

    # 1. Segment (Raw MD -> Segmented MD) - Using DeepSeek
    print("\n[Step 1] Segmenting text (DeepSeek)...")
    # Ensure we use the Python executable from the current environment if possible, or just "python"
    run_command(f'python deepseek_segment_raw_md.py "{raw_md_path}" --out_dir "{segmented_md_dir}"')

    # 2. Deep Reading (Segmented MD -> Analysis)
    print("\n[Step 2] Running Deep Reading Agent...")
    env = {"DEEP_READING_OUTPUT_DIR": final_output_dir}
    run_command(f'python deep_read_pipeline.py "{segmented_md_file}" --out_dir "{final_output_dir}"', env=env)

    # 3. Supplemental Check & Fix
    print("\n[Step 3] Checking for missing sections and fixing...")
    report_path = os.path.join(final_output_dir, "Final_Deep_Reading_Report.md")
    run_command(f'python run_supplemental_reading.py "{report_path}" --regenerate', env=env)

    # 4. Dataview Summaries
    print("\n[Step 4] Injecting Dataview Summaries...")
    run_command(f'python inject_dataview_summaries.py "{final_output_dir}"')

    # 5. Obsidian Metadata
    print("\n[Step 5] Injecting Obsidian Metadata & Links...")
    run_command(f'python inject_obsidian_meta.py "{raw_md_path}" "{final_output_dir}" --raw_md "{raw_md_path}"')

    print(f"\n--- Pipeline Complete! ---")
    print(f"Results are in: {final_output_dir}")

if __name__ == "__main__":
    main()
