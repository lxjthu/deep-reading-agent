#!/usr/bin/env python3
"""
基础用法示例 - PaddleOCR PDF Extractor

展示如何使用独立模块提取 PDF 为 Markdown
"""

import sys
from pathlib import Path

# 如果模块在同级目录，直接导入
# 如果模块在其他位置，添加路径
# sys.path.insert(0, "/path/to/paddleocr_extractor")

from paddleocr_extractor import PaddleOCRPDFExtractor


def main():
    # 配置 API 凭证（方式一：直接传入）
    extractor = PaddleOCRPDFExtractor(
        remote_url="https://your-api.com/layout-parsing",
        remote_token="your-token"
    )
    
    # 方式二：使用环境变量（需要先设置 .env 或 export）
    # extractor = PaddleOCRPDFExtractor()
    
    # 提取单个 PDF
    pdf_file = "论文.pdf"  # 替换为你的 PDF 路径
    
    print(f"开始提取: {pdf_file}")
    result = extractor.extract_pdf(
        pdf_path=pdf_file,
        out_dir="output",
        download_images=True  # 下载论文中的插图
    )
    
    # 输出结果
    print("\n" + "="*50)
    print("提取完成!")
    print("="*50)
    print(f"Markdown 文件: {result['markdown_path']}")
    print(f"图片目录: {result['images_dir']}")
    print(f"图片数量: {result['stats']['downloaded_images']}")
    print(f"总页数: {result['stats']['total_pages']}")
    
    # 列出下载的图片
    if result['images']:
        print("\n下载的图片:")
        for img in result['images']:
            print(f"  - {img['original_name']} ({img['size_kb']} KB)")


if __name__ == "__main__":
    main()
