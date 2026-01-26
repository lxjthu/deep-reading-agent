# 当前已实现功能与代码映射

本文档基于对仓库 `D:\code\skill` 的代码扫描，总结**目前已经实现**的功能模块、入口脚本与关键代码文件（尽量以“代码中确实存在的入口/调用关系”为准，不做臆测）。

## 1. 总览

这个仓库实现了一个面向学术论文的“从 PDF 到精读知识库”的工具链，核心由三类能力组成：

- **文本获取**：PDF 文本抽取 → 原文逐页 Markdown →（可选）结构化分段 Markdown。
- **分析生成**：批量信息抽取（表格化）与“7 步深度精读”两条主线。
- **知识库落地**：对精读产物注入 Obsidian 可用的 YAML 元数据、Dataview 可查询摘要、双向导航链接。

## 2. 环境与配置

### 2.1 必要环境变量

`.env.example` 给出了当前代码实际读取的环境变量示例：[.env.example](file:///d:/code/skill/.env.example)

- `OPENAI_API_KEY`：用于 `OPENAI_BASE_URL` 指定的兼容 OpenAI SDK 的服务（常用为 Kimi/Moonshot）。
- `OPENAI_BASE_URL`：默认 `https://api.moonshot.cn/v1`。
- `OPENAI_MODEL`：默认 `moonshot-v1-auto`。
- `DEEPSEEK_API_KEY`：用于 DeepSeek（当前默认 base url 固定为 `https://api.deepseek.com`）。

### 2.2 不应被追踪的目录

仓库已有 `.gitignore`，用于避免将 PDF 原文与生成结果提交到 Git：[.gitignore](file:///d:/code/skill/.gitignore)

典型包括：`pdf/`、`reports/`、`deep_reading_results/`、`pdf_raw_md/`、`pdf_segmented_md/`、`references/` 等。

## 3. 主功能与入口脚本

### 3.1 批量“论文要素抽取”与 Excel 汇总

目标：扫描输入目录内 PDF，抽取论文核心要素（7 维框架）并写入 Excel，同时为每篇论文生成一份 Markdown 报告。

- 入口（Python CLI）：[main.py](file:///d:/code/skill/main.py)
  - 参数解析与主流程：`main()`：[main.py:L8-L162](file:///d:/code/skill/main.py#L8-L162)
  - 支持输入目录或单文件，接受 `.pdf`/`.md`：[main.py:L33-L45](file:///d:/code/skill/main.py#L33-L45)
- 运行封装（PowerShell）：[run_analyzer.ps1](file:///d:/code/skill/run_analyzer.ps1)
- 关键实现：
  - PDF 文本抽取：`PDFExtractor`：[extractor.py](file:///d:/code/skill/extractor.py)
    - `extract_content()` / `_clean_text()`：[extractor.py:L8-L66](file:///d:/code/skill/extractor.py#L8-L66)
  - LLM 结构化抽取与 Markdown 生成：`LLMAnalyzer`：[llm_analyzer.py](file:///d:/code/skill/llm_analyzer.py)
    - `analyze()` / `generate_markdown_report()`：[llm_analyzer.py:L11-L170](file:///d:/code/skill/llm_analyzer.py#L11-L170)

输出约定（来自代码默认参数）：

- Excel：默认 `results.xlsx`（可 `--output` 指定）：[main.py:L11-L12](file:///d:/code/skill/main.py#L11-L12)
- 单篇报告目录：默认 `reports/`（可 `--markdown_dir` 指定）：[main.py:L12](file:///d:/code/skill/main.py#L12)

### 3.2 PDF → 逐页 Raw Markdown

目标：将 PDF 每页抽取为文本并生成“逐页” Markdown（每页一个 `## Page N`，正文通常在 ```text 块内）。

- 入口（Python CLI）：[anthropic_pdf_extract_raw.py](file:///d:/code/skill/anthropic_pdf_extract_raw.py)
  - `extract_text_per_page()`：[anthropic_pdf_extract_raw.py:L15-L39](file:///d:/code/skill/anthropic_pdf_extract_raw.py#L15-L39)
  - `render_markdown()`：[anthropic_pdf_extract_raw.py:L59-L85](file:///d:/code/skill/anthropic_pdf_extract_raw.py#L59-L85)
  - `main()`：[anthropic_pdf_extract_raw.py:L100-L126](file:///d:/code/skill/anthropic_pdf_extract_raw.py#L100-L126)
- 运行封装（PowerShell）：[run_anthropic_pdf_raw.ps1](file:///d:/code/skill/run_anthropic_pdf_raw.ps1)
- 输出目录：默认 `pdf_raw_md/`（`--out_dir`）：[anthropic_pdf_extract_raw.py:L103-L106](file:///d:/code/skill/anthropic_pdf_extract_raw.py#L103-L106)

### 3.3 Raw Markdown → 论文结构分段 Markdown（Kimi）

目标：将逐页 raw md 按“论文结构（7 大部分）”切分为一个结构化分段文档（仍尽量保留原文）。

- 入口（Python CLI）：[kimi_segment_raw_md.py](file:///d:/code/skill/kimi_segment_raw_md.py)
  - 解析逐页 raw md：`parse_raw_page_md()`：[kimi_segment_raw_md.py:L22-L58](file:///d:/code/skill/kimi_segment_raw_md.py#L22-L58)
  - 构造带页码标签全文：`build_full_text_with_page_tags()`：[kimi_segment_raw_md.py:L67-L76](file:///d:/code/skill/kimi_segment_raw_md.py#L67-L76)
  - 调 LLM 输出章节边界 JSON：`call_kimi_boundaries()`：[kimi_segment_raw_md.py:L85-L138](file:///d:/code/skill/kimi_segment_raw_md.py#L85-L138)
  - 按边界切片：`slice_segments()`：[kimi_segment_raw_md.py:L170-L236](file:///d:/code/skill/kimi_segment_raw_md.py#L170-L236)
  - 输出：`render_segmented_md()`：[kimi_segment_raw_md.py:L238-L268](file:///d:/code/skill/kimi_segment_raw_md.py#L238-L268)
- 运行封装（PowerShell）：[run_kimi_segment_raw_md.ps1](file:///d:/code/skill/run_kimi_segment_raw_md.ps1)
- 输出目录：默认 `pdf_segmented_md/`（`--out_dir`）：[kimi_segment_raw_md.py:L272-L274](file:///d:/code/skill/kimi_segment_raw_md.py#L272-L274)

### 3.4 “7 步深度精读”流水线（DeepSeek）

目标：针对“已分段的论文原文 Markdown”，分 7 步进行深度分析，每一步生成一个子报告，最后合成为总报告。

- **核心升级**：
  - **语义索引 (Semantic Indexing)**：引入 `semantic_router.py`，对全文进行智能分块与打标，生成 `semantic_index.json`，解决物理分段混乱问题。
  - **混合路由 (Hybrid Routing)**：结合 LLM 动态映射、本地规则兜底和语义索引，确保内容分发准确无误。
  - **防幻觉机制**：通过“原文原样打标”策略与系统提示词约束，杜绝 LLM 编造数据。
  - **按篇归档**：结果输出到 `deep_reading_results/{Paper_Name}/` 独立文件夹。

- 入口（Python CLI）：[deep_read_pipeline.py](file:///d:/code/skill/deep_read_pipeline.py)
  - `main()`：[deep_read_pipeline.py:L19-L134](file:///d:/code/skill/deep_read_pipeline.py#L19-L134)
- 运行封装（PowerShell）：[run_deep_reading_pipeline.ps1](file:///d:/code/skill/run_deep_reading_pipeline.ps1)
- 步骤实现（每个文件提供 `run(sections, titles, output_dir, step_id)`）：
  - Step1：Overview：[step_1_overview.py](file:///d:/code/skill/deep_reading_steps/step_1_overview.py)
  - Step2：Theory：[step_2_theory.py](file:///d:/code/skill/deep_reading_steps/step_2_theory.py)
  - Step3：Data：[step_3_data.py](file:///d:/code/skill/deep_reading_steps/step_3_data.py)
  - Step4：Variables：[step_4_vars.py](file:///d:/code/skill/deep_reading_steps/step_4_vars.py)
  - Step5：Identification：[step_5_identification.py](file:///d:/code/skill/deep_reading_steps/step_5_identification.py)
  - Step6：Results：[step_6_results.py](file:///d:/code/skill/deep_reading_steps/step_6_results.py)
  - Step7：Critique：[step_7_critique.py](file:///d:/code/skill/deep_reading_steps/step_7_critique.py)
- 公共能力（DeepSeek 调用、加载 segmented md、保存产物）：[common.py](file:///d:/code/skill/deep_reading_steps/common.py)
  - `get_combined_text_for_step()`：优先从 Semantic Index 读取，失败则回退到 Section Dict，支持 Next-Section Fallback。
  - `smart_chunk()`：智能分块函数，按段落边界切分长文本。
  - `route_sections_to_steps()`：混合路由逻辑。
- 语义路由能力：[semantic_router.py](file:///d:/code/skill/deep_reading_steps/semantic_router.py)
  - `generate_semantic_index()`：生成语义索引文件。

### 3.5 “全流程一键跑”（单篇）

目标：把“PDF→raw→segmented→7步精读→补缺→Dataview→Obsidian”串起来，适合对单篇论文做端到端处理。

- 入口（Python CLI）：[run_full_pipeline.py](file:///d:/code/skill/run_full_pipeline.py)
  - `main()`：[run_full_pipeline.py:L23-L84](file:///d:/code/skill/run_full_pipeline.py#L23-L84)
  - 内部通过子进程依次调用：
    - `anthropic_pdf_extract_raw.py`：[run_full_pipeline.py:L51-L54](file:///d:/code/skill/run_full_pipeline.py#L51-L54)
    - `kimi_segment_raw_md.py`：[run_full_pipeline.py:L55-L58](file:///d:/code/skill/run_full_pipeline.py#L55-L58)
    - `deep_read_pipeline.py`（设置 `DEEP_READING_OUTPUT_DIR`）：[run_full_pipeline.py:L59-L64](file:///d:/code/skill/run_full_pipeline.py#L59-L64)
    - `run_supplemental_reading.py --regenerate`：[run_full_pipeline.py:L65-L70](file:///d:/code/skill/run_full_pipeline.py#L65-L70)
    - `inject_dataview_summaries.py`：[run_full_pipeline.py:L71-L74](file:///d:/code/skill/run_full_pipeline.py#L71-L74)
    - `inject_obsidian_meta.py`：[run_full_pipeline.py:L75-L79](file:///d:/code/skill/run_full_pipeline.py#L75-L79)

输出目录约定（来自代码）：

- raw md：`pdf_raw_md/`：[run_full_pipeline.py:L38-L42](file:///d:/code/skill/run_full_pipeline.py#L38-L42)
- segmented md：`pdf_segmented_md/`：[run_full_pipeline.py:L41-L44](file:///d:/code/skill/run_full_pipeline.py#L41-L44)
- deep reading 结果：`deep_reading_results/{pdf_basename}/`：[run_full_pipeline.py:L45-L47](file:///d:/code/skill/run_full_pipeline.py#L45-L47)

### 3.6 批量全流程（目录）

目标：对目录内所有 PDF 逐个跑“全流程一键跑”，并在存在 Final 报告时跳过。

- 入口（Python CLI）：[run_batch_pipeline.py](file:///d:/code/skill/run_batch_pipeline.py)
  - `main()`：[run_batch_pipeline.py:L17-L62](file:///d:/code/skill/run_batch_pipeline.py#L17-L62)
  - **递归搜索**：支持递归扫描输入目录及其子目录下的所有 PDF 文件。
  - **哈希去重**：集成 `state_manager.py`，基于 MD5 内容哈希进行去重。如果文件内容已处理过（即使改名或移动），系统会自动跳过，避免重复消耗 Token。
- 运行封装（PowerShell）：[run_batch_pipeline.ps1](file:///d:/code/skill/run_batch_pipeline.ps1)

### 3.7 “补缺/重建”精读报告

目标：当 Final 报告出现“缺失/泛化内容”（提示抽取失败）时，从 raw md 抽取上下文并重跑对应 step；或通过 `--regenerate` 强制重建 Final（并清理 step 文档中的 frontmatter/nav）。

- 入口（Python CLI）：[run_supplemental_reading.py](file:///d:/code/skill/run_supplemental_reading.py)
  - `main()`：[run_supplemental_reading.py:L121-L301](file:///d:/code/skill/run_supplemental_reading.py#L121-L301)
  - Step 映射（step 模块、关键词、目标文件）：`STEP_MAPPING`：[run_supplemental_reading.py:L32-L40](file:///d:/code/skill/run_supplemental_reading.py#L32-L40)
  - 从 raw md 抽上下文：`extract_context_from_raw()`：[run_supplemental_reading.py:L59-L103](file:///d:/code/skill/run_supplemental_reading.py#L59-L103)
  - 重建 Final 时清理 frontmatter/nav：`strip_frontmatter_and_nav()`：[run_supplemental_reading.py:L104-L120](file:///d:/code/skill/run_supplemental_reading.py#L104-L120)
- 运行封装（PowerShell）：[run_supplemental_reading.ps1](file:///d:/code/skill/run_supplemental_reading.ps1)

注意：该脚本顶部存在硬编码路径常量（需要按实际目录调整）：[run_supplemental_reading.py:L42-L43](file:///d:/code/skill/run_supplemental_reading.py#L42-L43)

### 3.8 Obsidian 集成

#### 3.8.1 Dataview 摘要注入

目标：对 `deep_reading_results` 下的 `1_Overview.md`~`7_Critique.md` 注入可查询的 YAML key/value 摘要字段（DeepSeek 抽取）。

- 入口（Python CLI）：[inject_dataview_summaries.py](file:///d:/code/skill/inject_dataview_summaries.py)
  - `extract_summaries()`：[inject_dataview_summaries.py:L30-L83](file:///d:/code/skill/inject_dataview_summaries.py#L30-L83)
  - `process_file()`：[inject_dataview_summaries.py:L84-L126](file:///d:/code/skill/inject_dataview_summaries.py#L84-L126)
  - `main()`：[inject_dataview_summaries.py:L127-L149](file:///d:/code/skill/inject_dataview_summaries.py#L127-L149)
- 运行封装（PowerShell）：[run_dataview_summarizer.ps1](file:///d:/code/skill/run_dataview_summarizer.ps1)

#### 3.8.2 元数据与双向链接注入

目标：从 raw/segmented 文本抽取 `title/authors/journal/year/tags` 等元数据并注入 YAML frontmatter，同时为 Final 与 Steps 建立导航链接。

- 入口（Python CLI）：[inject_obsidian_meta.py](file:///d:/code/skill/inject_obsidian_meta.py)
  - 元数据抽取：`extract_metadata_from_text()`：[inject_obsidian_meta.py:L21-L68](file:///d:/code/skill/inject_obsidian_meta.py#L21-L68)
  - 读取 raw md 前两页：`read_first_two_pages()`：[inject_obsidian_meta.py:L69-L88](file:///d:/code/skill/inject_obsidian_meta.py#L69-L88)
  - 注入/合并 frontmatter：`inject_frontmatter()`：[inject_obsidian_meta.py:L96-L148](file:///d:/code/skill/inject_obsidian_meta.py#L96-L148)
  - 添加双向导航：`add_bidirectional_links()`：[inject_obsidian_meta.py:L149-L180](file:///d:/code/skill/inject_obsidian_meta.py#L149-L180)
  - `main()`：[inject_obsidian_meta.py:L182-L228](file:///d:/code/skill/inject_obsidian_meta.py#L182-L228)
- 运行封装（PowerShell）：[run_obsidian_injector.ps1](file:///d:/code/skill/run_obsidian_injector.ps1)

### 3.9 Stata 代码精修（DeepSeek）

目标：对 `reports/` 下的 Markdown 报告中的 Stata 代码建议段落进行“专家级”重写/精修并写回。

- 入口（Python CLI）：[refine_stata.py](file:///d:/code/skill/refine_stata.py)
  - `main()`：[refine_stata.py:L8-L67](file:///d:/code/skill/refine_stata.py#L8-L67)
- 关键实现：`StataRefiner`：[stata_refiner.py](file:///d:/code/skill/stata_refiner.py)
  - 生成/精修：`refine_code()`：[stata_refiner.py:L10-L73](file:///d:/code/skill/stata_refiner.py#L10-L73)
  - 写回报告：`update_markdown_report()`：[stata_refiner.py:L74-L106](file:///d:/code/skill/stata_refiner.py#L74-L106)

### 3.10 参考文献抽取与引用追踪（DeepSeek）

目标：从论文 `*_segmented.md` 中抽取参考文献列表形成结构化 Excel，并反向追踪正文引用位置（含上下文摘录）。

- 参考文献抽取入口（PowerShell）：[run_reference_extractor.ps1](file:///d:/code/skill/run_reference_extractor.ps1)
- 参考文献抽取实现（Python CLI）：[extract_references.py](file:///d:/code/skill/extract_references.py)
  - 两阶段流程：`extract_raw_references()` 提取原始文本 → `extract_references_with_llm()` 直接调用 DeepSeek 进行结构化解析 → 写入 Excel
  - 分批处理：自动按约 8000 字符分批，避免单次请求过长

- 引用追踪入口（PowerShell）：[run_citation_tracer.ps1](file:///d:/code/skill/run_citation_tracer.ps1)
- 引用追踪实现（Python CLI）：[citation_tracer.py](file:///d:/code/skill/citation_tracer.py)
  - 文本预处理：`preprocess_text()`（去页码标记、去除 ```text 块标记、截断参考文献段）
  - 指纹生成：`generate_fingerprints()`（作者-年份 / 数字编号两类）
  - 候选检索：`find_candidates()`（正则宽召回）
  - LLM 核验与摘录：`verify_citations_with_llm()`（输出精确原句，并由本地逻辑扩展上下文）

输出约定（默认写入 `references/` 目录）：
- `*_references.xlsx`：结构化参考文献表（含 `raw_text` 等字段）
- `*_references_citation_trace.md`：引用追踪日志（按参考文献条目输出引用摘录）
- `*_references_with_citations.xlsx`：在原表基础上追加：
  - `Citation_Count`
  - `Citation_Contexts_All`（多条引用用 ` || ` 拼接）
  - `Citation_Chinese_All`（英文引用的中文重述拼接；中文引用默认留空）
  - `Citation_1..N` / `Citation_1_ZH..N_ZH`（便于筛选与人工复核，N 默认最多 8）

### 3.11 社科文献深度阅读（Social Science Scholar）

目标：针对管理学/社会学文献，执行“4层金字塔”深度提取，生成分层报告、全景报告与 Excel 汇总。

- 入口（Python CLI）：[run_social_science_task.py](file:///d:/code/skill/run_social_science_task.py)
  - 流程：`deepseek_segment_raw_md` (切分) -> `social_science_analyzer` (分析) -> `link_social_science_docs` (链接注入)。
  - 筛选：脚本内 `KEYWORDS` 列表控制处理哪些论文。
- 核心实现：[social_science_analyzer.py](file:///d:/code/skill/social_science_analyzer.py)
  - 4层 Prompt 定义：`analyze_l1_context` 等方法。
  - 报告生成：`generate_full_report` / `generate_markdown`。
- 辅助工具：[link_social_science_docs.py](file:///d:/code/skill/link_social_science_docs.py)
  - 功能：为生成的 L1-L4 及 Full Report 注入双向导航链接。

### 3.12 智能科研助理（Smart Scholar）

目标：作为统一入口，智能分类并路由论文到最佳分析管线。

- 入口（Python CLI）：[smart_scholar.py](file:///d:/code/skill/smart_scholar.py) / [smart_scholar_lib.py](file:///d:/code/skill/smart_scholar_lib.py)
  - 流程：PDF -> Raw MD -> Segmented MD -> `classify_paper` (LLM) -> `dispatch`.
  - 分类逻辑：基于摘要和方法论关键词判断 `QUANT` vs `QUAL`。
    - **综述支持**：明确支持将 "Literature Review", "Survey", "Meta-analysis" 等综述类文章归类为 `QUAL`。
    - **默认策略**：当分类不确定或失败时，默认回退到 `QUAL`（对综述和理论文章更友好），而非之前的 `QUANT`。
  - 路由目标：
    - `QUANT` -> [deep_read_pipeline.py](file:///d:/code/skill/deep_read_pipeline.py)
    - `QUAL` -> [social_science_analyzer.py](file:///d:/code/skill/social_science_analyzer.py)

### 3.13 状态管理与去重 (State Manager)

目标：提供基于内容哈希的持久化去重能力，解决文件名变更或移动导致的重复处理问题。

- 入口（Python Library）：[state_manager.py](file:///d:/code/skill/state_manager.py)
  - `is_processed(file_path)`: 计算文件 MD5 并查询 `processed_papers.json` 账本，支持检查输出产物完整性。
  - `mark_completed(...)`: 记录处理完成状态及输出目录。
  - 持久化文件：`processed_papers.json`（自动生成，不纳入 Git）。

### 3.14 智能合成修复 (Smart Synthesis)

目标：在合成 Final Report 时，自动清洗分步文件中的冗余元数据（YAML Frontmatter）和导航链接，确保最终报告格式整洁。

- 独立工具：[smart_resynthesize.py](file:///d:/code/skill/smart_resynthesize.py)
- 集成情况：核心逻辑已集成至 `deep_read_pipeline.py` 的最终合成步骤中。

## 4. 另一条“深读”路线（不依赖 segmented md）

仓库还实现了另一套“对单篇 PDF 全文进行串行抽取与合成”的深度研读工具（与 7-step pipeline 并行存在）。

- 入口（Python CLI）：[run_deep_read.py](file:///d:/code/skill/run_deep_read.py)
  - 输出目录默认 `deep_reports/`：[run_deep_read.py:L9](file:///d:/code/skill/run_deep_read.py#L9)
- 关键实现：`DeepAnalyzer`：[deep_analyzer.py](file:///d:/code/skill/deep_analyzer.py)
  - 主流程：`analyze_paper_deeply()`：[deep_analyzer.py:L82-L253](file:///d:/code/skill/deep_analyzer.py#L82-L253)
  - 报告生成：`generate_deep_report()`：[deep_analyzer.py:L254-L342](file:///d:/code/skill/deep_analyzer.py#L254-L342)

## 5. 辅助/调试脚本

这些脚本在仓库中存在，但不一定被“主流程”调用；主要用于调试、验证或一次性处理：

- PDF 抽取预览调试：[debug_extraction.py](file:///d:/code/skill/debug_extraction.py)
- 关键词命中调试：[debug_keywords.py](file:///d:/code/skill/debug_keywords.py)
- Excel 结构校验：[verify_results.py](file:///d:/code/skill/verify_results.py)

注意：部分脚本包含硬编码路径（按需修改）：

- Excel 追加更新示例：[append_result.py](file:///d:/code/skill/append_result.py)
- 针对特定目录的元数据修复：[fix_metadata_cfps.py](file:///d:/code/skill/fix_metadata_cfps.py)

## 6. Trae Skills（与代码的对应关系）

仓库 `.trae/skills/` 中的 `SKILL.md` 用于描述“如何使用本仓库脚本完成某项任务”。这些文档与实际脚本的映射如下：

- `academic-pdf-analyzer` → `run_analyzer.ps1` / `main.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/academic-pdf-analyzer/SKILL.md)
- `kimi-pdf-raw-segmenter` → `run_kimi_segment_raw_md.ps1` / `kimi_segment_raw_md.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/kimi-pdf-raw-segmenter/SKILL.md)

### 3. 结构化切分 (Structure Segmentation)
- **目标**: 还原论文逻辑结构（Introduction, Data, Model 等）。
- **工具**: `deepseek-segment` (推荐，统一使用 DeepSeek) / `kimi-pdf-raw-segmenter`
- **创新**:
  - **直接分片模式**: LLM 一次性返回所有章节的完整内容，避免本地正则匹配失败
  - **智能骨架提取**: 超长文档自动提取骨架用于边界检测
- **输出**: `*_segmented.md`

### 4. 深度精读 (Deep Reading & Analysis)
- **目标**: 像 Daron Acemoglu 级别的审稿人一样，对论文进行批判性分析。
- **工具**: `deep-reading-expert`
- **逻辑**: 分步处理（全景扫描 -> 理论 -> 数据 -> 变量 -> 识别 -> 结果 -> 批判）。
- **优化**:
  - **语义索引**: 使用 `semantic_router.py` 生成全文语义索引，确保内容分发不依赖物理章节。
  - **防幻觉机制**: 系统级提示词约束，禁止 LLM 在信息缺失时编造内容。
  - **无压缩原文**: 采用分块打标 + 原文拼接的方式，最大限度保留论文细节。
- **输出**: `Final_Deep_Reading_Report.md` 及各分步报告。
- `deep-reading-expert` → `run_deep_reading_pipeline.ps1` / `deep_read_pipeline.py` / `deep_reading_steps/*`：[SKILL.md](file:///d:/code/skill/.trae/skills/deep-reading-expert/SKILL.md)
- `batch-pdf-processor` → `run_batch_pipeline.ps1` / `run_batch_pipeline.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/batch-pdf-processor/SKILL.md)
- `supplemental-reading-skill` → `run_supplemental_reading.ps1` / `run_supplemental_reading.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/supplemental-reading-skill/SKILL.md)
- `obsidian-dataview-summarizer` → `run_dataview_summarizer.ps1` / `inject_dataview_summaries.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/obsidian-dataview-summarizer/SKILL.md)
- `obsidian-metadata-injector` → `run_obsidian_injector.ps1` / `inject_obsidian_meta.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/obsidian-metadata-injector/SKILL.md)
- `social-science-scholar` → `run_social_science_task.py` / `social_science_analyzer.py`：[README_SOCIAL_SCIENCE.md](file:///d:/code/skill/README_SOCIAL_SCIENCE.md)

## 7. 第三方代码

- `third_party/anthropics-skills/` 为外部技能库镜像（仓库内存在，但根目录主流程代码未检索到对 `third_party` 的 import/调用）：[anthropics-skills](file:///d:/code/skill/third_party/anthropics-skills/)
