# 学术论文深度分析与知识管理工作流 (Deep Reading Workflow)

本文档总结了从原始 PDF 文档到结构化知识库的全流程解决方案。该方案集成了 PDF 转换、批量信息提取、深度精读分析以及 Obsidian 知识库构建等功能。

## 1. 核心功能模块

### 1.0 智能文献筛选 (Smart Literature Filter) - **New!**
从 Web of Science 或 CNKI 导出的成百上千篇文献列表中，利用 AI 进行“专家级”预筛选，快速定位高价值论文。
- **支持格式**：WoS (`savedrecs.txt`) 和 CNKI (`Refworks` 格式)。
- **三种模式**：`explorer` (入门), `reviewer` (综述), `empiricist` (实证)。
- **输出**：带 AI 评分、中文摘要、推荐理由的 Excel 表格。

### 1.1 PDF 转 Markdown (PDF Extraction)
将原始 PDF 文档转换为适合 LLM 处理的 Markdown 格式，包含两种模式：
- **Raw Extraction**: 直接提取文本，保留原始排版结构。
- **Segmentation**: 基于论文结构的智能分块（引言、理论、实证等）。

### 1.2 批量信息提取与制表 (Batch Analysis & Tabulation)
对文件夹中的所有论文进行“Acemoglu 级”的核心要素提取，并生成 Excel 汇总表。
- **提取维度**：全景扫描、理论基础、数据来源、变量定义、识别策略、结果与不足、Stata 代码。
- **输出**：`xlsx` 汇总表 + 单篇 `md` 报告。

### 1.3 深度精读 (Deep Reading Agent)
针对单篇论文进行深入的、分章节的专家级研读。
- **流程**：将论文切分为 7 个部分（Overview, Theory, Data, Vars, Identification, Results, Critique），分别调用 LLM 进行深度解析。
- **输出**：包含 7 个分部文档和 1 个最终汇总报告 (`Final_Deep_Reading_Report.md`)。

### 1.4 Obsidian 知识库构建 (Knowledge Base Integration)
自动为生成的 Markdown 文档添加元数据和双向链接，使其直接成为 Obsidian 可用的知识节点。
- **元数据**：标题、作者、期刊、年份、研究主题、核心变量等（YAML Frontmatter）。
- **链接**：分部文档与总报告之间的双向导航链接。

### 1.5 参考文献抽取与引用追踪 (References & Citation Tracing)
将“参考文献表”从论文中结构化抽取，并反向定位每条参考文献在正文中的引用位置（含上下文摘录）。
- **参考文献抽取产出**：`references\*_references.xlsx`
- **引用追踪产出**：
  - `references\*_references_citation_trace.md`
  - `references\*_references_with_citations.xlsx`

### 1.6 社科文献深度阅读 (Social Science Scholar)
专为管理学、社会学设计，采用“四层金字塔”模型（L1背景、L2理论、L3逻辑、L4价值）进行分层提取。
- **流程**: PDF -> 智能切分 -> 4层深度分析 -> 生成全景报告 & Excel -> 注入双向链接。
- **产出**: 4个分层 MD、1个全景 MD、1个汇总 Excel。

### 1.7 智能科研助理 (Smart Scholar)
集成式入口，通过 AI 自动判断论文类型并分发任务。
- **输入**: PDF 文件或文件夹（支持递归扫描）。
- **分类**: 
  - `QUANT` (定量): 实证研究、计量回归。
  - `QUAL` (定性): 案例研究、文献综述 (Reviews)、理论文章。
  - `IGNORE` (忽略): 非研究文档（卷首语、书评、目录等）。
- **路由**: 自动调用对应的深度阅读 Skill。当分类不确定时，默认回退到 `QUAL`。

### 1.8 状态管理与去重 (State Manager)
提供基于内容哈希的持久化去重能力。
- **核心逻辑**: 计算文件 MD5 并查询 `processed_papers.json` 账本。
- **优势**: 即使文件名变更或文件移动，只要内容不变，系统就能识别并跳过，避免重复消耗 Token。

### 1.9 智能合成修复 (Smart Synthesis)
在合成 Final Report 时，自动清洗分步文件中的冗余元数据（YAML Frontmatter）和导航链接，确保最终报告格式整洁。

