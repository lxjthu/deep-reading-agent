import argparse
import os
import re
import json
import logging
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import json_repair

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_deepseek_client():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = "https://api.deepseek.com"
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not found.")
        return None
    return OpenAI(api_key=api_key, base_url=base_url)

# --- STAGE 1: RAW EXTRACTION ---
def extract_raw_references(md_path):
    """
    Stage 1: Load MD, find References section, clean metadata.
    Returns: cleaned_text (str)
    """
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"File not found: {md_path}")
        
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    lines = content.split('\n')
    ref_content = []
    in_ref = False
    ref_keywords = ["References", "Bibliography", "Works Cited", "参考文献"]
    
    for line in lines:
        if line.startswith("## "):
            is_target = any(kw in line for kw in ref_keywords)
            if is_target:
                in_ref = True
                continue 
            elif in_ref:
                break
        
        if in_ref:
            if line.strip().startswith("- start_page:") or \
               line.strip().startswith("- start_marker:") or \
               line.strip().startswith("- boundary_source:"):
                continue
            ref_content.append(line)
            
    text = "\n".join(ref_content)
    text = re.sub(r"```text", "", text)
    text = re.sub(r"```", "", text)
    
    return text.strip()

# --- STAGE 2: PATTERN DISCOVERY & SEGMENTATION ---
def get_segmentation_pattern(sample_text):
    """
    Stage 2a: Ask LLM for split regex.
    """
    client = get_deepseek_client()
    prompt = f"""
You are an expert in text processing.
Here are the first 30 lines of a bibliography:
{sample_text}

Task: Provide a Python REGEX to split this text into individual reference entries.
- The regex should match the *separator* or the *start* of a new entry.
- Common patterns: `r'\\n(?=[A-Z])'` (newline before Capital), `r'\\n\\n'`, `r'\\n\\['`.

Output JSON ONLY:
{{
  "split_pattern": "regex",
  "explanation": "why"
}}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json_repair.repair_json(response.choices[0].message.content, return_objects=True)
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return None

def segment_references(full_text, split_pattern):
    """
    Stage 2b: Execute split.
    """
    try:
        # Use re.split but keep delimiters if possible? 
        # Usually split pattern matches the delimiter (newline).
        entries = re.split(split_pattern, full_text)
        # Filter empty
        entries = [e.strip() for e in entries if len(e.strip()) > 10]
        return entries
    except Exception as e:
        logger.error(f"Split Error: {e}")
        return []

# --- STAGE 3: PARSING (REGEX FIRST) ---
def get_parsing_pattern(sample_text):
    """
    Stage 3a: Ask LLM for parse regex.
    """
    client = get_deepseek_client()
    prompt = f"""
Here is a single reference entry:
{sample_text}

Task: Provide a Python REGEX with named groups to extract:
author, year, title, journal, vol_issue, pages.
Use `(?P<name>...)` syntax. Use `re.DOTALL` compatible regex.

Output JSON ONLY:
{{
  "parse_pattern": "regex"
}}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json_repair.repair_json(response.choices[0].message.content, return_objects=True)
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return None

def parse_with_regex(entries, pattern):
    parsed = []
    success_count = 0
    for entry in entries:
        row = {"raw_text": entry}
        try:
            match = re.search(pattern, entry, re.VERBOSE | re.DOTALL)
            if match:
                for k, v in match.groupdict().items():
                    row[k] = v.strip() if v else None
                if row.get("title") or row.get("author"):
                    success_count += 1
        except:
            pass
        parsed.append(row)
    return parsed, success_count

# --- STAGE 4: LLM RESCUE ---
def batch_llm_parse(entries, batch_size=10):
    """
    Stage 4: Fallback to pure LLM parsing.
    """
    client = get_deepseek_client()
    all_parsed = []
    
    for i in range(0, len(entries), batch_size):
        batch = entries[i:i+batch_size]
        batch_text = "\n\n".join([f"[{j}] {txt}" for j, txt in enumerate(batch)])
        
        prompt = f"""
Parse these {len(batch)} references into JSON.
Input:
{batch_text}

Output JSON List of objects with keys: author, year, title, journal, vol_issue, pages.
"""
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            # Expecting {"references": [...]} or just [...]
            res_json = json_repair.repair_json(response.choices[0].message.content, return_objects=True)
            
            # Normalize output
            items = res_json if isinstance(res_json, list) else res_json.get("references", [])
            # Map back to raw text if possible (simple order assumption)
            for idx, item in enumerate(items):
                if idx < len(batch):
                    item["raw_text"] = batch[idx]
            
            all_parsed.extend(items)
            logger.info(f"LLM Parsed batch {i}-{i+len(batch)}")
        except Exception as e:
            logger.error(f"Batch Parse Error: {e}")
            
    return all_parsed

# --- MAIN PIPELINE ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("segmented_md")
    parser.add_argument("--force-llm", action="store_true", help="Skip regex, use LLM directly")
    args = parser.parse_args()
    
    # Setup Paths
    base_name = os.path.splitext(os.path.basename(args.segmented_md))[0]
    if base_name.endswith("_segmented"): base_name = base_name[:-10]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "references")
    if not os.path.exists(out_dir): os.makedirs(out_dir)
    
    # 1. Raw Extraction
    logger.info("Phase 1: Raw Extraction...")
    raw_text = extract_raw_references(args.segmented_md)
    with open(os.path.join(out_dir, f"{base_name}_raw_refs.txt"), "w", encoding="utf-8") as f:
        f.write(raw_text)
        
    if len(raw_text) < 50:
        logger.error("Text too short.")
        return

    # 2. Pattern & Segmentation
    logger.info("Phase 2: Segmentation...")
    sample = "\n".join(raw_text.split('\n')[:20])
    seg_rules = get_segmentation_pattern(sample)
    split_pat = seg_rules.get("split_pattern")
    logger.info(f"Split Pattern: {split_pat}")
    
    entries = segment_references(raw_text, split_pat)
    logger.info(f"Segmented into {len(entries)} entries.")
    
    # 3. Parsing (Regex)
    logger.info("Phase 3: Regex Parsing...")
    parse_rules = get_parsing_pattern(entries[0] if entries else sample)
    parse_pat = parse_rules.get("parse_pattern")
    
    parsed_data, success_count = parse_with_regex(entries, parse_pat)
    success_rate = success_count / len(entries) if entries else 0
    logger.info(f"Regex Success Rate: {success_rate:.2%}")
    
    # 4. Evaluation & Rescue
    final_data = parsed_data
    if args.force_llm or success_rate < 0.8:
        logger.warning("Phase 4: Low quality (or forced). Triggering LLM Rescue...")
        final_data = batch_llm_parse(entries)
    
    # Save
    df = pd.DataFrame(final_data)
    out_path = os.path.join(out_dir, f"{base_name}_references.xlsx")
    df.to_excel(out_path, index=False)
    logger.info(f"Saved to {out_path}")

if __name__ == "__main__":
    main()
