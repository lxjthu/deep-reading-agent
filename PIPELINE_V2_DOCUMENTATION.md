# Deep Reading Agent - 新流水线详细流程文档

**创建时间**: 2026-02-03
**版本**: v2.0 (集成 Obsidian 元数据注入)
**状态**: ✅ 生产就绪

---

## 目录

1. [整体架构](#整体架构)
2. [入口脚本详解](#入口脚本详解)
3. [核心流程步骤](#核心流程步骤)
4. [代码映射表](#代码映射表)
5. [参数配置说明](#参数配置说明)
6. [数据流转图](#数据流转图)

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    run_batch_pipeline.py                      │
│                      (批量入口脚本)                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                   smart_scholar_lib.py                        │
│              (SmartScholar 类：核心调度)                      │
│  - ensure_segmented_md()  确保分段 MD 存在                 │
│  - classify_paper()        论文类型分类                       │
│  - run_command()          子进程调用                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ↓                       ↓
┌──────────────────┐    ┌──────────────────┐
│   PDF → MD      │    │  PDF → MD      │
│  PaddleOCR      │    │   Legacy        │
│  (推荐)         │    │  (降级)         │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ↓                       ↓
┌──────────────────┐    ┌──────────────────┐
│ PaddleOCR MD    │    │  Raw MD         │
│ *_paddleocr.md  │    │  *_raw.md       │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                smart_segment_router.py                         │
│              (SmartSegmentRouter: 智能分段)                    │
│  - extract_headings()    提取章节标题                        │
│  - classify_headings()  LLM 分类标题                          │
│  - segment_by_routing() 代码切分内容                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                  *_segmented.md                               │
│              (结构化分段输出)                                  │
│  - QUANT: 7步 (1-7)                                       │
│  - QUAL: 4层 (L1-L4)                                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                smart_scholar_lib.py                            │
│              (classify_paper: 类型分类)                          │
│  - QUANT: 定量/计量经济学                                      │
│  - QUAL:  定性社会科学                                        │
│  - IGNORE: 非研究内容                                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ↓                       ↓
┌──────────────────┐    ┌──────────────────┐
│  QUANT 路由      │    │  QUAL 路由      │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         ↓                       ↓
┌──────────────────┐    ┌──────────────────┐
│deep_read_       │    │social_science_  │
│ pipeline.py      │    │analyzer.py      │
│ (7步精读)        │    │ (4层金字塔)       │
└────────┬─────────┘    └────────┬─────────┘
         │                       │
         ↓                       ↓
┌──────────────────┐    ┌──────────────────┐
│deep_reading_    │    │social_science_  │
│results/xxx/     │    │results_v2/xxx/ │
│  1_Overview.md  │    │  L1_Context.md  │
│  2_Theory.md    │    │  L2_Theory.md  │
│  3_Data.md      │    │  L3_Logic.md   │
│  ...            │    │  L4_Value.md   │
│  Final_...md    │    │  Full_Report.md │
└────────┬─────────┘    └──────────────────┘
         │
         ↓ (仅 QUANT)
┌─────────────────────────────────────────────────────────────────┐
│                inject_obsidian_meta.py                          │
│              (Obsidian 元数据注入)                               │
│  - Step 1: 从 MD 解析元数据                                   │
│  - Step 2: PDF 视觉提取 (Qwen-vl-plus)                      │
│  - Step 3: DeepSeek 子章节摘要 (30字中文)                      │
│  - Step 4: 注入 Frontmatter + 导航链接                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 入口脚本详解

### run_batch_pipeline.py

**文件路径**: `D:\code\deepagent\deep-reading-agent\run_batch_pipeline.py`

**功能**: 批量处理 PDF 目录，自动分类并路由到对应分析流水线

**关键配置**:
```python
# 脚本常量定义 (第 12-18 行)
SCRIPT_PIPELINE_QUANT = os.path.join(BASE_DIR, "deep_read_pipeline.py")    # 7步精读
SCRIPT_PIPELINE_QUAL = os.path.join(BASE_DIR, "social_science_analyzer.py")  # 4层金字塔
SCRIPT_INJECT_OBSIDIAN = os.path.join(BASE_DIR, "inject_obsidian_meta.py")   # 元数据注入

# 输出目录 (第 51-52 行)
deep_reading_results_dir = "deep_reading_results"      # QUANT 输出
qual_results_dir = "social_science_results_v2"      # QUAL 输出
```

**main() 函数流程** (第 25-141 行):

| 步骤 | 代码行 | 方法/函数 | 输入 | 输出 | 说明 |
|------|---------|-----------|------|------|------|
| 1. 参数解析 | 26-28 | argparse.ArgumentParser() | CLI 参数 | args | 解析 pdf_dir 参数 |
| 2. 查找 PDF | 36-44 | os.walk() | pdf_dir | pdf_files[] | 递归查找所有 .pdf 文件 |
| 3. 初始化 | 48-49 | SmartScholar(), StateManager() | - | scholar, state_mgr | 创建调度器实例 |
| 4. 循环处理 | 54-137 | for pdf_path in pdf_files | 单个 PDF | - | 遍历每个 PDF |
| 4.1 去重检查 | 57-60 | state_mgr.is_processed() | pdf_path | bool | MD5 哈希去重 |
| 4.2 文件检查 | 62-74 | os.path.exists() | 输出路径 | bool | 传统文件名检查（降级） |
| 4.3 标记开始 | 76-77 | state_mgr.mark_started() | pdf_path | - | 更新处理状态 |
| 4.4 确保分段 | 81-84 | scholar.ensure_segmented_md() | pdf_path | seg_md_path | 提取+分段 MD |
| 4.5 类型分类 | 86-91 | scholar.classify_paper() | seg_md_path[:5000] | "QUANT"/"QUAL"/"IGNORE" | LLM 分类 |
| 4.6 分发路由 | 94-132 | - | paper_type | - | 根据类型选择流水线 |

**QUANT 路由处理** (第 99-123 行):

```python
if paper_type == "QUANT":
    # 1. 运行 7 步精读流水线
    scholar.run_command([
        sys.executable,
        SCRIPT_PIPELINE_QUANT,  # deep_read_pipeline.py
        seg_md_path           # 输入: *_segmented.md
    ])

    # 2. 确定源 MD 路径 (优先 PaddleOCR)
    paddleocr_md_path = f"{PADDLEOCR_DIR}/{basename}_paddleocr.md"
    raw_md_path = f"{PDF_RAW_DIR}/{basename}_raw.md"

    if os.path.exists(paddleocr_md_path):
        source_md_path = paddleocr_md_path
    else:
        source_md_path = raw_md_path

    # 3. 注入 Obsidian 元数据 (关键修改!)
    scholar.run_command([
        sys.executable,
        SCRIPT_INJECT_OBSIDIAN,   # inject_obsidian_meta.py
        source_md_path,           # 参数1: 源 MD
        paper_output_dir,          # 参数2: 目标目录
        "--use_pdf_vision",       # 参数3: 启用 PDF 视觉提取
        "--pdf_dir", pdf_dir     # 参数4: PDF 目录
    ])

    # 4. 标记完成
    state_mgr.mark_completed(pdf_path, paper_output_dir, "QUANT")
```

---

## 核心流程步骤

### 步骤 1: PDF → Markdown 提取

#### 1.1 PaddleOCR 提取 (推荐路径)

**脚本**: `paddleocr_pipeline.py`

**核心方法**: `extract_pdf_with_paddleocr()` (第 22-66 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| pdf_path | str | 输入 PDF 文件路径 |
| out_dir | str | 输出目录 (默认: "paddleocr_md") |
| download_images | bool | 是否下载图片 (默认: False，提速) |

**调用链**:
```python
# paddleocr_pipeline.py 第 22-50 行
extractor = PaddleOCRPDFExtractor()
result = extractor.extract_pdf(
    pdf_path,
    out_dir=out_dir,
    download_images=download_images
)
```

**返回值**:
- `markdown_path`: 生成的 MD 文件路径 (`*_paddleocr.md`)
- `metadata`: 元数据字典
  ```python
  {
      "title": str,
      "abstract": str,
      "keywords": list,
      "sections": list,
      "extractor": "paddleocr",
      "stats": {...}
  }
  ```

**输出格式** (`*_paddleocr.md`):
```markdown
---
title: 论文标题
extractor: paddleocr
---

## 1. Introduction

### 1.1 Research Background
文本内容...

### 1.2 Problem Statement
文本内容...

## 2. Literature Review
...
```

**YAML Frontmatter 标识**:
- `extractor: paddleocr` → 用于识别提取方式
- `extractor: pdfplumber_fallback` → 降级标识

#### 1.2 Legacy 提取 (降级路径)

**脚本**: `anthropic_pdf_extract_raw.py` (间接调用)

**触发条件**: PaddleOCR API 不可用时自动降级

**输出格式** (`*_raw.md`):
```markdown
## Page 1
页面 1 内容...

## Page 2
页面 2 内容...
```

---

### 步骤 2: 智能分段路由

#### 2.1 SmartSegmentRouter 初始化

**脚本**: `smart_segment_router.py`

**类**: `SmartSegmentRouter` (第 31-60 行)

**初始化**:
```python
router = SmartSegmentRouter(api_key=os.getenv("DEEPSEEK_API_KEY"))
```

**步骤定义** (第 42-59 行):

**QUANT (定量)** - 7步精读:
```python
QUANT_STEPS = {
    1: "Overview (全景扫描) - 摘要、引言、结论、研究背景、核心贡献",
    2: "Theory (理论与假说) - 文献综述、理论框架、研究假设",
    3: "Data (数据考古) - 数据来源、样本选择、数据清洗",
    4: "Variables (变量与测量) - 核心变量定义、测量方法、描述性统计",
    5: "Identification (识别策略) - 计量模型、内生性讨论、IV/DID/RDD",
    6: "Results (结果解读) - 实证结果、回归分析、稳健性检验",
    7: "Critique (专家批判) - 研究局限、未来展望、政策建议"
}
```

**QUAL (定性)** - 4层金字塔:
```python
QUAL_STEPS = {
    "L1": "L1_Context (背景层) - 摘要、引言、政策背景、现状数据",
    "L2": "L2_Theory (理论层) - 文献综述、理论框架、核心构念",
    "L3": "L3_Logic (逻辑层) - 方法设计、案例分析、机制路径、实证结果",
    "L4": "L4_Value (价值层) - 结论、讨论、研究缺口、理论贡献、实践启示"
}
```

#### 2.2 提取章节标题

**方法**: `extract_headings()` (第 67-135 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| content | str | PaddleOCR MD 完整内容 |

**策略** (第 72-76 行):
1. 优先提取 `###` 三级章节标题 (如 "1.1 Research Background")
2. 如果 `###` 数量 < 3，则回退到 `##` 二级标题
3. 如果有 `###`，则忽略 `## Text Content` 这种容器章节
4. 记录每个标题在原文中的位置 (start_pos/end_pos)

**返回值**: `List[Heading]`
```python
@dataclass
class Heading:
    level: int      # 1=#, 2=##, 3=###
    title: str     # 标题文本
    start_pos: int # 起始位置
    end_pos: int   # 结束位置
```

**示例输出**:
```python
[
    Heading(level=3, title="1. Introduction", start_pos=100, end_pos=500),
    Heading(level=3, title="2. Literature Review", start_pos=500, end_pos=800),
    ...
]
```

#### 2.3 LLM 标题分类

**方法**: `classify_headings()` (第 137-220 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| headings | List[Heading] | 章节标题列表 |
| mode | str | "auto" / "quant" / "qual" |

**工作流程**:

1. **构建标题列表** (第 143-150 行):
```python
heading_titles = [h.title for h in headings]
```

2. **调用 DeepSeek LLM** (第 152-185 行):
```python
response = self.client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    temperature=0.0,
    response_format={"type": "json_object"}
)
```

**System Prompt** (QUANT 模式):
```
你是学术论文智能分段专家。
将以下章节标题映射到 7 个分析步骤。

7个步骤定义:
1. Overview: 摘要、引言、结论、研究背景、核心贡献
2. Theory: 文献综述、理论框架、研究假设
3. Data: 数据来源、样本选择、数据清洗
4. Variables: 核心变量定义、测量方法、描述性统计
5. Identification: 计量模型、内生性讨论、IV/DID/RDD
6. Results: 实证结果、回归分析、稳健性检验
7. Critique: 研究局限、未来展望、政策建议

规则:
- 一个章节可以属于多个步骤
- 无法分类的章节归为 "0" (忽略)
- 返回 JSON 格式
```

**User Prompt**:
```
章节标题:
1. Introduction
2. Literature Review
3. Methodology
4. Data
5. Results
6. Discussion
7. Conclusion

请输出映射:
{
  "1": ["1. Introduction", "7. Conclusion"],
  "2": ["2. Literature Review"],
  ...
}
```

3. **解析 LLM 响应** (第 187-195 行):
```python
result = json_repair.repair_json(content, return_objects=True)
```

**返回值**: `Dict[str, List[str]]`
```python
{
    "1": ["1. Introduction", "7. Conclusion"],
    "2": ["2. Literature Review", "3. Methodology"],
    "3": ["4. Data"],
    "4": ["4. Data"],
    "5": ["3. Methodology"],
    "6": ["5. Results"],
    "7": ["6. Discussion"]
}
```

#### 2.4 代码切分内容

**方法**: `segment_by_routing()` (第 222-295 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| content | str | PaddleOCR MD 完整内容 |
| headings | List[Heading] | 章节标题列表 |
| routing | Dict[str, List[str]] | 步骤→标题映射 |
| steps_def | Dict | 步骤定义 (QUANT_STEPS 或 QUAL_STEPS) |

**工作流程**:

1. **提取文本内容** (第 236-245 行):
```python
for step_id, title_list in routing.items():
    step_texts = []
    for title in title_list:
        # 找到对应的 Heading 对象
        heading = next((h for h in headings if h.title == title), None)
        if heading:
            # 根据 start_pos/end_pos 从 content 中切片
            text = content[heading.start_pos:heading.end_pos]
            step_texts.append(text)
    step_contents[step_id] = "\n\n".join(step_texts)
```

2. **自动填充空步骤** (第 297-315 行):
```python
def _fill_empty_steps(step_contents: dict, order: list) -> dict:
    for i, step_id in enumerate(order):
        if not step_contents.get(step_id):
            # 从前一个步骤复制
            if i > 0:
                prev_step = order[i-1]
                step_contents[step_id] = step_contents.get(prev_step, "")
            # 从后一个步骤复制
            elif i < len(order) - 1:
                next_step = order[i+1]
                step_contents[step_id] = step_contents.get(next_step, "")
```

**返回值**: `Dict[str, str]`
```python
{
    "1": "【原文：1. Introduction】\n\n完整内容...",
    "2": "【原文：2. Literature Review】\n\n完整内容...",
    ...
}
```

#### 2.5 保存分段 MD

**方法**: `save_segmented_md()` (第 317-375 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| step_contents | Dict[str, str] | 步骤ID → 内容映射 |
| steps_def | Dict | 步骤定义 |
| output_path | str | 输出文件路径 |

**输出格式** (`*_segmented.md`):
```markdown
# 论文原文结构化分段（Smart Router）

- Source: paddleocr_md/xxx_paddleocr.md
- Mode: quant
- Generated: 2026-02-03T10:30:00

## 路由映射

- 1: Overview (全景扫描)
- 2: Theory (理论与假说)
- 3: Data (数据考古)
- 4: Variables (变量与测量)
- 5: Identification (识别策略)
- 6: Results (结果解读)
- 7: Critique (专家批判)

## 1. Overview (全景扫描)

```text
【原文：1. Introduction】
...

【原文：7. Conclusion】
...
```

## 2. Theory (理论与假说)

```text
【原文：2. Literature Review】
...
```

...
```

---

### 步骤 3: 论文类型分类

#### 3.1 SmartScholar.classify_paper()

**脚本**: `smart_scholar_lib.py`

**方法**: `classify_paper()` (第 43-81 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| text_segment | str | 论文文本预览 (前 4000 字符) |

**System Prompt** (第 47-63 行):
```
You are an expert Academic Editor. Your task is to classify a research paper into one of three categories based on its content (Abstract, Intro, Methodology).

Categories:
1. "QUANT": Quantitative Economics / Econometrics / Empirical Finance.
   - Keywords: Regression, Identification Strategy, Difference-in-Differences (DID), IV, RDD, Stata, Equation, Robustness Check, Coefficients.
   - Style: Mathematical, Statistical, Hypothesis Testing.

2. "QUAL": Qualitative Social Science / Management / Case Study / Literature Review.
   - Keywords: Case Study, Grounded Theory, Qualitative Comparative Analysis (QCA), Semi-structured Interview, Theoretical Framework, Construct, Mechanism (narrative), Literature Review, Research Progress, Survey, Overview, Meta-analysis.
   - Style: Narrative, Theoretical, Conceptual, Process Model, Comprehensive Review.

3. "IGNORE": Non-Research Content / Editorials / Metadata.
   - Keywords: Host's Introduction, Editor's Note, Preface, Call for Papers, Table of Contents, Conference Announcement, Erratum, Book Review, News.
   - Style: Very short (< 2 pages), introductory, administrative, non-academic structure.

Output JSON: {"type": "QUANT" | "QUAL" | "IGNORE", "reason": "short explanation"}
```

**调用** (第 67-76 行):
```python
response = self.client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Classify this paper content:\n\n{text_segment[:4000]}"}
    ],
    temperature=0.0,
    response_format={"type": "json_object"}
)
```

**返回值**: `"QUANT"` / `"QUAL"` / `"IGNORE"`

---

### 步骤 4: QUANT 7步精读

#### 4.1 deep_read_pipeline.py 主流程

**脚本**: `deep_read_pipeline.py`

**main() 函数** (第 38-155 行):

| 步骤 | 代码行 | 方法/函数 | 输入 | 输出 | 说明 |
|------|---------|-----------|------|------|------|
| 1. 参数解析 | 38-42 | argparse | CLI | args | 解析 segmented_md_path |
| 2. 加载分段 | 49 | common.load_segmented_md() | segmented_md_path | sections | 解析 MD 章节 |
| 3. 创建输出目录 | 56-62 | os.makedirs() | paper_basename | paper_output_dir | 每个论文独立目录 |
| 4. 生成语义索引 | 64-77 | generate_semantic_index() | full_text | semantic_index.json | 处理分段不完整的情况 |
| 5. 路由章节 | 81-82 | common.route_sections_to_steps() | sections | section_routing | 章节 → 步骤映射 |
| 6. 执行 7 步分析 | 110-129 | step_*.run() | sections, routing | step_*.md | 逐步生成分析文件 |
| 7. 生成总报告 | 132-150 | 文件合并 | step_*.md | Final_...md | 汇总所有步骤 |

#### 4.2 执行单个步骤

**代码** (第 110-129 行):
```python
# Step 1: Overview
step_1_overview.run(sections, section_routing.get(1, []), paper_output_dir, step_id=1)

# Step 2: Theory
step_2_theory.run(sections, section_routing.get(2, []), paper_output_dir, step_id=2)

# Step 3: Data
step_3_data.run(sections, section_routing.get(3, []), paper_output_dir, step_id=3)

# Step 4: Variables
step_4_vars.run(sections, section_routing.get(4, []), paper_output_dir, step_id=4)

# Step 5: Identification
step_5_identification.run(sections, section_routing.get(5, []), paper_output_dir, step_id=5)

# Step 6: Results
step_6_results.run(sections, section_routing.get(6, []), paper_output_dir, step_id=6)

# Step 7: Critique
step_7_critique.run(sections, section_routing.get(7, []), paper_output_dir, step_id=7)
```

**step_*.run() 参数**:
```python
def run(
    sections: dict,           # 所有章节内容 {title: content}
    assigned_titles: list,    # 分配给此步骤的章节标题列表
    output_dir: str,         # 输出目录
    step_id: int            # 步骤 ID (1-7)
) -> None
```

**输出文件**:
- `1_Overview.md`
- `2_Theory.md`
- `3_Data.md`
- `4_Variables.md`
- `5_Identification.md`
- `6_Results.md`
- `7_Critique.md`

#### 4.3 生成总报告

**代码** (第 132-150 行):
```python
final_report_path = os.path.join(paper_output_dir, "Final_Deep_Reading_Report.md")

with open(final_report_path, 'w', encoding='utf-8') as f:
    f.write(f"# Deep Reading Report: {paper_basename}\n\n")

    steps = [
        "1_Overview", "2_Theory", "3_Data", "4_Variables",
        "5_Identification", "6_Results", "7_Critique"
    ]

    for step in steps:
        step_file = os.path.join(paper_output_dir, f"{step}.md")
        if os.path.exists(step_file):
            with open(step_file, 'r', encoding='utf-8') as sf:
                content = sf.read()
                cleaned_content = clean_content(content)  # 去除 frontmatter 和导航
                f.write(f"## {step.replace('_', ' ')}\n\n")
                f.write(cleaned_content + "\n\n")
```

**输出文件**: `Final_Deep_Reading_Report.md`

---

### 步骤 5: Obsidian 元数据注入 (核心新功能)

#### 5.1 inject_obsidian_meta.py 主流程

**脚本**: `inject_obsidian_meta.py`

**main() 函数** (第 388-500 行):

| 步骤 | 代码行 | 方法/函数 | 输入 | 输出 | 说明 |
|------|---------|-----------|------|------|------|
| 1. 参数解析 | 388-398 | argparse | CLI | args | 解析 source_md, target_dir, --use_pdf_vision, --pdf_dir |
| 2. MD 元数据提取 | 404-411 | parse_paddleocr_frontmatter() | source_md | md_metadata | 解析 YAML frontmatter |
| 3. PDF 视觉提取 | 413-436 (可选) | extract_metadata_from_pdf_images() | PDF | pdf_metadata | Qwen-vl-plus 识别 |
| 4. 元数据合并 | 438-441 | - | md_metadata, pdf_metadata | merged_metadata | PDF 优先覆盖核心字段 |
| 5. 循环处理文件 | 446-546 | for filename in all_files | target_dir | - | 遍历所有 MD 文件 |
| 5.1 步骤文件处理 | 456-499 | extract_subsections(), summarize_with_deepseek(), inject_frontmatter(), add_bidirectional_links() | 单个 MD | 更新后的 MD | 提取+总结+注入 |
| 5.2 Final 报告处理 | 501-527 | inject_frontmatter() | Final_*.md | 更新后的 MD | 只注入 PDF 元数据 |

#### 5.2 从 MD 解析元数据

**方法**: `parse_paddleocr_frontmatter()` (第 41-115 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| path | str | PaddleOCR MD 文件路径 |

**解析逻辑**:

1. **提取 YAML Frontmatter** (第 56-63 行):
```python
if content.startswith("---\n"):
    end_idx = content.find("\n---\n", 4)
    if end_idx != -1:
        fm_str = content[4:end_idx]
        metadata = yaml.safe_load(fm_str) or {}
```

2. **提取正文内容** (第 66-70 行):
```python
if content.startswith("---\n"):
    end_idx = content.find("\n---\n", 4)
    if end_idx != -1:
        body = content[end_idx + 5:]
else:
    body = content
```

3. **补充元数据** (从正文正则提取):

   **Title** (第 75-85 行):
   ```python
   if not metadata.get("title") or metadata.get("title").endswith(".pdf"):
       for line in body.split('\n')[:30]:
           line = line.strip()
           if (line and not line.startswith('#') and len(line) > 15):
               metadata["title"] = line
               break
   ```

   **Abstract** (第 87-97 行):
   ```python
   if not metadata.get("abstract"):
       # 中文
       match = re.search(r'摘要[：:]\s*(.+?)(?=\n\n|关键词)', body, re.DOTALL)
       if match:
           metadata["abstract"] = match.group(1).strip()[:500]
       else:
           # 英文
           match = re.search(r'Abstract[：:.]?\s*(.+?)(?=\n\n|Keywords)', body, re.DOTALL | re.IGNORECASE)
           if match:
               metadata["abstract"] = match.group(1).strip()[:500]
   ```

   **Keywords** (第 99-104 行):
   ```python
   if not metadata.get("keywords"):
       match = re.search(r'关键词[：:]\s*(.+?)(?=\n)', body)
       if match:
           keywords = match.group(1)
           metadata["keywords"] = [k.strip() for k in re.split(r'[；;,，]', keywords)]
   ```

   **Authors** (第 106-113 行):
   ```python
   if not metadata.get("authors"):
       author_match = re.search(r'(?:作者|Author)[：:s]*\s*(.+?)(?=\n|摘要|Abstract)', body, re.IGNORECASE)
       if author_match:
           authors_text = author_match.group(1).strip()
           metadata["authors"] = [a.strip() for a in re.split(r'[,，、]', authors_text)]
   ```

**返回值**: `dict`
```python
{
    "title": str,
    "authors": list,
    "journal": str,
    "year": str,
    "abstract": str,
    "keywords": list
}
```

#### 5.3 PDF 视觉元数据提取

**方法**: `extract_metadata_from_pdf_images()` (第 272-347 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| pdf_path | str | PDF 文件路径 |

**工作流程**:

1. **检查 pymupdf** (第 284-291 行):
```python
if not pymupdf:
    return {
        "title": "Unknown",
        "authors": ["Unknown"],
        "journal": "Unknown",
        "year": "Unknown"
    }
```

2. **检查 PDF 存在** (第 293-300 行):
```python
if not os.path.exists(pdf_path):
    return {"title": "Unknown", ...}
```

3. **提取前两页图片** (第 302-314 行):
```python
doc = pymupdf.open(pdf_path)
images = []

for page_num in range(min(2, len(doc))):
    page = doc.load_page(page_num)
    mat = pymupdf.Matrix(pymupdf.Identity)
    pix = page.get_pixmap(matrix=mat, dpi=200)

    img_bytes = pix.tobytes("png")
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    images.append(img_base64)

doc.close()
```

4. **调用 Qwen-vl-plus** (第 316-371 行):

**Prompt** (第 331-348 行):
```
请从以下论文图片中提取以下元数据：
1. 论文标题（完整）
2. 作者列表（所有作者，用逗号分隔）
3. 发表期刊（期刊全名）
4. 发表年份（仅数字）

请以 JSON 格式返回：
{
    "title": "...",
    "authors": ["...", "..."],
    "journal": "...",
    "year": "..."
}

注意：
- 期刊名称和年份通常在页面顶部的页眉
- 仔细识别页眉位置的期刊名和年份
```

**API 调用** (第 350-371 行):
```python
client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

content_messages = [{"type": "text", "text": prompt}]

for img_base64 in images:
    content_messages.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{img_base64}"}
    })

resp = client.chat.completions.create(
    model="qwen-vl-plus",
    messages=[
        {"role": "system", "content": "你是专业的学术论文元数据提取专家。"},
        {"role": "user", "content": content_messages}
    ],
    temperature=0.0
)
```

5. **解析响应** (第 273-287 行):
```python
response_content = resp.choices[0].message.content

# 提取 JSON (支持 markdown 代码块)
if "```json" in response_content:
    start_idx = response_content.find("```json") + 7
    end_idx = response_content.find("```", start_idx)
    json_str = response_content[start_idx:end_idx].strip()
elif "```" in response_content:
    start_idx = response_content.find("```") + 3
    end_idx = response_content.find("```", start_idx)
    json_str = response_content[start_idx:end_idx].strip()
else:
    json_str = response_content.strip()

result = json.loads(json_str)
return result
```

**返回值**: `dict`
```python
{
    "title": "Digital revitalization or useless effort? Public e-commerce support and local specialty sales",
    "authors": ["Xintong Han", "Jan Victor Dee", "Shaonia Wang", "Kefan Chen"],
    "journal": "Journal of Development Economics",
    "year": "2026"
}
```

**环境变量要求**:
- `QWEN_API_KEY`: 阿里云通义千问 API Key

#### 5.4 元数据合并

**代码** (第 438-441 行):
```python
merged_metadata = md_metadata.copy()
if pdf_metadata:
    merged_metadata.update(pdf_metadata)  # PDF 元数据优先覆盖核心字段
```

**合并策略**:
- PDF 元数据优先级最高（覆盖 MD 中的 title/authors/journal/year）
- MD 中其他字段（如 abstract/keywords）保留

#### 5.5 子章节提取与总结

**子章节提取**: `extract_subsections()` (第 217-241 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| content | str | Markdown 文件内容 |

**逻辑**:
```python
subsections = {}
current_title = None
current_content = []

for line in content.split('\n'):
    if line.startswith('### '):
        if current_title:
            subsections[current_title] = '\n'.join(current_content).strip()
        current_title = line[4:].strip()
        current_content = []
    elif line.startswith('## '):
        if current_title:
            subsections[current_title] = '\n'.join(current_content).strip()
        current_title = None
        current_content = []
    else:
        if current_title:
            current_content.append(line)

if current_title:
    subsections[current_title] = '\n'.join(current_content).strip()

return subsections
```

**返回值**: `Dict[str, str]`
```python
{
    "**1. 研究主题与核心结论**": "本文以中国茶农为研究对象...",
    "**2. 问题意识**": "- 具体的科学问题：本文旨在解决...",
    ...
}
```

**子章节总结**: `summarize_with_deepseek()` (第 243-270 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| title | str | 子章节标题 |
| text | str | 子章节内容 |

**Prompt** (第 248-256 行):
```
请将以下内容总结为30字以内的一句话：
标题：{title}
内容：{text}

要求：
- 中文输出
- 30字以内
- 抓住核心要点
```

**API 调用** (第 258-266 行):
```python
resp = deepseek_client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "你是一个精确的学术内容总结专家。"},
        {"role": "user", "content": prompt}
    ],
    temperature=0.3,
    max_tokens=100
)
```

**返回值**: `str` (30字以内的中文摘要)

**示例输出**:
- "**1. 研究主题与核心结论**": 电商平台使茶农销售从线下转至线上，但未提升总销售额。
- "**2. 问题意识**": 政府电商赋能小农户，主要优化渠道而非创造新需求。

#### 5.6 注入 Frontmatter

**方法**: `inject_frontmatter()` (第 448-489 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| content | str | 原始 Markdown 内容 |
| metadata | dict | 要注入的元数据 |

**逻辑**:

1. **解析现有 Frontmatter** (第 450-407 行):
```python
existing_meta = {}
body_content = content

if has_frontmatter(content):
    end_idx = content.find("\n---\n", 4)
    if end_idx != -1:
        try:
            fm_str = content[4:end_idx]
            existing_meta = yaml.safe_load(fm_str) or {}
            body_content = content[end_idx+5:]
        except Exception:
            pass
```

2. **合并元数据** (第 409-413 行):
```python
merged_meta = existing_meta.copy()
merged_meta.update(metadata)  # 新元数据覆盖现有
```

3. **合并 Tags** (第 415-436 行):
```python
tags = set()

# 添加现有 tags
if "tags" in existing_meta:
    if isinstance(existing_meta["tags"], list):
        tags.update(existing_meta["tags"])
    elif isinstance(existing_meta["tags"], str):
        tags.add(existing_meta["tags"])

# 添加新 tags
if "tags" in metadata:
    if isinstance(metadata["tags"], list):
        tags.update(metadata["tags"])
    elif isinstance(metadata["tags"], str):
        tags.add(metadata["tags"])

# 始终确保基础 tags
tags.add("paper")
tags.add("deep-reading")

merged_meta["tags"] = list(tags)
```

4. **生成 Frontmatter** (第 438-443 行):
```python
yaml_str = yaml.safe_dump(merged_meta, allow_unicode=True, sort_keys=False).strip()
frontmatter_block = f"---\n{yaml_str}\n---\n\n"

return frontmatter_block + body_content
```

#### 5.7 添加导航链接

**方法**: `add_bidirectional_links()` (第 491-530 行)

| 参数 | 类型 | 说明 |
|------|------|------|
| content | str | Markdown 内容 |
| filename | str | 当前文件名 |
| all_files | List[str] | 目标目录所有 MD 文件 |

**逻辑**:

1. **判断文件类型** (第 500 行):
```python
is_final = "Final" in filename
```

2. **生成导航段落** (第 502-470 行):
```python
links_section = "\n\n## 导航 (Navigation)\n\n"

if is_final:
    # Final 报告：链接到所有步骤
    steps = [f for f in all_files if f != filename and f.endswith(".md")]
    steps.sort()

    links_section += "**分步分析文档：**\n"
    for s in steps:
        link_name = os.path.splitext(s)[0]
        links_section += f"- [[{link_name}]]\n"
else:
    # 步骤文件：链接到 Final 报告
    final_files = [f for f in all_files if "Final" in f and f.endswith(".md")]
    if final_files:
        link_name = os.path.splitext(final_files[0])[0]
        links_section += f"**返回总报告：** [[{link_name}]]\n"
```

3. **避免重复** (第 472-474 行):
```python
if "## 导航 (Navigation)" in content:
    return content  # 已存在，跳过
```

**返回值**: 带导航链接的 Markdown 内容

#### 5.8 区分处理逻辑

**步骤文件** (1-7_*.md):
```python
if is_step and deepseek_client:
    # 1. 提取子章节
    subsections = extract_subsections(content)

    # 2. DeepSeek 总结
    for title, section_text in subsections.items():
        if len(section_text) >= 50:
            summary = summarize_with_deepseek(deepseek_client, title, section_text)
            subsections_meta[title] = summary

    # 3. 注入完整元数据 (MD + PDF + subsections)
    merged_metadata["tags"] = ["paper", "deep-reading"]
    full_metadata = merged_metadata.copy()
    if subsections_meta:
        full_metadata["subsections"] = subsections_meta

    new_content = inject_frontmatter(content, full_metadata)

    # 4. 添加导航链接
    new_content = add_bidirectional_links(new_content, filename, all_files)
```

**Final 报告文件** (Final_Deep_Reading_Report.md):
```python
if is_final:
    # 1. 只提取 PDF 视觉元数据
    final_metadata = {}
    for key in ["title", "authors", "journal", "year"]:
        if pdf_metadata.get(key):
            final_metadata[key] = pdf_metadata[key]

    # 2. 添加 tags
    final_metadata["tags"] = ["paper", "deep-reading"]

    # 3. 注入 Frontmatter (不加导航链接)
    new_content = inject_frontmatter(content, final_metadata)
```

#### 5.9 输出示例

**步骤文件 (1_Overview.md)**:
```markdown
---
title: Digital revitalization or useless effort? Public e-commerce support and local
  specialty sales
authors:
- Xintong Han
- Jan Victor Dee
- Shaonia Wang
- Kefan Chen
journal: Journal of Development Economics
year: '2026'
tags:
- paper
- deep-reading
subsections:
  '**1. 研究主题与核心结论**': 电商平台使茶农销售从线下转至线上，但未显著提升总销售额。
  '**2. 问题意识**': 政府电商项目对小农户销售行为的影响：优化渠道而非创造新需求。
  '**3. 重要性**': 严格评估电商支持项目，避免资源错配，理解其作用机制以科学指导政策。
  '**4. 贡献定位**': 本文首次实证研究公共电商平台对生产者的影响，揭示了其作为互补性数字基础设施的微观机制与政策启示。
---

### **1. 研究主题与核心结论**
本文以中国茶农为研究对象...

## 导航 (Navigation)

**返回总报告：** [[Final_Deep_Reading_Report]]
```

**Final 报告 (Final_Deep_Reading_Report.md)**:
```markdown
---
title: Digital revitalization or useless effort? Public e-commerce support and local
  specialty sales
authors:
- Xintong Han
- Jan Victor Dee
- Shaonia Wang
- Kefan Chen
journal: Journal of Development Economics
year: '2026'
tags:
- paper
- deep-reading
---

# Deep Reading Report: xxx
...
```

---

## 代码映射表

| 功能模块 | 文件 | 核心方法/类 | 输入 | 输出 | 说明 |
|---------|------|------------|------|------|------|
| **批量入口** | | | | | |
| 批量处理 | run_batch_pipeline.py | main() | pdf_dir | - | 遍历 PDF 目录 |
| 核心调度 | smart_scholar_lib.py | SmartScholar | - | - | 封装流水线操作 |
| **PDF 提取** | | | | | |
| PaddleOCR 提取 | paddleocr_pipeline.py | extract_pdf_with_paddleocr() | pdf_path | *_paddleocr.md | 远程 API 提取 |
| Legacy 提取 | anthropic_pdf_extract_raw.py | - | pdf_path | *_raw.md | 降级方案 |
| **智能分段** | | | | | |
| 标题提取 | smart_segment_router.py | SmartSegmentRouter.extract_headings() | content | List[Heading] | 解析 ##/### 标题 |
| LLM 分类 | smart_segment_router.py | SmartSegmentRouter.classify_headings() | headings | routing | DeepSeek 分类 |
| 代码切分 | smart_segment_router.py | SmartSegmentRouter.segment_by_routing() | content, routing | step_contents | 直接切片 |
| 空步骤填充 | smart_segment_router.py | SmartSegmentRouter._fill_empty_steps() | step_contents | step_contents | 自动填充 |
| 保存分段 | smart_segment_router.py | SmartSegmentRouter.save_segmented_md() | step_contents | *_segmented.md | 生成兼容格式 |
| **论文分类** | | | | | |
| 类型判断 | smart_scholar_lib.py | SmartScholar.classify_paper() | text[:4000] | "QUANT"/"QUAL"/"IGNORE" | LLM 分类 |
| **7步精读** | | | | | |
| 加载分段 | deep_read_pipeline.py | common.load_segmented_md() | segmented.md | sections | 解析 MD 章节 |
| 语义索引 | deep_read_pipeline.py | generate_semantic_index() | full_text | semantic_index.json | 处理分段不完整 |
| 路由章节 | deep_read_pipeline.py | common.route_sections_to_steps() | sections | routing | 章节→步骤映射 |
| Step 1 | deep_read_pipeline.py | step_1_overview.run() | sections, routing | 1_Overview.md | 全景扫描 |
| Step 2 | deep_read_pipeline.py | step_2_theory.run() | sections, routing | 2_Theory.md | 理论与假说 |
| Step 3 | deep_read_pipeline.py | step_3_data.run() | sections, routing | 3_Data.md | 数据考古 |
| Step 4 | deep_read_pipeline.py | step_4_vars.run() | sections, routing | 4_Variables.md | 变量与测量 |
| Step 5 | deep_read_pipeline.py | step_5_identification.run() | sections, routing | 5_Identification.md | 识别策略 |
| Step 6 | deep_read_pipeline.py | step_6_results.run() | sections, routing | 6_Results.md | 结果解读 |
| Step 7 | deep_read_pipeline.py | step_7_critique.run() | sections, routing | 7_Critique.md | 专家批判 |
| 总报告 | deep_read_pipeline.py | main() (合并) | step_*.md | Final_*.md | 汇总所有步骤 |
| **元数据注入** | | | | | |
| MD 解析 | inject_obsidian_meta.py | parse_paddleocr_frontmatter() | *_segmented.md | md_metadata | YAML + 正则 |
| PDF 视觉 | inject_obsidian_meta.py | extract_metadata_from_pdf_images() | PDF | pdf_metadata | Qwen-vl-plus |
| 元数据合并 | inject_obsidian_meta.py | main() (update) | md, pdf | merged_metadata | PDF 优先 |
| 子章节提取 | inject_obsidian_meta.py | extract_subsections() | content | subsections | 解析 ### |
| 子章节总结 | inject_obsidian_meta.py | summarize_with_deepseek() | title, text | summary | DeepSeek 30字 |
| 注入 Frontmatter | inject_obsidian_meta.py | inject_frontmatter() | content, metadata | content | YAML |
| 添加导航 | inject_obsidian_meta.py | add_bidirectional_links() | content, filename | content | Wikilinks |
| 去重管理 | state_manager.py | StateManager | - | - | MD5 哈希 |

---

## 参数配置说明

### 环境变量 (.env)

| 变量名 | 用途 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| DEEPSEEK_API_KEY | DeepSeek API | ✅ 是 | - | 用于 LLM 调用（分类、分段、总结） |
| QWEN_API_KEY | 通义千问 API | ✅ 是 (PDF 视觉) | - | Qwen-vl-plus PDF 元数据提取 |
| PADDLEOCR_REMOTE_URL | PaddleOCR API | ❌ 否 | - | 远程 PaddleOCR 服务地址 |
| PADDLEOCR_REMOTE_TOKEN | PaddleOCR Token | ❌ 否 | - | 远程 PaddleOCR 认证令牌 |

### CLI 参数

#### run_batch_pipeline.py

```bash
python run_batch_pipeline.py <pdf_dir>
```

| 参数 | 必需 | 说明 |
|------|------|------|
| pdf_dir | ✅ 是 | 包含 PDF 文件的目录 |

#### inject_obsidian_meta.py

```bash
python inject_obsidian_meta.py <source_md> <target_dir> [options]
```

| 参数 | 必需 | 说明 |
|------|------|------|
| source_md | ✅ 是 | 源 Markdown 文件路径 (用于提取元数据) |
| target_dir | ✅ 是 | 目标目录 (包含步骤文件和 Final 报告) |
| --use_pdf_vision | ❌ 否 | 启用 PDF 视觉元数据提取 |
| --pdf_dir | ❌ 否 | PDF 文件所在目录 (默认: "E:\\pdf\\001") |

#### deep_read_pipeline.py

```bash
python deep_read_pipeline.py <segmented_md_path> [--out_dir <dir>]
```

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| segmented_md_path | ✅ 是 | - | 分段后的 Markdown 文件路径 |
| --out_dir | ❌ 否 | deep_reading_results | 输出目录 |

#### smart_segment_router.py

```bash
python smart_segment_router.py <paddleocr_md_path> [--out_dir <dir>] [--mode <mode>]
```

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| paddleocr_md_path | ✅ 是 | - | PaddleOCR 提取的 Markdown 文件 |
| --out_dir | ❌ 否 | pdf_segmented_md | 分段输出目录 |
| --mode | ❌ 否 | auto | 分段模式: auto / quant / qual |

#### paddleocr_pipeline.py

```bash
python paddleocr_pipeline.py <pdf_path> [--out_dir <dir>] [--download_images]
```

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| pdf_path | ✅ 是 | - | PDF 文件路径 |
| --out_dir | ❌ 否 | paddleocr_md | Markdown 输出目录 |
| --download_images | ❌ 否 | False | 是否下载 PDF 图片 |

---

## 数据流转图

### 完整数据流

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 输入阶段                                                │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  PDF 文件 (E:\pdf\001\xxx.pdf)                             │
│  - 包含原始学术内容                                             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓ [paddleocr_pipeline.py]
┌─────────────────────────────────────────────────────────────────┐
│  PaddleOCR MD (paddleocr_md\xxx_paddleocr.md)                │
│  ---                                                          │
│  title: xxx                                                   │
│  extractor: paddleocr                                         │
│  ---                                                          │
│  ## 1. Introduction                                          │
│  ### 1.1 Background                                         │
│  ...                                                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓ [smart_segment_router.py]
┌─────────────────────────────────────────────────────────────────┐
│  Segmented MD (pdf_segmented_md\xxx_segmented.md)              │
│  # 论文原文结构化分段（Smart Router）                          │
│  - Mode: quant                                                │
│  ## 路由映射                                                  │
│  - 1: Overview                                               │
│  - 2: Theory                                                 │
│  ...                                                          │
│  ## 1. Overview (全景扫描)                                     │
│  ```text                                                      │
│  【原文：1. Introduction】                                    │
│  ...                                                          │
│  ```                                                          │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓ [smart_scholar_lib.classify_paper()]
┌─────────────────────────────────────────────────────────────────┐
│  论文类型分类 ("QUANT")                                      │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓ [deep_read_pipeline.py]
┌─────────────────────────────────────────────────────────────────┐
│  deep_reading_results/xxx/                                   │
│  ├── semantic_index.json                                     │
│  ├── section_routing.md                                      │
│  ├── 1_Overview.md                                         │
│  ├── 2_Theory.md                                           │
│  ├── 3_Data.md                                             │
│  ├── 4_Variables.md                                         │
│  ├── 5_Identification.md                                    │
│  ├── 6_Results.md                                           │
│  ├── 7_Critique.md                                          │
│  └── Final_Deep_Reading_Report.md                            │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓ [inject_obsidian_meta.py]
┌─────────────────────────────────────────────────────────────────┐
│  元数据注入后                                                │
│  ├── 1_Overview.md [已更新 frontmatter + 导航]               │
│  ├── 2_Theory.md [已更新 frontmatter + 导航]                 │
│  ...                                                          │
│  └── Final_Deep_Reading_Report.md [已更新 PDF 元数据]          │
└─────────────────────────────────────────────────────────────────┘
```

### 元数据流转

```
┌─────────────────────┐
│  MD 元数据提取      │
│  - YAML Frontmatter│
│  - 正文正则提取    │
└────────┬──────────┘
         │
         ↓
┌─────────────────────┐
│ md_metadata:       │
│ {                 │
│   title,          │
│   authors,        │
│   abstract,       │
│   keywords        │
│ }                 │
└────────┬──────────┘
         │
         │
         ┌────┴────┐
         │         │
         ↓         ↓
┌─────────────┐  ┌─────────────────┐
│ PDF 视觉提取 │  │ 合并 (PDF 优先) │
│ Qwen-vl-plus│  └────┬────────────┘
└──────┬──────┘       │
       │              │
       ↓              │
┌─────────────┐       │
│pdf_metadata:│       │
│ {           │       │
│  title,     │       │
│  authors,   │       │
│  journal,   │       │
│  year       │       │
│ }           │       │
└──────┬──────┘       │
       │              │
       └──────┬───────┘
              ↓
┌─────────────────────┐
│ merged_metadata:    │
│ {                 │
│   title (PDF),     │
│   authors (PDF),   │
│   journal (PDF),   │
│   year (PDF),      │
│   abstract (MD),    │
│   keywords (MD),    │
│   tags: [paper,    │
│          deep-      │
│          reading]   │
│ }                 │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
    ↓         ↓
┌────────┐ ┌──────────┐
│步骤文件  │ │Final 报告│
│完整元   │ │仅PDF元  │
│数据     │ │数据      │
└────────┘ └──────────┘
```

---

## 使用示例

### 完整批量处理

```bash
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 批量处理 PDF 目录
python run_batch_pipeline.py "E:\pdf\001"
```

**自动执行流程**:
1. 查找所有 PDF 文件
2. 去重检查 (MD5 哈希)
3. PDF → PaddleOCR MD (paddleocr_md/)
4. PaddleOCR MD → Segmented MD (pdf_segmented_md/)
5. 分类论文类型 (QUANT/QUAL/IGNORE)
6. QUANT → 7步精读 (deep_reading_results/xxx/)
7. QUAL → 4层金字塔 (social_science_results_v2/xxx/)
8. **QUANT 仅注入 Obsidian 元数据** (PDF 视觉 + 子章节摘要)
9. 更新状态管理器 (processed_papers.json)

### 单独测试元数据注入

```bash
# 不使用 PDF 视觉 (仅 MD 解析)
python inject_obsidian_meta.py \
  "paddleocr_md\xxx_paddleocr.md" \
  "deep_reading_results\xxx"

# 使用 PDF 视觉提取 (Qwen-vl-plus)
python inject_obsidian_meta.py \
  "paddleocr_md\xxx_paddleocr.md" \
  "deep_reading_results\xxx" \
  --use_pdf_vision \
  --pdf_dir "E:\pdf\001"
```

### 单独测试智能分段

```bash
# 自动检测模式
python smart_segment_router.py \
  "paddleocr_md\xxx_paddleocr.md" \
  --out_dir test_segmented

# 强制定量模式
python smart_segment_router.py \
  "paddleocr_md\xxx_paddleocr.md" \
  --out_dir test_segmented \
  --mode quant

# 强制定性模式
python smart_segment_router.py \
  "paddleocr_md\xxx_paddleocr.md" \
  --out_dir test_segmented \
  --mode qual
```

---

## 关键特性

### 1. 元数据注入层级

| 文件类型 | 注入内容 | 说明 |
|---------|---------|------|
| **步骤文件** (1-7_*.md) | MD 元数据 + PDF 元数据 + subsections 摘要 + 导航链接 | 完整 Obsidian 兼容 |
| **Final 报告** (Final_*.md) | 仅 PDF 元数据 | 标题、作者、期刊、年份 |

### 2. 导航链接结构

```
步骤文件 (1_Overview.md)
  ↓
【返回总报告：】 → [[Final_Deep_Reading_Report]]

Final 报告 (Final_Deep_Reading_Report.md)
  ↓
（无导航链接，保持简洁）
```

**注意**: 当前逻辑 Final 报告不添加导航链接（第 470 行已跳过）

### 3. Tags 自动管理

所有文件自动添加:
- `paper` - 标识为论文
- `deep-reading` - 标识为深度精读

### 4. 子章节摘要特性

- **长度限制**: 30 字以内中文
- **摘要方法**: DeepSeek-chat (temperature=0.3)
- **提取范围**: `###` 三级标题内容
- **最小长度**: 仅总结 ≥50 字符的章节

### 5. PDF 视觉提取

- **模型**: Qwen-vl-plus (通义千问视觉大模型)
- **提取页面**: 前 2 页
- **提取字段**: title, authors, journal, year
- **图片分辨率**: 200 DPI
- **触发条件**: `--use_pdf_vision` 参数

### 6. 去重机制

**方式 1**: MD5 哈希 (优先)
```python
state_mgr.is_processed(pdf_path)
```

**方式 2**: 文件名检查 (降级)
```python
os.path.exists("deep_reading_results/xxx/Final_Deep_Reading_Report.md")
os.path.exists("social_science_results_v2/xxx/xxx_Full_Report.md")
```

---

## 输出目录结构

### QUANT 论文 (定量)

```
deep_reading_results/
└── xxx/
    ├── semantic_index.json              # 语义索引 (处理分段不完整)
    ├── section_routing.md             # 章节→步骤映射记录
    ├── 1_Overview.md                # 步骤1: 全景扫描
    │   ├── frontmatter: title, authors, journal, year, tags, subsections
    │   └── 导航链接: [[Final_Deep_Reading_Report]]
    ├── 2_Theory.md                  # 步骤2: 理论与假说
    ├── 3_Data.md                    # 步骤3: 数据考古
    ├── 4_Variables.md              # 步骤4: 变量与测量
    ├── 5_Identification.md         # 步骤5: 识别策略
    ├── 6_Results.md                # 步骤6: 结果解读
    ├── 7_Critique.md               # 步骤7: 专家批判
    └── Final_Deep_Reading_Report.md # 总报告
        └── frontmatter: title, authors, journal, year, tags
```

### QUAL 论文 (定性)

```
social_science_results_v2/
└── xxx/
    ├── L1_Context.md               # 背景层
    ├── L2_Theory.md               # 理论层
    ├── L3_Logic.md                # 逻辑层
    ├── L4_Value.md               # 价值层
    └── xxx_Full_Report.md        # 总报告
```

### 中间文件

```
paddleocr_md/
└── xxx_paddleocr.md              # PaddleOCR 提取

pdf_segmented_md/
└── xxx_segmented.md              # 智能分段输出

pdf_raw_md/
└── xxx_raw.md                   # Legacy 提取 (降级)
```

---

## 故障排查

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| PaddleOCR 失败 | API 不可用 | 自动降级到 legacy 提取 |
| 元数据注入失败 | QWEN_API_KEY 未设置 | 在 `.env` 中配置 API Key |
| 分段不完整 | PDF 结构异常 | 自动使用语义索引兜底 |
| DeepSeek 调用失败 | DEEPSEEK_API_KEY 无效 | 检查 API Key 配置 |
| 编码错误 | Windows 控制台 | 不影响文件输出，可忽略 |

### 日志位置

| 脚本 | 日志级别 | 关键信息 |
|------|---------|---------|
| run_batch_pipeline.py | INFO | 处理进度、分类结果 |
| smart_segment_router.py | INFO | LLM 调用、路由映射 |
| deep_read_pipeline.py | INFO | 步骤执行进度 |
| inject_obsidian_meta.py | INFO | PDF 提取、子章节总结 |

---

## 新方案：Markdown 格式输出体系 (2026-02-03)

### 背景

为解决 JSON 格式输出的解析问题和稳定性问题，开发了新的直接 Markdown 输出方案。

### 核心变更

| 维度 | 旧方案 (JSON) | 新方案 (Markdown) |
|------|--------------|------------------|
| **输出格式** | 结构化 JSON | 直接 Markdown 文档 |
| **解析需求** | 需要 json_repair | 无需解析，直接可用 |
| **稳定性** | 可能出现格式错误 | 高度稳定 |
| **可读性** | 需要转换 | 直接可读 |
| **元数据提取** | JSON 键值对 | 正则表达式 `## 数字. 标题` |
| **人工审阅** | 需要工具 | 直接打开 MD |

### 提示词体系

#### L1_Context (背景层) - 6部分

```markdown
## 1. 论文分类
## 2. 核心问题
## 3. 政策文件
## 4. 现状数据
## 5. 理论重要性
## 6. 实践重要性
## 7. 关键文献
```

**提示词文件**: `prompts/qual_analysis/L1_Context_Prompt.md`

**特点**:
- 动态识别研究体裁 (Case Study / QCA / Review / Quantitative / Theoretical)
- 提取政策背景和现状数据
- 双重视角分析重要性 (理论+实践)

#### L2_Theory (理论层) - 6部分

```markdown
## 1. 经典理论回顾
## 2. 核心构念
## 3. 构念关系
## 4. 理论框架
## 5. 理论贡献
## 6. 详细分析
```

**提示词文件**: `prompts/qual_analysis/L2_Theory_Prompt.md`

**特点**:
- 使用表格呈现理论回顾和核心构念
- 梳理构念间的相互作用机制
- 构建理论框架并评估创新性

#### L3_Logic (逻辑层) - 11部分 (自适应体裁)

**Theoretical (理论构建) 格式**:
```markdown
## 1. 研究体裁
## 2. 逻辑类型
## 3. 核心问题
## 4. 概念体系
## 5. 逻辑推演
## 6. 模型构建
## 7. 命题提出
## 8. 理论贡献
## 9. 应用价值
## 10. 理论依据
## 11. 详细分析
```

**其他体裁格式**:
- **Case Study**: 关键阶段、整体流程、相互作用、因果关系、关键节点...
- **QCA**: 因果路径、条件组合、组间比较、路径效应、统计证据...
- **Quantitative**: 研究假设、变量关系、模型设定、回归结果、统计显著性...
- **Review**: 整合框架、理论谱系、演进阶段、跨域对话、发展趋势...

**提示词文件**: `prompts/qual_analysis/L3_Logic_Prompt.md`

**特点**:
- 根据 `{genre}` 变量动态调整输出格式
- 每种体裁 11 个核心部分
- 保持 `##` 统一标题格式

#### L4_Value (价值层) - 5部分

```markdown
## 1. 研究缺口
## 2. 学术贡献
## 3. 实践启示
## 4. 价值定位
## 5. 详细分析
## 6. 未来展望 (可选)
```

**提示词文件**: `prompts/qual_analysis/L4_Value_Prompt.md`

**特点**:
- 多维度分析研究缺口 (理论/方法/实践/数据)
- 分类归纳学术贡献 (理论/方法/实证/综合)
- 提供具体可操作的建议 (政策/实践/研究/技术)

### 测试报告

**测试时间**: 2026-02-03
**测试论文**: 类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径
**测试结果**: ✅ 全部通过

#### L1_Context 测试结果

- **输出文件**: test_output_qual/L1_Context_Analysis.md (71行)
- **格式验证**: ✅ 严格遵循 `## 数字. 标题` 格式
- **内容质量**:
  - ✅ 准确识别为 "Theoretical" 研究类型
  - ✅ 详细阐述核心问题的理论/实践维度
  - ✅ 提取关键政策文件 (党的二十大报告)
  - ✅ 提取 4 个关键现状数据项
  - ✅ 提供 200+ 字的重要性分析

#### L2_Theory 测试结果

- **输出文件**: test_output_qual/L2_Theory_Analysis.md (67行)
- **格式验证**: ✅ 使用表格增强可读性
- **内容质量**:
  - ✅ 经典理论回顾表格 (4个理论)
  - ✅ 核心构念表格 (5个构念)
  - ✅ 构念关系详细梳理 (4种关系类型)
  - ✅ 构建"技术赋能-条件约束-风险反思"三维框架
  - ✅ 400+ 字深入理论分析

#### L3_Logic 测试结果

- **输出文件**: test_output_qual/L3_Logic_Analysis.md (62行)
- **格式验证**: ✅ 完整的 11 部分结构
- **内容质量**:
  - ✅ 正确识别体裁为 "Theoretical"
  - ✅ 系统梳理概念体系 (驱动/制约/整合)
  - ✅ 清晰呈现"机遇-挑战-路径"三段式逻辑
  - ✅ 构建"技术赋能-风险制约-系统整合"模型
  - ✅ 500+ 字深入逻辑分析

#### L4_Value 测试结果

- **输出文件**: test_output_qual/L4_Value_Analysis.md (46行)
- **格式验证**: ✅ 5个核心部分完整
- **内容质量**:
  - ✅ 4维度研究缺口分析
  - ✅ 4类学术贡献归纳
  - ✅ 具体可操作的建议 (4大类)
  - ✅ 全面价值定位评估
  - ✅ 300+ 字综合价值分析

### 关键优势

#### 1. 格式稳定

所有层级严格遵循 `## 数字. 标题` 格式，便于元数据提取：

```python
import re

def extract_metadata(md_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取所有二级标题
    sections = re.findall(r'^##\s+(\d+)\.\s+(.+)$', content, re.MULTILINE)
    
    # 返回结构化数据
    return {num: title for num, title in sections}
```

#### 2. 无需 JSON 解析

**旧方案问题**:
```python
# 可能失败
result = json_repair.repair_json(llm_output, return_objects=True)
# ❌ "Expecting property name enclosed in double quotes"
# ❌ "Extra data"
# ❌ "No JSON found"
```

**新方案优势**:
```python
# 直接可用
with open('L1_Context_Analysis.md', 'r', encoding='utf-8') as f:
    result = f.read()
# ✅ 无需解析，直接是 Markdown
```

#### 3. 元数据友好

统一的标题格式便于后续处理：

```python
# 提取核心问题
def extract_core_issue(md_content):
    match = re.search(r'## 2\. 核心问题\s*\n+(.+?)(?=##|\Z)', 
                      md_content, re.DOTALL)
    return match.group(1).strip() if match else None

# 提取政策文件
def extract_policies(md_content):
    match = re.search(r'## 3\. 政策文件\s*\n+(.+?)(?=##|\Z)', 
                      md_content, re.DOTALL)
    return match.group(1).strip() if match else None
```

#### 4. 用户友好

- **直接可读**: 无需任何工具转换
- **人工审阅**: 打开即看，一目了然
- **版本控制**: Git diff 友好
- **便于分享**: 直接发送 MD 文件

### 技术实现

#### 动态提示词加载

```python
def load_prompt(layer_name):
    """动态载入对应层的提示词"""
    prompt_path = f"prompts/qual_analysis/{layer_name}_Prompt.md"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()
```

#### 体裁自适应

```python
# L3 Logic 层需要知道研究体裁
if layer_code == "L3":
    genre = detect_genre_from_content(content)  # "Theoretical", "Case Study", etc.
    prompt = load_prompt("L3_Logic").replace("{genre}", genre)
```

#### Markdown 格式强制

```python
system_prompt = f"""{loaded_prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。
直接输出Markdown格式的结构化内容即可。
"""
```

### 下一步整合计划

#### 阶段 1: 更新 QUAL 分析器 (当前优先级)

**文件**: `social_science_analyzer.py`

**修改内容**:

1. **移除 JSON 解析逻辑**
   ```python
   # 旧代码 (第 150-180 行)
   result = json_repair.repair_json(content, return_objects=True)
   
   # 新代码
   result = content  # 直接使用 Markdown
   ```

2. **更新提示词路径**
   ```python
   # 旧代码 (内联提示词)
   system_prompt = """You are a Social Science..."""
   
   # 新代码
   system_prompt = load_prompt(f"{layer}_Prompt")
   ```

3. **调整输出保存**
   ```python
   # 保存为 Markdown
   with open(output_path, 'w', encoding='utf-8') as f:
       f.write(result)  # 直接写入，无需 JSON 序列化
   ```

4. **L3 体裁检测**
   ```python
   # 从 L1 结果中获取体裁
   genre = l1_result.get("genre", "Theoretical")
   
   # 或从内容推断
   genre = detect_genre_from_paper(segmented_md_path)
   ```

**预期工作量**: 2-3 小时

#### 阶段 2: 开发元数据提取工具

**新文件**: `qual_metadata_extractor.py`

**功能**:

```python
import re
import yaml

class QualMetadataExtractor:
    """从 QUAL 分析 Markdown 中提取结构化元数据"""
    
    def extract_all_layers(self, paper_name):
        """提取所有 4 层的元数据"""
        return {
            "L1_Context": self.extract_l1(paper_name),
            "L2_Theory": self.extract_l2(paper_name),
            "L3_Logic": self.extract_l3(paper_name),
            "L4_Value": self.extract_l4(paper_name)
        }
    
    def extract_l1(self, paper_name):
        """提取 L1 元数据"""
        path = f"social_science_results_v2/{paper_name}/L1_Context.md"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "genre": self._extract_section(content, 1),
            "core_issue": self._extract_section(content, 2),
            "policies": self._extract_section(content, 3),
            "status_data": self._extract_section(content, 4),
            "theoretical_importance": self._extract_section(content, 5),
            "practical_importance": self._extract_section(content, 6)
        }
    
    def _extract_section(self, content, section_num):
        """提取指定章节内容"""
        pattern = rf'## {section_num}\. .+?\n+(.+?)(?=##\s*\d+\.|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else None
```

**使用示例**:

```python
extractor = QualMetadataExtractor()
metadata = extractor.extract_all_layers("类ChatGPT人工智能技术赋能乡村文化振兴")

# 输出 JSON
import json
with open("metadata.json", 'w', encoding='utf-8') as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)
```

**预期工作量**: 1-2 小时

#### 阶段 3: 生成总报告

**新文件**: `generate_qual_full_report.py`

**功能**:

```python
def generate_full_report(paper_name):
    """生成完整的 QUAL 分析总报告"""
    layers = {
        "L1_Context.md",
        "L2_Theory.md",
        "L3_Logic.md",
        "L4_Value.md"
    }
    
    output_path = f"social_science_results_v2/{paper_name}/{paper_name}_Full_Report.md"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Qualitative Deep Reading Report: {paper_name}\n\n")
        
        for layer_file in sorted(layers):
            layer_path = f"social_science_results_v2/{paper_name}/{layer_file}"
            with open(layer_path, 'r', encoding='utf-8') as lf:
                content = lf.read()
                
                # 移除 frontmatter (如果有)
                content = remove_frontmatter(content)
                
                # 添加到总报告
                f.write(f"## {layer_file.replace('.md', '')}\n\n")
                f.write(content + "\n\n---\n\n")
```

**预期工作量**: 1 小时

#### 阶段 4: 集成到批量流水线

**文件**: `run_batch_pipeline.py`

**修改内容**:

1. **QUAL 路由调用新分析器**
   ```python
   if paper_type == "QUAL":
       # 调用更新后的分析器
       from social_science_analyzer_v2 import SocialScienceAnalyzerV2
       
       analyzer = SocialScienceAnalyzerV2()
       analyzer.run_full_analysis(seg_md_path, paper_output_dir)
       
       # 生成总报告
       from generate_qual_full_report import generate_full_report
       generate_full_report(paper_name)
   ```

2. **添加元数据提取步骤**
   ```python
   if paper_type == "QUAL":
       # 运行 4 层分析...
       
       # 提取元数据
       from qual_metadata_extractor import QualMetadataExtractor
       extractor = QualMetadataExtractor()
       metadata = extractor.extract_all_layers(paper_name)
       
       # 保存为 JSON (用于搜索/索引)
       metadata_path = f"{paper_output_dir}/metadata.json"
       with open(metadata_path, 'w', encoding='utf-8') as f:
           json.dump(metadata, f, ensure_ascii=False, indent=2)
   ```

**预期工作量**: 1-2 小时

#### 阶段 5: Obsidian 元数据注入 (扩展)

**文件**: `inject_obsidian_meta.py`

**新增功能**:

```python
def inject_qual_metadata(source_md, target_dir):
    """为 QUAL 分析注入 Obsidian 元数据"""
    
    # 1. 提取 PDF 元数据 (复用现有逻辑)
    pdf_metadata = extract_metadata_from_pdf_images(pdf_path)
    
    # 2. 为每个层级文件注入
    layers = ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
    
    for layer in layers:
        layer_file = f"{target_dir}/{layer}.md"
        
        with open(layer_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 注入 frontmatter
        new_content = inject_frontmatter(content, pdf_metadata)
        
        # 添加导航链接
        new_content = add_qual_navigation_links(new_content, layer, layers)
        
        with open(layer_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
```

**预期工作量**: 2 小时

### 实施优先级

| 阶段 | 优先级 | 工作量 | 依赖 | 预计完成时间 |
|------|--------|--------|------|-------------|
| 1. 更新 QUAL 分析器 | 🔴 高 | 2-3h | 无 | 第1天 |
| 2. 开发元数据提取工具 | 🟡 中 | 1-2h | 阶段1 | 第2天 |
| 3. 生成总报告 | 🟡 中 | 1h | 阶段1 | 第2天 |
| 4. 集成到批量流水线 | 🟢 低 | 1-2h | 阶段1,2,3 | 第3天 |
| 5. Obsidian 元数据注入 | 🟢 低 | 2h | 阶段1,2,3 | 第3天 |

**总计**: 约 7-10 小时开发工作量

### 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| LLM 不严格遵循格式 | 中 | 高 | 增加系统提示词强调 + 后处理验证 |
| 体裁识别错误 | 低 | 中 | L1 结果中显式输出体裁供人工确认 |
| 元数据提取失败 | 低 | 低 | 提供降级方案 (返回原始 MD) |
| 总报告格式混乱 | 低 | 低 | 使用模板严格格式化 |

---

## 版本历史

### v2.1 (计划中) - Markdown 格式输出

**计划新增**:
- 📋 QUAL 分析器 Markdown 输出
- 📋 元数据提取工具
- 📋 QUAL 总报告生成
- 📋 Obsidian 元数据注入扩展

### v2.0 (2026-02-03)

**新增功能**:
- ✅ 集成 PDF 视觉元数据提取 (Qwen-vl-plus)
- ✅ 自动子章节摘要生成 (DeepSeek 30字中文)
- ✅ 区分步骤文件与 Final 报告的元数据注入策略
- ✅ 双向导航链接系统
- ✅ Tags 自动管理 (paper, deep-reading)

**改进**:
- 🔧 移除 dataview 注入步骤 (简化流程)
- 🔧 修复 pymupdf API 调用 (`tobyte` → `tobytes`)
- 🔧 支持 markdown 代码块 JSON 解析

**性能**:
- 🚀 Token 消耗降低 (LLM 只分类标题，不切分内容)
- 🚀 内容完整性 100% (代码直接切分，不经过 LLM)

### v1.0 (2026-02-02)

**初始版本**:
- ✅ 智能分段路由 (SmartSegmentRouter)
- ✅ 论文类型自动分类 (QUANT/QUAL)
- ✅ 批量处理流水线
- ✅ MD5 哈希去重

---

## 附录

### A. 文件依赖关系图

```
run_batch_pipeline.py
  ├── smart_scholar_lib.py
  │   ├── paddleocr_pipeline.py
  │   │   └── paddleocr_extractor/
  │   ├── smart_segment_router.py
  │   └── state_manager.py
  ├── deep_read_pipeline.py
  │   ├── deep_reading_steps/
  │   │   ├── common.py
  │   │   ├── step_1_overview.py
  │   │   ├── ...
  │   │   └── step_7_critique.py
  │   └── deep_reading_steps/semantic_router.py
  └── inject_obsidian_meta.py
      ├── pymupdf
      └── openai (DeepSeek + Qwen)
```

### B. 关键配置文件

**.env**:
```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
PADDLEOCR_REMOTE_URL=https://your-paddleocr-api
PADDLEOCR_REMOTE_TOKEN=your-paddleocr-token
```

**processed_papers.json**:
```json
{
  "pdf_hash_abc123": {
    "pdf_path": "E:\\pdf\\001\\xxx.pdf",
    "output_dir": "deep_reading_results\\xxx",
    "type": "QUANT",
    "timestamp": "2026-02-03T10:30:00"
  }
}
```

### C. LLM 模型使用

| 任务 | 模型 | 温度 | 用途 |
|------|------|------|------|
| 论文分类 | deepseek-chat | 0.0 | QUANT/QUAL/IGNORE |
| 标题分类 | deepseek-chat | 0.0 | 章节 → 步骤映射 |
| 7步精读 | deepseek-reasoner | 0.7 | 深度分析 |
| 子章节总结 | deepseek-chat | 0.3 | 30字中文摘要 |
| PDF 元数据 | qwen-vl-plus | 0.0 | 视觉识别 |

---

**文档结束**

*最后更新: 2026-02-03*
*维护者: Deep Reading Agent Team*
