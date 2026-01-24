# 社科文献深度阅读 Skill (Social Science Scholar)

本 Skill 专为管理学、社会学等社科领域的学术文献设计，采用“四层金字塔”模型进行深度情报提取。

## 1. 功能特点

- **分层提取**: 将深度阅读拆解为 4 个独立层级，确保信息的颗粒度与准确性。
  - **L1 基础情报**: 政策背景、现状数据、文章体裁。
  - **L2 理论探讨**: 核心构念界定、过往理论、本文框架。
  - **L3 核心逻辑**: 案例过程模型、实证因果组态、文献演进图谱。
  - **L4 价值升华**: 研究缺口、理论贡献、实践启示。
- **Obsidian 兼容**: 生成的所有 Markdown 文档均包含详细的 YAML Frontmatter，可直接被 Obsidian Dataview 索引。
- **中文输出**: 强制 AI 使用简体中文进行详细解读，降低阅读门槛。
- **结构化 Excel**: 自动汇总所有分析结果至 Excel 表格，便于文献横向对比。

## 2. 使用方法

### 2.1 准备工作
确保 `pdf` 文件夹中放入待分析的 PDF 文档。

### 2.2 运行分析
提供两种运行方式：

**方式 A: Python 脚本 (推荐)**
```bash
python run_social_science_task.py
```
*此脚本会自动处理 `pdf` 文件夹中的目标文献（需在脚本中配置关键词，默认包含本次任务的3篇文献）。*

**方式 B: PowerShell 脚本**
```powershell
.\run_social_science_batch.ps1
```

### 2.3 输出结果
结果保存在 `social_science_results_v2` 文件夹中：
- `Social_Science_Analysis_4Layer.xlsx`: 汇总表格。
- `[论文文件名]/`: 每篇论文的独立文件夹，包含：
  - `*_L1_Context.md`
  - `*_L2_Theory.md`
  - `*_L3_Logic.md`
  - `*_L4_Value.md`
  - `*_Full_Report.md` (全景整合报告)
  - 文档间包含双向链接 (`[[Link]]`)，支持在 L1-L4 与 Full Report 之间快速跳转。

## 3. 核心代码文件
- `social_science_analyzer.py`: 核心分析逻辑（Prompt 工程、分层提取）。
- `link_social_science_docs.py`: 文档双向链接注入工具（自动运行）。
- `deepseek_segment_raw_md.py`: 基于 LLM 的文档智能分块工具。
- `anthropic_pdf_extract_raw.py`: PDF 转 Markdown 工具。

## 4. 提取标准 (Schema)

| 层级 | 核心字段 | 说明 |
| :--- | :--- | :--- |
| **L1** | Policy Context | 具体的政策文件名称、年份、层级 |
| **L1** | Status Data | 关键统计数据（如 GEP 转化率、资金投入） |
| **L2** | Key Constructs | 核心概念及其原文定义 |
| **L3** | Process/Path | 案例的过程阶段或实证的路径组态 |
| **L4** | Implications | 对政策制定者的具体建议 |
