# Deep Reading Agent System

这是一个专为学术论文深度精读设计的自动化 Agent 系统。它模拟了顶级计量经济学家的阅读与分析流程，将一篇 PDF 论文转化为结构化、深度解析且适合 Obsidian 知识管理的 Markdown 报告。

## 核心工作流 (Pipeline)

整个系统由五个核心步骤（Skills）串联而成：

```mermaid
graph TD
    A[原始 PDF] -->|Step 1: 格式转换| B(逐页 Raw Markdown)
    B -->|Step 2: 批量分析| F(Excel 汇总表)
    B -->|Step 3: 结构化切分| C(分段 Segmented Markdown)
    C -->|Step 4: 深度精读| D(分步深度报告 Step Reports)
    D -->|Step 5: 知识图谱化| E(Obsidian Ready 知识库)

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style F fill:#ff9,stroke:#333,stroke-width:2px
    style E fill:#9f9,stroke:#333,stroke-width:2px
```

### 1. 格式转换 (PDF to Raw Markdown)
- **目标**: 将 PDF 转换为大模型可读的纯文本，同时保留页码信息以便定位。
- **工具**: `anthropic-pdf-extract` (基于 `pdfplumber`/`pypdf`)
- **输出**: `*_raw.md`

### 2. 批量分析与制表 (Batch Analysis)
- **目标**: 快速扫描文件夹，提取核心信息（主题、变量、结论、Stata代码）生成 Excel 对比表。
- **工具**: `academic-pdf-analyzer` (LLM-Enhanced)
- **输出**: `analysis_results.xlsx` 及 Markdown 简报。

### 3. 结构化切分 (Structure Segmentation)
- **目标**: 还原论文逻辑结构（Introduction, Data, Model 等）。
- **工具**: `kimi-pdf-raw-segmenter`
- **输出**: `*_segmented.md`

### 4. 深度精读 (Deep Reading & Analysis)
- **目标**: 像 Daron Acemoglu 级别的审稿人一样，对论文进行批判性分析。
- **工具**: `deep-reading-expert`
- **逻辑**: 分步处理（全景扫描 -> 理论 -> 数据 -> 变量 -> 识别 -> 结果 -> 批判）。
- **输出**: `Final_Deep_Reading_Report.md` 及各分步报告。

### 5. 知识图谱化 (Obsidian Integration)
- **目标**: 无缝接入 Obsidian，实现元数据检索与双向链接。
- **工具**: `obsidian-metadata-injector` & `obsidian-dataview-summarizer`
- **输出**: 包含 YAML 头（含内容摘要）和导航链接的 Markdown 文件群。

## 快速开始

详细的使用指南和命令说明，请参阅 **[工作流手册 (Workflow Guide)](README_WORKFLOW.md)**。

### 核心命令速查

```powershell
# 1. 批量分析制表
.\run_analyzer.ps1 -InputPath "path/to/pdfs" -Output "results.xlsx"

# 2. 单篇全流程精读
python run_full_pipeline.py "paper.pdf"

# 3. 批量全流程精读 (跳过已读)
.\run_batch_pipeline.ps1 "path/to/pdfs"
```

## 目录结构

```
.
├── .trae/skills/               # Skill 定义文档
├── pdf_raw_md/                 # Step 1 产物
├── pdf_segmented_md/           # Step 3 产物
├── deep_reading_results/       # Step 4 & 5 产物 (最终报告)
├── deep_reading_steps/         # 精读子任务 Python 脚本
├── *.py / *.ps1                # 各步骤主控脚本
├── README_WORKFLOW.md          # 详细使用手册
└── requirements.txt
```
