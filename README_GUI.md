# Deep Reading Agent - GUI 使用手册

本文档详细说明 Gradio 图形界面 (`app.py`) 的环境配置、启动方式和功能使用。

---

## 目录

- [系统要求](#系统要求)
- [环境配置](#环境配置)
  - [1. Python 虚拟环境](#1-python-虚拟环境)
  - [2. 安装依赖](#2-安装依赖)
  - [3. 配置环境变量 (.env)](#3-配置环境变量-env)
- [环境变量详解](#环境变量详解)
  - [必需变量](#必需变量)
  - [推荐变量](#推荐变量)
  - [可选变量](#可选变量)
- [启动 GUI](#启动-gui)
  - [方式一：一键启动（推荐）](#方式一一键启动推荐)
  - [方式二：手动启动](#方式二手动启动)
- [界面功能说明](#界面功能说明)
  - [Tab 1: PDF 提取](#tab-1-pdf-提取)
  - [Tab 2: 全流程精读](#tab-2-全流程精读)
  - [Tab 3: 批量处理](#tab-3-批量处理)
  - [Tab 4: 智能文献筛选](#tab-4-智能文献筛选)
  - [Tab 5: MD 文件精读](#tab-5-md-文件精读)
- [输出目录结构](#输出目录结构)
- [命令行用法](#命令行用法)
- [常见问题排查](#常见问题排查)

---

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 (推荐)、Linux、macOS |
| Python | 3.10 及以上 |
| 内存 | 建议 8 GB 以上 |
| 网络 | 需要访问 DeepSeek API（国内可直连） |
| 磁盘 | 每篇论文产出约 200KB-2MB 的 Markdown 文件 |

---

## 环境配置

### 1. Python 虚拟环境

如果还没有创建虚拟环境，在项目根目录执行：

```powershell
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

激活后终端提示符前会出现 `(venv)` 标记。

### 2. 安装依赖

```powershell
# 安装全部依赖（含 gradio）
pip install -r requirements.txt
```

`requirements.txt` 中包含以下主要包：

| 包名 | 用途 |
|------|------|
| `gradio` | Web GUI 界面框架 |
| `openai` | 调用 DeepSeek API（兼容 OpenAI SDK） |
| `python-dotenv` | 从 `.env` 文件加载环境变量 |
| `pdfplumber` / `pypdf` / `PyPDF2` | PDF 文本提取（Legacy 回退方案） |
| `pdfminer.six` | PDF 解析辅助 |
| `pandas` / `openpyxl` | 数据处理与 Excel 输出 |
| `pyyaml` | YAML 前置元数据解析 |
| `json_repair` | 修复 LLM 返回的格式异常 JSON |
| `tqdm` | 命令行进度条 |
| `spacy` / `nltk` | 自然语言处理（分词等） |

### 3. 配置环境变量 (.env)

在项目根目录创建 `.env` 文件。该文件不会被 Git 跟踪（已在 `.gitignore` 中排除）。

下面给出完整的 `.env` 模板，你可以复制后修改：

```ini
# ============================================================
# Deep Reading Agent 环境变量配置
# ============================================================

# ------ 必需 ------

# DeepSeek API 密钥（必须配置，否则所有分析功能不可用）
# 申请地址：https://platform.deepseek.com/
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ------ 推荐 ------

# PaddleOCR 远程 API（推荐配置，提取质量远优于 pdfplumber）
# 如不配置，系统自动回退到 pdfplumber 提取
PADDLEOCR_REMOTE_URL=https://your-paddleocr-api-endpoint
PADDLEOCR_REMOTE_TOKEN=your-paddleocr-token

# ------ 可选 ------

# DeepSeek API 地址（通常无需修改，国内可直连默认地址）
# DEEPSEEK_BASE_URL=https://api.deepseek.com

# Qwen VL (通义千问视觉) API 密钥
# 用于从 PDF 首页图像中提取论文标题/作者/期刊/年份
# 如不配置，元数据注入阶段将跳过 PDF 视觉提取
# QWEN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Kimi (Moonshot AI) API（仅旧版 Legacy 分析器使用，GUI 不需要）
# OPENAI_API_KEY=sk-your-kimi-key
# OPENAI_BASE_URL=https://api.moonshot.cn/v1
# OPENAI_MODEL=moonshot-v1-auto
```

---

## 环境变量详解

### 必需变量

| 变量名 | 说明 | 使用场景 |
|--------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek 平台的 API 密钥 | 全部核心功能：7步深度阅读、论文分类、Dataview 摘要提取、元数据注入中的子章节摘要、智能文献筛选 AI 评估 |

**如何获取**：

1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/)
2. 注册并登录
3. 在「API Keys」页面创建新密钥
4. 复制以 `sk-` 开头的完整密钥

**使用的模型**：

| 模型 | 用途 | 调用位置 |
|------|------|----------|
| `deepseek-reasoner` | 7 步深度阅读分析（模拟 Acemoglu 教授视角的深度推理） | `deep_reading_steps/common.py` |
| `deepseek-chat` | 论文分类 (QUANT/QUAL/IGNORE)、Dataview 摘要、元数据摘要、文献筛选 AI 评估 | `smart_scholar_lib.py`、`inject_dataview_summaries.py`、`inject_obsidian_meta.py`、`smart_literature_filter.py` |

**费用提示**：一篇 20 页论文的完整精读（7 步分析 + 元数据注入）大约消耗 15-30 万 token。`deepseek-reasoner` 的推理 token 价格高于 `deepseek-chat`，请注意余额。

### 推荐变量

| 变量名 | 说明 | 使用场景 |
|--------|------|----------|
| `PADDLEOCR_REMOTE_URL` | PaddleOCR 远程 Layout Parsing API 的端点地址 | Tab 1 PDF 提取、Tab 2/3 流水线的第一步 |
| `PADDLEOCR_REMOTE_TOKEN` | PaddleOCR API 的访问令牌 | 与 `PADDLEOCR_REMOTE_URL` 配套使用 |

**PaddleOCR 与 pdfplumber 的区别**：

| 特性 | PaddleOCR (推荐) | pdfplumber (回退) |
|------|-------------------|-------------------|
| 表格识别 | 自动转 HTML/Markdown 表格 | 不支持 |
| 公式识别 | 自动转 LaTeX | 不支持 |
| 版面分析 | 自动检测多栏、标题层级 | 无版面分析，纯文本拼接 |
| 中文 OCR | 高精度 | 依赖 PDF 内嵌字体，扫描件无法处理 |
| 图表提取 | 支持（可选） | 不支持 |
| API 依赖 | 需要远程 API | 本地处理，无需网络 |

**如果不配置 PaddleOCR**：系统自动回退到 pdfplumber，仍可正常工作，但提取质量会下降（尤其对含表格、公式、扫描件的论文）。

### 可选变量

| 变量名 | 说明 | 使用场景 |
|--------|------|----------|
| `DEEPSEEK_BASE_URL` | 自定义 DeepSeek API 地址 | 仅在使用代理或私有部署时需要修改，默认 `https://api.deepseek.com` |
| `QWEN_API_KEY` | 通义千问视觉 (Qwen VL Plus) 的 API 密钥 | 元数据注入阶段，从 PDF 首页截图中用视觉模型提取论文标题、作者、期刊、年份。不配置则跳过此步骤，使用文本解析方式提取元数据 |
| `OPENAI_API_KEY` | Kimi (Moonshot) 的 API 密钥 | 仅旧版 Legacy 分析器使用（`kimi_segment_raw_md.py`、`llm_analyzer.py`），GUI 主流程不需要 |
| `OPENAI_BASE_URL` | Kimi API 地址 | 同上，默认 `https://api.moonshot.cn/v1` |
| `OPENAI_MODEL` | Kimi 模型名称 | 同上，默认 `moonshot-v1-auto` |

---

## 启动 GUI

### 方式一：一键启动（推荐）

双击项目根目录下的 `start.bat` 即可自动完成所有准备工作：

1. **检测 Python** — 自动查找系统中的 Python 3（支持 `py`、`python`、`python3`）
2. **创建虚拟环境** — 如果 `venv/` 目录不存在，自动执行 `python -m venv venv`
3. **安装依赖** — 检测 `requirements.txt` 是否有更新，自动执行 `pip install`
4. **配置环境变量** — 如果 `.env` 文件不存在或未配置 `DEEPSEEK_API_KEY`，自动弹出图形化配置对话框（`setup_env.py`）
5. **启动 GUI** — 运行 `app.py` 并自动打开浏览器

配置对话框支持以下操作：
- 填写所有 API 密钥（密码字段默认遮罩，可切换显示）
- **Save & Start**：保存配置并继续启动
- **Skip**：跳过配置直接启动（之后可手动编辑 `.env`）
- **Cancel**：取消启动

### 方式二：手动启动

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
python app.py
```

```bash
# Linux / macOS
source venv/bin/activate
python app.py
```

### 启动输出

启动后终端会输出：

```
Running on local URL: http://127.0.0.1:7860
```

在浏览器中打开该地址即可使用。

页面顶部会显示当前环境状态，例如：

```
Environment: DeepSeek API: Configured | PaddleOCR API: Not configured (will use pdfplumber fallback) | Qwen Vision: Not configured
```

如果看到 `DeepSeek API: Missing`，说明 `.env` 文件未正确配置，所有分析功能将无法使用。

---

## 界面功能说明

### Tab 1: PDF 提取

**功能**：将单个 PDF 文件提取为结构化 Markdown 文件。

**左栏（参数）**：

| 控件 | 说明 | 默认值 |
|------|------|--------|
| Upload PDF | 上传一个 PDF 文件 | - |
| Output Directory | 输出目录（相对于项目根目录） | `paddleocr_md` |
| Table Recognition | 启用表格识别，自动转 Markdown 表格 | 开启 |
| Formula Recognition | 启用公式识别，自动转 LaTeX | 开启 |
| Chart Parsing | 启用图表解析（速度较慢） | 关闭 |
| Orientation Correction | 启用文档方向矫正（针对扫描件） | 关闭 |
| Download Images | 下载论文中的图片 | 关闭 |
| Pages per Batch | 每次 API 调用处理的最大页数 | 10 |
| Disable Fallback | 禁用 pdfplumber 自动回退（PaddleOCR 失败时直接报错） | 关闭 |
| Force pdfplumber | 跳过 PaddleOCR，强制使用 pdfplumber 提取 | 关闭 |
| **Start Extraction** | 开始提取 | - |

**右栏（结果）**：

| 控件 | 说明 |
|------|------|
| Extraction Log | 实时滚动的提取日志 |
| Markdown Preview | 提取结果的 Markdown 预览（前 10000 字符） |
| Metadata (JSON) | 提取到的元数据（标题、摘要、关键词等） |
| Download Result | 生成的 `.md` 文件，可直接下载 |

**所需环境变量**：
- PaddleOCR 模式：`PADDLEOCR_REMOTE_URL` + `PADDLEOCR_REMOTE_TOKEN`
- pdfplumber 模式：无需任何环境变量

### Tab 2: 全流程精读

**功能**：对单篇论文执行从提取到元数据注入的完整 5 阶段流水线。

**5 个阶段**：

| 阶段 | 内容 | 调用方式 | 所需环境变量 |
|------|------|----------|--------------|
| 1. 提取 | PDF 转 Markdown | 直接 import `paddleocr_pipeline` | `PADDLEOCR_REMOTE_URL`（可选） |
| 2. 深度阅读 | 7 步 Acemoglu 模式分析 | 直接 import `deep_reading_steps` | `DEEPSEEK_API_KEY` |
| 3. 补充检查 | 检查缺失章节并补充 | subprocess 调用 `run_supplemental_reading.py` | `DEEPSEEK_API_KEY` |
| 4. Dataview 摘要 | 提取结构化摘要字段 | subprocess 调用 `inject_dataview_summaries.py` | `DEEPSEEK_API_KEY` |
| 5. 元数据注入 | 注入 Obsidian 前置元数据和双向链接 | subprocess 调用 `inject_obsidian_meta.py` | `DEEPSEEK_API_KEY`、`QWEN_API_KEY`（可选） |

**7 步深度阅读详解**（阶段 2）：

| 步骤 | 分析维度 | 输出文件 |
|------|----------|----------|
| Step 1 | Overview（研究概览） | `1_Overview.md` |
| Step 2 | Theory（理论框架） | `2_Theory.md` |
| Step 3 | Data（数据与样本） | `3_Data.md` |
| Step 4 | Variables（变量定义） | `4_Variables.md` |
| Step 5 | Identification（识别策略） | `5_Identification.md` |
| Step 6 | Results（实证结果） | `6_Results.md` |
| Step 7 | Critique（批判性评价） | `7_Critique.md` |

最终合并为 `Final_Deep_Reading_Report.md`。

**左栏**：

| 控件 | 说明 |
|------|------|
| Upload PDF | 上传 PDF 文件 |
| Extraction Method | 选择 PaddleOCR 或 Legacy (pdfplumber) |
| **Start Deep Reading** | 开始全流程 |
| **Stop** | 在当前阶段结束后取消 |

**右栏**：

| 控件 | 说明 |
|------|------|
| Current Stage | 当前正在执行的阶段 |
| Pipeline Log | 完整运行日志（实时更新） |
| Final Report Preview | 最终报告的 Markdown 预览 |
| Results Directory | 结果目录路径 |

### Tab 3: 批量处理

**功能**：对一个文件夹中的所有 PDF 进行自动分类（QUANT/QUAL/IGNORE）和路由分析。

**处理流程**：

```
扫描文件夹 → 逐个 PDF:
  ├─ MD5 去重检查（跳过已处理）
  ├─ 提取（PDF → Markdown）
  ├─ AI 分类（QUANT / QUAL / IGNORE）
  ├─ QUANT → 7 步深度阅读 + 元数据注入
  ├─ QUAL  → 4 层金字塔分析 + 元数据提取
  └─ IGNORE → 跳过（非学术内容）
```

**左栏**：

| 控件 | 说明 |
|------|------|
| PDF Folder Path | 包含 PDF 的文件夹路径（支持递归扫描子目录） |
| **Validate Path** | 验证路径并统计 PDF 数量 |
| Folder Status | 显示验证结果 |
| Skip Already Processed | 跳过已处理的文件（基于 MD5 哈希去重） |
| **Start Batch Processing** | 开始批量处理 |
| **Stop** | 取消 |

**右栏**：

| 控件 | 说明 |
|------|------|
| Progress | 进度表格（文件名 / 类型 / 状态 / 耗时） |
| Current Log | 当前正在处理的文件的日志 |
| Overall Progress | 总体统计（完成/跳过/失败数量） |

**所需环境变量**：`DEEPSEEK_API_KEY`（必需）、`PADDLEOCR_REMOTE_URL`（推荐）

### Tab 4: 智能文献筛选

**功能**：解析 Web of Science (WoS) 或 CNKI 导出的文献列表文件，可选启用 AI 评估对每篇文献与研究主题的相关性打分，输出排序后的 Excel 表格。

**典型工作流**：

```
WoS/CNKI 检索数百篇 → Tab 4 筛选出高相关文献 → 下载 PDF → Tab 2 或 Tab 3 精读
```

**左栏（参数）**：

| 控件 | 说明 | 默认值 |
|------|------|--------|
| Upload WoS/CNKI Export File | 上传 WoS 的 `savedrecs.txt` 或 CNKI 导出的文本文件 | - |
| AI Evaluation Mode | AI 评估模式：None（不启用）、explorer（广泛探索）、reviewer（严格评审）、empiricist（实证导向） | None |
| Research Topic | 研究主题，启用 AI 模式时必填 | - |
| Min Year | 仅保留该年份及之后的文献（留空则不过滤） | - |
| Keywords Filter | 按标题/摘要关键词过滤，逗号分隔，多个词之间为 OR 关系 | - |
| AI Evaluation Limit | 限制 AI 评估的文献数量，0 表示全部评估 | 0 |
| **Start Filtering** | 开始筛选 | - |

**右栏（结果）**：

| 控件 | 说明 |
|------|------|
| Log | 实时日志（解析进度、过滤结果、AI 评估进度） |
| Results | 筛选结果表格（标题、作者、期刊、年份、AI 评分等） |
| Download Excel | 完整结果的 `.xlsx` 文件下载 |

**AI 评估模式对比**：

| 模式 | 适用场景 | 评估侧重 |
|------|----------|----------|
| `explorer` | 初步探索，不确定方向 | 广泛筛选，关注主题相关性 |
| `reviewer` | 系统性综述，需要全面覆盖 | 严格评审，关注方法论质量 |
| `empiricist` | 实证研究，寻找可复制的方法 | 关注数据、模型、识别策略 |

**支持的输入格式**：

| 来源 | 导出方式 | 识别特征 |
|------|----------|----------|
| Web of Science | 导出 → 纯文本 | 文件以 `FN Clarivate` 开头 |
| CNKI (知网) | 导出 → 自定义文本 | 文件包含 `SrcDatabase-` 或 `Title-题名` |

**所需环境变量**：
- 仅解析和关键词过滤：无需任何环境变量
- AI 评估模式：需要 `DEEPSEEK_API_KEY`

### Tab 5: MD 文件精读

**功能**：跳过 PDF→MD 提取步骤，直接对已有的 Markdown 文件进行精读分析。适用于已经通过 Tab 1 提取好 MD、或从其他渠道获得 MD 文件的场景。

**两种模式**：

| 模式 | 说明 |
|------|------|
| 单文件 | 上传一个 `.md` 文件，执行精读，完成后在右栏预览最终报告 |
| 文件夹 | 输入包含 `.md` 文件的文件夹路径，批量精读所有 MD 文件 |

**自动检测与路由**：

```
上传/扫描 MD 文件 → 逐个处理:
  ├─ AI 分类（QUANT / QUAL / IGNORE）
  ├─ QUANT → 7 步深度阅读 + 元数据注入
  ├─ QUAL  → 4 层金字塔分析 + 元数据提取
  └─ IGNORE → 跳过
```

**左栏（参数）**：

| 控件 | 说明 |
|------|------|
| 模式 | 单文件 或 文件夹（切换后显示对应的输入控件） |
| 上传 MD 文件 | 单文件模式：上传一个 `.md` 文件 |
| MD 文件夹路径 | 文件夹模式：输入包含 MD 文件的目录路径 |
| **验证路径** | 文件夹模式：检查路径并统计 MD 文件数量 |
| 文件夹状态 | 验证结果显示 |
| 跳过已处理 | 如果结果目录中已存在最终报告，则跳过该文件 |
| **开始精读** | 开始处理 |
| **停止** | 取消 |

**右栏（结果）**：

| 控件 | 说明 |
|------|------|
| 进度 | 进度表格（文件名 / 类型 / 状态 / 耗时） |
| 当前日志 | 实时运行日志 |
| 总体进度 | 总体统计（完成/跳过/失败） |
| 最终报告预览 | 单文件模式完成后预览最终报告内容 |
| 下载结果 | 最终报告文件下载 |

**所需环境变量**：`DEEPSEEK_API_KEY`（必需）

---

## 输出目录结构

所有输出目录均已在 `.gitignore` 中排除：

```
项目根目录/
├── _gui_uploads/           # GUI 上传文件的临时存放目录
├── paddleocr_md/           # 提取阶段输出（PaddleOCR / pdfplumber Markdown）
├── deep_reading_results/   # 计量经济学 (QUANT) 分析结果
│   └── {论文名}/
│       ├── semantic_index.json
│       ├── section_routing.md
│       ├── 1_Overview.md
│       ├── 2_Theory.md
│       ├── 3_Data.md
│       ├── 4_Variables.md
│       ├── 5_Identification.md
│       ├── 6_Results.md
│       ├── 7_Critique.md
│       └── Final_Deep_Reading_Report.md
├── social_science_results_v2/  # 社会科学 (QUAL) 分析结果
│   └── {论文名}/
│       ├── L1_Context.md
│       ├── L2_Theory.md
│       ├── L3_Logic.md
│       ├── L4_Value.md
│       └── {论文名}_Full_Report.md
└── processed_papers.json   # 批量处理状态追踪（MD5 去重数据库）
```

**Obsidian 用户**：将 `deep_reading_results/` 或 `social_science_results_v2/` 文件夹拖入 Obsidian Vault 即可使用。所有 `.md` 文件包含 YAML 前置元数据，支持 Dataview 插件查询。

---

## 命令行用法

智能文献筛选功能已集成到 GUI 的 Tab 4 中。如果你更习惯命令行操作，也可以直接调用 `smart_literature_filter.py`：

### 用法

```powershell
# 基础用法：解析 WoS 导出文件，生成 Excel 汇总
python smart_literature_filter.py "savedrecs.txt" --output "summary.xlsx"

# 按年份和关键词预过滤
python smart_literature_filter.py "savedrecs.txt" --min_year 2015 --keywords "DID" "regression"

# 启用 AI 评估（需要 DEEPSEEK_API_KEY）
python smart_literature_filter.py "savedrecs.txt" \
    --ai_mode reviewer \
    --topic "数字经济对制造业全要素生产率的影响" \
    --output "screened.xlsx"

# 限制 AI 评估数量（节省 token）
python smart_literature_filter.py "savedrecs.txt" \
    --ai_mode explorer \
    --topic "ESG and firm value" \
    --limit 100 \
    --output "top100_screened.xlsx"
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `input_file` | WoS 的 `savedrecs.txt` 或 CNKI 导出的文本文件 |
| `--output` | 输出 Excel 路径（默认 `literature_summary.xlsx`） |
| `--min_year` | 仅保留该年份及之后的文献 |
| `--keywords` | 按标题/摘要关键词过滤（多个词之间为 OR 关系） |
| `--ai_mode` | AI 评估模式：`explorer` / `reviewer` / `empiricist`（详见 Tab 4 说明） |
| `--topic` | 研究主题（使用 `--ai_mode` 时必须指定） |
| `--limit` | 限制 AI 评估的文献数量（0 表示全部） |

---

## 常见问题排查

### Q: 启动时报 `ModuleNotFoundError: No module named 'gradio'`

确认已在虚拟环境中安装依赖：

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Q: 页面顶部显示 `DeepSeek API: Missing`

检查 `.env` 文件：

1. 文件是否在项目根目录（与 `app.py` 同级）
2. 密钥是否正确（以 `sk-` 开头）
3. 等号两边不要有空格
4. 不要用引号包裹密钥值

正确写法：
```ini
DEEPSEEK_API_KEY=sk-abc123def456
```

错误写法：
```ini
DEEPSEEK_API_KEY = "sk-abc123def456"    # 不要加空格和引号
```

### Q: PDF 提取后内容为空或乱码

- 如果是扫描件 PDF（图片型），必须配置 PaddleOCR，pdfplumber 无法处理
- 尝试勾选 "Orientation Correction"（方向矫正）
- 尝试调小 "Pages per Batch"（降低到 5）

### Q: 提取阶段报 `ConnectionError` 或 `TimeoutError`

- 这表示 PaddleOCR API 不可达
- 检查 `PADDLEOCR_REMOTE_URL` 是否正确
- 如果不需要 PaddleOCR，取消勾选或不配置相关变量，系统会自动使用 pdfplumber

### Q: 深度阅读过程中某个 Step 报错或输出为空

- 这通常是 DeepSeek API 调用失败（网络波动或 token 余额不足）
- 检查 DeepSeek 平台余额
- 查看 Pipeline Log 中的具体错误信息
- 可以重新运行，系统不会覆盖已生成的 `semantic_index.json`

### Q: 批量处理时如何跳过已完成的文件

- 勾选 "Skip Already Processed"（默认开启）
- 系统通过 `processed_papers.json` 中的 MD5 哈希判断文件是否已处理
- 如需强制重新处理所有文件，删除项目根目录下的 `processed_papers.json`

### Q: 停止按钮点了没反应

- 取消机制在**阶段之间**检查，当前阶段的 API 调用会等待完成
- 如果某个 DeepSeek API 调用耗时过长（特别是 `deepseek-reasoner`），需要等它返回后才能停止
- 如需立即终止，直接在终端按 `Ctrl+C`

### Q: 端口 7860 被占用

在 `app.py` 最后一行修改端口号，或通过命令行指定：

```python
app.launch(server_name="127.0.0.1", server_port=7861)  # 改为其他端口
```

### Q: 想让局域网内其他设备访问

修改 `app.py` 中的 `server_name`：

```python
app.launch(server_name="0.0.0.0", server_port=7860)  # 监听所有网络接口
```

然后通过 `http://你的IP:7860` 访问。
