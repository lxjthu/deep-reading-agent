"""
元数据合并模块
"""

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_base_metadata(pdf_metadata: dict) -> dict:
    """
    创建基础元数据（PDF 元数据 + tags）
    
    Args:
        pdf_metadata: 从 PDF 提取的元数据
    
    Returns:
        基础元数据字典
    """
    return {
        "title": pdf_metadata.get("title", ""),
        "authors": pdf_metadata.get("authors", []),
        "journal": pdf_metadata.get("journal", ""),
        "year": pdf_metadata.get("year", ""),
        "tags": ["paper", "qual", "deep-reading"]
    }


def create_layer_metadata(base_metadata: dict, subsections: dict, layer_name: str) -> dict:
    """
    为单个层级创建元数据（基础元数据 + 该层的子章节）
    
    Args:
        base_metadata: 基础元数据
        subsections: 该层的子章节字典
        layer_name: 层级名称（如 "L1_Context"）
    
    Returns:
        该层的完整元数据
    """
    layer_metadata = base_metadata.copy()
    # 直接将 subsections 合并到顶层，不嵌套在 layer_name_subsections 下
    layer_metadata.update(subsections)
    logger.info(f"Created metadata for {layer_name} with {len(subsections)} subsections")
    return layer_metadata
