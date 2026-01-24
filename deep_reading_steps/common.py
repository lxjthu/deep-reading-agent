import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# LLM Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-reasoner" # Using reasoner for Acemoglu-level thinking

DEEP_READING_DIR = os.getenv("DEEP_READING_OUTPUT_DIR", os.path.join(os.getcwd(), "deep_reading_results"))

def get_deepseek_client():
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not found in environment variables.")
        return None
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def call_deepseek(prompt, system_prompt="You are a helpful assistant."):
    client = get_deepseek_client()
    if not client:
        return None

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek API call failed: {e}")
        return None

def load_segmented_md(md_path):
    """
    Parses the segmented markdown file into a dictionary of sections.
    Keys are section titles (or approximation), values are text content.
    """
    if not os.path.exists(md_path):
        logger.error(f"Segmented MD file not found: {md_path}")
        return {}

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple parsing based on "## " headers
    sections = {}
    current_section = None
    current_text = []

    for line in content.split('\n'):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_text).strip()
            current_section = line.strip("# ").strip()
            current_text = []
        else:
            current_text.append(line)
    
    if current_section:
        sections[current_section] = "\n".join(current_text).strip()

    return sections

def save_step_result(step_name, result, output_dir=None):
    if output_dir is None:
        output_dir = DEEP_READING_DIR
        
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_path = os.path.join(output_dir, f"{step_name}.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)
    logger.info(f"Saved result for {step_name} to {output_path}")
    return output_path
