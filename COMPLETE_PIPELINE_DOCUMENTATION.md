# Deep Reading Agent 完整技术文档

**创建时间**: 2026-02-04  
**版本**: v2.0 (双路径完整版)  
**状态**: ✅ 生产就绪

---

## 目录

1. [系统概述](#系统概述)
2. [双路径架构](#双路径架构)
3. [通用流程（步骤1-3）](#通用流程步骤1-3)
4. [QUANT 路径（步骤4-6）](#quant-路径步骤4-6)
5. [QUAL 路径（步骤4-6）](#qual-路径步骤4-6)
6. [模块详解](#模块详解)
7. [测试指南](#测试指南)

---

## 系统概述

### 功能说明

本系统实现了学术论文的**自动化深度分析流水线**，支持**定量（QUANT）**和**定性（QUAL）**两种论文类型的智能识别与分流处理。

### 核心特性

- ✅ **智能类型识别**：自动判断论文是定量还是定性
- ✅ **双路径分析**：定量走7步精读，定性走4层金字塔
- ✅ **元数据自动提取**：PDF视觉提取 + MD内容总结
- ✅ **Obsidian 注入**：生成兼容 Obsidian Dataview 的文件
- ✅ **去重管理**：MD5哈希避免重复处理

### 支持的论文类型

| 类型 | 判定标准 | 分析方法 | 输出结构 |
|------|---------|---------|---------|
| **QUANT** (定量) | 回归、IV/DID/RDD、计量模型、系数、稳健性检验 | 7步精读法 | 1-7_*.md + Final_Report.md |
| **QUAL** (定性) | 案例研究、理论构建、QCA、扎根理论、访谈 | 4层金字塔 | L1-L4.md + Full_Report.md |
| **IGNORE** (忽略) | 编者按、目录、会议通知、书评 | 不处理 | - |

---

## 双路径架构

### 完整流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                    run_batch_pipeline.py                      │
│                    (批量入口，任务调度)                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│                      smart_scholar_lib.py                      │
│              (SmartScholar: 核心调度器)                         │
│  - ensure_segmented_md()    # 提取 + 分段 (auto模式)           │
│  - classify_paper()         # 类型分类                        │
│  - run_command()            # 子进程调用                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────────┐
│              通用流程（步骤 1-3）                                │
│                                                                  │
│  步骤 1: PDF → Markdown 提取                                    │
│    ├─ PaddleOCR (推荐，远程API)                                 │
│    └─ pdfplumber (降级，本地)                                   │
│                                                                  │
│  步骤 2: Markdown → 分段 Markdown (auto模式)                   │
│    ├─ 自动检测论文类型 (quant/qual)                            │
│    ├─ quant → 7步分段 (1-7)                                    │
│    └─ qual → 4层分段 (L1-L4)                                   │
│                                                                  │
│  步骤 3: 论文类型分类 (再次确认)                                │
│    └─ LLM判断: "QUANT" / "QUAL" / "IGNORE"                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ↓                               ↓
┌──────────────────────┐    ┌──────────────────────┐
│   QUANT 路径          │    │   QUAL 路径          │
│  (定量论文)           │    │  (定性论文)           │
└──────────┬───────────┘    └──────────┬───────────┘
           │                             │
           ↓                             ↓
┌──────────────────────┐    ┌──────────────────────┐
│ 步骤 4: 7步精读       │    │ 步骤 4: 4层金字塔     │
│ deep_read_pipeline.py│    │ social_science_      │
│                      │    │   _analyzer_v2.py    │
│ - Step 1: Overview   │    │ - L1: Context        │
│ - Step 2: Theory     │    │ - L2: Theory         │
│ - Step 3: Data       │    │ - L3: Logic          │
│ - Step 4: Variables  │    │ - L4: Value          │
│ - Step 5: Identification│    │ (体裁自适应)        │
│ - Step 6: Results    │    │                      │
│ - Step 7: Critique   │    │                      │
└──────────┬───────────┘    └──────────┬───────────┘
           │                             │
           ↓                             ↓
┌──────────────────────┐    ┌──────────────────────┐
│ 步骤 5: 元数据提取    │    │ 步骤 5: 元数据提取    │
│ inject_obsidian_meta │    │ qual_metadata_        │
│       .py            │    │   _extractor/        │
│                      │    │                      │
│ - MD解析 (YAML+正则) │    │ - MD提取 (DeepSeek)  │
│ - PDF视觉 (Qwen)     │    │ - PDF视觉 (Qwen)     │
│ - 子章节提取 (###)   │    │ - 子章节提取 (## 数字.)│
│ - 子章节总结 (30字)  │    │ - 子章节总结 (30字)  │
└──────────┬───────────┘    └──────────┬───────────┘
           │                             │
           ↓                             ↓
┌──────────────────────┐    ┌──────────────────────┐
│ 步骤 6: 元数据注入    │    │ 步骤 6: 元数据注入    │
│                      │    │                      │
│ deep_reading_results/│    │ social_science_      │
│   论文名/            │    │   _results_v2/       │
│   论文名/            │    │   论文名/             │
│                      │    │                      │
│ ├─ 1_Overview.md    │    │ ├─ L1_Context.md     │
│ ├─ 2_Theory.md      │    │ ├─ L2_Theory.md      │
│ ├─ 3_Data.md        │    │ ├─ L3_Logic.md       │
│ ├─ 4_Variables.md   │    │ ├─ L4_Value.md       │
│ ├─ 5_Identification │    │ └─ xxx_Full_Report.md│
│ ├─ 6_Results.md     │    │                      │
│ ├─ 7_Critique.md    │    │ 每个文件:            │
│ └─ Final_*.md       │    │ ├─ PDF元数据 (基础)  │
│                      │    │ ├─ 自己的子章节 (扁平)│
│ 每个文件:            │    │ └─ 导航链接          │
│ ├─ PDF元数据 (基础)  │    │                      │
│ ├─ 子章节摘要 (嵌套) │    │                      │
│ └─ 导航链接          │    │                      │
└──────────────────────┘    └──────────────────────┘
```

---

## 通用流程（步骤1-3）

### 步骤 1: PDF → Markdown 提取

**文件**: `paddleocr_pipeline.py` (主) / `anthropic_pdf_extract_raw.py` (降级)

**核心方法**:
```python
def extract_pdf_with_paddleocr(
    pdf_path: str,
    out_dir: str = "paddleocr_md"
) -> dict
```

**输出**: `paddleocr_md/xxx_paddleocr.md`

**格式**:
```markdown
---
title: 论文标题
extractor: paddleocr
abstract: 摘要
keywords: [关键词]
---

## 1. Introduction
### 1.1 Background
内容...
```

**环境变量**:
```env
PADDLEOCR_REMOTE_URL=https://your-api-endpoint
PADDLEOCR_REMOTE_TOKEN=your-token
```

---

### 步骤 2: Markdown → 分段 Markdown (auto模式)

**文件**: `smart_segment_router.py`

**核心类**: `SmartSegmentRouter`

**分段定义**:

#### QUANT (定量) - 7步分段

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

#### QUAL (定性) - 4层分段

```python
QUAL_STEPS = {
    "L1": "L1_Context (背景层) - 摘要、引言、政策背景、现状数据",
    "L2": "L2_Theory (理论层) - 文献综述、理论框架、核心构念",
    "L3": "L3_Logic (逻辑层) - 方法设计、案例分析、机制路径、实证结果",
    "L4": "L4_Value (价值层) - 结论、讨论、研究缺口、理论贡献、实践启示"
}
```

**自动检测逻辑**:
```python
def _detect_paper_type(self, headings: List[str]) -> str:
    """根据标题内容自动检测论文类型"""
    heading_text = ' '.join(headings).lower()
    
    quant_keywords = ['regression', 'ols', 'did', 'iv', 'rdd', 'panel data', 
                     'robustness', 'endogeneity', '系数', '回归', '稳健性',
                     '实证分析', '计量模型', '内生性']
    
    qual_keywords = ['case study', 'grounded theory', 'qca', 'qualitative',
                    'interview', '案例研究', '扎根理论', '访谈', '质性研究']
    
    quant_score = sum(1 for k in quant_keywords if k in heading_text)
    qual_score = sum(1 for k in qual_keywords if k in heading_text)
    
    return "quant" if quant_score >= qual_score else "qual"
```

**输出**: `pdf_segmented_md/xxx_segmented.md`

**格式 (QUANT)**:
```markdown
# 论文原文结构化分段（Smart Router）

- Mode: quant

## 路由映射
- 1: Overview
- 2: Theory
- 3: Data
- 4: Variables
- 5: Identification
- 6: Results
- 7: Critique

## 1. Overview (全景扫描)
【原文：1. Introduction】
...

## 2. Theory (理论与假说)
【原文：2. Literature Review】
...
```

**格式 (QUAL)**:
```markdown
# 论文原文结构化分段（Smart Router）

- Mode: qual

## 路由映射
- L1: Context
- L2: Theory
- L3: Logic
- L4: Value

## L1: Context (背景层)
【原文：1. Introduction】
...

## L2: Theory (理论层)
【原文：2. Literature Review】
...
```

---

### 步骤 3: 论文类型分类 (再次确认)

**文件**: `smart_scholar_lib.py`

**方法**: `SmartScholar.classify_paper()`

**System Prompt**:
```
你是学术编辑。将论文分类为以下三类：

1. "QUANT": 定量经济学/计量经济学/实证金融
   - 关键词: Regression, Identification, DID, IV, RDD, Stata, Equation, 
              Robustness, Coefficients
   - 风格: 数学化、统计、假设检验

2. "QUAL": 定性社会科学/管理学/案例研究/文献综述
   - 关键词: Case Study, Grounded Theory, QCA, Semi-structured Interview,
              Theoretical Framework, Construct, Mechanism, Literature Review
   - 风格: 叙述性、理论化、概念化、过程模型

3. "IGNORE": 非研究内容/编者按/元数据
   - 关键词: Host's Introduction, Editor's Note, Preface, Table of Contents

输出: {"type": "QUANT" | "QUAL" | "IGNORE", "reason": "简短说明"}
```

**输入**: `*_segmented.md` 的前 5000 字符
**输出**: `"QUANT"` / `"QUAL"` / `"IGNORE"`

---

## QUANT 路径（步骤4-6）

### 步骤 4: 7步精读分析

**文件**: `deep_read_pipeline.py`

**核心逻辑**:
```python
# 加载分段
sections = common.load_segmented_md(segmented_md_path)

# 生成语义索引
semantic_index = generate_semantic_index(full_text)

# 路由章节到步骤
section_routing = common.route_sections_to_steps(sections, semantic_index)

# 执行7步分析
step_1_overview.run(sections, section_routing.get(1, []), paper_output_dir, step_id=1)
step_2_theory.run(sections, section_routing.get(2, []), paper_output_dir, step_id=2)
step_3_data.run(sections, section_routing.get(3, []), paper_output_dir, step_id=3)
step_4_vars.run(sections, section_routing.get(4, []), paper_output_dir, step_id=4)
step_5_identification.run(sections, section_routing.get(5, []), paper_output_dir, step_id=5)
step_6_results.run(sections, section_routing.get(6, []), paper_output_dir, step_id=6)
step_7_critique.run(sections, section_routing.get(7, []), paper_output_dir, step_id=7)
```

**输出目录**: `deep_reading_results/论文名/`

**输出文件**:
```
1_Overview.md
2_Theory.md
3_Data.md
4_Variables.md
5_Identification.md
6_Results.md
7_Critique.md
```

**每步输出格式** (以 1_Overview.md 为例):
```markdown
### **1. 研究主题与核心结论**
本文以中国茶农为研究对象...

### **2. 问题意识**
本文旨在解决的科学问题是...

### **3. 重要性**
...

### **4. 贡献定位**
...
```

---

### 步骤 5: 元数据提取 (QUANT)

**文件**: `inject_obsidian_meta.py`

**子章节提取**:
```python
def extract_subsections(content: str) -> dict:
    """提取 ### 三级标题"""
    subsections = {}
    current_title = None
    current_content = []
    
    for line in content.split('\n'):
        if line.startswith('### '):
            if current_title:
                subsections[current_title] = '\n'.join(current_content).strip()
            current_title = line[4:].strip()
            current_content = []
        else:
            if current_title:
                current_content.append(line)
    
    return subsections
```

**输出示例**:
```python
{
    "**1. 研究主题与核心结论**": "本文以中国茶农为研究对象...",
    "**2. 问题意识**": "本文旨在解决的科学问题是...",
    "**3. 重要性**": "严格评估电商支持项目...",
    "**4. 贡献定位**": "本文首次实证研究公共电商平台..."
}
```

**子章节总结 (DeepSeek 30字)**:
```python
def summarize_with_deepseek(title: str, text: str) -> str:
    prompt = f"""请将以下内容总结为30字以内的一句话：
标题：{title}
内容：{text}

要求：
- 中文输出
- 30字以内
- 抓住核心要点
"""
    # ... DeepSeek API 调用
    return summary
```

---

### 步骤 6: 元数据注入 (QUANT)

**文件**: `inject_obsidian_meta.py`

**注入格式**:
```markdown
---
title: Digital revitalization or useless effort?
authors:
- Xintong Han
- Jan Victor Dee
journal: Journal of Development Economics
year: '2026'
tags:
- paper
- deep-reading
subsections:
  '**1. 研究主题与核心结论**': 电商平台使茶农销售从线下转至线上，但未显著提升总销售额。
  '**2. 问题意识**': 政府电商项目对小农户销售行为的影响：优化渠道而非创造新需求。
  '**3. 重要性**': 严格评估电商支持项目，避免资源错配，理解其作用机制。
  '**4. 贡献定位**': 本文首次实证研究公共电商平台对生产者的影响。
---

### **1. 研究主题与核心结论**
本文以中国茶农为研究对象...

## 导航 (Navigation)

**返回总报告：** [[Final_Deep_Reading_Report]]
```

---

## QUAL 路径（步骤4-6）

### 步骤 4: 4层金字塔分析

**文件**: `social_science_analyzer_v2.py`

**核心类**: `SocialScienceAnalyzerV2`

**关键特性**:
- ✅ 直接 Markdown 输出（无需 JSON 解析）
- ✅ 动态加载外部提示词文件
- ✅ L3 层体裁自适应
- ✅ 自动体裁提取

**分析流程**:
```python
# 加载分段
with open(seg_md_path, 'r', encoding='utf-8') as f:
    segmented_md = f.read()

# L1: 背景层分析
l1_text = extract_layer_text(segmented_md, "L1")
l1_markdown = analyzer.analyze_l1_context(l1_text)

# L2: 理论层分析
l2_text = extract_layer_text(segmented_md, "L2")
l2_markdown = analyzer.analyze_l2_theory(l2_text)

# L3: 逻辑层分析 (体裁自适应)
genre = analyzer._extract_genre_from_l1_markdown(l1_markdown)
l3_text = extract_layer_text(segmented_md, "L3")
l3_markdown = analyzer.analyze_l3_logic(l3_text, genre=genre)

# L4: 价值层分析
l4_text = extract_layer_text(segmented_md, "L4")
l4_markdown = analyzer.analyze_l4_value(l4_text)

# 生成总报告
full_report = analyzer.generate_full_report(
    l1_markdown, l2_markdown, l3_markdown, l4_markdown,
    paper_basename, paper_output_dir
)
```

**输出目录**: `social_science_results_v2/论文名/`

**输出文件**:
```
L1_Context.md
L2_Theory.md
L3_Logic.md
L4_Value.md
论文名_Full_Report.md
```

**L3 体裁自适应**:

| 体裁 | 格式特点 | 特殊章节 |
|------|---------|---------|
| **Theoretical** | 理论构建 | 概念体系、逻辑推演、模型构建、命题提出 |
| **Case Study** | 案例研究 | 关键阶段、整体流程、相互作用、因果关系 |
| **QCA** | 定性比较分析 | 因果路径、条件组合、组间比较、路径效应 |
| **Quantitative** | 定量研究 | 研究假设、变量关系、模型设定、回归结果 |
| **Review** | 文献综述 | 整合框架、理论谱系、演进阶段、跨域对话 |

---

### 步骤 5: 元数据提取 (QUAL)

**目录**: `qual_metadata_extractor/`

**文件结构**:
```
qual_metadata_extractor/
├── __init__.py
├── extractor.py         # 主流程
├── md_extractor.py      # MD 提取
├── pdf_extractor.py     # PDF 提取
├── merger.py            # 元数据合并
└── injector.py          # Frontmatter 注入
```

**第一次提取：从 MD 报告中提取**

**文件**: `md_extractor.py`

**提取逻辑**:
```python
def extract_sections_from_markdown(md_content: str) -> dict:
    """提取 ## 数字. 标题 格式的章节"""
    sections = {}
    for line in md_content.split('\n'):
        match = re.match(r'^##\s+(\d+)\.\s+(.+)$', line)
        if match:
            current_num = match.group(1)
            current_title = match.group(2).strip()
            # ... 提取内容
    return sections
```

**DeepSeek 30字总结**:
```python
def summarize_section_with_deepseek(client, title: str, content: str) -> str:
    prompt = f"""请将以下内容总结为30字以内的一句话：
标题：{title}
内容：{content}
"""
    # ... DeepSeek API 调用
    return summary
```

**输出示例**:
```python
{
    "L1_Context": {
        "1. 论文分类": "本文构建类ChatGPT技术赋能乡村文化振兴的理论分析框架。",
        "2. 核心问题": "本文探讨类ChatGPT技术如何为乡村文化振兴带来机遇与挑战。",
        "3. 政策文件": "党的二十大报告提出精细化服务理念。",
        "4. 现状数据": "ChatGPT月活破亿，算力消耗巨大。",
        "5. 理论重要性": "本研究拓展了技术社会学与乡村文化振兴理论。",
        "6. 实践重要性": "本研究为政府、基层实践者提供决策参考。",
        "7. 关键文献": "关键文献从技术范式、实时检索、艺术应用等方面进行分析。"
    },
    "L2_Theory": {
        "1. 经典理论回顾": "本研究运用技术接受模型和数字鸿沟理论进行分析。",
        "2. 核心构念": "本研究探讨类ChatGPT技术如何赋能乡村文化振兴。",
        "3. 构念关系": "数字基础设施、农民素养、内容适配性促进技术赋能。",
        "4. 理论框架": "该论文构建了"机遇-挑战-条件"辩证框架。",
        "5. 理论贡献": "本研究拓展了技术接受与数字鸿沟理论。",
        "6. 详细分析": "该论文构建了技术赋能乡村文化的系统框架。"
    },
    "L3_Logic": {
        "2. 逻辑类型": "论文以辩证逻辑构建类ChatGPT赋能乡村文化振兴的系统理论。",
        "3. 核心问题": "探究ChatGPT类技术赋能乡村文化振兴的机遇、挑战与路径。",
        # ...
    },
    "L4_Value": {
        "1. 研究缺口": "研究在理论、方法、实践及数据制度层面存在缺口。",
        "2. 学术贡献": "该文构建了AI赋能乡村文化振兴的系统分析框架。",
        # ...
    }
}
```

---

### 步骤 6: 元数据注入 (QUAL)

**元数据合并策略**:
```python
# 创建基础元数据 (PDF + tags)
base_metadata = {
    "title": pdf_metadata.get("title", ""),
    "authors": pdf_metadata.get("authors", []),
    "journal": pdf_metadata.get("journal", ""),
    "year": pdf_metadata.get("year", ""),
    "tags": ["paper", "qual", "deep-reading"]
}

# 为每个层级创建元数据 (基础 + 自己的子章节，扁平结构)
layer_metadata = base_metadata.copy()
layer_metadata.update(subsections)  # 直接合并到顶层
```

**注入格式 (L1_Context.md)**:
```markdown
---
title: 类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径
authors:
- 曹银山
- 邹照斌
journal: 中国学术期刊电子出版物
year: '2024'
tags:
- paper
- qual
- deep-reading
1. 论文分类: 本文构建类ChatGPT技术赋能乡村文化振兴的理论分析框架。
2. 核心问题: 本文探讨类ChatGPT技术如何为乡村文化振兴带来机遇与挑战。
3. 政策文件: 党的二十大报告提出精细化服务理念。
4. 现状数据: ChatGPT月活破亿，算力消耗巨大。
5. 理论重要性: 本研究拓展了技术社会学与乡村文化振兴理论。
6. 实践重要性: 本研究为政府、基层实践者提供决策参考。
7. 关键文献: 关键文献从技术范式、实时检索、艺术应用等方面进行分析。
---

## 1. 论文分类
**Theoretical** (理论构建)...

## 导航

**返回总报告**：[[类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径_Full_Report]]

**其他层级**：
- [[L2_Theory]]
- [[L3_Logic]]
- [[L4_Value]]
```

**注入格式 (Full_Report.md)**:
```markdown
---
title: 类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径
authors:
- 曹银山
- 邹照斌
journal: 中国学术期刊电子出版物
year: '2024'
tags:
- paper
- qual
- deep-reading
---

# 社会科学深度阅读报告：类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径
...
```

---

## 模块详解

### 核心脚本对照表

| 功能模块 | 文件 | 输入 | 输出 | 说明 |
|---------|------|------|------|------|
| **通用** | | | | |
| 批量入口 | run_batch_pipeline.py | pdf_dir | - | 遍历PDF目录，智能分流 |
| 核心调度 | smart_scholar_lib.py | pdf_path | seg_md_path | 提取+分段+分类 |
| PDF提取 | paddleocr_pipeline.py | pdf_path | *_paddleocr.md | 远程API，推荐 |
| PDF提取(降级) | anthropic_pdf_extract_raw.py | pdf_path | *_raw.md | 本地pdfplumber |
| 智能分段 | smart_segment_router.py | *_paddleocr.md | *_segmented.md | auto模式自动检测 |
| **QUANT路径** | | | | |
| 7步精读 | deep_read_pipeline.py | *_segmented.md | 1-7_*.md | 分步分析 |
| Step 1 | deep_reading_steps/step_1_overview.py | sections | 1_Overview.md | 全景扫描 |
| Step 2 | deep_reading_steps/step_2_theory.py | sections | 2_Theory.md | 理论与假说 |
| Step 3 | deep_reading_steps/step_3_data.py | sections | 3_Data.md | 数据考古 |
| Step 4 | deep_reading_steps/step_4_vars.py | sections | 4_Variables.md | 变量与测量 |
| Step 5 | deep_reading_steps/step_5_identification.py | sections | 5_Identification.md | 识别策略 |
| Step 6 | deep_reading_steps/step_6_results.py | sections | 6_Results.md | 结果解读 |
| Step 7 | deep_reading_steps/step_7_critique.py | sections | 7_Critique.md | 专家批判 |
| 元数据注入 | inject_obsidian_meta.py | source_md, target_dir | 更新的MD | ### 子章节 + PDF元数据 |
| **QUAL路径** | | | | |
| 4层分析 | social_science_analyzer_v2.py | *_segmented.md | L1-L4.md | 体裁自适应 |
| 元数据提取 | qual_metadata_extractor/extractor.py | paper_dir, pdf_dir | 更新的MD | ## 子章节 + PDF元数据 |
| MD提取 | qual_metadata_extractor/md_extractor.py | L*.md | 子章节摘要 | DeepSeek 30字 |
| PDF提取 | qual_metadata_extractor/pdf_extractor.py | pdf_path | PDF元数据 | Qwen-vl-plus |
| 元数据合并 | qual_metadata_extractor/merger.py | md, pdf | 合并元数据 | 扁平结构 |
| Frontmatter注入 | qual_metadata_extractor/injector.py | content, metadata | 更新的MD | YAML + 导航 |

---

## 测试指南

### 环境配置

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
PADDLEOCR_REMOTE_URL=https://your-paddleocr-api-endpoint
PADDLEOCR_REMOTE_TOKEN=your-token
```

### 测试论文

**E:\pdf\001\ 目录**:
1. `类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径.pdf` (QUAL)
2. `短视频与直播赋能乡村振兴的内在逻辑与路径分析.pdf` (QUAL)
3. `关于机器学习在农业经济领域应用的若干思考.pdf` (可能为 QUAL/QUANT)

### 完整测试流程

```bash
# 运行完整批量流水线
python run_batch_pipeline.py "E:/pdf/001"
```

### 验证检查点

**通用检查**:
- [ ] PDF 提取成功 (`*_paddleocr.md` 存在)
- [ ] 智能分段成功 (`*_segmented.md` 存在)
- [ ] 类型分类正确 (日志显示 "QUANT" 或 "QUAL")

**QUANT 路径检查**:
- [ ] 7个步骤文件生成 (`1_Overview.md` ~ `7_Critique.md`)
- [ ] Final_Report 生成 (`Final_Deep_Reading_Report.md`)
- [ ] 元数据注入成功 (YAML Frontmatter 存在)
- [ ] 子章节摘要存在 (`subsections` 字段)
- [ ] 导航链接存在 (返回总报告)

**QUAL 路径检查**:
- [ ] 4个层级文件生成 (`L1_Context.md` ~ `L4_Value.md`)
- [ ] Full_Report 生成 (`*_Full_Report.md`)
- [ ] 元数据注入成功 (YAML Frontmatter 存在)
- [ ] 子章节扁平化 (无嵌套结构)
- [ ] 每个文件只包含自己的子章节
- [ ] 导航链接存在 (返回总报告 + 其他层级)
- [ ] Full_Report 无导航

**Obsidian 兼容性**:
- [ ] Dataview 可读取元数据
- [ ] Wikilinks 可点击跳转
- [ ] 标签正确显示

---

**维护者**: Deep Reading Agent Team  
**最后更新**: 2026-02-04
