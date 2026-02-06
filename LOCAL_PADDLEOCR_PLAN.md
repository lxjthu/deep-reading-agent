# Plan: 本地 PaddleOCR PDF 提取功能

## 目标
在项目中添加本地 PaddleOCR (GPU) PDF 转 Markdown 功能，替代远程 API 调用，并整合到 GUI 中。

## 前置步骤：安装缺失依赖

PP-StructureV3 需要 `paddlex[ocr]` 的额外依赖才能运行：

```powershell
pip install "paddlex[ocr]==3.4.1"
```

这会安装 `beautifulsoup4`, `einops`, `lxml`, `scikit-learn`, `scipy`, `tiktoken` 等所需包。

---

## Step 1: 创建 `paddleocr_local.py` (本地提取模块)

**新建文件**: `paddleocr_local.py`

核心功能：
- 使用 `PPStructureV3` (from `paddleocr`) 在本地 GPU 上执行版面分析 + OCR
- 输出格式与远程 API 完全一致（YAML frontmatter 含 `extractor: paddleocr`）
- 文件名约定 `{name}_paddleocr.md` 不变

关键设计：
- PPStructureV3 引擎使用单例模式（模块级全局变量），避免重复加载模型
- YAML frontmatter 使用 `extract_mode: local_gpu` 以区分远程 API
- `extractor: paddleocr` 保持不变，下游 `paddleocr_segment.py` 无需修改

---

## Step 2: 在 `paddleocr_pipeline.py` 中添加本地提取入口

**修改文件**: `paddleocr_pipeline.py`

- 添加新函数 `extract_pdf_local_paddleocr()`
- 更新 `extract_with_fallback()` 的回退链：远程 → 本地 → pdfplumber
- 添加 CLI 参数 `--local` 支持命令行使用本地模式

---

## Step 3: 用 `E:\pdf\003` 测试批量转换

测试文件（3 个中文学术 PDF，共约 7MB）：
- 生成式人工智能赋能数字乡村建设.pdf
- 生成式人工智能助力乡村振兴.pdf
- 数智赋能乡村文化新质生产力.pdf

验证要点：
1. MD 文件生成到 `paddleocr_md/` 且含正确 YAML frontmatter
2. 中文内容完整提取，表格/公式正常识别
3. GPU 加速正常工作

---

## Step 4: 整合到 GUI (`app.py`)

### 4a. 更新环境状态显示 (`_env_status()`)
添加本地 PaddleOCR 可用性检测

### 4b. Tab 1 (PDF 提取)
添加新 Checkbox：`使用本地 PaddleOCR (GPU)` — 优先级高于远程 API

### 4c. Tab 2 (全流程精读)
更新 Radio 选项为三选一：本地GPU / 远程API / Legacy

### 4d. Tab 3 (批量处理)
添加提取方式选择 Radio

---

## 涉及的文件

| 文件 | 操作 |
|------|------|
| `paddleocr_local.py` | **新建** - 本地 PaddleOCR 提取核心模块 |
| `paddleocr_pipeline.py` | **修改** - 添加本地提取入口和回退链 |
| `app.py` | **修改** - GUI 集成本地提取选项 |
| `requirements.txt` | **修改** - 添加 `paddlex[ocr]` 依赖 |

不需要修改的文件（接口兼容）：
- `paddleocr_segment.py` — `extractor: paddleocr` 不变
- `deep_reading_steps/common.py` — 下游管道不受影响
- `smart_scholar_lib.py` — 通过 `paddleocr_pipeline` 间接调用
