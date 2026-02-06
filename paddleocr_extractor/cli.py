#!/usr/bin/env python3
"""
命令行工具 - PaddleOCR PDF Extractor

提供便捷的命令行接口，无需编写 Python 代码即可使用。

用法:
    python cli.py 论文.pdf
    python cli.py 论文.pdf -o output_dir
    python cli.py papers/*.pdf --batch
"""

import sys
import argparse
from pathlib import Path
from paddleocr_extractor import PaddleOCRPDFExtractor, __version__


def main():
    parser = argparse.ArgumentParser(
        description="PaddleOCR PDF Extractor - PDF 转 Markdown 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 提取单个 PDF
  python cli.py 论文.pdf

  # 指定输出目录
  python cli.py 论文.pdf -o my_output

  # 仅提取文本（不下载图片）
  python cli.py 论文.pdf --text-only

  # 批量处理
  python cli.py papers/*.pdf --batch

  # 显示版本
  python cli.py --version
        """
    )
    
    parser.add_argument("files", nargs="+", help="PDF 文件路径（支持通配符）")
    parser.add_argument("-o", "--output", default="output", 
                        help="输出目录（默认: output）")
    parser.add_argument("--text-only", action="store_true",
                        help="仅提取文本，不下载图片")
    parser.add_argument("--batch", action="store_true",
                        help="批量模式（处理多个文件）")
    parser.add_argument("--timeout", type=int, default=600,
                        help="请求超时时间（秒，默认: 600）")
    parser.add_argument("--version", action="version", 
                        version=f"%(prog)s {__version__}")
    
    args = parser.parse_args()
    
    # 初始化提取器
    try:
        extractor = PaddleOCRPDFExtractor(timeout=args.timeout)
    except ValueError as e:
        print(f"[ERROR] 初始化失败: {e}")
        print("\n请设置环境变量或创建 .env 文件:")
        print("  export PADDLEOCR_REMOTE_URL=https://your-api.com/layout-parsing")
        print("  export PADDLEOCR_REMOTE_TOKEN=your-token")
        sys.exit(1)
    
    # 处理文件
    pdf_files = [Path(f) for f in args.files if f.endswith('.pdf')]
    
    if not pdf_files:
        print("[ERROR] 未找到 PDF 文件")
        sys.exit(1)
    
    print(f"共 {len(pdf_files)} 个文件待处理\n")
    
    success_count = 0
    fail_count = 0
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] 处理: {pdf_path.name}")
        
        if not pdf_path.exists():
            print(f"  [FAIL] 文件不存在")
            fail_count += 1
            continue
        
        try:
            # 为每个文件创建子目录
            out_dir = Path(args.output) / pdf_path.stem if args.batch else Path(args.output)
            
            if args.text_only:
                # 仅提取文本
                result = extractor.extract_text_only(str(pdf_path))
                print(f"  [OK] 标题: {result['title'][:50]}...")
                print(f"       关键词: {', '.join(result['keywords'])}")
            else:
                # 完整提取
                result = extractor.extract_pdf(
                    pdf_path=str(pdf_path),
                    out_dir=str(out_dir)
                )
                print(f"  [OK] Markdown: {result['markdown_path']}")
                print(f"       图片: {result['stats']['downloaded_images']} 张")
            
            success_count += 1
            
        except Exception as e:
            print(f"  [FAIL] {e}")
            fail_count += 1
        
        print()
    
    # 汇总
    print("=" * 50)
    print("处理完成!")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  输出: {Path(args.output).absolute()}")


if __name__ == "__main__":
    main()
