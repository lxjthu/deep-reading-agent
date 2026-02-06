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

import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clean_content(text):
    """
    Strips YAML frontmatter and Navigation sections from text.
    """
    # 1. Strip YAML Frontmatter (between --- and --- at start)
    # Match start of string, ---, content, ---, newline
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
    
    # 2. Strip Navigation section
    # Look for "## 导航" or "## Navigation" and remove everything after
    nav_markers = ["## 导航", "## Navigation"]
    for marker in nav_markers:
        if marker in text:
            text = text.split(marker)[0]
            
    return text.strip()

def main():
    parser = argparse.ArgumentParser(description="Run Deep Reading Pipeline")
    parser.add_argument("md_path", help="Path to the markdown file (extraction output or segmented)")
    parser.add_argument("--out_dir", default="deep_reading_results", help="Output directory for results")
    args = parser.parse_args()

    if not os.path.exists(args.md_path):
        logger.error(f"File not found: {args.md_path}")
        return

    logger.info(f"Loading MD: {args.md_path}")
    sections = common.load_md_sections(args.md_path)

    if not sections:
        logger.error("No sections found in MD file.")
        return

    # Create Per-Paper Output Directory
    paper_basename = os.path.splitext(os.path.basename(args.md_path))[0]
    for suffix in ("_segmented", "_paddleocr", "_raw"):
        if paper_basename.endswith(suffix):
            paper_basename = paper_basename[:-len(suffix)]
            break
        
    paper_output_dir = os.path.join(args.out_dir, paper_basename)
    os.makedirs(paper_output_dir, exist_ok=True)
    logger.info(f"Output directory: {paper_output_dir}")
    
    # NEW: Semantic Indexing Layer (to handle bad segmentation)
    from deep_reading_steps.semantic_router import generate_semantic_index
    
    # Check if index exists or needs generation
    index_path = os.path.join(paper_output_dir, "semantic_index.json")
    if not os.path.exists(index_path):
        # Extract full text for indexing
        # Note: In broken MDs, Section 1 often contains all text. 
        # We'll join all sections just to be safe.
        full_text = "\n\n".join(sections.values())
        logger.info(f"Generating Semantic Index from {len(full_text)} chars of text...")
        generate_semantic_index(full_text, paper_output_dir)
    else:
        logger.info("Semantic Index found, skipping generation.")

    # NEW: 智能路由章节到 7 个步骤 (Still run this for logging purposes, though steps will prefer Semantic Index)
    logger.info("--- Routing sections to steps ---")
    section_routing = common.route_sections_to_steps(sections)
    common.save_routing_result(section_routing, sections, paper_output_dir)
    
    # 执行 7 步分析
    # Note: We pass the FULL sections dict, assigned titles, AND the output_dir
    # The step functions will pass these to get_combined_text_for_step, which now checks for semantic_index.json
    
    def run_step(step_module, step_id, step_name):
        logger.info(f"--- Step {step_id}: {step_name} ---")
        assigned_titles = section_routing.get(step_id, [])
        # Pass step_id explicitly so common.py can query the semantic index
        # We need to update the run signature in step modules to accept step_id, OR update common.get_combined_text_for_step call inside them
        # EASIER: The step modules call common.get_combined_text_for_step(sections, assigned_titles, output_dir)
        # But common.py needs step_id to filter the JSON index.
        # FIX: We need to patch the step modules to pass step_id.
        # TEMPORARY HACK: We can monkey-patch or just update the step files. 
        # Actually, let's update the step files to pass step_id.
        # Wait, the prompt plan said "Modify common.py to support loading text...".
        # Let's update the step files quickly to pass step_id.
        
        # Actually, to avoid editing 7 files again, let's rely on the fact that get_combined_text_for_step
        # receives `assigned_titles`. But `assigned_titles` doesn't help with Semantic Index (which uses IDs).
        # We MUST update step_*.py to pass step_id.
        pass

    # Updating execution block to pass step_id to run()
    # I will update the step files in the next turn or via search/replace if I can.
    # For now, let's assume I will update them.
    
    logger.info("--- Step 1: Overview ---")
    step_1_overview.run(sections, section_routing.get(1, []), paper_output_dir, step_id=1)
    
    logger.info("--- Step 2: Theory ---")
    step_2_theory.run(sections, section_routing.get(2, []), paper_output_dir, step_id=2)
    
    logger.info("--- Step 3: Data ---")
    step_3_data.run(sections, section_routing.get(3, []), paper_output_dir, step_id=3)
    
    logger.info("--- Step 4: Variables ---")
    step_4_vars.run(sections, section_routing.get(4, []), paper_output_dir, step_id=4)
    
    logger.info("--- Step 5: Identification ---")
    step_5_identification.run(sections, section_routing.get(5, []), paper_output_dir, step_id=5)
    
    logger.info("--- Step 6: Results ---")
    step_6_results.run(sections, section_routing.get(6, []), paper_output_dir, step_id=6)
    
    logger.info("--- Step 7: Critique ---")
    step_7_critique.run(sections, section_routing.get(7, []), paper_output_dir, step_id=7)

    # Final Synthesis
    logger.info("Generating Final Report...")
    final_report_path = os.path.join(paper_output_dir, "Final_Deep_Reading_Report.md")
    with open(final_report_path, 'w', encoding='utf-8') as f:
        f.write(f"# Deep Reading Report: {paper_basename}\n\n")
        
        steps = [
            "1_Overview", "2_Theory", "3_Data", "4_Variables", 
            "5_Identification", "6_Results", "7_Critique"
        ]
        
        for step in steps:
            step_file = os.path.join(paper_output_dir, f"{step}.md")
            if os.path.exists(step_file):
                with open(step_file, 'r', encoding='utf-8') as sf:
                    content = sf.read()
                    cleaned_content = clean_content(content)
                    f.write(f"## {step.replace('_', ' ')}\n\n")
                    f.write(cleaned_content + "\n\n")
    
    logger.info(f"Done. Final report at: {final_report_path}")

if __name__ == "__main__":
    main()
