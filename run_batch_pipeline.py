import os
import sys
import argparse
import logging
from smart_scholar_lib import SmartScholar
from state_manager import StateManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
SCRIPT_PIPELINE_QUANT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_read_pipeline.py")
SCRIPT_PIPELINE_QUAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_science_analyzer.py")
SCRIPT_LINK_QUAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "link_social_science_docs.py")
SCRIPT_INJECT_DATAVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inject_dataview_summaries.py")
SCRIPT_INJECT_OBSIDIAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inject_obsidian_meta.py")
PDF_SEG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_segmented_md")
PDF_RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_raw_md")

def main():
    parser = argparse.ArgumentParser(description="Smart Batch Run Deep Reading Pipeline")
    parser.add_argument("pdf_dir", help="Directory containing PDF files")
    args = parser.parse_args()

    pdf_dir = os.path.abspath(args.pdf_dir)
    if not os.path.exists(pdf_dir):
        logger.error(f"Directory not found: {pdf_dir}")
        return

    # Find all PDFs (recursively)
    pdf_files = []
    for root, dirs, files in os.walk(pdf_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(root, file))
    
    if not pdf_files:
        logger.error(f"No PDF files found in {pdf_dir}")
        return
        
    logger.info(f"Found {len(pdf_files)} PDF files in {pdf_dir}")
    
    scholar = SmartScholar()
    state_mgr = StateManager()
    
    deep_reading_results_dir = os.path.join(os.getcwd(), "deep_reading_results")
    qual_results_dir = os.path.join(os.getcwd(), "social_science_results_v2")
    
    for pdf_path in pdf_files:
        basename = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Hash-based check
        if state_mgr.is_processed(pdf_path, output_check_func=lambda d: os.path.exists(d) and (os.path.exists(os.path.join(d, "Final_Deep_Reading_Report.md")) or os.path.exists(os.path.join(d, f"{basename}_Full_Report.md")))):
            logger.info(f"[SKIP] Hash check passed for: {basename}")
            continue

        # Fallback to filename check (legacy)
        quant_report = os.path.join(deep_reading_results_dir, basename, "Final_Deep_Reading_Report.md")
        qual_report = os.path.join(qual_results_dir, basename, f"{basename}_Full_Report.md")
        
        if os.path.exists(quant_report):
            logger.info(f"[SKIP] Found existing Quant report for: {basename}")
            # Opportunistically mark as completed in state manager if not present
            state_mgr.mark_completed(pdf_path, os.path.dirname(quant_report), "QUANT")
            continue
        if os.path.exists(qual_report):
            logger.info(f"[SKIP] Found existing Qual report for: {basename}")
            state_mgr.mark_completed(pdf_path, os.path.dirname(qual_report), "QUAL")
            continue
            
        logger.info(f"\n[START] Processing {basename}...")
        state_mgr.mark_started(pdf_path)
        
        try:
            # 1. Extract & Segment (using lib)
            seg_md_path = scholar.ensure_segmented_md(pdf_path)
            if not seg_md_path:
                state_mgr.mark_failed(pdf_path, "Segmentation failed")
                continue

            # 2. Classify
            logger.info("Classifying Paper Type...")
            with open(seg_md_path, 'r', encoding='utf-8') as f:
                content_preview = f.read(5000)
            paper_type = scholar.classify_paper(content_preview)
            logger.info(f"Paper Classified as: {paper_type}")
            
            # 3. Dispatch
            if paper_type == "IGNORE":
                logger.info(f"[SKIP] Ignored non-research paper: {basename}")
                state_mgr.mark_completed(pdf_path, None, "IGNORE")
                continue

            if paper_type == "QUANT":
                logger.info(">>> Routing to Deep Reading Expert (Acemoglu Mode) <<<")
                
                # Run Deep Reading Pipeline
                scholar.run_command([sys.executable, SCRIPT_PIPELINE_QUANT, seg_md_path])
                
                # Post-processing: Metadata Injection
                paper_output_dir = os.path.join(deep_reading_results_dir, basename)
                raw_md_path = os.path.join(PDF_RAW_DIR, f"{basename}_raw.md")
                
                logger.info(">>> Injecting Dataview Summaries <<<")
                scholar.run_command([sys.executable, SCRIPT_INJECT_DATAVIEW, paper_output_dir])
                
                logger.info(">>> Injecting Obsidian Metadata & Links <<<")
                scholar.run_command([sys.executable, SCRIPT_INJECT_OBSIDIAN, raw_md_path, paper_output_dir, "--raw_md", raw_md_path])
                
                state_mgr.mark_completed(pdf_path, paper_output_dir, "QUANT")
                
            elif paper_type == "QUAL":
                logger.info(">>> Routing to Social Science Scholar (4-Layer Model) <<<")
                scholar.run_command([sys.executable, SCRIPT_PIPELINE_QUAL, PDF_SEG_DIR, "--filter", basename])
                # Run linker
                scholar.run_command([sys.executable, SCRIPT_LINK_QUAL, "social_science_results_v2"])
                
                paper_output_dir = os.path.join(qual_results_dir, basename)
                state_mgr.mark_completed(pdf_path, paper_output_dir, "QUAL")
                
        except Exception as e:
            logger.error(f"Error processing {basename}: {e}")
            state_mgr.mark_failed(pdf_path, str(e))
            
    logger.info("\n--- Batch Processing Complete ---")

if __name__ == "__main__":
    main()
