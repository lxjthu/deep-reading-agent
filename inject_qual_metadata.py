#!/usr/bin/env python3
"""
QUAL 论文 Obsidian 元数据注入脚本

专门处理社会科学 4 层金字塔模型的元数据注入：
- L1_Context.md
- L2_Theory.md
- L3_Logic.md
- L4_Value.md
- xxx_Full_Report.md

功能：
1. PDF 视觉元数据提取（Qwen-vl-plus）
2. L1-L4 文件统一 frontmatter
3. 双向导航链接
4. Tags 统一管理
"""

import argparse
import os
import re
import yaml
import json
import base64
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import pymupdf
except ImportError:
    pymupdf = None
    logger.warning("pymupdf not installed. PDF image extraction will be disabled.")


def _env(name, default=None):
    return os.getenv(name, default)


def is_paddleocr_md(path: str) -> bool:
    """Check if file is from PaddleOCR extraction."""
    if not os.path.exists(path):
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read(500)

        if not content.startswith("---\n"):
            return False

        return "extractor: paddleocr" in content or "extractor: pdfplumber_fallback" in content
    except Exception:
        return False


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

    # Title: first substantial line (skip headers and metadata)
    if not metadata.get("title") or metadata.get("title", "").endswith(".pdf"):
        for line in body.split('\n')[:30]:
            line = line.strip()
            # Skip markdown headers, tool info, and short lines
            if (line and
                not line.startswith('#') and
                not line.startswith('*') and
                not line.startswith('-') and
                len(line) > 15):
                metadata["title"] = line
                break

    # Abstract (Chinese and English patterns)
    if not metadata.get("abstract"):
        # Chinese
        match = re.search(r'摘要[：:]\s*(.+?)(?=\n\n|关键词|中图分类号|Keywords)', body, re.DOTALL)
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
            metadata["keywords"] = [k.strip() for k in re.split(r'[；;,，]', keywords) if k.strip()]

    # Authors (try to extract from common patterns)
    if not metadata.get("authors"):
        # Look for author line patterns (often near title)
        # Common patterns: name separated by comma, or Chinese names with spaces
        author_match = re.search(r'(?:作者|Author)[：:s]*\s*(.+?)(?=\n|摘要|Abstract)', body, re.IGNORECASE)
        if author_match:
            authors_text = author_match.group(1).strip()
            metadata["authors"] = [a.strip() for a in re.split(r'[,，、]', authors_text) if a.strip()]

    return metadata


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
    if not pymupdf:
        logger.warning("pymupdf not available, skipping PDF image extraction")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }

    if not os.path.exists(pdf_path):
        logger.warning(f"PDF not found: {pdf_path}")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }

    doc = pymupdf.open(pdf_path)
    images = []

    for page_num in range(min(2, len(doc))):
        page = doc.load_page(page_num)
        mat = pymupdf.Matrix(pymupdf.Identity)
        pix = page.get_pixmap(matrix=mat, dpi=200)

        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        images.append(img_base64)

    doc.close()

    qwen_api_key = os.getenv("QWEN_API_KEY")
    if not qwen_api_key:
        logger.warning("QWEN_API_KEY not found in .env")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }

    client = OpenAI(
        api_key=qwen_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    prompt = """请从以下论文图片中提取以下元数据：
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
- 期刊名称和年份通常在页面顶部的页眉
- 仔细识别页眉位置的期刊名和年份
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

        logger.info(f"Sending request to Qwen VL with {len(images)} images...")

        resp = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[
                {"role": "system", "content": "你是专业的学术论文元数据提取专家。"},
                {"role": "user", "content": content_messages}
            ],
            temperature=0.0
        )

        response_content = resp.choices[0].message.content
        logger.info(f"Qwen VL response: {response_content[:200]}...")

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
        logger.error(f"Qwen VL extraction failed: {e}")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }


def has_frontmatter(content):
    return content.startswith("---\n")


def inject_frontmatter(content, metadata, layer_type=None):
    """
    Inject frontmatter into markdown content.

    For QUAL papers, also injects layer-specific fields (genre, key_policies, etc.)
    """
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
                logger.warning(f"Warning: Failed to parse existing frontmatter: {e}")

    # 2. Merge metadata (PDF metadata takes priority)
    merged_meta = existing_meta.copy()
    merged_meta.update(metadata)

    # 3. Handle tags (merge)
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

    # Always ensure standard tags
    tags.add("paper")
    tags.add("deep-reading")

    merged_meta["tags"] = list(tags)

    # 4. Layer-specific enhancements for QUAL papers
    if layer_type:
        if layer_type == "L1":
            # Keep existing genre, key_policies, status_summary if present
            pass
        elif layer_type == "L2":
            # Keep existing theories, key_constructs if present
            pass
        elif layer_type == "L3":
            # Keep existing mechanism_type, core_components if present
            pass
        elif layer_type == "L4":
            # Keep existing gaps, contributions if present
            pass

    # 5. Dump to YAML
    yaml_str = yaml.safe_dump(merged_meta, allow_unicode=True, sort_keys=False).strip()

    frontmatter_block = f"---\n{yaml_str}\n---\n\n"

    return frontmatter_block + body_content


def add_qual_navigation_links(content, filename, all_files):
    """
    Add bidirectional navigation links for QUAL papers.

    L1-L4 files: Link to each other and to Full Report
    Full Report: Link to all L1-L4 files
    """
    # Check if links already exist
    if "## 导航" in content or "## Navigation" in content:
        return content

    is_full_report = "Full_Report" in filename
    is_layer_file = filename.endswith("_Context.md") or filename.endswith("_Theory.md") or \
                     filename.endswith("_Logic.md") or filename.endswith("_Value.md")

    if not is_layer_file and not is_full_report:
        return content

    # Build navigation section
    links_section = "\n\n## 导航 (Navigation)\n\n"

    if is_full_report:
        # Full Report: Link to all L1-L4 layers
        layers = [f for f in all_files if not f.startswith("_") and
                  (f.endswith("_Context.md") or f.endswith("_Theory.md") or
                   f.endswith("_Logic.md") or f.endswith("_Value.md"))]
        # Sort layers: L1 -> L2 -> L3 -> L4
        layer_order = ["Context", "Theory", "Logic", "Value"]
        def get_layer_key(filename):
            for layer in layer_order:
                if layer in filename:
                    return layer_order.index(layer)
            return 99
        layers.sort(key=get_layer_key)

        links_section += "**分层分析文档：**\n"
        for layer in layers:
            layer_name = os.path.splitext(layer)[0]
            layer_label = layer_name.split("_")[-1]
            links_section += f"- [[{layer_name}|{layer_label}]]\n"
    else:
        # Layer files: Link to other layers and Full Report
        # Extract current layer name
        if filename.endswith("_Context.md"):
            current_layer = "L1_Context"
        elif filename.endswith("_Theory.md"):
            current_layer = "L2_Theory"
        elif filename.endswith("_Logic.md"):
            current_layer = "L3_Logic"
        elif filename.endswith("_Value.md"):
            current_layer = "L4_Value"
        else:
            return content

        links_section += "**其他层级：**\n"

        # Links to all layers
        layers = ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
        for layer in layers:
            if layer != current_layer:
                links_section += f"- [[{layer}]]\n"

        # Link to Full Report
        full_report_files = [f for f in all_files if "Full_Report" in f and f.endswith(".md")]
        if full_report_files:
            link_name = os.path.splitext(full_report_files[0])[0]
            links_section += f"\n**返回总报告：** [[{link_name}|Full Report]]\n"

    return content + links_section


def main():
    parser = argparse.ArgumentParser(description="Inject Obsidian metadata for QUAL papers")
    parser.add_argument("source_md", help="Source markdown file (segmented or raw) to extract metadata from")
    parser.add_argument("target_dir", help="Directory containing QUAL markdown files (L1-L4, Full_Report)")
    parser.add_argument("--use_pdf_vision", action="store_true", help="Enable PDF vision extraction with Qwen (disabled by default)")
    parser.add_argument("--pdf_dir", help="PDF directory path (default: E:\\pdf\\001)", default="E:\\pdf\\001")
    args = parser.parse_args()

    # Step 1: Extract metadata from processed MD file
    logger.info(f"Step 1: Extracting metadata from processed MD: {args.source_md}")

    if not os.path.exists(args.source_md):
        logger.error(f"Error: Source MD file not found: {args.source_md}")
        return

    # Parse metadata from the processed MD file
    md_metadata = parse_paddleocr_frontmatter(args.source_md)

    if md_metadata:
        logger.info(f"  MD metadata: title={md_metadata.get('title', 'Unknown')[:40]}...")
    else:
        logger.warning("  Warning: No metadata found in MD frontmatter")

    # Step 2: Extract metadata from original PDF using Qwen-vl-plus (optional)
    pdf_metadata = {}
    if args.use_pdf_vision:
        logger.info("Step 2: Extracting metadata from PDF images")
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

        if os.path.exists(pdf_path):
            logger.info(f"  PDF found: {pdf_path}")
            pdf_metadata = extract_metadata_from_pdf_images(pdf_path)
            logger.info(f"  PDF metadata: title={pdf_metadata.get('title', 'Unknown')[:40]}...")
        else:
            logger.warning(f"  PDF not found: {pdf_path}")
    else:
        logger.info("Step 2: PDF vision extraction skipped (use --use_pdf_vision to enable)")

    # Step 3: Merge metadata (PDF metadata takes priority for core fields)
    merged_metadata = md_metadata.copy()
    if pdf_metadata:
        merged_metadata.update(pdf_metadata)

    logger.info(f"Merged metadata: title={merged_metadata.get('title', 'Unknown')[:40]}...")

    # Step 4: Process target files
    if not os.path.exists(args.target_dir):
        logger.error(f"Target dir not found: {args.target_dir}")
        return

    all_files = [f for f in os.listdir(args.target_dir) if f.endswith(".md")]

    for filename in all_files:
        path = os.path.join(args.target_dir, filename)

        # Skip non-QUAL files
        is_layer_file = filename.endswith("_Context.md") or filename.endswith("_Theory.md") or \
                         filename.endswith("_Logic.md") or filename.endswith("_Value.md")
        is_full_report = "Full_Report" in filename

        if not is_layer_file and not is_full_report:
            continue

        logger.info(f"Processing file: {filename}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Determine layer type for metadata enhancement
        layer_type = None
        if is_layer_file:
            if filename.endswith("_Context.md"):
                layer_type = "L1"
            elif filename.endswith("_Theory.md"):
                layer_type = "L2"
            elif filename.endswith("_Logic.md"):
                layer_type = "L3"
            elif filename.endswith("_Value.md"):
                layer_type = "L4"

        # Inject frontmatter with merged metadata
        new_content = inject_frontmatter(content, merged_metadata, layer_type=layer_type)

        # Add navigation links
        new_content = add_qual_navigation_links(new_content, filename, all_files)

        if new_content != content:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            logger.info(f"  Updated: {filename}")
        else:
            logger.info(f"  Skipped (no change): {filename}")

    logger.info("QUAL metadata injection complete.")


if __name__ == "__main__":
    main()
