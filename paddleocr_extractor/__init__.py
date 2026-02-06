"""
PaddleOCR PDF Extractor - Standalone Module

一个独立的 PDF 转 Markdown 模块，基于 PaddleOCR 远程 Layout Parsing API。

基本用法:
    >>> from paddleocr_extractor import PaddleOCRPDFExtractor
    >>> extractor = PaddleOCRPDFExtractor()
    >>> result = extractor.extract_pdf("论文.pdf", out_dir="output")
    >>> print(result['markdown_path'])

作者: Deep Reading Agent Team
版本: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "Deep Reading Agent Team"

from .extractor import PaddleOCRPDFExtractor

__all__ = ["PaddleOCRPDFExtractor"]
