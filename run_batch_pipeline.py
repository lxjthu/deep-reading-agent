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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PIPELINE_QUANT = os.path.join(BASE_DIR, "deep_read_pipeline.py")
SCRIPT_PIPELINE_QUAL = os.path.join(BASE_DIR, "social_science_analyzer_v2.py")
SCRIPT_QUAL_METADATA_EXTRACTOR = os.path.join(BASE_DIR, "-m", "qual_metadata_extractor.extractor")
SCRIPT_LINK_QUAL = os.path.join(BASE_DIR, "link_social_science_docs.py")
SCRIPT_INJECT_QUAL_META = os.path.join(BASE_DIR, "inject_qual_metadata.py")
SCRIPT_INJECT_OBSIDIAN = os.path.join(BASE_DIR, "inject_obsidian_meta.py")

# Directories
PADDLEOCR_DIR = os.path.join(BASE_DIR, "paddleocr_md")
PDF_RAW_DIR = os.path.join(BASE_DIR, "pdf_raw_md")  # Legacy fallback

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
            # 1. Extract (no segmentation step)
            extracted_md_path = scholar.ensure_extracted_md(pdf_path)
            if not extracted_md_path:
                state_mgr.mark_failed(pdf_path, "Extraction failed")
                continue

            # 2. Classify
            logger.info("Classifying Paper Type...")
            with open(extracted_md_path, 'r', encoding='utf-8') as f:
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

                # Run Deep Reading Pipeline (pass extraction MD directly)
                scholar.run_command([sys.executable, SCRIPT_PIPELINE_QUANT, extracted_md_path])

                # Post-processing: Metadata Injection
                paper_output_dir = os.path.join(deep_reading_results_dir, basename)

                logger.info(">>> Injecting Obsidian Metadata & Links (with PDF Vision) <<<")
                # 直接传递 PDF 路径，避免文件名匹配问题
                if os.getenv("QWEN_API_KEY"):
                    scholar.run_command([sys.executable, SCRIPT_INJECT_OBSIDIAN, extracted_md_path, paper_output_dir, "--use_pdf_vision", "--pdf_path", pdf_path])
                else:
                    scholar.run_command([sys.executable, SCRIPT_INJECT_OBSIDIAN, extracted_md_path, paper_output_dir])

                state_mgr.mark_completed(pdf_path, paper_output_dir, "QUANT")

            elif paper_type == "QUAL":
                logger.info(">>> Routing to Social Science Scholar V2 (4-Layer Model) <<<")

                # Run QUAL V2 Analysis (pass extraction directory)
                extraction_dir = os.path.dirname(extracted_md_path)
                scholar.run_command([sys.executable, SCRIPT_PIPELINE_QUAL, extraction_dir, "--filter", basename])
                
                # Step 2: Extract and Inject Metadata
                paper_output_dir = os.path.join(qual_results_dir, basename)
                pdf_dir_for_meta = os.path.dirname(pdf_path)
                
                logger.info(">>> Extracting and Injecting QUAL Metadata <<<")
                # 直接传递 PDF 路径，避免文件名匹配问题
                scholar.run_command([
                    sys.executable,
                    "-m",
                    "qual_metadata_extractor.extractor",
                    paper_output_dir,
                    pdf_dir_for_meta,
                    "--pdf_path", pdf_path,
                ])

                state_mgr.mark_completed(pdf_path, paper_output_dir, "QUAL")
                
        except Exception as e:
            logger.error(f"Error processing {basename}: {e}")
            state_mgr.mark_failed(pdf_path, str(e))
            
    logger.info("\n--- Batch Processing Complete ---")

if __name__ == "__main__":
    main()
