#!/usr/bin/env python3
"""
与其他代码对接示例 - PaddleOCR PDF Extractor

展示如何将 PDF 提取模块集成到现有的分析流水线中
"""

import os
import json
from pathlib import Path
from typing import Dict

from paddleocr_extractor import PaddleOCRPDFExtractor


class DeepSeekAnalyzer:
    """
    模拟的 DeepSeek 分析器
    实际使用时替换为你的真实分析模块
    """
    
    def analyze(self, markdown_path: str, images_dir: str = None) -> Dict:
        """
        分析论文内容
        
        Args:
            markdown_path: Markdown 文件路径
            images_dir: 图片目录
            
        Returns:
            分析结果字典
        """
        # 这里替换为实际的 DeepSeek API 调用
        print(f"  [DeepSeek] 正在分析: {markdown_path}")
        
        # 模拟分析结果
        content = Path(markdown_path).read_text(encoding='utf-8')
        
        return {
            "summary": "这是一篇关于...的论文",
            "key_points": ["要点1", "要点2", "要点3"],
            "methodology": "使用了双重差分法",
            "conclusion": "研究发现...",
            "word_count": len(content)
        }


class PaperProcessingPipeline:
    """
    论文处理流水线
    
    整合 PDF 提取和 DeepSeek 分析
    """
    
    def __init__(self, output_dir: str = "pipeline_output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化模块
        self.extractor = PaddleOCRPDFExtractor()
        self.analyzer = DeepSeekAnalyzer()
    
    def process(self, pdf_path: str) -> Dict:
        """
        处理单篇论文
        
        流程: PDF -> Markdown -> DeepSeek分析 -> 结构化结果
        
        Args:
            pdf_path: PDF 文件路径
            
        Returns:
            完整的处理结果
        """
        pdf_path = Path(pdf_path)
        print(f"\n{'='*60}")
        print(f"开始处理: {pdf_path.name}")
        print('='*60)
        
        # Step 1: PDF 提取
        print("\n[Step 1] PDF 提取...")
        paper_dir = self.output_dir / pdf_path.stem
        extract_result = self.extractor.extract_pdf(
            pdf_path=str(pdf_path),
            out_dir=str(paper_dir),
            download_images=True
        )
        
        # Step 2: DeepSeek 分析
        print("\n[Step 2] DeepSeek 分析...")
        analysis = self.analyzer.analyze(
            markdown_path=extract_result['markdown_path'],
            images_dir=extract_result['images_dir']
        )
        
        # Step 3: 整合结果
        result = {
            "paper_id": pdf_path.stem,
            "source_pdf": str(pdf_path),
            "extraction": {
                "markdown_path": extract_result['markdown_path'],
                "images_dir": extract_result['images_dir'],
                "stats": extract_result['stats']
            },
            "analysis": analysis,
            "metadata": self._extract_metadata(extract_result['markdown_path'])
        }
        
        # 保存结果
        result_file = paper_dir / "result.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n[完成] 结果保存: {result_file}")
        
        return result
    
    def batch_process(self, pdf_dir: str):
        """
        批量处理目录中的所有 PDF
        
        Args:
            pdf_dir: PDF 文件目录
        """
        pdf_dir = Path(pdf_dir)
        
        all_results = []
        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            try:
                result = self.process(str(pdf_file))
                all_results.append(result)
            except Exception as e:
                print(f"\n[ERROR] 处理失败 {pdf_file.name}: {e}")
        
        # 生成汇总报告
        self._generate_report(all_results)
        
        return all_results
    
    def _extract_metadata(self, markdown_path: str) -> Dict:
        """提取元数据"""
        content = Path(markdown_path).read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 简单提取标题（第一行非空内容）
        title = ""
        for line in lines[20:30]:  # 跳过 frontmatter
            line = line.strip()
            if line and not line.startswith('#') and len(line) > 10:
                title = line
                break
        
        return {"title": title}
    
    def _generate_report(self, results: list):
        """生成汇总报告"""
        report_path = self.output_dir / "processing_report.json"
        
        report = {
            "total": len(results),
            "successful": len([r for r in results if 'error' not in r]),
            "papers": [
                {
                    "id": r["paper_id"],
                    "title": r["metadata"]["title"],
                    "word_count": r["analysis"]["word_count"]
                }
                for r in results
            ]
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*60}")
        print(f"批量处理完成!")
        print(f"总计: {report['total']} 篇")
        print(f"成功: {report['successful']} 篇")
        print(f"报告: {report_path}")


def main():
    """示例运行"""
    # 创建流水线
    pipeline = PaperProcessingPipeline(output_dir="pipeline_output")
    
    # 处理单篇论文
    # result = pipeline.process("论文.pdf")
    
    # 批量处理
    # results = pipeline.batch_process("papers/")
    
    print("请修改代码中的 pdf 路径后运行")
    print("\n示例:")
    print("  result = pipeline.process('论文.pdf')")
    print("  results = pipeline.batch_process('papers/')")


if __name__ == "__main__":
    main()
