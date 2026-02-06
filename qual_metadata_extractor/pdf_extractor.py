"""
第二次提取：从原始 PDF 文件中提取基础元数据
使用 pymupdf + Qwen-vl-plus 视觉模型
"""

import os
import json
import base64
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import pymupdf
except ImportError:
    pymupdf = None
    logger.warning("pymupdf not available, PDF metadata extraction will be disabled")


def convert_pdf_to_images(pdf_path: str, max_pages: int = 3) -> list:
    """
    将 PDF 前几页转换为图片（base64）
    
    Args:
        pdf_path: PDF 文件路径
        max_pages: 转换的最大页数（默认 2）
    
    Returns:
        [base64_image1, base64_image2, ...]
    """
    if not pymupdf:
        logger.error("pymupdf not available, cannot convert PDF to images")
        return []
    
    if not os.path.exists(pdf_path):
        logger.error(f"PDF not found: {pdf_path}")
        return []
    
    try:
        doc = pymupdf.open(pdf_path)
        images = []

        for page_num in range(min(max_pages, len(doc))):
            page = doc.load_page(page_num)
            rect = page.rect
            # 只截取上半部分（上 1/2），期刊名称和年份通常在页眉位置
            clip_rect = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height / 2)
            pix = page.get_pixmap(clip=clip_rect, dpi=200)

            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            images.append(img_base64)

        doc.close()
        logger.info(f"Converted {len(images)} PDF pages (top half) to base64 images")
        return images
        
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        return []


def extract_pdf_metadata_with_qwen(images: list) -> dict:
    """
    用 Qwen-vl-plus 从 PDF 图片中提取元数据
    
    Args:
        images: PDF 图片列表（base64）
    
    Returns:
        {
            "title": "论文标题",
            "authors": ["作者1", "作者2"],
            "journal": "期刊名称",
            "year": "2024"
        }
    """
    qwen_api_key = os.getenv("QWEN_API_KEY")
    if not qwen_api_key:
        logger.warning("QWEN_API_KEY not found in environment")
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
    
    prompt = """请从以下论文图片中提取以下元数据（图片为PDF前三页的上半部分，包含页眉区域）：
1. 论文标题（完整）
2. 作者列表（所有作者，用逗号分隔）
3. 发表期刊（期刊全名）
4. 发表年份（仅4位数字）

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
- 作者信息通常在标题下方
- 如果某项信息无法识别，返回 "Unknown"
"""
    
    try:
        content_messages = [{"type": "text", "text": prompt}]
        
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
        
        # 提取 JSON（支持 markdown 代码块）
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
        logger.info(f"Successfully extracted PDF metadata: {result.get('title', 'Unknown')[:50]}...")
        return result
        
    except Exception as e:
        logger.error(f"Qwen VL extraction failed: {e}")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }


def extract_pdf_metadata(pdf_path: str) -> dict:
    """
    从 PDF 文件中提取元数据（完整流程）
    
    Args:
        pdf_path: PDF 文件路径
    
    Returns:
        {
            "title": "...",
            "authors": [...],
            "journal": "...",
            "year": "..."
        }
    """
    logger.info(f"Starting PDF metadata extraction from: {pdf_path}")
    
    # 步骤 1: 转换 PDF 为图片
    images = convert_pdf_to_images(pdf_path, max_pages=2)
    
    if not images:
        logger.error("No images extracted, skipping PDF metadata extraction")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }
    
    # 步骤 2: Qwen-vl-plus 视觉提取
    metadata = extract_pdf_metadata_with_qwen(images)
    
    return metadata
