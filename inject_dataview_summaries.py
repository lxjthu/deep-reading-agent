import os
import sys
import yaml
import json
import logging
import argparse
from openai import OpenAI
from dotenv import load_dotenv

# Ensure we can find local modules if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# LLM Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat" # Use chat for faster extraction, or reasoner if complex

def get_client():
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not found.")
        return None
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def extract_summaries(filename, content):
    client = get_client()
    if not client:
        return {}

    # Define specific keys we want for each file type to guide the LLM
    # This ensures consistency across different papers
    file_hints = {
        "1_Overview": "research_theme, problem_statement, importance, contribution",
        "2_Theory": "theoretical_foundation, hypothesis, mechanism",
        "3_Data": "data_source, sample_period, cleaning_method",
        "4_Variables": "dependent_variable, independent_variable, controls",
        "5_Identification": "econometric_model, identification_strategy, robustness",
        "6_Results": "main_finding, mechanism_result, heterogeneity",
        "7_Critique": "weakness, future_direction"
    }
    
    base_name = os.path.splitext(filename)[0]
    # Default hint
    hint = "key_points"
    for k, v in file_hints.items():
        if k in base_name:
            hint = v
            break

    prompt = f"""
    You are a research assistant summarizing academic notes for Obsidian Dataview.
    
    Task:
    1. Analyze the Markdown content provided below.
    2. Extract key insights corresponding to the suggested keys: [{hint}].
    3. You can add other relevant keys if important information exists (e.g., 'policy_implication').
    4. For each key, write a SINGLE, CONCISE sentence in CHINESE summarizing the content.
    5. Return ONLY a JSON object where keys are in English (snake_case) and values are the Chinese summaries.
    
    Content:
    {content[:5000]}
    """

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error extracting summaries for {filename}: {e}")
        return {}

def process_file(file_path):
    logger.info(f"Processing {file_path}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Separate existing Frontmatter
    frontmatter = {}
    body = content
    
    if content.startswith("---"):
        try:
            end_idx = content.find("\n---\n", 3)
            if end_idx != -1:
                fm_str = content[3:end_idx]
                frontmatter = yaml.safe_load(fm_str)
                body = content[end_idx+5:]
        except Exception as e:
            logger.warning(f"Failed to parse existing frontmatter: {e}")

    # Extract Summaries from Body
    summaries = extract_summaries(os.path.basename(file_path), body)
    
    if not summaries:
        logger.warning("No summaries extracted.")
        return

    # Merge into Frontmatter (Dataview fields)
    # We prefix keys with 'dv_' to identify them easily, or just use semantic keys?
    # User said: "small title as key, summary as value".
    # Let's keep keys clean like 'research_theme'.
    
    for k, v in summaries.items():
        frontmatter[k] = v
        
    # Reconstruct File
    new_fm_str = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    new_content = f"---\n{new_fm_str}\n---\n\n{body}"
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    logger.info(f"Updated {file_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_dir", help="Directory containing the 7 sub-part markdown files")
    args = parser.parse_args()
    
    target_dir = args.target_dir
    
    # Expected files
    patterns = [
        "1_Overview.md", "2_Theory.md", "3_Data.md", 
        "4_Variables.md", "5_Identification.md", 
        "6_Results.md", "7_Critique.md"
    ]
    
    for fname in patterns:
        fpath = os.path.join(target_dir, fname)
        if os.path.exists(fpath):
            process_file(fpath)
        else:
            logger.warning(f"File not found: {fpath}")

if __name__ == "__main__":
    main()
