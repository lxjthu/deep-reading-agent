import argparse
import os
import re
import yaml
import json
import base64
import io
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

try:
    import pymupdf
except ImportError:
    pymupdf = None
    print("Warning: pymupdf not installed. PDF image extraction will be disabled.")


def _env(name, default=None):
    return os.getenv(name, default)


def is_paddleocr_md(path: str) -> bool:
    """Check if file is from PaddleOCR extraction."""
    if not os.path.exists(path):
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read(500)  # Just check the header

        if not content.startswith("---\n"):
            return False

        return "extractor: paddleocr" in content or "extractor: pdfplumber_fallback" in content
    except Exception:
        return False


def _merge_spaced_chinese_names(text: str) -> str:
    """
    Merge single Chinese characters separated by spaces into plausible names.

    Chinese academic papers often format author names with spaces between
    characters, e.g. "刘　行　张昊天　田　轩" should become "刘行 张昊天 田轩".

    Heuristic: scan left to right, greedily merge adjacent single CJK chars
    into groups of 2-3 (typical Chinese name length).
    """
    tokens = re.split(r'[\s\u3000]+', text.strip())
    if not tokens:
        return text

    result = []
    buf = ""
    for tok in tokens:
        if len(tok) == 1 and re.match(r'^[\u4e00-\u9fff]$', tok):
            buf += tok
            # Flush at 3 chars (surname + 2-char given name)
            if len(buf) >= 3:
                result.append(buf)
                buf = ""
        else:
            if buf:
                result.append(buf)
                buf = ""
            result.append(tok)
    if buf:
        # Remaining 1-2 chars: merge with last name if possible, or keep as-is
        if len(buf) == 1 and result and 1 <= len(result[-1]) <= 2 and re.match(r'^[\u4e00-\u9fff]+$', result[-1]):
            result[-1] += buf
        else:
            result.append(buf)
    return ' '.join(result)


