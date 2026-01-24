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

典型包括：`pdf/`、`reports/`、`deep_reading_results/`、`pdf_raw_md/`、`pdf_segmented_md/` 等。

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

- 入口（Python CLI）：[deep_read_pipeline.py](file:///d:/code/skill/deep_read_pipeline.py)
  - `main()`：[deep_read_pipeline.py:L19-L92](file:///d:/code/skill/deep_read_pipeline.py#L19-L92)
- 运行封装（PowerShell）：[run_deep_reading_pipeline.ps1](file:///d:/code/skill/run_deep_reading_pipeline.ps1)
- 步骤实现（每个文件提供 `run(sections)`）：
  - Step1：Overview：[step_1_overview.py](file:///d:/code/skill/deep_reading_steps/step_1_overview.py)
  - Step2：Theory：[step_2_theory.py](file:///d:/code/skill/deep_reading_steps/step_2_theory.py)
  - Step3：Data：[step_3_data.py](file:///d:/code/skill/deep_reading_steps/step_3_data.py)
  - Step4：Variables：[step_4_vars.py](file:///d:/code/skill/deep_reading_steps/step_4_vars.py)
  - Step5：Identification：[step_5_identification.py](file:///d:/code/skill/deep_reading_steps/step_5_identification.py)
  - Step6：Results：[step_6_results.py](file:///d:/code/skill/deep_reading_steps/step_6_results.py)
  - Step7：Critique：[step_7_critique.py](file:///d:/code/skill/deep_reading_steps/step_7_critique.py)
- 公共能力（DeepSeek 调用、加载 segmented md、保存产物）：[common.py](file:///d:/code/skill/deep_reading_steps/common.py)
  - `call_deepseek()` / `load_segmented_md()` / `save_step_result()`：[common.py:L21-L88](file:///d:/code/skill/deep_reading_steps/common.py#L21-L88)
  - 输出目录可通过 `DEEP_READING_OUTPUT_DIR` 控制，默认 `deep_reading_results/`：[common.py:L19-L21](file:///d:/code/skill/deep_reading_steps/common.py#L19-L21)

已知实现细节（来自代码）：`deep_read_pipeline.py` 在拼接 Final 报告时读取 step 文件使用了硬编码相对目录 `deep_reading_results`：[deep_read_pipeline.py:L70-L88](file:///d:/code/skill/deep_read_pipeline.py#L70-L88)

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
  - 跳过逻辑：存在 `deep_reading_results/{basename}/Final_Deep_Reading_Report.md` 则跳过：[run_batch_pipeline.py:L42-L50](file:///d:/code/skill/run_batch_pipeline.py#L42-L50)
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
- `deep-reading-expert` → `run_deep_reading_pipeline.ps1` / `deep_read_pipeline.py` / `deep_reading_steps/*`：[SKILL.md](file:///d:/code/skill/.trae/skills/deep-reading-expert/SKILL.md)
- `batch-pdf-processor` → `run_batch_pipeline.ps1` / `run_batch_pipeline.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/batch-pdf-processor/SKILL.md)
- `supplemental-reading-skill` → `run_supplemental_reading.ps1` / `run_supplemental_reading.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/supplemental-reading-skill/SKILL.md)
- `obsidian-dataview-summarizer` → `run_dataview_summarizer.ps1` / `inject_dataview_summaries.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/obsidian-dataview-summarizer/SKILL.md)
- `obsidian-metadata-injector` → `run_obsidian_injector.ps1` / `inject_obsidian_meta.py`：[SKILL.md](file:///d:/code/skill/.trae/skills/obsidian-metadata-injector/SKILL.md)

## 7. 第三方代码

- `third_party/anthropics-skills/` 为外部技能库镜像（仓库内存在，但根目录主流程代码未检索到对 `third_party` 的 import/调用）：[anthropics-skills](file:///d:/code/skill/third_party/anthropics-skills/)

