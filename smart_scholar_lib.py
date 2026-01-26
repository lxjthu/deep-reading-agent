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
PDF_RAW_DIR = os.path.join(BASE_DIR, "pdf_raw_md")
PDF_SEG_DIR = os.path.join(BASE_DIR, "pdf_segmented_md")

# Scripts
SCRIPT_PDF_TO_RAW = os.path.join(BASE_DIR, "anthropic_pdf_extract_raw.py")
SCRIPT_RAW_TO_SEG = os.path.join(BASE_DIR, "deepseek_segment_raw_md.py")
SCRIPT_PIPELINE_QUANT = os.path.join(BASE_DIR, "deep_read_pipeline.py") # Step-based
SCRIPT_PIPELINE_QUAL = os.path.join(BASE_DIR, "social_science_analyzer.py") # 4-Layer
SCRIPT_LINK_QUAL = os.path.join(BASE_DIR, "link_social_science_docs.py")
SCRIPT_FULL_QUANT = os.path.join(BASE_DIR, "run_full_pipeline.py") # Wrapper for Quant

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

    def ensure_segmented_md(self, pdf_path):
        """
        Ensures that raw and segmented MD files exist for the given PDF.
        Returns the path to the segmented MD file.
        """
        basename = os.path.basename(pdf_path)
        filename_no_ext = os.path.splitext(basename)[0]
        
        raw_md_path = os.path.join(PDF_RAW_DIR, f"{filename_no_ext}_raw.md")
        seg_md_path = os.path.join(PDF_SEG_DIR, f"{filename_no_ext}_segmented.md")
        
        # 1. PDF -> Raw MD
        if not os.path.exists(raw_md_path):
            logger.info(f"[Step 1] Extracting Raw Text for {basename}...")
            self.run_command([sys.executable, SCRIPT_PDF_TO_RAW, pdf_path, "--out_dir", PDF_RAW_DIR])
        
        if not os.path.exists(raw_md_path):
            logger.error(f"Failed to generate raw MD for {basename}")
            return None

        # 2. Raw MD -> Segmented MD
        if not os.path.exists(seg_md_path):
            logger.info(f"[Step 2] Segmenting Text for {basename}...")
            self.run_command([sys.executable, SCRIPT_RAW_TO_SEG, raw_md_path, "--out_dir", PDF_SEG_DIR])
            
        if not os.path.exists(seg_md_path):
            logger.error(f"Failed to generate segmented MD for {basename}")
            return None
            
        return seg_md_path
