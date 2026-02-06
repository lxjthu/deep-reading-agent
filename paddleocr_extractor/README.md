# PaddleOCR PDF 提取模块 (Standalone)

一个独立的 PDF 转 Markdown 模块，基于 PaddleOCR 远程 Layout Parsing API，专为学术论文提取优化。

## 功能特性

| 功能 | 说明 |
|------|------|
| **PDF 转 Markdown** | 直接上传 PDF，返回结构化 Markdown 文本 |
| **图片提取** | 自动提取论文中的插图（图1、图2等），过滤公式/表格截图 |
| **公式识别** | 保留 LaTeX 格式的数学公式 |
| **表格转换** | 将 PDF 表格转为 HTML/Markdown 格式 |
| **中文优化** | 针对中文学术论文优化，识别准确率高 |
| **零本地依赖** | 无需 poppler/pdf2image，纯远程 API 处理 |

## 环境要求

- **Python**: 3.8+
- **操作系统**: Windows / macOS / Linux

### Python 依赖

```
requests>=2.25.0
python-dotenv>=0.19.0
```

### API 凭证

需要从 PaddleOCR 获取远程 Layout Parsing API 的凭证：
- `REMOTE_URL`: API 端点地址
- `REMOTE_TOKEN`: 访问令牌

## 安装

```bash
# 安装依赖
pip install requests python-dotenv

# 配置环境变量
export PADDLEOCR_REMOTE_URL="https://your-api.com/layout-parsing"
export PADDLEOCR_REMOTE_TOKEN="your-token"
```

## 快速开始

### 基础用法

```python
from paddleocr_extractor import PaddleOCRPDFExtractor

# 初始化提取器
extractor = PaddleOCRPDFExtractor(
    remote_url="https://your-api.com/layout-parsing",
    remote_token="your-token"
)

# 提取 PDF
result = extractor.extract_pdf(
    pdf_path="论文.pdf",
    out_dir="output"
)

print(f"Markdown 文件: {result['markdown_path']}")
print(f"图片数量: {len(result['images'])}")
```

### 环境变量配置

创建 `.env` 文件：
```env
PADDLEOCR_REMOTE_URL=https://your-api.com/layout-parsing
PADDLEOCR_REMOTE_TOKEN=your-token
```

代码中自动加载：
```python
from paddleocr_extractor import PaddleOCRPDFExtractor

# 自动从 .env 文件加载配置
extractor = PaddleOCRPDFExtractor()
result = extractor.extract_pdf("论文.pdf")
```

## API 文档

### PaddleOCRPDFExtractor 类

#### 构造函数

```python
PaddleOCRPDFExtractor(
    remote_url: Optional[str] = None,      # API 端点
    remote_token: Optional[str] = None,    # 访问令牌
    timeout: int = 300,                     # 请求超时(秒)
    only_original_images: bool = True       # 只保留论文原图
)
```

#### 主要方法

**extract_pdf(pdf_path, out_dir)** - 提取 PDF 文件

参数：
- `pdf_path` (str): PDF 文件路径
- `out_dir` (str): 输出目录
- `download_images` (bool): 是否下载图片 (默认: True)

返回值：
```python
{
    "markdown_path": "output/论文_paddleocr.md",
    "images_dir": "output/imgs",
    "images": [
        {
            "original_name": "img_in_image_box_xxx.jpg",
            "local_path": "output/imgs/img_xxx.jpg",
            "size_kb": 31.58
        }
    ],
    "stats": {
        "total_pages": 19,
        "total_images": 97,
        "downloaded_images": 2,
        "filtered_images": 95
    }
}
```

**extract_text_only(pdf_path)** - 仅提取文本，不下载图片

返回值：
```python
{
    "title": "论文标题",
    "content": "完整 Markdown 文本",
    "abstract": "摘要内容",
    "keywords": ["关键词1", "关键词2"],
    "sections": [
        {"title": "一、引言", "content": "..."},
    ]
}
```

## 与其他代码对接

### 场景一：集成到深度学习流水线

```python
from paddleocr_extractor import PaddleOCRPDFExtractor
import deepseek_analyzer

def process_paper(pdf_path):
    # Step 1: PDF 转 Markdown
    extractor = PaddleOCRPDFExtractor()
    result = extractor.extract_pdf(pdf_path, out_dir="temp")
    
    # Step 2: DeepSeek 分析
    analysis = deepseek_analyzer.analyze(
        markdown_path=result["markdown_path"],
        images_dir=result["images_dir"]
    )
    
    return {
        "paper_info": result,
        "analysis": analysis
    }
```

### 场景二：批量处理并导出到 Excel

```python
from paddleocr_extractor import PaddleOCRPDFExtractor
import pandas as pd
import os

extractor = PaddleOCRPDFExtractor()
papers = []

for pdf_file in os.listdir("papers"):
    if pdf_file.endswith(".pdf"):
        result = extractor.extract_text_only(f"papers/{pdf_file}")
        papers.append({
            "filename": pdf_file,
            "title": result["title"],
            "abstract": result["abstract"],
            "keywords": ", ".join(result["keywords"])
        })

# 导出到 Excel
df = pd.DataFrame(papers)
df.to_excel("papers_summary.xlsx", index=False)
```

### 场景三：作为 Web 服务的后台

```python
from flask import Flask, request, jsonify
from paddleocr_extractor import PaddleOCRPDFExtractor
import tempfile

app = Flask(__name__)
extractor = PaddleOCRPDFExtractor()

@app.route('/extract', methods=['POST'])
def extract_pdf():
    pdf_file = request.files['pdf']
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        pdf_file.save(tmp.name)
        result = extractor.extract_pdf(tmp.name, out_dir="output")
    
    return jsonify(result)
```

## 输出格式说明

### Markdown 文件结构

```markdown
---
title: 论文标题
source_pdf: 论文.pdf
extractor: paddleocr
extract_mode: remote_layout
extract_date: 2026-02-02T10:11:30
---

# 论文标题

*提取工具: PaddleOCR (远程 Layout Parsing API)*

## Text Content

# 论文正文...

## 一、引言
...

<div style="text-align: center;">
  <img src="imgs/img_in_chart_box_xxx.jpg" alt="Image" width="39%" />
</div>
<div style="text-align: center;">图1 说明文字</div>
```

### 图片过滤规则

默认只保留真正的论文插图，过滤：
- API 生成的检测图 (`layout_det_res_*`)
- OCR 结果图 (`overall_ocr_res_*`)
- 区域检测图 (`region_det_res_*`)
- 公式截图 (`img_in_formula_box_*`)
- 表格截图 (`img_in_table_box_*`)

只保留：
- 论文原图 (`img_in_image_box_*`, `img_in_chart_box_*`)

## 故障排除

### 问题1：API 连接失败
```
无法连接到服务器: https://...
```
**解决：** 检查网络连接和 API 地址是否正确

### 问题2：认证失败
```
API 请求失败: 401 Unauthorized
```
**解决：** 检查 REMOTE_TOKEN 是否正确设置

### 问题3：超时
```
请求超时，PDF 文件可能过大
```
**解决：** 增加 timeout 参数或分批处理

## 许可证

MIT License
