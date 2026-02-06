"""
QUAL 论文元数据提取主模块

完整的元数据提取流程：
1. 从 MD 报告中提取子章节（DeepSeek 30字总结）
2. 从 PDF 文件中提取基础元数据（Qwen-vl-plus）
3. 合并元数据
4. 注入 Frontmatter 和导航链接
"""

import os
import logging
from typing import Optional

from .md_extractor import get_deepseek_client, extract_layer_subsections
from .pdf_extractor import extract_pdf_metadata
from .merger import create_base_metadata, create_layer_metadata
from .injector import save_with_metadata

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_pdf_for_paper(pdf_dir: str, paper_dir: str) -> Optional[str]:
    """
    根据论文目录名称查找对应的 PDF 文件
    
    Args:
        pdf_dir: PDF 根目录
        paper_dir: 论文输出目录（如 "social_science_results_v2/类ChatGPT..."）
    
    Returns:
        PDF 文件路径，未找到返回 None
    """
    # 从目录名提取论文名称
    paper_name = os.path.basename(paper_dir)
    
    # 尝试匹配 PDF
    if not os.path.exists(pdf_dir):
        logger.warning(f"PDF directory not found: {pdf_dir}")
        return None
    
    for root, dirs, files in os.walk(pdf_dir):
        for file in files:
            if file.endswith('.pdf'):
                # 移除 .pdf 后缀后比较
                pdf_basename = os.path.splitext(file)[0]
                if pdf_basename in paper_name or paper_name in pdf_basename:
                    pdf_path = os.path.join(root, file)
                    logger.info(f"Found PDF: {pdf_path}")
                    return pdf_path
    
    logger.warning(f"No PDF found for paper: {paper_name}")
    return None


def extract_qual_metadata(paper_dir: str, pdf_dir: str, output_dir: Optional[str] = None, pdf_path: Optional[str] = None):
    """
    完整的 QUAL 元数据提取流程
    
    Args:
        paper_dir: 论文输出目录（包含 L1_Context.md 等）
        pdf_dir: PDF 文件目录
        output_dir: 输出目录（可选，默认覆盖原文件）
    """
    # 确定输出目录
    if output_dir is None:
        output_dir = paper_dir
    
    # 论文名称（用于导航链接）
    paper_name = os.path.basename(paper_dir)
    
    # 1. 加载所有层级的 Markdown 内容
    layer_outputs = {}
    for layer in ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]:
        layer_file = os.path.join(paper_dir, f"{layer}.md")
        if os.path.exists(layer_file):
            with open(layer_file, 'r', encoding='utf-8') as f:
                layer_outputs[layer] = f.read()
    
    if not layer_outputs:
        logger.error(f"No layer files found in {paper_dir}")
        return
    
    logger.info(f"Loaded {len(layer_outputs)} layer files from {paper_dir}")
    
    # 2. 第一次提取：从 MD 中提取子章节（DeepSeek 30字总结）
    deepseek_client = get_deepseek_client()
    if not deepseek_client:
        logger.error("DeepSeek client not available")
        return
    
    logger.info("Starting Step 1: Extract subsections from MD (DeepSeek summary)...")
    subsections_meta = {}
    
    for layer_name, md_content in layer_outputs.items():
        subsections = extract_layer_subsections(layer_name, md_content, deepseek_client)
        if subsections:
            subsections_meta[layer_name] = subsections
    
    if not subsections_meta:
        logger.warning("No subsections extracted from MD files")
        return
    
    logger.info(f"Step 1 complete: Extracted subsections from {len(subsections_meta)} layers")
    
    # 3. 第二次提取：从 PDF 中提取基础元数据
    # 优先使用直接指定的 pdf_path，否则回退到目录查找
    actual_pdf_path = None
    if pdf_path and os.path.exists(pdf_path):
        actual_pdf_path = pdf_path
        logger.info(f"Using provided PDF path: {actual_pdf_path}")
    else:
        actual_pdf_path = find_pdf_for_paper(pdf_dir, paper_dir)

    pdf_metadata = {}

    if actual_pdf_path:
        logger.info(f"Starting Step 2: Extract metadata from PDF ({actual_pdf_path})...")
        pdf_metadata = extract_pdf_metadata(actual_pdf_path)
        logger.info(f"Step 2 complete: Extracted PDF metadata")
    else:
        logger.warning(f"No PDF found for paper in {pdf_dir}")
    
    # 4. 创建基础元数据（PDF 元数据 + tags）
    logger.info("Creating base metadata from PDF...")
    base_metadata = create_base_metadata(pdf_metadata)
    
    # 5. 为每个层级文件注入对应的元数据和导航
    all_layers = ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
    
    for layer in all_layers:
        if layer in layer_outputs:
            layer_file = os.path.join(output_dir, f"{layer}.md")
            
            with open(layer_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 创建该层的元数据（基础元数据 + 该层的子章节）
            subsections = subsections_meta.get(layer, {})
            layer_metadata = create_layer_metadata(base_metadata, subsections, layer)
            
            # 保存（注入元数据和导航）
            save_with_metadata(layer_file, content, layer_metadata, layer, paper_name, all_layers)
    
    # 6. 处理 Full_Report（只注入基础元数据，不包含 subsections）
    full_report_file = os.path.join(output_dir, f"{paper_name}_Full_Report.md")
    if os.path.exists(full_report_file):
        logger.info("Processing Full_Report...")
        
        with open(full_report_file, 'r', encoding='utf-8') as f:
            full_report_content = f.read()
        
        # 只注入基础元数据，不添加导航
        save_with_metadata(full_report_file, full_report_content, base_metadata, "Full_Report", paper_name, [])
        logger.info("Full_Report updated with base metadata only")
    
    logger.info("QUAL metadata extraction complete!")


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="QUAL metadata extractor")
    parser.add_argument("paper_dir", help="Paper output directory containing L1_Context.md, etc.")
    parser.add_argument("pdf_dir", help="PDF directory for fallback lookup")
    parser.add_argument("--output_dir", help="Output directory (default: same as paper_dir)")
    parser.add_argument("--pdf_path", help="Direct path to the PDF file (overrides pdf_dir lookup)")

    args = parser.parse_args()

    extract_qual_metadata(args.paper_dir, args.pdf_dir, args.output_dir, args.pdf_path)
