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
        
    with open(md_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = content.replace("\x00", "")
        
    lines = content.split('\n')
    ref_content = []
    in_ref = False
    ref_keywords = ["References", "Bibliography", "Works Cited", "参考文献"]
    
    for line in lines:
        stripped = line.strip()
        if line.startswith("## "):
            header = stripped[3:].strip()
            header_norm = re.sub(r"\s+", " ", header)
            is_target = False
            if len(header_norm) <= 30:
                is_target = (
                    header_norm in ref_keywords
                    or bool(re.match(r"^\d+(\.\d+)*\s*(References|Bibliography|Works Cited|参考文献)\s*$", header_norm))
                )
            if is_target:
                in_ref = True
                continue
            elif in_ref:
                break

        if not in_ref:
            is_plain_ref = stripped in ref_keywords
            is_plain_ref_cn = bool(re.match(r"^参考文献\s*[:：]?\s*$", stripped))
            is_numbered_ref = bool(re.match(r"^\d+[\.\\s、-]*参考文献\s*[:：]?\s*$", stripped))
            if is_plain_ref or is_plain_ref_cn or is_numbered_ref:
                in_ref = True
                continue
        
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

# --- STAGE 2: DIRECT LLM EXTRACTION ---
def extract_references_with_llm(raw_text, batch_size=15):
    """
    直接使用 LLM 从原始参考文献文本中提取结构化数据。
    分批处理以避免单次请求过长。
    """
    client = get_deepseek_client()
    if not client:
        return []
    
    # 按行粗分条目（简单策略：每行以数字/作者名开头可能是新条目）
    lines = raw_text.split('\n')
    
    # 合并为一个文本块，让 LLM 自己识别条目边界
    all_parsed = []
    
    # 分批处理
    total_chars = len(raw_text)
    chunk_size = 8000  # 每批约 8000 字符
    
    for start in range(0, total_chars, chunk_size):
        chunk = raw_text[start:start + chunk_size]
        
        # 如果不是第一块，找到合适的断点（避免在条目中间切断）
        if start > 0:
            # 找最近的换行符
            newline_pos = chunk.find('\n')
            if newline_pos > 0 and newline_pos < 200:
                chunk = chunk[newline_pos + 1:]
        
        # 如果不是最后一块，找到合适的结束点
        if start + chunk_size < total_chars:
            last_newline = chunk.rfind('\n')
            if last_newline > len(chunk) - 200:
                chunk = chunk[:last_newline]
        
        if len(chunk.strip()) < 30:
            continue
            
        prompt = f"""你是一个学术文献解析专家。请从以下参考文献文本中提取每一条参考文献的结构化信息。

原始文本：
{chunk}

任务要求：
1. 识别文本中的每一条参考文献
2. 提取以下字段（如有）：
   - author: 作者（所有作者，保持原文格式）
   - year: 出版年份
   - title: 论文/书籍标题
   - journal: 期刊/出版社名称
   - vol_issue: 卷期号
   - pages: 页码
   - raw_text: 该条目的原始文本

输出格式：JSON 对象，包含 "references" 数组：
{{
  "references": [
    {{
      "author": "...",
      "year": "...",
      "title": "...",
      "journal": "...",
      "vol_issue": "...",
      "pages": "...",
      "raw_text": "..."
    }}
  ]
}}

注意：
- 如果某个字段无法提取，使用 null
- 保持作者名的原始格式
- raw_text 应包含该条目的完整原始文本
"""
        
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1  # 低温度以提高解析一致性
            )
            
            result = json_repair.repair_json(
                response.choices[0].message.content, 
                return_objects=True
            )
            
            # 提取结果
            if isinstance(result, dict):
                refs = result.get("references", [])
            elif isinstance(result, list):
                refs = result
            else:
                refs = []
            
            all_parsed.extend(refs)
            logger.info(f"Batch extracted {len(refs)} references (chars {start}-{start + len(chunk)})")
            
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
    
    return all_parsed

# --- MAIN PIPELINE ---
def main():
    parser = argparse.ArgumentParser(description="从论文中提取参考文献（直接调用大模型）")
    parser.add_argument("segmented_md", help="分段后的 Markdown 文件路径")
    args = parser.parse_args()
    
    # Setup Paths
    base_name = os.path.splitext(os.path.basename(args.segmented_md))[0]
    if base_name.endswith("_segmented"): 
        base_name = base_name[:-10]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(script_dir, "references")
    if not os.path.exists(out_dir): 
        os.makedirs(out_dir)
    
    # 1. Raw Extraction
    logger.info("Phase 1: Extracting raw references section...")
    raw_text = extract_raw_references(args.segmented_md)
    
    # 保存原始文本用于调试
    raw_path = os.path.join(out_dir, f"{base_name}_raw_refs.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_text)
    logger.info(f"Raw text saved to {raw_path}")
        
    if len(raw_text) < 50:
        logger.error("References text too short, aborting.")
        return

    # 2. Direct LLM Extraction
    logger.info("Phase 2: Extracting references with LLM...")
    parsed_refs = extract_references_with_llm(raw_text)
    logger.info(f"Total references extracted: {len(parsed_refs)}")
    
    if not parsed_refs:
        logger.error("No references extracted.")
        return
    
    # 3. Save to Excel
    df = pd.DataFrame(parsed_refs)
    
    # 确保列顺序
    column_order = ["author", "year", "title", "journal", "vol_issue", "pages", "raw_text"]
    existing_cols = [c for c in column_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in column_order]
    df = df[existing_cols + other_cols]
    
    out_path = os.path.join(out_dir, f"{base_name}_references.xlsx")
    df.to_excel(out_path, index=False)
    logger.info(f"Saved {len(parsed_refs)} references to {out_path}")

if __name__ == "__main__":
    main()
