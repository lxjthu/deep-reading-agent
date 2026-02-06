import os
import sys
import logging
import json
import subprocess
import json_repair
from openai import OpenAI
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Constants / Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PADDLEOCR_DIR = os.path.join(BASE_DIR, "paddleocr_md")
PDF_RAW_DIR = os.path.join(BASE_DIR, "pdf_raw_md")  # Legacy fallback

# Scripts - Extraction
SCRIPT_PDF_TO_MD = os.path.join(BASE_DIR, "paddleocr_pipeline.py")
SCRIPT_PDF_TO_RAW = os.path.join(BASE_DIR, "anthropic_pdf_extract_raw.py")

# Scripts - Analysis pipelines
SCRIPT_PIPELINE_QUANT = os.path.join(BASE_DIR, "deep_read_pipeline.py")  # Step-based
SCRIPT_PIPELINE_QUAL = os.path.join(BASE_DIR, "social_science_analyzer.py")  # 4-Layer
SCRIPT_LINK_QUAL = os.path.join(BASE_DIR, "link_social_science_docs.py")
SCRIPT_FULL_QUANT = os.path.join(BASE_DIR, "run_full_pipeline.py")  # Wrapper for Quant

class SmartScholar:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment")
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        
    def classify_paper(self, text_segment: str) -> str:
        """
        Classify the paper as 'QUANT' or 'QUAL' based on text content.
        """
        system_prompt = """
        You are an expert Academic Editor. Your task is to classify a research paper into one of three categories based on its content (Abstract, Intro, Methodology).
        
        Categories:
        1. "QUANT": Quantitative Economics / Econometrics / Empirical Finance.
           - Keywords: Regression, Identification Strategy, Difference-in-Differences (DID), IV, RDD, Stata, Equation, Robustness Check, Coefficients.
           - Style: Mathematical, Statistical, Hypothesis Testing.
           
        2. "QUAL": Qualitative Social Science / Management / Case Study / Literature Review.
           - Keywords: Case Study, Grounded Theory, Qualitative Comparative Analysis (QCA), Semi-structured Interview, Theoretical Framework, Construct, Mechanism (narrative), Literature Review, Research Progress, Survey, Overview, Meta-analysis.
           - Style: Narrative, Theoretical, Conceptual, Process Model, Comprehensive Review.
           
        3. "IGNORE": Non-Research Content / Editorials / Metadata.
           - Keywords: Host's Introduction, Editor's Note, Preface, Call for Papers, Table of Contents, Conference Announcement, Erratum, Book Review, News.
           - Style: Very short (< 2 pages), introductory, administrative, non-academic structure.
           
        Output JSON: {"type": "QUANT" | "QUAL" | "IGNORE", "reason": "short explanation"}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this paper content:\n\n{text_segment[:4000]}"}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            result = json_repair.repair_json(content, return_objects=True)
            return result.get("type", "QUAL") # Default to QUAL if unsure (safer for reviews/theory)
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return "QUAL" # Fallback to QUAL

    def run_command(self, cmd, cwd=None):
        if cwd is None:
            cwd = BASE_DIR
        logger.info(f"Running command: {' '.join(cmd)}")
        try:
            subprocess.check_call(cmd, cwd=cwd)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {e}")
            raise

    def ensure_extracted_md(self, pdf_path, use_paddleocr=True):
        """
        Ensures that an extracted MD file exists for the given PDF.
        Returns the path to the extraction MD file (no segmentation step).

        Args:
            pdf_path: Path to the PDF file
            use_paddleocr: If True, use PaddleOCR pipeline (default); else use legacy

        Returns:
            Path to extracted MD file, or None on failure
        """
        basename = os.path.basename(pdf_path)
        filename_no_ext = os.path.splitext(basename)[0]

        if use_paddleocr:
            # PaddleOCR path
            paddleocr_md_path = os.path.join(PADDLEOCR_DIR, f"{filename_no_ext}_paddleocr.md")

            # PDF -> PaddleOCR MD
            if not os.path.exists(paddleocr_md_path):
                logger.info(f"[Extraction] Extracting text (PaddleOCR) for {basename}...")
                os.makedirs(PADDLEOCR_DIR, exist_ok=True)
                self.run_command([sys.executable, SCRIPT_PDF_TO_MD, pdf_path, "--out_dir", PADDLEOCR_DIR])

            if os.path.exists(paddleocr_md_path):
                logger.info(f"[Extraction] Complete: {paddleocr_md_path}")
                return paddleocr_md_path

            logger.warning(f"PaddleOCR failed for {basename}, trying legacy extraction...")
            return self.ensure_extracted_md(pdf_path, use_paddleocr=False)

        else:
            # Legacy path
            raw_md_path = os.path.join(PDF_RAW_DIR, f"{filename_no_ext}_raw.md")

            # PDF -> Raw MD
            if not os.path.exists(raw_md_path):
                logger.info(f"[Extraction] Extracting text (legacy) for {basename}...")
                os.makedirs(PDF_RAW_DIR, exist_ok=True)
                self.run_command([sys.executable, SCRIPT_PDF_TO_RAW, pdf_path, "--out_dir", PDF_RAW_DIR])

            if os.path.exists(raw_md_path):
                logger.info(f"[Extraction] Complete: {raw_md_path}")
                return raw_md_path

            logger.error(f"Failed to extract MD for {basename}")
            return None

    # Deprecated alias for backward compatibility
    def ensure_segmented_md(self, pdf_path, use_paddleocr=True):
        """Deprecated: use ensure_extracted_md() instead."""
        return self.ensure_extracted_md(pdf_path, use_paddleocr=use_paddleocr)
