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

def _expand_excerpt(paragraph_text: str, focus_quote: str, window_chars: int = 260) -> str:
    if not paragraph_text or not focus_quote:
        return (focus_quote or "").strip()
    paragraph_text = str(paragraph_text)
    focus_quote = str(focus_quote).strip()
    if not focus_quote:
        return ""
    idx = paragraph_text.find(focus_quote)
    if idx < 0:
        return focus_quote

    start = max(0, idx - window_chars)
    end = min(len(paragraph_text), idx + len(focus_quote) + window_chars)
    excerpt = paragraph_text[start:end].strip()

    left = max(excerpt.rfind("。", 0, idx - start), excerpt.rfind(".", 0, idx - start), excerpt.rfind("！", 0, idx - start), excerpt.rfind("？", 0, idx - start), excerpt.rfind(";", 0, idx - start), excerpt.rfind("；", 0, idx - start))
    if left >= 0 and left + 1 < len(excerpt):
        excerpt = excerpt[left + 1 :].lstrip()

    right_pos = idx - start + len(focus_quote)
    rights = [excerpt.find("。", right_pos), excerpt.find(".", right_pos), excerpt.find("！", right_pos), excerpt.find("？", right_pos), excerpt.find(";", right_pos), excerpt.find("；", right_pos)]
    rights = [r for r in rights if r >= 0]
    if rights:
        right = min(rights)
        excerpt = excerpt[: right + 1].rstrip()

    if len(excerpt) > 900:
        excerpt = excerpt[:900].rstrip() + "..."
    return excerpt

def get_deepseek_client():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = "https://api.deepseek.com"
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not found.")
        return None
    return OpenAI(api_key=api_key, base_url=base_url)