def parse_paddleocr_frontmatter(path: str) -> dict:
    """
    Parse metadata from PaddleOCR markdown file.

    Reads YAML frontmatter and extracts additional metadata from content.
    """
    if not os.path.exists(path):
        return {}

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    metadata = {}

    # Parse YAML frontmatter
    if content.startswith("---\n"):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            try:
                fm_str = content[4:end_idx]
                metadata = yaml.safe_load(fm_str) or {}
            except Exception:
                pass

    # Extract body content
    body = content
    if content.startswith("---\n"):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            body = content[end_idx + 5:]

    # Extract additional metadata from body if not in frontmatter

    # Title: prefer first # heading (actual paper title), fallback to first substantial line
    if not metadata.get("title") or metadata.get("title", "").endswith(".pdf"):
        found_title = False
        for line in body.split('\n')[:30]:
            stripped = line.strip()
            # First priority: first `# ` heading (not `## `) that's not the filename
            if (stripped.startswith('# ') and not stripped.startswith('## ')
                    and not stripped.endswith('.pdf') and len(stripped) > 4):
                metadata["title"] = stripped[2:].strip()
                found_title = True
                break
        if not found_title:
            for line in body.split('\n')[:30]:
                stripped = line.strip()
                # Second priority: first substantial non-header line
                if (stripped and
                    not stripped.startswith('#') and
                    not stripped.startswith('*') and
                    not stripped.startswith('-') and
                    len(stripped) > 15):
                    metadata["title"] = stripped
                    break

    # Abstract (Chinese and English patterns)
    if not metadata.get("abstract"):
        # Chinese
        match = re.search(r'(?:摘要|内容提要)[：:]\s*(.+?)(?=\n\n|关键词|中图分类号|Keywords)', body, re.DOTALL)
        if match:
            metadata["abstract"] = match.group(1).strip()[:500]
        else:
            # English
            match = re.search(r'Abstract[：:.]?\s*(.+?)(?=\n\n|Keywords|Introduction)', body, re.DOTALL | re.IGNORECASE)
            if match:
                metadata["abstract"] = match.group(1).strip()[:500]

    # Keywords (Chinese)
    if not metadata.get("keywords"):
        match = re.search(r'关键词[：:]\s*(.+?)(?=\n|中图分类号)', body)
        if match:
            keywords = match.group(1)
            # Split by semicolons, commas, or spaces (some Chinese papers use space-separated keywords)
            parts = re.split(r'[；;,，]', keywords)
            if len(parts) == 1 and ' ' in keywords.strip():
                # Fallback: split by spaces
                space_parts = keywords.strip().split()
                # Validate: each keyword should be at least 2 chars
                if all(len(p) >= 2 for p in space_parts):
                    parts = space_parts
            metadata["keywords"] = [k.strip() for k in parts if k.strip()]

    # Authors (try to extract from common patterns)
    if not metadata.get("authors"):
        # Pattern 1: Explicit label like "作者：" or "Author:" (require colon after label)
        author_match = re.search(r'(?:^|[^\[])(?:作者|Author)[：:]\s*(.+?)(?=\n|摘要|Abstract)', body, re.IGNORECASE)
        if author_match:
            authors_text = author_match.group(1).strip()
            metadata["authors"] = [a.strip() for a in re.split(r'[,，、]', authors_text) if a.strip()]

        # Pattern 2: Chinese papers - authors on line between title and abstract
        # Typically: title line → author line → abstract
        if not metadata.get("authors"):
            lines = body.split('\n')
            # Find the paper title (# heading or first substantial line) and the abstract line
            title_idx = -1
            abstract_idx = -1
            for i, line in enumerate(lines[:40]):
                stripped = line.strip()
                if title_idx == -1 and stripped.startswith('# ') and not stripped.startswith('## '):
                    title_idx = i
                if abstract_idx == -1 and re.match(r'^(?:摘要|内容提要|Abstract)[：:.]', stripped):
                    abstract_idx = i
                    break

            # If no # heading found, use first substantial text line as title anchor
            if title_idx == -1 and abstract_idx > 0:
                for i, line in enumerate(lines[:abstract_idx]):
                    stripped = line.strip()
                    if (stripped and not stripped.startswith('#') and not stripped.startswith('*')
                            and not stripped.startswith('-') and len(stripped) > 15
                            and not re.match(r'^\d{4}\s*年', stripped)):
                        title_idx = i
                        break

            # Look for author-like lines between title and abstract
            if title_idx >= 0 and abstract_idx > title_idx:
                for i in range(title_idx + 1, abstract_idx):
                    line = lines[i].strip()
                    # Skip empty lines, subtitles (starting with ——), headers, page markers
                    if (not line or line.startswith('#') or line.startswith('*')
                            or line.startswith('——') or line.startswith('—')
                            or re.match(r'^[-\d\s]+$', line)):
                        continue
                    # Author line: short (< 80 chars), no period/colon, no digits
                    if len(line) < 80 and not re.search(r'[。：:；\d]', line):
                        # Pre-process: merge single Chinese chars separated by spaces into names
                        # E.g. "刘　行　张昊天　田　轩" → "刘行 张昊天 田轩"
                        merged_line = _merge_spaced_chinese_names(line)
                        # Split by spaces
                        names = re.split(r'[\s\u3000]+', merged_line)
                        # Filter: each segment should be 2-4 Chinese chars (typical name length)
                        valid_names = [n for n in names if n and 2 <= len(n) <= 4 and re.match(r'^[\u4e00-\u9fff]+$', n)]
                        if len(valid_names) >= 2:
                            metadata["authors"] = valid_names
                            break

        # Pattern 3: Extract from filename like "标题_作者.pdf"
        if not metadata.get("authors"):
            source_pdf = metadata.get("source_pdf", "")
            if source_pdf:
                stem = os.path.splitext(source_pdf)[0]
                # Match "_作者名" at end of filename (2-4 Chinese chars)
                fn_match = re.search(r'_([\u4e00-\u9fff]{2,4})$', stem)
                if fn_match:
                    metadata["authors"] = [fn_match.group(1)]

    # Journal (try to extract from page header patterns in first few lines)
    if not metadata.get("journal"):
        # Chinese journal patterns in header area:
        # "《经济研究》" or "经济研究 2024年第1期"
        # Often in the first 5 lines of body content
        first_lines = '\n'.join(body.split('\n')[:15])
        # Pattern: 《journal_name》
        j_match = re.search(r'[《](.+?)[》]', first_lines)
        if j_match:
            metadata["journal"] = j_match.group(1)
        else:
            # Pattern: "Journal Name, Vol.XX" or "JOURNAL 2024"
            j_match = re.search(r'^([A-Z][A-Za-z\s&]+(?:Journal|Review|Economics|Quarterly|Science))', first_lines, re.MULTILINE)
            if j_match:
                metadata["journal"] = j_match.group(1).strip()

    # Year (try to extract from patterns in first few lines)
    if not metadata.get("year"):
        first_lines = '\n'.join(body.split('\n')[:15])
        # Pattern: "2024年" or "2024, Vol" or "(2024)"
        y_match = re.search(r'(20[12]\d)\s*[年,，]', first_lines)
        if y_match:
            metadata["year"] = y_match.group(1)
        else:
            y_match = re.search(r'\(?(20[12]\d)\)?', first_lines)
            if y_match:
                metadata["year"] = y_match.group(1)

    return metadata


