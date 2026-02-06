# PaddleOCR PDF 提取模块 — 技术参考文档

> 本文档详细描述 PaddleOCR PDF 提取模块的全部代码、类、方法、参数及其工作原理。
> 最后更新: 2026-02-04

---

## 目录

1. [模块概览与架构](#1-模块概览与架构)
2. [paddleocr_extractor/\_\_init\_\_.py — 包入口](#2-paddleocr_extractor__init__py--包入口)
3. [paddleocr_extractor/extractor.py — 核心提取器](#3-paddleocr_extractorextractorpy--核心提取器)
   - 3.1 [类 PaddleOCRPDFExtractor](#31-类-paddleocrpdfextractor)
   - 3.2 [构造函数 \_\_init\_\_](#32-构造函数-__init__)
   - 3.3 [extract_pdf — 完整提取](#33-extract_pdf--完整提取)
   - 3.4 [extract_text_only — 仅文本提取](#34-extract_text_only--仅文本提取)
   - 3.5 [_split_pdf_to_chunks — PDF 分片](#35-_split_pdf_to_chunks--pdf-分片)
   - 3.6 [_call_api — 分片调度](#36-_call_api--分片调度)
   - 3.7 [_call_api_single — 单次 API 调用（含重试）](#37-_call_api_single--单次-api-调用含重试)
   - 3.8 [_download_images — 图片保存](#38-_download_images--图片保存)
   - 3.9 [_update_image_paths — Markdown 图片路径替换](#39-_update_image_paths--markdown-图片路径替换)
   - 3.10 [_save_markdown — Markdown 保存](#310-_save_markdown--markdown-保存)
   - 3.11 [元数据提取辅助方法](#311-元数据提取辅助方法)
   - 3.12 [模块级便捷函数](#312-模块级便捷函数)
4. [paddleocr_pipeline.py — 管线入口](#4-paddleocr_pipelinepy--管线入口)
   - 4.1 [extract_pdf_with_paddleocr](#41-extract_pdf_with_paddleocr)
   - 4.2 [extract_pdf_legacy — pdfplumber 回退](#42-extract_pdf_legacy--pdfplumber-回退)
   - 4.3 [extract_with_fallback — 自动回退调度](#43-extract_with_fallback--自动回退调度)
   - 4.4 [extract_metadata_from_paddleocr_md — Markdown 元数据解析](#44-extract_metadata_from_paddleocr_md--markdown-元数据解析)
   - 4.5 [iter_pdfs — PDF 文件发现](#45-iter_pdfs--pdf-文件发现)
   - 4.6 [main — 命令行入口及参数](#46-main--命令行入口及参数)
5. [paddleocr_extractor/cli.py — 独立命令行工具](#5-paddleocr_extractorclipy--独立命令行工具)
6. [API 请求/响应格式](#6-api-请求响应格式)
7. [与上游管线的集成点](#7-与上游管线的集成点)

---

## 1. 模块概览与架构

PaddleOCR PDF 提取模块负责将学术论文 PDF 转换为结构化 Markdown 文本。该模块由两层组成：

```
┌─────────────────────────────────────────────────────────────┐
│  paddleocr_pipeline.py  (管线层 — 对外统一接口)              │
│  ┌────────────────────┐  ┌──────────────────────────────┐   │
│  │ extract_with_       │  │ extract_pdf_legacy           │   │
│  │ fallback            │  │ (pdfplumber/pypdf 回退)      │   │
│  └────────┬───────────┘  └──────────────────────────────┘   │
│           │ 正常路径                 ↑ 异常回退              │
│           ▼                         │                       │
│  ┌────────────────────────────────┐ │                       │
│  │ extract_pdf_with_paddleocr     │─┘                       │
│  └────────┬───────────────────────┘                         │
└───────────┼─────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│  paddleocr_extractor/extractor.py  (核心层)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PaddleOCRPDFExtractor                                │   │
│  │  ├── extract_pdf()          完整提取 (文本+图片)      │   │
│  │  ├── extract_text_only()    仅文本提取               │   │
│  │  ├── _split_pdf_to_chunks() PDF 分片 (pypdf)         │   │
│  │  ├── _call_api()            分片调度                  │   │
│  │  ├── _call_api_single()     单次 API + 重试           │   │
│  │  ├── _download_images()     图片保存 (Base64/URL)     │   │
│  │  ├── _update_image_paths()  路径替换                  │   │
│  │  ├── _save_markdown()       Markdown 落盘             │   │
│  │  └── _extract_*()           元数据辅助方法            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**调用关系**：上游管线（`run_batch_pipeline.py`、`smart_scholar_lib.py`）调用 `paddleocr_pipeline.py` 的函数；`paddleocr_pipeline.py` 封装了 PaddleOCR 主路径 + pdfplumber 回退路径；核心提取逻辑在 `paddleocr_extractor/extractor.py` 中。

---

## 2. paddleocr_extractor/\_\_init\_\_.py — 包入口

**文件**: `paddleocr_extractor/__init__.py` (22 行)

```python
from .extractor import PaddleOCRPDFExtractor
__all__ = ["PaddleOCRPDFExtractor"]
```

**功能**: 将 `paddleocr_extractor` 目录注册为 Python 包，导出唯一公开类 `PaddleOCRPDFExtractor`。

**包元数据**:
| 属性 | 值 |
|------|-----|
| `__version__` | `"1.0.0"` |
| `__author__` | `"Deep Reading Agent Team"` |

**使用方式**:
```python
from paddleocr_extractor import PaddleOCRPDFExtractor
```

---

## 3. paddleocr_extractor/extractor.py — 核心提取器

**文件**: `paddleocr_extractor/extractor.py` (456 行)

### 3.0 环境变量加载

模块启动时自动尝试加载 `.env` 文件（使用 `python-dotenv`）：

1. 首先查找模块目录下的 `.env` (`paddleocr_extractor/.env`)
2. 然后查找项目根目录的 `.env` (向上两级，`override=False` 不覆盖已有变量)
3. 如果未安装 `python-dotenv`，静默跳过

### 3.1 类 PaddleOCRPDFExtractor

使用远程 PP-StructureV3 Layout Parsing API 将 PDF 文件转换为 Markdown 格式。支持表格识别、公式识别（LaTeX）、图表解析等 8 项 API 功能开关，以及 PDF 分片和自动重试。

### 3.2 构造函数 \_\_init\_\_

```python
def __init__(
    self,
    remote_url=None, remote_token=None, timeout=600,
    only_original_images=True,
    use_table_recognition=True,
    use_formula_recognition=True,
    use_chart_recognition=False,
    use_seal_recognition=False,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    use_region_detection=True,
    max_pages_per_chunk=10,
    max_retries=5,
    retry_interval=10,
)
```

#### 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `remote_url` | `str \| None` | `None` → 读 `PADDLEOCR_REMOTE_URL` | PP-StructureV3 API 端点 URL |
| `remote_token` | `str \| None` | `None` → 读 `PADDLEOCR_REMOTE_TOKEN` | API 访问令牌 |
| `timeout` | `int` | `600` | 单次 HTTP 请求超时（秒）。长文档/大 PDF 建议保持 600 |
| `only_original_images` | `bool` | `True` | 是否只保留论文原图（`img_in_image_box`、`img_in_chart_box`），过滤公式/表格截图 |
| `use_table_recognition` | `bool` | `True` | **表格识别**：API 将表格区域转为 HTML/Markdown 表格，而非截图 |
| `use_formula_recognition` | `bool` | `True` | **公式识别**：API 将数学公式转为 LaTeX 格式 (`$...$`) |
| `use_chart_recognition` | `bool` | `False` | **图表解析**：API 解析图表中的数据。默认关闭（速度较慢） |
| `use_seal_recognition` | `bool` | `False` | **印章识别**：识别文档中的印章文字。学术论文通常不需要 |
| `use_doc_orientation_classify` | `bool` | `False` | **文档方向矫正**：自动旋转倾斜/旋转的页面。扫描件建议开启 |
| `use_doc_unwarping` | `bool` | `False` | **文档扭曲矫正**：矫正弯曲变形的页面（如翻拍照片） |
| `use_textline_orientation` | `bool` | `False` | **文本行方向矫正**：针对竖排/旋转文字。常规横排论文不需要 |
| `use_region_detection` | `bool` | `True` | **版面区域检测**：识别页面中的文本/图片/表格/公式区域。核心功能，建议保持开启 |
| `max_pages_per_chunk` | `int` | `10` | PDF 分片大小。API 服务端默认只处理前 10 页，客户端按此值切分后逐片提交 |
| `max_retries` | `int` | `5` | API 调用失败时的最大重试次数 |
| `retry_interval` | `int` | `10` | 重试间隔（秒） |

**初始化校验**: 如果 `remote_url` 和 `remote_token` 均未提供（参数和环境变量都为空），抛出 `ValueError`。

---

### 3.3 extract_pdf — 完整提取

```python
def extract_pdf(
    self,
    pdf_path: str,
    out_dir: str = "output",
    download_images: bool = True,
    image_filter: Optional[Callable[[str], bool]] = None
) -> Dict
```

**功能**: 将 PDF 文件完整提取为 Markdown 文件 + 图片文件。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pdf_path` | `str` | — | PDF 文件路径 |
| `out_dir` | `str` | `"output"` | 输出目录，自动创建 |
| `download_images` | `bool` | `True` | 是否保存图片到本地 |
| `image_filter` | `Callable[[str], bool] \| None` | `None` | 自定义图片过滤函数，接收图片名，返回是否保留 |

#### 返回值

```python
{
    "markdown_path": str,         # Markdown 文件绝对路径
    "images_dir": str | None,     # 图片目录路径（无图片时为 None）
    "images": [                   # 已下载图片列表
        {
            "original_name": str,  # API 返回的原始图片名
            "local_path": str,     # 本地保存路径
            "size_kb": float       # 文件大小 (KB)
        }
    ],
    "stats": {
        "total_pages": int,        # 总页数（估算）
        "total_images": int,       # API 返回的图片数
        "downloaded_images": int   # 实际保存的图片数
    }
}
```

#### 执行流程

1. 验证 PDF 文件存在
2. 创建输出目录
3. 调用 `_call_api()` → 获取 Markdown 文本 + 图片字典
4. 图片过滤：
   - 若提供 `image_filter`，按自定义函数过滤
   - 若 `only_original_images=True`（默认），只保留名称包含 `img_in_image_box` 或 `img_in_chart_box` 的图片
5. 调用 `_download_images()` 保存图片
6. 调用 `_update_image_paths()` 替换 Markdown 中的图片引用
7. 调用 `_save_markdown()` 保存 Markdown 文件（含 YAML frontmatter）
8. 返回结果字典

**输出文件命名**: `{pdf_stem}_paddleocr.md`，图片保存在 `{out_dir}/imgs/` 下。

---

### 3.4 extract_text_only — 仅文本提取

```python
def extract_text_only(self, pdf_path: str) -> Dict
```

**功能**: 仅提取文本和元数据，不保存图片，不写入文件。用于快速获取论文结构信息。

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `pdf_path` | `str` | PDF 文件路径 |

#### 返回值

```python
{
    "title": str,         # 论文标题
    "content": str,       # 完整 Markdown 文本
    "abstract": str,      # 摘要
    "keywords": [str],    # 关键词列表
    "sections": [         # 章节结构
        {"number": str, "title": str}
    ]
}
```

**注意**: 此方法会再次调用 `_call_api()`，即 **再次请求 API**。如果在 `extract_pdf()` 之后调用，会产生双倍 API 消耗。`paddleocr_pipeline.py` 中的 `extract_pdf_with_paddleocr()` 会先调用 `extract_pdf()` 再调用 `extract_text_only()`，因此每个 PDF 会被 API 处理两次。

---

### 3.5 _split_pdf_to_chunks — PDF 分片

```python
def _split_pdf_to_chunks(self, pdf_path: str) -> List[bytes]
```

**功能**: 将 PDF 按 `max_pages_per_chunk` 页数切分为多个 PDF 字节块。全部在内存中操作，不写临时文件。

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `pdf_path` | `str` | PDF 文件路径 |

#### 返回值

`List[bytes]` — 每个元素是一个完整的 PDF 文件的字节内容。

#### 工作原理

1. 使用 `pypdf.PdfReader` 读取 PDF，获取总页数
2. 若总页数 ≤ `max_pages_per_chunk`，直接返回原始文件字节（单元素列表）
3. 否则按 `max_pages_per_chunk` 步长切分：
   - 使用 `pypdf.PdfWriter` 逐页添加
   - 写入 `io.BytesIO` 缓冲区
   - 提取 `.getvalue()` 作为字节块
4. 打印分片信息：`分片 N: 第 X-Y 页 (共 Z 页)`

**示例**: 25 页 PDF，`max_pages_per_chunk=10` → 3 个分片 (1-10, 11-20, 21-25)

---

### 3.6 _call_api — 分片调度

```python
def _call_api(self, pdf_path: str) -> Tuple[str, Dict[str, str]]
```

**功能**: 分片调度器。将 PDF 切分后逐片调用 API，合并所有分片的结果。

#### 返回值

`Tuple[str, Dict[str, str]]` — `(合并后的 Markdown 文本, 合并后的图片字典)`

#### 工作流程

1. 调用 `_split_pdf_to_chunks()` 获取分片列表
2. 遍历每个分片：
   - Base64 编码分片字节
   - 调用 `_call_api_single(file_data_b64, file_type=0)` （`file_type=0` 表示 PDF）
   - 多分片时，给图片 key 添加 `chunk{idx}_` 前缀，避免不同分片间的图片名冲突
3. 用 `"\n\n"` 连接所有分片的 Markdown 文本
4. 合并所有分片的图片字典

---

### 3.7 _call_api_single — 单次 API 调用（含重试）

```python
def _call_api_single(self, file_data_b64: str, file_type: int) -> Tuple[str, Dict[str, str]]
```

**功能**: 执行单次 PP-StructureV3 API 调用，失败时自动重试。

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_data_b64` | `str` | Base64 编码的文件内容 |
| `file_type` | `int` | 文件类型。`0` = PDF，`1` = 图片 |

#### 返回值

`Tuple[str, Dict[str, str]]` — `(Markdown 文本, 图片字典)`

#### API 请求构造

**Headers**:
```
Authorization: token {remote_token}
Content-Type: application/json
```

**JSON Payload**:
```json
{
    "file": "<base64_encoded_content>",
    "fileType": 0,
    "useDocOrientationClassify": false,
    "useDocUnwarping": false,
    "useTextlineOrientation": false,
    "useChartRecognition": false,
    "useTableRecognition": true,
    "useFormulaRecognition": true,
    "useSealRecognition": false,
    "useRegionDetection": true
}
```

#### 重试机制

- 最多重试 `max_retries` 次（默认 5）
- 每次失败后等待 `retry_interval` 秒（默认 10）
- 捕获所有异常（包括 `requests.HTTPError`、网络超时等）
- 最后一次失败时 `raise` 原始异常
- 每次失败打印：`API 调用失败 (第 N/M 次): 错误信息` + `Ns 后重试...`

#### 响应解析

API 返回 JSON 结构:
```json
{
    "result": {
        "layoutParsingResults": [
            {
                "markdown": {
                    "text": "...",
                    "images": { "path/to/img.jpg": "<base64>" }
                },
                "outputImages": { ... }
            }
        ]
    }
}
```

解析逻辑:
1. 遍历 `layoutParsingResults` 数组中每个元素
2. 提取 `markdown.text` 追加到 Markdown 列表
3. 收集 `markdown.images`：
   - `dict` 格式: 直接合并（key=路径/名称, value=Base64 或 URL）
   - `list` 格式: 兼容处理（按 `name`/`url` 字段或字符串索引）
4. 收集 `outputImages`（API 的可视化输出图）：
   - `dict` 格式: key 加页码后缀
   - `list` 格式: 自动编号
5. 所有页的 Markdown 用 `"\n\n"` 连接

---

### 3.8 _download_images — 图片保存

```python
def _download_images(self, images: Dict[str, str], out_dir: Path) -> Dict[str, str]
```

**功能**: 将图片数据保存到本地磁盘。支持两种数据来源。

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `images` | `Dict[str, str]` | 图片字典。key=图片名, value=Base64 字符串或 HTTP URL |
| `out_dir` | `Path` | 输出根目录 |

#### 返回值

`Dict[str, str]` — key=原始图片名, value=相对路径 (`imgs/xxx.jpg`)

#### 双模式处理

1. **URL 模式**: 如果 `img_value` 以 `http://` 或 `https://` 开头 → `requests.get()` 下载
2. **Base64 模式**: 否则 → `base64.b64decode()` 解码

**文件名清理**: 移除路径分隔符 (`/`, `\`)，只保留字母数字和 `._-`。空名时自动生成 `img_N.jpg`。

**保存位置**: `{out_dir}/imgs/{safe_name}`

---

### 3.9 _update_image_paths — Markdown 图片路径替换

```python
def _update_image_paths(self, markdown: str, image_map: Dict[str, str]) -> str
```

**功能**: 将 Markdown 文本中对图片的引用（原始 key 名称）替换为本地相对路径。

**原理**: 在 Markdown 中，图片引用格式为 `![alt](path/to/img.jpg)`。API 返回的 `images` 字典的 key 就是 Markdown 中 `()` 内的路径。此方法按 key 做字符串替换，将其替换为本地路径。

---

### 3.10 _save_markdown — Markdown 保存

```python
def _save_markdown(self, output_path: Path, pdf_name: str, content: str)
```

**功能**: 保存 Markdown 文件，自动添加 YAML frontmatter 头部。

**输出格式**:
```markdown
---
title: 论文.pdf
source_pdf: 论文.pdf
extractor: paddleocr
extract_mode: remote_layout
extract_date: 2026-02-04T13:38:01.123456
---

# 论文.pdf

*提取工具: PaddleOCR (远程 Layout Parsing API)*

## Text Content

{API 提取的 Markdown 内容}
```

**编码**: UTF-8

---

### 3.11 元数据提取辅助方法

以下四个方法从 Markdown 文本中使用正则表达式提取元数据，主要针对**中文学术论文**格式。

#### _extract_title

```python
def _extract_title(self, content: str) -> str
```

从内容前 10 行中查找第一个非空、非标题标记（不以 `#` 开头）、长度 > 10 的行作为标题。未找到时返回 `"Unknown"`。

#### _extract_abstract

```python
def _extract_abstract(self, content: str) -> str
```

正则匹配 `摘要：` 或 `摘要:` 后的内容，直到遇到空行、`关键词` 或 `中图分类号`。未找到返回空字符串。

#### _extract_keywords

```python
def _extract_keywords(self, content: str) -> List[str]
```

正则匹配 `关键词：` 或 `关键词:` 后的内容，按 `；`、`;` 分割为列表。未找到返回空列表。

#### _extract_sections

```python
def _extract_sections(self, content: str) -> List[Dict]
```

正则匹配 `## 一、标题` 格式的中文编号章节标题。返回列表：
```python
[{"number": "一、", "title": "引言"}, {"number": "二、", "title": "文献综述"}]
```

---

### 3.12 模块级便捷函数

#### extract_pdf

```python
def extract_pdf(pdf_path: str, out_dir: str = "output", **kwargs) -> Dict
```

快捷函数。实例化 `PaddleOCRPDFExtractor()`（使用环境变量配置），调用 `extract_pdf()`。`kwargs` 透传给 `extract_pdf` 方法。

#### extract_text

```python
def extract_text(pdf_path: str) -> Dict
```

快捷函数。实例化 `PaddleOCRPDFExtractor()`，调用 `extract_text_only()`。

---

## 4. paddleocr_pipeline.py — 管线入口

**文件**: `paddleocr_pipeline.py` (415 行)

该文件是 PaddleOCR 提取的**统一入口**，提供 PaddleOCR 主路径 + pdfplumber 自动回退，以及命令行接口。被 `smart_scholar_lib.py` 和 `run_batch_pipeline.py` 等上游管线调用。

---

### 4.1 extract_pdf_with_paddleocr

```python
def extract_pdf_with_paddleocr(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    download_images: bool = False,
    use_table_recognition: bool = True,
    use_formula_recognition: bool = True,
    use_chart_recognition: bool = False,
    use_doc_orientation_classify: bool = False,
    max_pages_per_chunk: int = 10,
) -> Tuple[str, Dict]
```

**功能**: 使用 PaddleOCR API 提取 PDF。这是 PaddleOCR 主路径的入口。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pdf_path` | `str` | — | PDF 文件路径 |
| `out_dir` | `str` | `"paddleocr_md"` | 输出目录 |
| `download_images` | `bool` | `False` | 是否下载图片。管线中默认关闭以加速 |
| `use_table_recognition` | `bool` | `True` | 透传给 `PaddleOCRPDFExtractor` |
| `use_formula_recognition` | `bool` | `True` | 透传给 `PaddleOCRPDFExtractor` |
| `use_chart_recognition` | `bool` | `False` | 透传给 `PaddleOCRPDFExtractor` |
| `use_doc_orientation_classify` | `bool` | `False` | 透传给 `PaddleOCRPDFExtractor` |
| `max_pages_per_chunk` | `int` | `10` | 透传给 `PaddleOCRPDFExtractor` |

#### 返回值

`Tuple[str, Dict]` — `(markdown_path, metadata_dict)`

`metadata_dict` 格式:
```python
{
    "title": str,
    "abstract": str,
    "keywords": [str],
    "sections": [{"number": str, "title": str}],
    "extractor": "paddleocr",
    "stats": {"total_pages": int, "total_images": int, "downloaded_images": int}
}
```

#### 执行流程

1. 实例化 `PaddleOCRPDFExtractor`，传入功能开关参数
2. 调用 `extractor.extract_pdf()` → 获取 Markdown 文件 + 统计信息
3. 调用 `extractor.extract_text_only()` → 获取标题、摘要、关键词、章节结构
4. 合并两次结果返回

**注意**: 此函数会调用 API **两次**（一次 `extract_pdf`，一次 `extract_text_only`），因为两个方法各自独立调用 `_call_api()`。对于长文档，每次调用都会分片，API 消耗成倍增加。

---

### 4.2 extract_pdf_legacy — pdfplumber 回退

```python
def extract_pdf_legacy(pdf_path: str, out_dir: str = "paddleocr_md") -> Tuple[str, Dict]
```

**功能**: 使用 `pypdf` + `pdfplumber` 的传统方式提取 PDF。当 PaddleOCR API 不可用时自动触发。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pdf_path` | `str` | — | PDF 文件路径 |
| `out_dir` | `str` | `"paddleocr_md"` | 输出目录 |

#### 返回值

`Tuple[str, Dict]` — `(markdown_path, metadata_dict)`

`metadata_dict` 格式:
```python
{
    "title": str,           # 来自 PDF 元数据
    "abstract": "",         # 回退模式不提取摘要
    "keywords": [],         # 回退模式不提取关键词
    "sections": [],         # 回退模式不提取章节
    "extractor": "pdfplumber_fallback",
    "stats": {"total_pages": int}
}
```

#### 提取逻辑

1. **pypdf 优先**: 使用 `PdfReader` 逐页提取文本
2. **pypdf 空白检查**: 如果所有页面都提取不到文字（扫描件等），切换到 pdfplumber
3. **pypdf 异常兜底**: 如果 pypdf 抛出异常，也切换到 pdfplumber
4. **PDF 元数据提取**: 从 `PdfReader.metadata` 读取 `title`、`author`、`subject`

#### 输出格式

```markdown
---
title: 论文.pdf
source_pdf: 论文.pdf
extractor: pdfplumber_fallback
extract_mode: hybrid
extract_date: 2026-02-04T13:38:01
---

# 论文.pdf

*Extraction method: pdfplumber/pypdf (fallback)*

## Text Content

{所有页面文本用 \n\n 连接}
```

**文件命名**: `{pdf_stem}_paddleocr.md`（与 PaddleOCR 输出保持一致的命名，便于下游管线统一处理）

---

### 4.3 extract_with_fallback — 自动回退调度

```python
def extract_with_fallback(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    download_images: bool = False,
    use_table_recognition: bool = True,
    use_formula_recognition: bool = True,
    use_chart_recognition: bool = False,
    use_doc_orientation_classify: bool = False,
    max_pages_per_chunk: int = 10,
    no_fallback: bool = False,
) -> Tuple[str, Dict]
```

**功能**: 主调度函数。先尝试 PaddleOCR，失败时自动回退到 pdfplumber。

#### 参数

前 8 个参数与 `extract_pdf_with_paddleocr` 相同，额外参数:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `no_fallback` | `bool` | `False` | 设为 `True` 时禁用自动回退。API 失败直接抛出异常 |

#### 回退触发条件

当 `no_fallback=False`（默认）时，以下异常会触发回退:

| 异常类型 | 含义 | 日志级别 |
|----------|------|----------|
| `ValueError` | API 凭证缺失 (`remote_url`/`remote_token` 未配置) | WARNING |
| `ConnectionError` | 网络连接失败 | WARNING |
| `TimeoutError` | 请求超时 | WARNING |
| `Exception` (其他) | API 返回错误 (如 500)、JSON 解析失败等 | WARNING |

当 `no_fallback=True` 时:
- 直接调用 `extract_pdf_with_paddleocr()`，不做 try/except
- API 异常直接向上抛出

---

### 4.4 extract_metadata_from_paddleocr_md — Markdown 元数据解析

```python
def extract_metadata_from_paddleocr_md(md_path: str) -> Dict
```

**功能**: 从已生成的 PaddleOCR Markdown 文件中解析元数据。用于在不重新调用 API 的情况下获取论文结构信息。

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `md_path` | `str` | Markdown 文件路径 |

#### 返回值

`Dict` — 包含 `title`、`abstract`、`keywords`、`sections` 等字段。文件不存在时返回空字典。

#### 解析逻辑

1. **YAML frontmatter 解析**: 读取 `---` 包围的头部，使用 `yaml.safe_load()` 解析
2. **标题提取**: 如果 frontmatter 中无标题，从正文前 20 行中查找（同 `_extract_title` 逻辑）
3. **摘要提取**: 中文模式 `摘要：...`，终止于空行/`关键词`/`中图分类号`/`Keywords`
4. **关键词提取**: 中文模式 `关键词：...`，按 `；;,，` 分割
5. **章节提取**: 匹配 `#` 或 `##` 后接中文数字编号（一、二、...）的标题行

---

### 4.5 iter_pdfs — PDF 文件发现

```python
def iter_pdfs(input_path: str) -> list
```

**功能**: 查找指定路径下的所有 PDF 文件。

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `input_path` | `str` | PDF 文件路径或包含 PDF 的目录路径 |

#### 返回值

`list` — 排序后的 PDF 文件路径列表

#### 逻辑

- 如果是单个 `.pdf` 文件 → 返回单元素列表
- 如果是目录 → `os.walk` 递归查找所有 `.pdf` 文件，按路径排序

---

### 4.6 main — 命令行入口及参数

```python
def main()
```

**功能**: CLI 入口，解析命令行参数并执行提取。

#### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `input_path` (位置参数) | `str` | — | PDF 文件路径或目录 |
| `--out_dir` | `str` | `"paddleocr_md"` | 输出目录 |
| `--download_images` | flag | `False` | 启用图片下载 |
| `--force_fallback` | flag | `False` | 跳过 PaddleOCR，强制使用 pdfplumber |
| `--no_table` | flag | `False` | 禁用表格识别 |
| `--no_formula` | flag | `False` | 禁用公式识别 |
| `--chart` | flag | `False` | 启用图表解析 |
| `--orientation` | flag | `False` | 启用文档方向矫正 |
| `--max_pages` | `int` | `10` | 每次 API 调用的最大页数 |
| `--no_fallback` | flag | `False` | 禁用自动回退（API 失败直接报错） |

#### 使用示例

```powershell
# 基本用法 — 单个 PDF
python paddleocr_pipeline.py "E:\pdf\论文.pdf"

# 批量处理目录
python paddleocr_pipeline.py "E:\pdf\002" --out_dir paddleocr_md

# 禁用回退 + 启用图表解析
python paddleocr_pipeline.py "E:\pdf\论文.pdf" --no_fallback --chart

# 强制使用 pdfplumber（不调用 API）
python paddleocr_pipeline.py "E:\pdf\论文.pdf" --force_fallback

# 禁用表格和公式识别（纯文本模式）
python paddleocr_pipeline.py "E:\pdf\论文.pdf" --no_table --no_formula

# 调整分片大小（适用于服务端配置了更大页数限制的情况）
python paddleocr_pipeline.py "E:\pdf\论文.pdf" --max_pages 20
```

#### 参数映射关系

```
CLI 参数              → Python 函数参数                  → API Payload 字段
--no_table           → use_table_recognition=False      → useTableRecognition: false
--no_formula         → use_formula_recognition=False    → useFormulaRecognition: false
--chart              → use_chart_recognition=True       → useChartRecognition: true
--orientation        → use_doc_orientation_classify=True → useDocOrientationClassify: true
--max_pages N        → max_pages_per_chunk=N            → (客户端分片，非 API 字段)
--no_fallback        → no_fallback=True                 → (客户端逻辑，非 API 字段)
--force_fallback     → (直接调用 extract_pdf_legacy)    → (不调用 API)
--download_images    → download_images=True             → (客户端逻辑，非 API 字段)
```

---

## 5. paddleocr_extractor/cli.py — 独立命令行工具

**文件**: `paddleocr_extractor/cli.py` (122 行)

这是 `paddleocr_extractor` 包自带的独立 CLI 工具，**不经过** `paddleocr_pipeline.py`，不具备 pdfplumber 自动回退功能。

#### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `files` (位置参数) | `str` (多个) | — | PDF 文件路径（支持通配符） |
| `-o`, `--output` | `str` | `"output"` | 输出目录 |
| `--text-only` | flag | `False` | 仅提取文本，不下载图片 |
| `--batch` | flag | `False` | 批量模式（为每个文件创建子目录） |
| `--timeout` | `int` | `600` | 请求超时时间（秒） |
| `--version` | flag | — | 显示版本号 |

#### 使用示例

```powershell
# 单个文件
python paddleocr_extractor/cli.py 论文.pdf

# 批量处理
python paddleocr_extractor/cli.py papers/*.pdf --batch -o output_dir

# 仅文本
python paddleocr_extractor/cli.py 论文.pdf --text-only
```

**与 paddleocr_pipeline.py 的区别**:
- `cli.py`: 直接使用 `PaddleOCRPDFExtractor`，无回退、无 API 功能开关暴露、无分片参数暴露
- `paddleocr_pipeline.py`: 封装了 PaddleOCR + pdfplumber 双路径，暴露全部 API 功能开关

---

## 6. API 请求/响应格式

### 请求

```
POST {PADDLEOCR_REMOTE_URL}
Authorization: token {PADDLEOCR_REMOTE_TOKEN}
Content-Type: application/json

{
    "file": "<base64_encoded_pdf_bytes>",
    "fileType": 0,                        // 0=PDF, 1=Image
    "useTableRecognition": true,
    "useFormulaRecognition": true,
    "useChartRecognition": false,
    "useSealRecognition": false,
    "useDocOrientationClassify": false,
    "useDocUnwarping": false,
    "useTextlineOrientation": false,
    "useRegionDetection": true
}
```

### 响应

```json
{
    "result": {
        "layoutParsingResults": [
            {
                "markdown": {
                    "text": "# 标题\n\n正文内容...\n\n$$E=mc^2$$\n\n| col1 | col2 |\n|---|---|\n| a | b |",
                    "images": {
                        "img_in_image_box_0_0.jpg": "<base64_encoded_image_data>",
                        "img_in_chart_box_0_1.jpg": "<base64_encoded_image_data>"
                    }
                },
                "outputImages": { ... },
                "prunedResult": { ... }
            }
        ]
    }
}
```

**`layoutParsingResults` 数组**: 每个元素对应 PDF 的一页。

**图片 key 命名规则** (由 API 生成):
- `img_in_image_box_*`: 论文中的插图（图 1、图 2 等）
- `img_in_chart_box_*`: 图表截图
- `img_in_table_box_*`: 表格截图（通常可忽略，因为表格已转为 Markdown）
- `img_in_formula_box_*`: 公式截图（通常可忽略，因为公式已转为 LaTeX）

**图片值**: Base64 编码的图片二进制数据（非 URL）。

---

## 7. 与上游管线的集成点

### smart_scholar_lib.py

`smart_scholar_lib.py` 在 `extract_with_paddleocr()` 函数中通过子进程调用:

```python
subprocess.run([sys.executable, "paddleocr_pipeline.py", pdf_path, "--out_dir", out_dir])
```

使用默认参数（表格识别开、公式识别开、分片=10页、自动回退开）。

### run_batch_pipeline.py

批量管线调用 `paddleocr_pipeline.extract_with_fallback()` 作为 Python 函数:

```python
from paddleocr_pipeline import extract_with_fallback
md_path, metadata = extract_with_fallback(pdf_path, out_dir="paddleocr_md")
```

### run_full_pipeline.py

全流程管线通过 `--use-paddleocr` 标志切换:

```powershell
python run_full_pipeline.py "paper.pdf" --use-paddleocr
```

启用时调用 `paddleocr_pipeline.py` 作为提取步骤。

### 输出兼容性

PaddleOCR 和 pdfplumber 回退两个路径的输出格式保持一致:
- 文件名: `{pdf_stem}_paddleocr.md`
- YAML frontmatter 中 `extractor` 字段区分来源: `paddleocr` vs `pdfplumber_fallback`
- 正文在 `## Text Content` 标题下
- 下游分段器 (`paddleocr_segment.py`) 可直接处理两种输出

---

*文档结束*
