# API 文档

详细的 API 参考手册

## 目录

- [PaddleOCRPDFExtractor 类](#paddleocrpdfextractor-类)
- [便捷函数](#便捷函数)
- [返回值结构](#返回值结构)
- [异常处理](#异常处理)

---

## PaddleOCRPDFExtractor 类

### 构造函数

```python
PaddleOCRPDFExtractor(
    remote_url: Optional[str] = None,
    remote_token: Optional[str] = None,
    timeout: int = 300,
    only_original_images: bool = True
)
```

**参数说明：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `remote_url` | str | None | API 端点地址。为 None 时从环境变量 `PADDLEOCR_REMOTE_URL` 读取 |
| `remote_token` | str | None | 访问令牌。为 None 时从环境变量 `PADDLEOCR_REMOTE_TOKEN` 读取 |
| `timeout` | int | 300 | HTTP 请求超时时间（秒） |
| `only_original_images` | bool | True | 是否只保留论文原图（过滤公式/表格截图） |

**示例：**

```python
# 方式一：直接传入
extractor = PaddleOCRPDFExtractor(
    remote_url="https://api.example.com/layout-parsing",
    remote_token="abc123",
    timeout=600
)

# 方式二：从环境变量读取
import os
os.environ["PADDLEOCR_REMOTE_URL"] = "https://api.example.com/layout-parsing"
os.environ["PADDLEOCR_REMOTE_TOKEN"] = "abc123"

extractor = PaddleOCRPDFExtractor()

# 方式三：使用 .env 文件
# 创建 .env 文件后自动加载
extractor = PaddleOCRPDFExtractor()
```

---

### extract_pdf 方法

提取 PDF 文件，生成 Markdown 并下载图片。

```python
extractor.extract_pdf(
    pdf_path: str,
    out_dir: str = "output",
    download_images: bool = True,
    image_filter: Optional[Callable[[str], bool]] = None
) -> Dict
```

**参数说明：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pdf_path` | str | 必填 | PDF 文件路径 |
| `out_dir` | str | "output" | 输出目录 |
| `download_images` | bool | True | 是否下载图片 |
| `image_filter` | Callable | None | 自定义图片过滤函数 |

**返回值：**

```python
{
    "markdown_path": str,      # Markdown 文件完整路径
    "images_dir": str,         # 图片目录路径（无图片时为 None）
    "images": [                # 图片列表
        {
            "original_name": str,   # 原始文件名
            "local_path": str,      # 本地完整路径
            "size_kb": float        # 文件大小（KB）
        }
    ],
    "stats": {                 # 统计信息
        "total_pages": int,        # 总页数（估算）
        "total_images": int,       # API 返回的总图片数
        "downloaded_images": int   # 实际下载的图片数
    }
}
```

**示例：**

```python
# 基础用法
result = extractor.extract_pdf("论文.pdf")

# 自定义输出目录
result = extractor.extract_pdf("论文.pdf", out_dir="my_output")

# 不下载图片（纯文本）
result = extractor.extract_pdf("论文.pdf", download_images=False)

# 自定义图片过滤（只保留文件名包含 "figure" 的图片）
result = extractor.extract_pdf(
    "论文.pdf",
    image_filter=lambda name: "figure" in name.lower()
)
```

---

### extract_text_only 方法

仅提取文本内容，不下载图片。速度更快，适合批量处理。

```python
extractor.extract_text_only(pdf_path: str) -> Dict
```

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `pdf_path` | str | PDF 文件路径 |

**返回值：**

```python
{
    "title": str,              # 论文标题（自动提取）
    "content": str,            # 完整 Markdown 文本
    "abstract": str,           # 摘要内容
    "keywords": List[str],     # 关键词列表
    "sections": [              # 章节结构
        {
            "number": str,     # 章节编号（如"一、"）
            "title": str       # 章节标题
        }
    ]
}
```

**示例：**

```python
result = extractor.extract_text_only("论文.pdf")

print(f"标题: {result['title']}")
print(f"关键词: {', '.join(result['keywords'])}")
print(f"章节数: {len(result['sections'])}")
print(f"字数: {len(result['content'])}")
```

---

## 便捷函数

模块提供了两个便捷的顶层函数，无需实例化类。

### extract_pdf

```python
from paddleocr_extractor import extract_pdf

result = extract_pdf(
    pdf_path: str,
    out_dir: str = "output",
    **kwargs
) -> Dict
```

自动创建 extractor 实例并调用 extract_pdf 方法。

### extract_text

```python
from paddleocr_extractor import extract_text

result = extract_text(pdf_path: str) -> Dict
```

自动创建 extractor 实例并调用 extract_text_only 方法。

---

## 返回值结构

### 图片信息结构

```python
{
    "original_name": "img_in_image_box_619_531_1053_880.jpg",
    "local_path": "/project/output/imgs/img_in_image_box_619_531_1053_880.jpg",
    "size_kb": 31.58
}
```

### 章节信息结构

```python
{
    "number": "一、",
    "title": "引言"
}
```

---

## 异常处理

模块可能抛出以下异常：

| 异常类型 | 触发条件 | 处理建议 |
|----------|----------|----------|
| `ValueError` | 缺少 API 凭证 | 检查环境变量或传入参数 |
| `FileNotFoundError` | PDF 文件不存在 | 检查文件路径 |
| `requests.Timeout` | 请求超时 | 增加 timeout 参数或检查网络 |
| `requests.HTTPError` | HTTP 错误（401/403/500） | 检查 token 和网络连接 |

**示例：**

```python
from paddleocr_extractor import PaddleOCRPDFExtractor

extractor = PaddleOCRPDFExtractor()

try:
    result = extractor.extract_pdf("论文.pdf")
except ValueError as e:
    print(f"配置错误: {e}")
except FileNotFoundError:
    print("PDF 文件不存在")
except Exception as e:
    print(f"未知错误: {e}")
```

---

## 高级用法

### 自定义图片过滤

```python
def my_filter(image_name: str) -> bool:
    """
    自定义过滤规则
    返回 True 表示保留，False 表示过滤掉
    """
    # 只保留文件名包含 "chart" 或 "figure" 的图片
    return any(keyword in image_name.lower() 
               for keyword in ["chart", "figure"])

result = extractor.extract_pdf(
    "论文.pdf",
    image_filter=my_filter
)
```

### 批量处理带进度

```python
import os
from tqdm import tqdm
from paddleocr_extractor import PaddleOCRPDFExtractor

extractor = PaddleOCRPDFExtractor()
pdf_files = [f for f in os.listdir("papers") if f.endswith(".pdf")]

results = []
for pdf in tqdm(pdf_files, desc="处理论文"):
    try:
        result = extractor.extract_pdf(f"papers/{pdf}")
        results.append(result)
    except Exception as e:
        print(f"处理失败 {pdf}: {e}")
```