---

## 2. 详细使用指南

### 环境准备
确保已安装 Python 环境及所需依赖，并配置好 `.env` 文件（包含 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY`）。

```powershell
# 激活虚拟环境 (Windows)
.\venv\Scripts\Activate.ps1
```

### 步骤零：文献初筛 (Literature Filtering)

**功能**：在下载 PDF 之前，先对文献列表进行 AI 筛选。

**命令**：
```powershell
# 1. 筛选 Web of Science 导出文件 (英文)
# 模式: reviewer (适合写综述), topic: 研究主题
python smart_literature_filter.py "savedrecs.txt" --ai_mode reviewer --topic "Digital Economy" --output "wos_screened.xlsx"

# 2. 筛选 CNKI 导出文件 (中文)
# 模式: empiricist (寻找严谨实证), topic: 研究主题
python smart_literature_filter.py "cnki_export.txt" --ai_mode empiricist --topic "人工智能与农业" --output "cnki_screened.xlsx"
```

**产出**：
- Excel 文件：包含 AI 打分 (`score`)、中文标题 (`title_cn`)、中文摘要 (`abstract_cn`) 和推荐理由 (`reason`)。
- **自适应处理**：英文文献会自动翻译；中文文献会自动提炼为极简摘要（<20字）。

### 步骤一：PDF 转换 (PDF to Markdown)

**功能**：将 PDF 转换为 Raw Markdown。

**命令**：
```powershell
# 提取单个 PDF
python anthropic_pdf_extract_raw.py "path\to\paper.pdf" --out_dir "pdf_raw_md"

# (可选) 进一步分块
python kimi_pdf_raw_segmenter.py "pdf_raw_md\paper_raw.md" --out_dir "pdf_segmented_md"
```

### 步骤二：批量信息提取 (Batch Analysis)

**功能**：快速扫描文件夹下的所有 PDF/MD，提取关键信息生成 Excel 表格。

**命令**：
```powershell
# 使用 PowerShell 封装脚本 (推荐)
.\run_analyzer.ps1 -InputPath "d:\code\skill\pdf_raw_md" -Output "analysis_results.xlsx"

# 或直接调用 Python
python main.py "d:\code\skill\pdf_raw_md" --output "analysis_results.xlsx"
```

**产出**：
- `analysis_results.xlsx`: 包含所有论文核心要素的对比表。
- `reports/`: 每篇论文的独立 Markdown 报告。

### 步骤三：深度精读 (Deep Reading)

**功能**：对特定论文进行全流程深度精读（包含提取、分块、精读、补缺）。

**场景 A：单篇精读**
```powershell
# 自动执行全流程
python run_full_pipeline.py "path\to\paper.pdf"
```

**场景 B：批量精读 (智能去重与递归)**
```powershell
# 自动扫描文件夹（含子目录），跳过内容哈希已记录的论文
.\run_batch_pipeline.ps1 "d:\code\skill\pdf"
```

**产出**：
- 在 `deep_reading_results/` 下生成以论文名命名的文件夹。
- 包含 `1_Overview.md` 到 `7_Critique.md` 及 `Final_Deep_Reading_Report.md`。
- 状态更新至 `processed_papers.json`。

### 步骤四：Obsidian 元数据注入 (Metadata Injection)

**功能**：为精读结果添加 Dataview 可读的元数据和导航链接。通常包含在“步骤三”的自动化流程中，但也可手动运行修复。

**命令**：
```powershell
# 1. 提取摘要元数据 (Dataview Summaries)
.\run_dataview_summarizer.ps1 "d:\code\skill\deep_reading_results"

# 2. 注入基础元数据 (Title/Author) 和导航
python inject_obsidian_meta.py "source_raw.md" "target_folder"
```

### 步骤五：（可选）参考文献抽取与引用追踪

**功能**：从 `*_segmented.md` 中抽取参考文献列表，并反向追踪正文引用位置。

**命令**：
```powershell
# 1) 抽取参考文献（输出到 references\*_references.xlsx）
.\run_reference_extractor.ps1 "pdf_segmented_md\paper_segmented.md"

