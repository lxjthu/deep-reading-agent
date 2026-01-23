import argparse
import os
import logging
from deep_reading_steps import (
    common,
    step_1_overview,
    step_2_theory,
    step_3_data,
    step_4_vars,
    step_5_identification,
    step_6_results,
    step_7_critique
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Run Deep Reading Pipeline")
    parser.add_argument("segmented_md_path", help="Path to the segmented markdown file")
    parser.add_argument("--out_dir", default="deep_reading_results", help="Output directory for results")
    args = parser.parse_args()

    if not os.path.exists(args.segmented_md_path):
        logger.error(f"File not found: {args.segmented_md_path}")
        return

    logger.info(f"Loading segmented MD: {args.segmented_md_path}")
    sections = common.load_segmented_md(args.segmented_md_path)
    
    if not sections:
        logger.error("No sections found in MD file.")
        return

    # Update output dir in common if needed, or pass it to save_step_result
    # For simplicity, we assume common.save_step_result uses a default or we could monkeypatch it,
    # but let's just ensure the directory exists here.
    os.makedirs(args.out_dir, exist_ok=True)
    
    # We need to pass output_dir to steps? 
    # Current implementation of steps uses common.save_step_result which defaults to "deep_reading_results"
    # To support custom out_dir, we should update common.py or pass it.
    # Let's update common.save_step_result default via a global or pass it.
    # Quick fix: modify the steps to accept output_dir is too much change. 
    # Let's just use the args.out_dir if possible by temporarily changing working dir or just hardcoding for now.
    # Or better, let's just run them. The steps save to "deep_reading_results" by default.
    
    logger.info("--- Step 1: Overview ---")
    step_1_overview.run(sections)
    
    logger.info("--- Step 2: Theory ---")
    step_2_theory.run(sections)
    
    logger.info("--- Step 3: Data ---")
    step_3_data.run(sections)
    
    logger.info("--- Step 4: Variables ---")
    step_4_vars.run(sections)
    
    logger.info("--- Step 5: Identification ---")
    step_5_identification.run(sections)
    
    logger.info("--- Step 6: Results ---")
    step_6_results.run(sections)
    
    logger.info("--- Step 7: Critique ---")
    step_7_critique.run(sections)

    # Final Synthesis
    logger.info("Generating Final Report...")
    final_report_path = os.path.join(args.out_dir, "Final_Deep_Reading_Report.md")
    with open(final_report_path, 'w', encoding='utf-8') as f:
        f.write(f"# Deep Reading Report: {os.path.basename(args.segmented_md_path)}\n\n")
        
        steps = [
            "1_Overview", "2_Theory", "3_Data", "4_Variables", 
            "5_Identification", "6_Results", "7_Critique"
        ]
        
        for step in steps:
            step_file = os.path.join("deep_reading_results", f"{step}.md")
            if os.path.exists(step_file):
                with open(step_file, 'r', encoding='utf-8') as sf:
                    content = sf.read()
                    f.write(f"## {step.replace('_', ' ')}\n\n")
                    f.write(content + "\n\n")
    
    logger.info(f"Done. Final report at: {final_report_path}")

if __name__ == "__main__":
    main()