# --- STEP 1: PREPROCESSING ---
def preprocess_text(md_path):
    """
    Loads MD, removes References section, cleans headers/page numbers, returns paragraphs.
    """
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"File not found: {md_path}")
        
    with open(md_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = content.replace("\x00", "")
    content = re.sub(r"\[PAGE\s+\d+\]\s*", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"```text\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"```", "", content)

    ref_keywords = ["## References", "## Bibliography", "## 参考文献"]
    for kw in ref_keywords:
        if kw in content:
            content = content.split(kw)[0]
            break

    if "## References" not in content and "## 参考文献" not in content:
        m = re.search(r"\n\s*参考文献\s*\n", content)
        if m:
            content = content[: m.start()]
            
    # 2. Split into paragraphs (by double newline)
    raw_paras = content.split('\n\n')
    
    # 3. Clean paragraphs
    clean_paras = []
    for idx, p in enumerate(raw_paras):
        # Remove single newlines within paragraph (reflow)
        text = p.replace('\n', ' ').strip()
        # Skip empty or too short
        if len(text) < 20:
            continue
        # Skip likely metadata (Page X of Y)
        if re.match(r'^Page \d+', text) or re.match(r'^\d+$', text):
            continue
            
        clean_paras.append({"id": idx, "text": text})
        
    return clean_paras

# --- STEP 2: FINGERPRINT GENERATION ---
def generate_fingerprints(row):
    """
    Generates regex patterns to find citations for a reference row.
    Returns list of regex strings.
    """
    fingerprints = []
    
    # Check for numeric citation [1]
    raw_text = str(row.get('raw_text', ''))
    # Heuristic: if raw_text starts with [N], assume numeric style
    numeric_match = re.match(r'^\s*(?:\[|［)\s*(\d+)\s*(?:\]|］)', raw_text)
    if numeric_match:
        ref_num = numeric_match.group(1)
        ref_num_escaped = re.escape(ref_num)
        fingerprints.append(rf'[\[［]\s*[\d\s,，、\-–—]*?(?<!\d){ref_num_escaped}(?!\d)[\d\s,，、\-–—]*?[\]］]')
        return fingerprints # If numeric, usually that's enough
    
    # Author-Year Logic
    author = str(row.get('author', ''))
    year = str(row.get('year', ''))
    
    if not author or author.lower() == 'none' or not year or year.lower() == 'none':
        # Fallback: try title matching if author/year missing
        title = str(row.get('title', ''))
        if len(title) > 20:
            # Take first 5 words
            short_title = " ".join(title.split()[:5])
            fingerprints.append(re.escape(short_title))
        return fingerprints

    # Clean year (remove parens if present)
    year = re.sub(r'[^\d]', '', year)
    
    # Clean author (extract surname of first author)
    # Common formats: "Smith, J.", "Smith, John", "Smith et al."
    # We want "Smith"
    first_author = author.split(',')[0].strip() # "Smith" from "Smith, J."
    first_author = first_author.split(' ')[0].strip() # "Smith" from "Smith J." just in case
    
    # Remove special chars
    first_author = re.sub(r'[^\w\u4e00-\u9fa5]', '', first_author) # Keep letters and Chinese chars
    
    if not first_author:
        return []

    # Pattern 1: Author (Year) -> Smith (2020) or Smith et al. (2020)
    p1 = rf"{re.escape(first_author)}.{{0,50}}\({year}\)"
    
    # Pattern 2: (Author, Year) -> (Smith, 2020)
    p2 = rf"\({re.escape(first_author)}.{{0,50}}{year}\)"
    
    # Pattern 3: Chinese style / loose -> Author ... Year
    p3 = rf"{re.escape(first_author)}.{{0,20}}{year}"
    
    fingerprints.append(p1)
    fingerprints.append(p2)
    fingerprints.append(p3)
    
    logger.info(f"Generated fingerprints for {first_author} ({year}): {fingerprints}")
    return fingerprints

# --- STEP 3: CANDIDATE RETRIEVAL ---
def find_candidates(paras, fingerprints):
    """
    Returns list of paragraph objects that match any fingerprint.
    """
    candidates = []
    seen_ids = set()
    
    for fp in fingerprints:
        try:
            pattern = re.compile(fp, re.IGNORECASE)
            for p in paras:
                if p['id'] in seen_ids:
                    continue
                if pattern.search(p['text']):
                    candidates.append(p)
                    seen_ids.add(p['id'])
        except re.error:
            continue
            
    return candidates

# --- STEP 4: LLM VERIFICATION ---
def verify_citations_with_llm(reference_text, candidates):
    """
    Asks LLM to verify if candidates are actual citations and extract context.
    """
    if not candidates:
        return []
        
    client = get_deepseek_client()
    
    # Prepare prompt context
    cand_text = ""
    for i, c in enumerate(candidates):
        cand_text += f"[Para {c['id']}]: {c['text'][:1600]}\n\n"
        
    prompt = f"""
I am tracing citations for this reference:
Reference: "{reference_text}"

Here are paragraphs from the paper that might cite it (found via keyword match):
{cand_text}

Task:
1. Determine which paragraphs ACTUALLY cite this specific reference (distinguish from same-name authors).
2. For each valid citation, extract an EXACT QUOTE from the paragraph (1-2 sentences). The quote must be a verbatim substring of the paragraph text.
3. Provide a Chinese restatement (中文重述) ONLY if the quote is in English. If the quote is Chinese, output empty string.
4. If it is only a list of citations, still return the exact sentence containing the citation.
5. If false positive, ignore.

Output JSON ONLY in this exact shape:
{{
  "citations": [
    {{ "para_id": 12, "quote": "Exact quote from paragraph...", "zh": "中文重述（可为空）" }}
  ]
}}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        res_json = json_repair.repair_json(response.choices[0].message.content, return_objects=True)
        
        items = res_json.get("citations", []) if isinstance(res_json, dict) else []
        para_text_by_id = {c.get("id"): c.get("text", "") for c in candidates if isinstance(c, dict)}
        verified = []
        for item in items:
            if not isinstance(item, dict):
                continue
            para_id = item.get("para_id", None)
            quote = item.get("quote", None)
            zh = item.get("zh", "")
            if quote and isinstance(quote, str):
                quote_clean = quote.strip()
                para_text = para_text_by_id.get(para_id, "")
                excerpt = _expand_excerpt(para_text, quote_clean)
                zh_clean = str(zh).strip() if zh is not None else ""
                if re.search(r"[\u4e00-\u9fff]", excerpt):
                    zh_clean = ""
                verified.append({"para_id": para_id, "quote": excerpt, "zh": zh_clean})
        return verified
        
    except Exception as e:
        logger.error(f"LLM Verification Error: {e}")
        return []

# --- MAIN ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("segmented_md", help="Path to full paper MD")
    parser.add_argument("references_xlsx", help="Path to references Excel")
    args = parser.parse_args()
    
    # Setup Output
    base_name = os.path.splitext(os.path.basename(args.references_xlsx))[0]
    out_dir = os.path.dirname(args.references_xlsx)
    out_md = os.path.join(out_dir, f"{base_name}_citation_trace.md")
    out_xlsx = os.path.join(out_dir, f"{base_name}_with_citations.xlsx")
    
    # 1. Load Data
    logger.info("Step 1: Loading data...")
    paras = preprocess_text(args.segmented_md)
    logger.info(f"Loaded {len(paras)} paragraphs from text.")
    
    df = pd.read_excel(args.references_xlsx)
    logger.info(f"Loaded {len(df)} references.")
    
    # 2. Process References
    results = []
    trace_log = []
    
    trace_log.append(f"# Citation Trace Log for {base_name}\n\n")
    
    # Limit for testing? No, process all but batching might be needed if slow.
    # For now, sequential is fine for <100 refs.
    
    for idx, row in df.iterrows():
        ref_text = str(row.get('raw_text', '')).strip()
        if not ref_text or ref_text.lower() == "nan":
            results.append([])
            trace_log.append(f"## Ref {idx+1}: 未识别到参考文献文本\n\n- 未检出引用（宁缺毋滥）\n\n")
            continue
        if ref_text.strip().lower() == "references":
            results.append([])
            trace_log.append(f"## Ref {idx+1}: References（标题行）\n\n- 跳过\n\n")
            continue
        logger.info(f"Processing Ref {idx+1}/{len(df)}: {ref_text[:30]}...")
        
        # Generate Fingerprints
        fps = generate_fingerprints(row)
        if not fps:
            results.append([])
            trace_log.append(f"## Ref {idx+1}: {row.get('author', 'Unknown')} ({row.get('year', '?')})\n> {ref_text}\n\n- 未生成检索指纹（宁缺毋滥）\n\n")
            continue
            
        candidates = find_candidates(paras, fps)
        
        if not candidates:
            results.append([])
            trace_log.append(f"## Ref {idx+1}: {row.get('author', 'Unknown')} ({row.get('year', '?')})\n> {ref_text}\n\n- 未检出引用（宁缺毋滥）\n\n")
            continue
            
        candidates_all = candidates
        candidates_for_llm = candidates_all[:12] if len(candidates_all) > 12 else candidates_all
             
        citations = verify_citations_with_llm(ref_text, candidates_for_llm)
        
        results.append(citations)
        
        # Log to MD
        trace_log.append(f"## Ref {idx+1}: {row.get('author', 'Unknown')} ({row.get('year', '?')})\n")
        trace_log.append(f"> {ref_text}\n\n")
        if not citations:
            trace_log.append("- 有候选段落，但未能确认（宁缺毋滥）\n\n")
        else:
            for c in citations:
                quote = c.get("quote", "")
                zh = c.get("zh", "")
                trace_log.append(f"- 原文：{quote}\n")
                if zh:
                    trace_log.append(f"  - 中文重述：{zh}\n")
            trace_log.append("\n")
            
    # 3. Save Output
    # Add to DF
    df['Citation_Count'] = [len(r) for r in results]
    df['Citation_Contexts_All'] = [" || ".join([c.get("quote", "") for c in r]) for r in results]
    df['Citation_Chinese_All'] = [" || ".join([c.get("zh", "") for c in r if c.get("zh")]) for r in results]

    max_cols = min(8, max([len(r) for r in results] + [0]))
    for i in range(max_cols):
        df[f'Citation_{i+1}'] = [r[i].get("quote", "") if len(r) > i else "" for r in results]
        df[f'Citation_{i+1}_ZH'] = [r[i].get("zh", "") if len(r) > i else "" for r in results]
    
    df.to_excel(out_xlsx, index=False)
    
    with open(out_md, 'w', encoding='utf-8') as f:
        f.writelines(trace_log)
        
    logger.info(f"Saved trace log to {out_md}")
    logger.info(f"Saved extended Excel to {out_xlsx}")

if __name__ == "__main__":
    main()