def extract_subsections(content: str) -> dict:
    """提取所有 ### 三级标题及其内容"""
    subsections = {}
    current_title = None
    current_content = []
    
    for line in content.split('\n'):
        if line.startswith('### '):
            if current_title:
                subsections[current_title] = '\n'.join(current_content).strip()
            current_title = line[4:].strip()
            current_content = []
        elif line.startswith('## '):
            if current_title:
                subsections[current_title] = '\n'.join(current_content).strip()
                current_title = None
                current_content = []
        else:
            if current_title:
                current_content.append(line)
    
    if current_title:
        subsections[current_title] = '\n'.join(current_content).strip()
    
    return subsections

def summarize_with_deepseek(client, title: str, text: str) -> str:
    """用 DeepSeek 将文本总结为30字以内"""
    if len(text) < 50:
        return ""
    
    prompt = f"""请将以下内容总结为30字以内的一句话：
标题：{title}
内容：{text}

要求：
- 中文输出
- 30字以内
- 抓住核心要点
"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精确的学术内容总结专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Summary failed for {title}: {e}")
        return text[:30]

def extract_metadata_from_pdf_images(pdf_path: str) -> dict:
    """
    将 PDF 前两页转换为图片，用 Qwen-vl-plus 提取元数据
    
    Returns:
        {
            "title": str,
            "authors": list,
            "journal": str,
            "year": str
        }
    """
    _unknown = {
        "title": "Unknown",
        "authors": ["Unknown"],
        "journal": "Unknown",
        "year": "Unknown"
    }
    if not pymupdf:
        print("Warning: pymupdf not available, skipping PDF image extraction")
        return _unknown

    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        return _unknown
    
    doc = pymupdf.open(pdf_path)
    images = []
    
    for page_num in range(min(3, len(doc))):
        page = doc.load_page(page_num)
        rect = page.rect
        # 只截取上半部分（上 1/2），期刊名称和年份通常在页眉位置
        clip_rect = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height / 2)
        pix = page.get_pixmap(clip=clip_rect, dpi=200)
        
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        images.append(img_base64)
    
    doc.close()
    
    qwen_api_key = os.getenv("QWEN_API_KEY")
    if not qwen_api_key:
        print("Warning: QWEN_API_KEY not found in .env")
        return _unknown
    print(f"QWEN_API_KEY found: {qwen_api_key[:10]}...")
    
    client = OpenAI(
        api_key=qwen_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    
    prompt = """请从以下论文图片中提取以下元数据（图片为PDF前三页的上半部分，包含页眉区域）：
