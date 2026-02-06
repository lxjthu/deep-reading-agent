# 快速开始指南

5 分钟上手 PaddleOCR PDF Extractor

## 第一步：安装

```bash
# 创建项目目录
mkdir my_project
cd my_project

# 安装依赖
pip install requests python-dotenv

# 下载本模块（复制文件）
# 将 paddleocr_extractor/ 目录复制到你的项目中
```

## 第二步：配置

创建 `.env` 文件：

```bash
cat > .env << 'EOF'
PADDLEOCR_REMOTE_URL=https://your-api-endpoint.com/layout-parsing
PADDLEOCR_REMOTE_TOKEN=your-token-here
EOF
```

## 第三步：使用

### 最简用法（3 行代码）

```python
from paddleocr_extractor import extract_pdf

result = extract_pdf("论文.pdf")
print(result['markdown_path'])  # output/论文_paddleocr.md
```

### 完整用法

```python
from paddleocr_extractor import PaddleOCRPDFExtractor

# 1. 初始化
extractor = PaddleOCRPDFExtractor()

# 2. 提取
result = extractor.extract_pdf(
    pdf_path="论文.pdf",
    out_dir="output"
)

# 3. 使用结果
print(f"Markdown: {result['markdown_path']}")
print(f"图片数: {result['stats']['downloaded_images']}")
```

## 第四步：查看结果

```bash
# 生成的文件结构
output/
├── 论文_paddleocr.md    # Markdown 文件
└── imgs/                 # 图片目录
    ├── img_in_chart_box_xxx.jpg   # 图1
    └── img_in_image_box_xxx.jpg   # 图2

# 用 VS Code 或 Typora 打开 Markdown 查看
```

## 常见问题

### Q: 提示缺少 API 凭证？
**A:** 确保设置了环境变量或创建 `.env` 文件

```python
# 方式一：代码中指定
extractor = PaddleOCRPDFExtractor(
    remote_url="https://...",
    remote_token="your-token"
)

# 方式二：环境变量
export PADDLEOCR_REMOTE_URL="https://..."
export PADDLEOCR_REMOTE_TOKEN="your-token"
```

### Q: 如何只提取文本不下载图片？
**A:**
```python
result = extractor.extract_text_only("论文.pdf")
print(result['content'])  # 纯文本内容
```

### Q: 批量处理多个 PDF？
**A:** 参考 `example_batch.py`

```python
import os
from paddleocr_extractor import PaddleOCRPDFExtractor

extractor = PaddleOCRPDFExtractor()

for pdf in os.listdir("papers"):
    if pdf.endswith(".pdf"):
        extractor.extract_pdf(f"papers/{pdf}", out_dir="output")
```

## 下一步

- 阅读 [README.md](README.md) 了解完整功能
- 查看 [example_integration.py](example_integration.py) 学习如何对接其他代码
- 查看 [API 文档](API.md) 了解所有接口
