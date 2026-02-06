# 与 DeepSeek 集成指南

如何将 PaddleOCR PDF Extractor 与 DeepSeek 深度阅读流水线对接

## 架构概览

```
┌─────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│   PDF 文件   │───▶│  PaddleOCR          │───▶│  DeepSeek       │
│             │    │  PDF Extractor      │    │  Deep Reading   │
└─────────────┘    └─────────────────────┘    └─────────────────┘
                           │                           │
                           ▼                           ▼
                    ┌─────────────┐            ┌─────────────┐
                    │  Markdown   │            │  分析报告    │
                    │  + 图片      │            │  (7步精读)   │
                    └─────────────┘            └─────────────┘
```

## 对接方案

### 方案一：直接调用（推荐）

```python
# deep_read_pipeline.py
from paddleocr_extractor import PaddleOCRPDFExtractor
import openai

class DeepReadingPipeline:
    def __init__(self):
        self.extractor = PaddleOCRPDFExtractor()
        self.deepseek_client = openai.OpenAI(
            api_key="your-deepseek-key",
            base_url="https://api.deepseek.com"
        )
    
    def process(self, pdf_path: str) -> dict:
        """完整处理流程"""
        # Step 1: PDF → Markdown
        extract_result = self.extractor.extract_pdf(
            pdf_path=pdf_path,
            out_dir="temp"
        )
        
        # 读取 Markdown 内容
        with open(extract_result['markdown_path'], 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Step 2: DeepSeek 7步精读
        analysis = self._deep_reading_analysis(markdown_content)
        
        return {
            "extraction": extract_result,
            "analysis": analysis
        }
    
    def _deep_reading_analysis(self, content: str) -> dict:
        """DeepSeek 深度分析"""
        # 7步精读：Overview, Theory, Data, Vars, Identification, Results, Critique
        steps = ["Overview", "Theory", "Data", "Variables", "Identification", "Results", "Critique"]
        results = {}
        
        for step in steps:
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"You are an expert academic paper reviewer. Analyze the {step} aspect."},
                    {"role": "user", "content": content}
                ]
            )
            results[step] = response.choices[0].message.content
        
        return results

# 使用
pipeline = DeepReadingPipeline()
result = pipeline.process("论文.pdf")
```

### 方案二：通过文件系统对接

```python
# 步骤1：PDF 提取（extractor.py）
from paddleocr_extractor import extract_pdf

result = extract_pdf("论文.pdf", out_dir="pdf_paddleocr_md")
# 生成: pdf_paddleocr_md/论文_paddleocr.md

# 步骤2：DeepSeek 分析（analyzer.py）
# 读取生成的 Markdown 进行分析
with open("pdf_paddleocr_md/论文_paddleocr.md", 'r', encoding='utf-8') as f:
    content = f.read()

# 调用 DeepSeek API...
```

### 方案三：队列/消息系统对接

适合大规模批量处理：

```python
# producer.py - 提交 PDF
from task_queue import submit_task

submit_task({
    "type": "pdf_extraction",
    "pdf_path": "论文.pdf",
    "callback": "deepseek_analysis"
})

# consumer.py - 处理队列
from paddleocr_extractor import PaddleOCRPDFExtractor
from task_queue import get_task, complete_task

extractor = PaddleOCRPDFExtractor()

while True:
    task = get_task()
    if task["type"] == "pdf_extraction":
        result = extractor.extract_pdf(task["pdf_path"])
        
        # 提交下一步任务
        submit_task({
            "type": "deepseek_analysis",
            "markdown_path": result["markdown_path"],
            "images_dir": result["images_dir"]
        })
        
        complete_task(task["id"])
```

## 数据传递格式

### 从 Extractor 输出的数据

```python
{
    "markdown_path": "pdf_paddleocr_md/论文_paddleocr.md",
    "images_dir": "pdf_paddleocr_md/imgs",
    "images": [
        {"original_name": "img_in_chart_box_xxx.jpg", ...},
        ...
    ],
    "stats": {
        "total_pages": 19,
        "total_images": 2
    }
}
```