1. 论文标题（完整）
2. 作者列表（所有作者，用逗号分隔）
3. 发表期刊（期刊全名）
4. 发表年份（仅数字）

请以 JSON 格式返回：
{
    "title": "...",
    "authors": ["...", "..."],
    "journal": "...",
    "year": "..."
}

注意：
- 这些图片是页面上半部分的截图，专门用于捕获页眉信息
- 期刊名称和年份通常在页眉位置（页面最顶部的一行）
- 请仔细识别页眉中的期刊名、卷号、期号和年份
- 如果某项信息无法识别，返回 "Unknown"
"""
    
    try:
        content_messages = [
            {"type": "text", "text": prompt}
        ]

        for img_base64 in images:
            content_messages.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
            })

        print(f"Sending request to Qwen VL with {len(images)} images...")

        resp = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[
                {"role": "system", "content": "你是专业的学术论文元数据提取专家。"},
                {"role": "user", "content": content_messages}
            ],
            temperature=0.0
        )

        response_content = resp.choices[0].message.content
        print(f"Qwen VL response: {response_content[:200]}...")

        # Extract JSON from markdown code block if present
        if "```json" in response_content:
            start_idx = response_content.find("```json") + 7
            end_idx = response_content.find("```", start_idx)
            json_str = response_content[start_idx:end_idx].strip()
        elif "```" in response_content:
            start_idx = response_content.find("```") + 3
            end_idx = response_content.find("```", start_idx)
            json_str = response_content[start_idx:end_idx].strip()
        else:
            json_str = response_content.strip()

        result = json.loads(json_str)
        return result
        
    except Exception as e:
        print(f"Qwen VL extraction failed: {e}")
        return _unknown

def get_deepseek_client():
    """获取 DeepSeek 客户端"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

def has_frontmatter(content):
    return content.startswith("---\n")

def inject_frontmatter(content, metadata):
    # 1. Parse existing frontmatter if present
    existing_meta = {}
    body_content = content
    
    if has_frontmatter(content):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            try:
                fm_str = content[4:end_idx]
                existing_meta = yaml.safe_load(fm_str) or {}
                body_content = content[end_idx+5:]
            except Exception as e:
                print(f"Warning: Failed to parse existing frontmatter: {e}")
    
    # 2. Merge metadata (Priority: New Metadata > Existing Metadata for core fields, but keep other existing fields)
    # Actually, for core fields (Title, Authors), we probably trust the dedicated extraction more than random previous runs?
    # BUT, wait. Dataview Summarizer injected rich fields (e.g. research_theme). We MUST preserve them.
    # The 'metadata' argument contains only basic info (Title, Author...).
    
    merged_meta = existing_meta.copy()
    merged_meta.update(metadata)
    
    # Special handling for tags: merge them
    tags = set()
    
    # Add existing tags
    if "tags" in existing_meta:
        if isinstance(existing_meta["tags"], list):
            tags.update(existing_meta["tags"])
        elif isinstance(existing_meta["tags"], str):
            tags.add(existing_meta["tags"])
            
    # Add new tags
    if "tags" in metadata:
        if isinstance(metadata["tags"], list):
            tags.update(metadata["tags"])
        elif isinstance(metadata["tags"], str):
            tags.add(metadata["tags"])
            
    # Always ensure deep-reading tag
    tags.add("paper")
    tags.add("deep-reading")
    
    merged_meta["tags"] = list(tags)

    # 3. Dump to YAML
    yaml_str = yaml.safe_dump(merged_meta, allow_unicode=True, sort_keys=False).strip()
    
    frontmatter_block = f"---\n{yaml_str}\n---\n\n"
    
    return frontmatter_block + body_content

