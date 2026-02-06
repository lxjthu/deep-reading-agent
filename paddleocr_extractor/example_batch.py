#!/usr/bin/env python3
"""
批量处理示例 - PaddleOCR PDF Extractor

展示如何批量处理多个 PDF 文件，并导出结果到 Excel
"""

import os
import pandas as pd
from pathlib import Path
from paddleocr_extractor import PaddleOCRPDFExtractor


def batch_extract(pdf_dir: str, out_dir: str = "output"):
    """
    批量提取 PDF 文件
    
    Args:
        pdf_dir: PDF 文件所在目录
        out_dir: 输出目录
    """
    extractor = PaddleOCRPDFExtractor()
    
    pdf_dir = Path(pdf_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    # 遍历所有 PDF 文件
    for pdf_file in sorted(pdf_dir.glob("*.pdf")):
        print(f"\n处理: {pdf_file.name}")
        
        try:
            # 提取文本（不下载图片，加快速度）
            text_result = extractor.extract_text_only(str(pdf_file))
            
            # 收集信息
            results.append({
                "filename": pdf_file.name,
                "title": text_result["title"],
                "abstract": text_result["abstract"],
                "keywords": ", ".join(text_result["keywords"]),
                "sections": len(text_result["sections"]),
                "status": "成功"
            })
            
        except Exception as e:
            print(f"  [FAIL] {e}")
            results.append({
                "filename": pdf_file.name,
                "title": "",
                "abstract": "",
                "keywords": "",
                "sections": 0,
                "status": f"失败: {e}"
            })
    
    # 导出到 Excel
    df = pd.DataFrame(results)
    excel_path = out_dir / "papers_summary.xlsx"
    df.to_excel(excel_path, index=False)
    
    print(f"\n{'='*50}")
    print(f"批量处理完成!")
    print(f"总计: {len(results)} 个文件")
    print(f"成功: {sum(1 for r in results if r['status'] == '成功')} 个")
    print(f"结果保存: {excel_path}")
    
    return df


def main():
    # 配置
    PDF_DIR = "papers"  # PDF 文件目录
    OUT_DIR = "output"  # 输出目录
    
    # 执行批量提取
    df = batch_extract(PDF_DIR, OUT_DIR)
    
    # 显示前几行结果
    print("\n前5条结果预览:")
    print(df.head())


if __name__ == "__main__":
    main()