### 传递给 DeepSeek 的数据

```python
# 1. 完整 Markdown 文本（包含图片引用）
markdown_text = open(result["markdown_path"]).read()

# 2. 图片路径映射（用于展示）
image_map = {
    img["original_name"]: img["local_path"]
    for img in result["images"]
}

# 3. 元数据
metadata = {
    "title": "论文标题",
    "total_pages": result["stats"]["total_pages"],
    "extraction_date": "2026-02-02T10:11:30"
}
```

## 集成注意事项

### 1. 图片路径处理

DeepSeek 可能无法直接访问本地图片，处理方式：

```python
# 方式一：将图片转为 base64 嵌入 prompt
import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# 方式二：上传图片到图床，使用 URL
# 方式三：在 Markdown 中保留本地路径，由前端渲染
```

### 2. 长文本分段

PDF 可能很长，需要分段处理：

```python
def split_content(content: str, max_length: int = 4000):
    """按章节分割内容"""
    sections = content.split("## ")
    chunks = []
    current_chunk = ""
    
    for section in sections:
        if len(current_chunk) + len(section) > max_length:
            chunks.append(current_chunk)
            current_chunk = "## " + section
        else:
            current_chunk += "## " + section
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

# 对每个 chunk 分别调用 DeepSeek
for chunk in split_content(markdown_text):
    analyze(chunk)
```

### 3. 结构化输出

要求 DeepSeek 返回结构化数据：

```python
prompt = """
请分析以下论文，并以 JSON 格式返回：
{
    "research_question": "研究问题",
    "methodology": "方法论",
    "key_findings": ["发现1", "发现2"],
    "limitations": "局限性",
    "score": 8.5
}

论文内容：
{content}
"""
```

## 完整示例

```python
# integrated_pipeline.py
import os
import json
from pathlib import Path
from paddleocr_extractor import PaddleOCRPDFExtractor
import openai

class IntegratedPipeline:
    """集成 PaddleOCR + DeepSeek 的完整流水线"""
    
    def __init__(self, deepseek_api_key: str):
        self.extractor = PaddleOCRPDFExtractor()
        self.deepseek = openai.OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
    
    def process(self, pdf_path: str, output_dir: str = "results"):
        """处理单篇论文"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        paper_name = Path(pdf_path).stem
        paper_output = output_dir / paper_name
        paper_output.mkdir(exist_ok=True)
        
        print(f"处理: {paper_name}")
        
        # 1. PDF 提取
        print("  1. PDF 提取...")
        extract_result = self.extractor.extract_pdf(
            pdf_path=pdf_path,
            out_dir=str(paper_output)
        )
        
        # 2. DeepSeek 分析
        print("  2. DeepSeek 分析...")
        with open(extract_result['markdown_path'], 'r', encoding='utf-8') as f:
            content = f.read()
        
        analysis = self._analyze_with_deepseek(content)
        
        # 3. 保存结果
        result = {
            "paper_name": paper_name,
            "extraction": extract_result,
            "deepseek_analysis": analysis
        }
        
        result_file = paper_output / "analysis_result.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"  完成! 结果: {result_file}")
        return result
    
    def _analyze_with_deepseek(self, content: str):
        """调用 DeepSeek API"""
        # 这里实现你的 DeepSeek 分析逻辑
        # 可以是 7 步精读，也可以是其他分析方式
        pass

# 使用
pipeline = IntegratedPipeline(deepseek_api_key="your-key")
pipeline.process("论文.pdf")
```

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| Markdown 中文乱码 | 编码问题 | 使用 `encoding='utf-8'` |
| 图片无法显示 | 路径错误 | 检查相对路径是否正确 |
| DeepSeek token 超限 | 内容太长 | 分段处理或使用更大的模型 |
| API 调用失败 | 网络/认证 | 检查 API key 和网络连接 |
