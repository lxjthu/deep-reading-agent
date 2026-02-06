import os
import re
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-reasoner"

def get_deepseek_client():
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not found in environment variables.")
        return None
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def load_prompt(prompt_path):
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def extract_l1_content(segmented_md_path):
    with open(segmented_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'## L1\. L1_Context.*?```text\s*\n(.*?)\n```', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    fallback_match = re.search(r'## L1\. L1_Context.*?(?=## L2\.|## L3\.|## L4\.|$)', content, re.DOTALL)
    if fallback_match:
        text = fallback_match.group(0).replace('## L1. L1_Context (背景层)', '').strip()
        return text
    
    logger.error("Could not extract L1_Context content from the segmented markdown file.")
    return None

def call_deepseek_markdown(prompt, system_prompt):
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

def main():
    prompt_path = "prompts/qual_analysis/L1_Context_Prompt.md"
    segmented_md_path = "pdf_segmented_md/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径_segmented.md"
    
    test_output_dir = "test_output"
    os.makedirs(test_output_dir, exist_ok=True)
    
    prompt = load_prompt(prompt_path)
    l1_content = extract_l1_content(segmented_md_path)
    
    if not l1_content:
        logger.error("Failed to extract L1 content. Exiting.")
        return
    
    system_prompt = f"""{prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。直接输出Markdown格式的结构化内容即可。
"""
    
    user_prompt = f"""以下是论文的L1_Context（背景层）内容：

{l1_content}

请按照提示词要求进行分析，并直接输出Markdown格式的分析结果。"""
    
    logger.info("Calling DeepSeek API for L1 Context analysis...")
    result = call_deepseek_markdown(user_prompt, system_prompt)
    
    if result:
        output_path = os.path.join(test_output_dir, "L1_Context_Analysis.md")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        logger.info(f"Analysis saved to {output_path}")
        print(f"[OK] Analysis saved to: {output_path}")
    else:
        logger.error("Failed to get analysis result.")

if __name__ == "__main__":
    main()