def add_bidirectional_links(content, filename, all_files):
    # Strategy:
    # If this is Final Report, add links to all Steps.
    # If this is a Step, add link to Final Report.
    
    is_final = "Final" in filename
    
    links_section = "\n\n## 导航 (Navigation)\n\n"
    
    if is_final:
        # Link to steps
        steps = [f for f in all_files if f != filename and f.endswith(".md")]
        # Sort steps by number if possible
        steps.sort()
        
        links_section += "**分步分析文档：**\n"
        for s in steps:
            # Remove extension for wikilink
            link_name = os.path.splitext(s)[0]
            links_section += f"- [[{link_name}]]\n"
    else:
        # Link to Final
        final_files = [f for f in all_files if "Final" in f and f.endswith(".md")]
        if final_files:
            link_name = os.path.splitext(final_files[0])[0]
            links_section += f"**返回总报告：** [[{link_name}]]\n"
            
    # Check if links section already exists to avoid duplication
    if "## 导航 (Navigation)" in content:
        return content # Already added
        
    return content + links_section

def main():
    parser = argparse.ArgumentParser(description="Inject Obsidian metadata and links")
    parser.add_argument("source_md", help="Source markdown file from deep_reading_results to extract metadata from")
    parser.add_argument("target_dir", help="Directory containing markdown files to update")
    parser.add_argument("--use_pdf_vision", action="store_true", help="Enable PDF vision extraction with Qwen (disabled by default)")
    parser.add_argument("--pdf_path", help="Direct path to the PDF file (overrides --pdf_dir lookup)")
    parser.add_argument("--pdf_dir", help="PDF directory path for lookup (default: E:\\pdf\\001)", default="E:\\pdf\\001")
    args = parser.parse_args()

    # Step 1: Extract metadata from processed MD file
    print(f"Step 1: Extracting metadata from processed MD: {args.source_md}")

    if not os.path.exists(args.source_md):
        print(f"Error: Source MD file not found: {args.source_md}")
        return

    # Parse metadata from the processed MD file
    md_metadata = parse_paddleocr_frontmatter(args.source_md)

    if md_metadata:
        print(f"  MD metadata: title={md_metadata.get('title', 'Unknown')[:40]}...")
    else:
        print("  Warning: No metadata found in MD frontmatter")

    # Step 2: Extract metadata from original PDF using Qwen-vl-plus (optional)
    pdf_metadata = {}
    if args.use_pdf_vision:
        print(f"\nStep 2: Extracting metadata from PDF images")

        # Determine PDF path: prefer --pdf_path, fallback to --pdf_dir lookup
        pdf_path = None
        if args.pdf_path and os.path.exists(args.pdf_path):
            pdf_path = args.pdf_path
            print(f"  Using provided PDF path: {pdf_path}")
        else:
            # Handle both _segmented.md and _paddleocr.md suffixes
            base_name = os.path.basename(args.source_md)
            if base_name.endswith("_segmented.md"):
                pdf_name = base_name[:-13] + ".pdf"
            elif base_name.endswith("_paddleocr.md"):
                pdf_name = base_name[:-13] + ".pdf"
            elif base_name.endswith("_raw.md"):
                pdf_name = base_name[:-7] + ".pdf"
            else:
                pdf_name = os.path.splitext(base_name)[0] + ".pdf"

            pdf_path = os.path.join(args.pdf_dir, pdf_name)

        if pdf_path and os.path.exists(pdf_path):
            print(f"  PDF found: {pdf_path}")
            pdf_metadata = extract_metadata_from_pdf_images(pdf_path)
            print(f"  PDF metadata: title={pdf_metadata.get('title', 'Unknown')[:40]}...")
        else:
            print(f"  PDF not found: {pdf_path}")
    else:
        print(f"\nStep 2: PDF vision extraction skipped (use --use_pdf_vision to enable)")

    # Merge metadata (PDF metadata takes priority for core fields if enabled)
    merged_metadata = md_metadata.copy()
    if pdf_metadata:
        merged_metadata.update(pdf_metadata)

    print(f"\nMerged metadata: title={merged_metadata.get('title', 'Unknown')[:40]}...")

    # Step 3: Process target files
    if not os.path.exists(args.target_dir):
        print(f"Target dir not found: {args.target_dir}")
        return

    all_files = [f for f in os.listdir(args.target_dir) if f.endswith(".md")]

    deepseek_client = get_deepseek_client()
    
    for filename in all_files:
        path = os.path.join(args.target_dir, filename)

        # 跳过路由文件
        if filename in ["section_routing.md", "semantic_index.json"]:
            continue

        # 处理 Final_Deep_Reading_Report.md
        is_final = filename == "Final_Deep_Reading_Report.md"

        # 处理步骤文件
        is_step = re.match(r'^\d+_', filename) is not None

        if not is_final and not is_step:
            continue

        print(f"Processing file: {filename}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 步骤文件：提取并总结 ### 子标题
        subsections_meta = {}
        if is_step and deepseek_client:
            print(f"  Extracting subsections from: {filename}")
            subsections = extract_subsections(content)

            for title, section_text in subsections.items():
                if len(section_text) >= 50:  # 只总结足够长的部分
                    summary = summarize_with_deepseek(deepseek_client, title, section_text)
                    # 清洗 key：去掉 ** 标记和编号前缀（如 "**1. 研究主题**" → "研究主题"）
                    clean_key = title.replace("**", "").strip()
                    clean_key = re.sub(r'^\d+\.\s*', '', clean_key).strip()
                    subsections_meta[clean_key] = summary
                    print(f"    {clean_key}: {summary[:20]}...")

        # 注入元数据
        if is_final:
            # Final 报告：注入 title/authors/journal/year
            # 优先使用 PDF 视觉元数据，回退到 MD 文本提取的元数据
            final_metadata = {}
            for key in ["title", "authors", "journal", "year"]:
                # Prefer non-"Unknown" values from either source
                pdf_val = pdf_metadata.get(key)
                md_val = merged_metadata.get(key)
                # Pick the first real (non-Unknown) value; keep Unknown as placeholder
                if pdf_val and pdf_val != "Unknown" and pdf_val != ["Unknown"]:
                    final_metadata[key] = pdf_val
                elif md_val and md_val != "Unknown" and md_val != ["Unknown"]:
                    final_metadata[key] = md_val
                else:
                    # Preserve "Unknown" placeholder for future manual filling
                    final_metadata[key] = pdf_val or md_val or "Unknown"

            # 添加 tags
            if "tags" not in final_metadata:
                final_metadata["tags"] = []
            if "paper" not in final_metadata["tags"]:
                final_metadata["tags"].append("paper")
            if "deep-reading" not in final_metadata["tags"]:
                final_metadata["tags"].append("deep-reading")

            new_content = inject_frontmatter(content, final_metadata)
        else:
            # 步骤文件：注入完整元数据（MD + PDF + subsections）
            # Add paper tag if not present
            if "tags" not in merged_metadata:
                merged_metadata["tags"] = []
            if "paper" not in merged_metadata["tags"]:
                merged_metadata["tags"].append("paper")
            if "deep-reading" not in merged_metadata["tags"]:
                merged_metadata["tags"].append("deep-reading")

            # Merge subsections summary into metadata
            full_metadata = merged_metadata.copy()
            if subsections_meta:
                full_metadata.update(subsections_meta)

            new_content = inject_frontmatter(content, full_metadata)

            # Add Links
            new_content = add_bidirectional_links(new_content, filename, all_files)

        if new_content != content:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {filename}")
        else:
            print(f"Skipped (no change): {filename}")

if __name__ == "__main__":
    main()