# 2) 引用追踪（输出 MD 追踪日志 + 增强版 Excel）
.\run_citation_tracer.ps1 "pdf_segmented_md\paper_segmented.md" "references\paper_references.xlsx"
```

### 步骤六：社科文献深度阅读 (Social Science Scholar)

**功能**：针对社科类文献（案例/定性/组态）进行“四层金字塔”深度分析。自动完成“切分-分析-整合-链接”全流程。

**命令**：
```bash
# 推荐：使用 Python 脚本（需在脚本中配置 KEYWORDS 筛选文献）
python run_social_science_task.py
```

**产出**：
- 文件夹 `social_science_results_v2/`
- **Excel**: `Social_Science_Analysis_4Layer.xlsx`
- **Docs**: 每篇论文 5 个 MD 文件（L1-L4 分层报告 + Full Report），均包含双向链接和元数据。

### 步骤七：智能科研助理 (Smart Scholar)

**功能**：一键式“傻瓜”操作，自动完成 PDF 转换、切分、分类和深度阅读。

**命令**：
```bash
# 分析单个文件
python smart_scholar.py "path/to/paper.pdf"

# 分析整个目录
python smart_scholar.py "path/to/pdf_folder"
```

---

## 3. 常用脚本清单

| 脚本名 | 功能描述 | 核心参数 |
| :--- | :--- | :--- |
| `anthropic_pdf_extract_raw.py` | PDF -> Raw Markdown | `input_pdf`, `--out_dir` |
| `run_analyzer.ps1` | 批量提取信息制表 | `-InputPath`, `-Output` |
| `run_full_pipeline.py` | 单篇全流程精读 | `pdf_path` |
| `run_batch_pipeline.ps1` | 批量全流程精读 | `pdf_dir` |
| `run_dataview_summarizer.ps1` | 注入内容摘要元数据 | `target_dir` |
| `run_supplemental_reading.py` | 报告查漏补缺与整合 | `report_path`, `--regenerate` |
| `extract_references.py` | 从分段论文抽取参考文献 | `segmented_md`, `--out_xlsx` |
| `run_reference_extractor.ps1` | 抽取参考文献（封装） | `segmented_md` |
| `citation_tracer.py` | 引用追踪（反向定位正文引用） | `segmented_md`, `references_xlsx` |
| `run_citation_tracer.ps1` | 引用追踪（封装） | `segmented_md`, `references_xlsx` |
| `run_social_science_task.py` | 社科文献深度阅读全流程 | `KEYWORDS` (in script) |
| `social_science_analyzer.py` | 社科文献分析核心逻辑 | N/A |
| `state_manager.py` | 状态管理与哈希去重 | N/A |
| `fix_social_science_metadata.py` | 社科报告元数据修复 | `--target`, `--force` |

## 4. 运维与修复 (Maintenance)

### 4.1 元数据批量修复
当旧的社科分析报告缺失元数据（如 Journal, Year）时，可使用此脚本进行无损修复（无需重跑 AI 分析）。

```bash
# 自动扫描 social_science_results_v2 并修复元数据
python fix_social_science_metadata.py --force
```

### 4.2 状态管理
查看或重置处理状态账本。

- **账本位置**: `processed_papers.json`
- **操作**: 若需强制重跑某篇论文，可从 JSON 中删除对应条目，或直接删除该文件（将触发全量重跑，慎用）。

## 5. 最佳实践 (Best Practices)

1.  **先粗后细**：先用 **步骤二 (Batch Analysis)** 快速扫描一批文献，生成 Excel 表格筛选出值得精读的高价值论文。
2.  **重点突破**：对筛选出的重点论文，使用 **步骤三 (Deep Reading)** 进行深度研读。
3.  **知识管理**：将 `deep_reading_results` 文件夹作为 Obsidian 的一个 Vault 或子文件夹，利用 Dataview 插件进行跨文献检索和综述撰写。

### Obsidian Dataview 示例
在 Obsidian 中使用以下代码查询所有精读过的论文主题：

```dataview
TABLE research_theme, findings
FROM #deep-reading
WHERE file.name != "Final_Deep_Reading_Report"
SORT file.name ASC
```
