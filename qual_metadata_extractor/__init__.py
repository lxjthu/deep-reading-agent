"""
QUAL 论文元数据提取工具

从生成的 MD 报告和原始 PDF 中提取元数据，并注入到 Frontmatter
"""

from .extractor import extract_qual_metadata

__all__ = ['extract_qual_metadata']
