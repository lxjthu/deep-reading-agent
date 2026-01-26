import os
import sys
import argparse
import logging
from smart_scholar_lib import SmartScholar

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
SCRIPT_PIPELINE_QUANT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_read_pipeline.py")
SCRIPT_PIPELINE_QUAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_science_analyzer.py")
SCRIPT_LINK_QUAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "link_social_science_docs.py")
PDF_SEG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_segmented_md")

def main():
    parser = argparse.ArgumentParser(description="Smart Scholar: Intelligent Academic Paper Analyzer")
    parser.add_argument("input_path", help="Path to PDF file or directory of PDFs")
    args = parser.parse_args()
    
    scholar = SmartScholar()
    
    if os.path.isfile(args.input_path):
        if args.input_path.lower().endswith(".pdf"):
            process_single_pdf(scholar, args.input_path)
        else:
            logger.error("Input file must be a PDF")
            
    elif os.path.isdir(args.input_path):
        pdf_files = [os.path.join(args.input_path, f) for f in os.listdir(args.input_path) if f.lower().endswith(".pdf")]
        logger.info(f"Found {len(pdf_files)} PDFs in directory.")
        for pdf in pdf_files:
            try:
                process_single_pdf(scholar, pdf)
            except Exception as e:
                logger.error(f"Error processing {pdf}: {e}")
    else:
        logger.error(f"Invalid input path: {args.input_path}")

def process_single_pdf(scholar, pdf_path):
    logger.info(f"=== Processing: {os.path.basename(pdf_path)} ===")
    
    # 1. Extract & Segment (using lib)
    seg_md_path = scholar.ensure_segmented_md(pdf_path)
    if not seg_md_path:
        return

    # 2. Classify
    logger.info("[Step 3] Classifying Paper Type...")
    with open(seg_md_path, 'r', encoding='utf-8') as f:
        content_preview = f.read(5000)
        
    paper_type = scholar.classify_paper(content_preview)
    logger.info(f"Paper Classified as: {paper_type}")
    
    # 3. Dispatch
    filename_no_ext = os.path.splitext(os.path.basename(pdf_path))[0]
    
    if paper_type == "QUANT":
        logger.info(">>> Routing to Deep Reading Expert (Acemoglu Mode) <<<")
        scholar.run_command([sys.executable, SCRIPT_PIPELINE_QUANT, seg_md_path])
        
    elif paper_type == "QUAL":
        logger.info(">>> Routing to Social Science Scholar (4-Layer Model) <<<")
        # social_science_analyzer takes a dir and filter
        scholar.run_command([sys.executable, SCRIPT_PIPELINE_QUAL, PDF_SEG_DIR, "--filter", filename_no_ext])
        
        # Run linker for Qual papers
        logger.info("Injecting Bidirectional Links...")
        scholar.run_command([sys.executable, SCRIPT_LINK_QUAL, "social_science_results_v2"])
        
    else:
        logger.warning(f"Unknown paper type: {paper_type}")

if __name__ == "__main__":
    main()
