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

def extract_layer_content(segmented_md_path, layer):
    """
    Extract content for a specific layer from the segmented markdown file.
    Layer format: "L1", "L2", "L3", "L4"
    """
    with open(segmented_md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = rf'## {layer}\..*?```text\s*\n(.*?)\n```'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        return match.group(1).strip()

    fallback_pattern = rf'## {layer}\..*?(?=## L[1-4]\.|$)'
    fallback_match = re.search(fallback_pattern, content, re.DOTALL)
    if fallback_match:
        text = fallback_match.group(0)
        # Remove the header line
        text = re.sub(r'^## [Ll]\d+\..*?\n', '', text)
        return text.strip()

    logger.error(f"Could not extract {layer} content from the segmented markdown file.")
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

def analyze_layer(layer_name, prompt_path, segmented_md_path, output_dir):
    logger.info(f"Starting analysis for {layer_name}...")

    prompt = load_prompt(prompt_path)
    layer_code = layer_name.split('_')[0]  # Extract "L1" from "L1_Context"
    layer_content = extract_layer_content(segmented_md_path, layer_code)

    if not layer_content:
        logger.error(f"Failed to extract {layer_name} content. Skipping.")
        return False

    # For L3, we need to detect the genre
    genre = "Theoretical"  # Default for this paper
    if layer_code == "L3":
        # Detect genre from the content or metadata
        # For this paper, it's a theoretical analysis paper
        genre = "Theoretical"
        prompt = prompt.replace("{genre}", genre)
    else:
        # Remove {genre} placeholder if present
        prompt = prompt.replace("{genre}", "")

    system_prompt = f"""{prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。直接输出Markdown格式的结构化内容即可。
"""

    user_prompt = f"""以下是论文的{layer_name}部分内容：

{layer_content}

请按照提示词要求进行分析，并直接输出Markdown格式的分析结果。"""

    logger.info(f"Calling DeepSeek API for {layer_name} analysis...")
    result = call_deepseek_markdown(user_prompt, system_prompt)

    if result:
        output_filename = f"{layer_name}_Analysis.md"
        output_path = os.path.join(output_dir, output_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        logger.info(f"Analysis saved to {output_path}")
        print(f"[OK] {layer_name} analysis saved to: {output_path}")
        return True
    else:
        logger.error(f"Failed to get {layer_name} analysis result.")
        return False

def main():
    segmented_md_path = "test_segmented/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径_segmented.md"
    prompts_dir = "prompts/qual_analysis"
    test_output_dir = "test_output_qual"

    os.makedirs(test_output_dir, exist_ok=True)

    layers = [
        ("L1_Context", "L1_Context_Prompt.md"),
        ("L2_Theory", "L2_Theory_Prompt.md"),
        ("L3_Logic", "L3_Logic_Prompt.md"),
        ("L4_Value", "L4_Value_Prompt.md")
    ]

    results = {}
    for layer_name, prompt_filename in layers:
        prompt_path = os.path.join(prompts_dir, prompt_filename)
        success = analyze_layer(layer_name, prompt_path, segmented_md_path, test_output_dir)
        results[layer_name] = success
        print("-" * 80)

    summary = "\n".join([f"{k}: {'SUCCESS' if v else 'FAILED'}" for k, v in results.items()])
    print(f"\n{'='*80}\nANALYSIS SUMMARY\n{'='*80}\n{summary}\n{'='*80}")

if __name__ == "__main__":
    main()
