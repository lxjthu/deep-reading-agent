# 深度阅读智能体 (Deep Reading Agent) - 代码架构与流水线说明

**文档版本**: 2026-02-02  
**基于**: CLAUDE.md + PROJECT_PROGRESS_AND_PLAN.md + 源码分析

---

## 1. 项目概述

深度阅读智能体是一个自动化学术文献分析系统，采用**双模驱动架构**：
- **DeepSeek-R1 (Reasoner)**: 担任"理论家"和"计量专家"，负责深度推理和批判性分析
- **智能分类路由**: 自动区分定量(QUANT)与定性(QUAL)论文，分别采用不同的分析框架

**核心设计理念**：
- **分治策略**: 将长论文切分为独立模块，逐个深度分析
- **增量更新**: MD5 哈希去重，支持断点续传
- **Obsidian 兼容**: 所有输出包含 YAML Frontmatter，支持双向链接

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          深度阅读智能体架构图                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │   PDF 输入   │───▶│  提取与分段层    │───▶│      智能分类路由层          │  │
│  └─────────────┘    └─────────────────┘    └─────────────────────────────┘  │
│         │                  │                            │                   │
│         ▼                  ▼                            ▼                   │
│  ┌─────────────┐    ┌─────────────────┐         ┌──────────┬──────────┐    │
│  │ PaddleOCR   │    │ DeepSeek 分段   │         │  QUANT   │   QUAL   │    │
│  │ (Primary)   │    │ (LLM-based)     │         │ 定量论文  │ 定性论文  │    │
│  ├─────────────┤    ├─────────────────┤         └────┬─────┴─────┬────┘    │
│  │ pdfplumber  │    │ Semantic Index  │              │           │        │
│  │ (Fallback)  │    │ (智能语义索引)   │              ▼           ▼        │
│  └─────────────┘    └─────────────────┘    ┌─────────────┐ ┌─────────────┐ │
│                                             │ 7步深度研读 │ │ 4层金字塔   │ │
│                                             │ (Acemoglu) │ │ (社科分析)  │ │
│                                             └──────┬──────┘ └──────┬──────┘ │
│                                                    │               │       │
│                                             ┌──────┴──────┐ ┌──────┴──────┐│
│                                             │ Dataview    │ │ Obsidian    ││
│                                             │ Summaries   │ │ Metadata    ││
│                                             └─────────────┘ └─────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块详解

### 3.1 状态管理层 (State Management)

**文件**: `state_manager.py`

```python
class StateManager:
    - calculate_hash(file_path)        # MD5 文件指纹
    - is_processed(file_path)          # 检查是否已处理
    - mark_started/completed/failed()  # 状态标记
```

**功能**:
- 使用 `processed_papers.json` 持久化状态
- 哈希去重 + 输出文件存在性检查（防止误跳过）
- 支持 `in_progress`, `completed`, `failed` 三种状态

---

### 3.2 智能分类与路由层 (Smart Routing)

**文件**: `smart_scholar_lib.py`

```python
class SmartScholar:
    - classify_paper(text) -> "QUANT" | "QUAL" | "IGNORE"
    - ensure_segmented_md(pdf_path)    # 提取+分段一站式服务
    - run_command()                    # 子进程执行
```

**分类逻辑**:
1. **QUANT**: 关键词包含 regression, DID, IV, RDD, Stata, robustness 等
2. **QUAL**: 关键词包含 case study, QCA, grounded theory, framework 等
3. **IGNORE**: Editorials, prefaces, call for papers 等非研究性内容

**分类模型**: `deepseek-chat` (temperature=0, JSON 输出)

---

### 3.3 文本提取层 (Extraction Layer)

#### 主路径: PaddleOCR
**文件**: `paddleocr_pipeline.py`, `paddleocr_extractor/`

```python
# 主要流程
PDF → PaddleOCR API → Markdown (带 YAML frontmatter)
                     ↓
              ┌──────────────────┐
              │ 自动回退机制      │
              │ (ConnectionError │
              │  → pdfplumber)   │
              └──────────────────┘
```

**PaddleOCR 特点**:
- 支持远程 Layout Parsing API
- 输出格式: `extractor: paddleocr` in frontmatter
- 自动提取 title, abstract, keywords, sections

**回退机制** (`extract_pdf_legacy`):
- 使用 `pypdf` + `pdfplumber` 混合提取
- 输出兼容的 Markdown 格式
- 标记 `extractor: pdfplumber_fallback`

#### 分段模块
**文件**: `paddleocr_segment.py`

```python
# 分段流程
PaddleOCR MD → strip_artifacts() → add_page_tags() → 
               DeepSeek 分段 API → Segmented MD
```

**关键技术**:
- 清理图像标签、YAML frontmatter
- 合成分页标签 `[PAGE N]` (约 3000 字符/页)
- DeepSeek `deepseek-chat` 模型识别章节边界

---

### 3.4 定量论文分析流水线 (QUANT Pipeline)

**入口**: `deep_read_pipeline.py`

#### 整体流程

```
Segmented MD → Semantic Index → 7-Step Analysis → Final Report
                    ↓                ↓
              (JSON chunks)    (Step 1-7 .md files)
```

#### 步骤详解

**Step 0: 语义索引生成** (`semantic_router.py`)
```python
def generate_semantic_index(full_text, output_dir):
    # 1. 清理 PaddleOCR 格式
    # 2. smart_chunk() 分块 (6k tokens/chunk)
    # 3. LLM 标注每个 chunk 属于哪些步骤 [1,2,3...]
    # 4. 保存 semantic_index.json
```

**步骤 1-7: 深度分析** (`deep_reading_steps/step_*.py`)

| 步骤 | 文件 | 角色 | 核心任务 |
|-----|------|------|---------|
| 1 | `step_1_overview.py` | 全景扫描 | 研究主题、问题意识、贡献定位 |
| 2 | `step_2_theory.py` | 理论家 | 文献综述、理论框架、研究假设 |
| 3 | `step_3_data.py` | 数据审计 | 数据来源、样本选择、清洗方法 |
| 4 | `step_4_vars.py` | 变量专家 | 核心变量定义、测量方法、描述性统计 |
| 5 | `step_5_identification.py` | 计量专家 | 模型设定、识别策略、工具变量、机制图谱 |
| 6 | `step_6_results.py` | 结果解读 | 回归结果、显著性、经济意义 |
| 7 | `step_7_critique.py` | 批判专家 | 局限性、稳健性、未来方向 |

**每个步骤的执行逻辑** (`common.py`):
```python
def run(sections, assigned_titles, output_dir, step_id):
    # 1. 获取文本 (优先级: Semantic Index > 章节路由 > 位置回退)
    text = get_combined_text_for_step(sections, assigned_titles, output_dir, step_id)
    
    # 2. 智能分块 (如果文本过长)
    chunks = smart_chunk(text, max_tokens=10000)
    
    # 3. 调用 DeepSeek-R1 (deepseek-reasoner)
    result = call_deepseek(prompt, SYSTEM_PROMPT)
    
    # 4. 保存结果
    save_step_result(f"{step_id}_Name.md", result, output_dir)
```

#### 内容路由策略 (`common.py`)

```
Priority 1: Semantic Index (semantic_index.json)
            - 根据 chunk 的 tags 过滤对应步骤的文本
            
Priority 2: 章节路由 (section_routing.md)
            - LLM 动态映射章节标题到步骤 (支持多标签)
            - 本地规则回退 (关键词匹配)
            
Priority 3: 位置回退 (Positional Fallback)
            - Step 1-2: 前 25% 章节
            - Step 3-5: 中间 40% 章节
            - Step 6-7: 后 35% 章节
```

---

### 3.5 定性论文分析流水线 (QUAL Pipeline)

**入口**: `social_science_analyzer.py`

#### 四层金字塔模型

```
         ┌─────────────────┐
         │   L4: Value     │  价值升华 (研究缺口、理论贡献、实践启示)
         │    (批判层)     │
         ├─────────────────┤
         │   L3: Logic     │  核心逻辑 (案例过程模型、因果组态路径)
         │    (机制层)     │
         ├─────────────────┤
         │   L2: Theory    │  理论基础 (核心构念、理论框架、假设关系)
         │    (理论层)     │
         ├─────────────────┤
         │   L1: Context   │  背景情报 (政策背景、现状数据、文体分类)
         │    (背景层)     │
         └─────────────────┘
```

#### 执行流程

```python
def main():
    for file in segmented_md_files:
        sections = load_segmented_md(file)
        
        # 提取各层文本
        text_l1 = get_combined_text(sections, ["abstract", "introduction", ...])
        text_l2 = get_combined_text(sections, ["literature", "theory", ...])
        text_l3 = get_combined_text(sections, ["method", "result", ...])
        text_l4 = get_combined_text(sections, ["discussion", "conclusion", ...])
        
        # 四层分析
        l1_res = analyzer.analyze_l1_context(text_l1)
        l2_res = analyzer.analyze_l2_theory(text_l2)
        l3_res = analyzer.analyze_l3_logic(text_l3, genre)  # genre 来自 L1
        l4_res = analyzer.analyze_l4_value(text_l4)
        
        # 输出: 4个分层MD + 1个全景报告MD + 1个Excel汇总
```

#### 输出结构

```
social_science_results_v2/
└── {paper_name}/
    ├── {paper}_L1_Context.md
    ├── {paper}_L2_Theory.md
    ├── {paper}_L3_Logic.md
    ├── {paper}_L4_Value.md
    └── {paper}_Full_Report.md
```

---

### 3.6 后处理与元数据注入

#### Dataview 摘要注入
**文件**: `inject_dataview_summaries.py`

```python
# 为每个步骤文件提取关键字段
1_Overview.md → research_theme, problem_statement, importance
2_Theory.md   → theoretical_foundation, hypothesis, mechanism
3_Data.md     → data_source, sample_period, cleaning_method
...

# 注入 YAML frontmatter，供 Obsidian Dataview 查询
```

#### Obsidian 元数据注入
**文件**: `inject_obsidian_meta.py`

```python
# 元数据提取流程
if is_paddleocr_md(source_path):
    metadata = parse_paddleocr_frontmatter(source_path)  # 直接解析
else:
    metadata = extract_metadata_from_text(text)  # LLM 提取

# 双向链接注入
- Final Report ←→ Step 1-7 files
- 添加 [[Wikilink]] 语法
```

---

### 3.7 补充阅读与修复机制

**文件**: `run_supplemental_reading.py`

**功能**:
```python
# 1. 检测缺失的步骤结果
for step in steps:
    if section_text is empty or "未提供具体论文内容":
        # 从原始 MD 重新提取上下文
        context = extract_context_from_raw(raw_file, keywords)
        # 重新运行对应步骤
        result = step_module.run(sections)

# 2. 强制重新生成最终报告
if --regenerate:
    merge all 1_Overview.md ~ 7_Critique.md → Final_Deep_Reading_Report.md
```

---

## 4. 完整流水线执行流程

### 4.1 单文件完整流程 (run_full_pipeline.py)

```bash
python run_full_pipeline.py paper.pdf --use-paddleocr
```

```
Step 1: PDF → PaddleOCR MD (paddleocr_pipeline.py)
         ↓ 失败时自动回退到 pdfplumber
         
Step 2: PaddleOCR MD → Segmented MD (paddleocr_segment.py)
         ↓ DeepSeek LLM 分段
         
Step 3: Deep Reading (deep_read_pipeline.py)
         ├── Semantic Index 生成
         ├── Step 1-7 并行/串行分析
         └── Final Report 合并
         
Step 4: Supplemental Check (run_supplemental_reading.py)
         └── 检测并修复缺失步骤
         
Step 5: Dataview Summaries (inject_dataview_summaries.py)
         └── 提取关键字段注入 frontmatter
         
Step 6: Obsidian Metadata (inject_obsidian_meta.py)
         └── 元数据 + 双向链接
```

### 4.2 批量处理流程 (run_batch_pipeline.py)

```bash
python run_batch_pipeline.py /path/to/pdfs/
```

```
For each PDF in directory (递归):
    ├─ StateManager: 检查是否已处理 (MD5 哈希)
    ├─ SmartScholar.ensure_segmented_md() → 提取+分段
    ├─ SmartScholar.classify_paper() → QUANT/QUAL/IGNORE
    │
    ├─ 如果 QUANT:
    │   ├── deep_read_pipeline.py
    │   ├── inject_dataview_summaries.py
    │   └── inject_obsidian_meta.py
    │
    └─ 如果 QUAL:
        ├── social_science_analyzer.py
        └── link_social_science_docs.py
```

---

## 5. 关键设计决策

### 5.1 文本获取的优先级设计

```python
def get_combined_text_for_step(sections, assigned_titles, output_dir, step_id):
    # Priority 1: Semantic Index (解决分段错误问题)
    if semantic_index.json exists:
        return filter_chunks_by_step_id(step_id)
    
    # Priority 2: 传统章节路由
    for title in assigned_titles:
        text = sections[title]
        # 短文本回退: 如果 <100 字符，自动追加下一章节
        if len(text) < 100:
            text += sections[next_title]
    
    # Priority 3: 位置回退 (确保每个步骤都有内容)
    return positional_fallback_sections
```

### 5.2 智能分块策略 (smart_chunk)

```python
def smart_chunk(text, max_tokens=8000):
    # 1. 先尝试按段落分割 (\n\n)
    # 2. 长段落按句子分割 (。/. )
    # 3. 确保不截断句子
    # 4. 返回 chunk 列表
```

### 5.3 抗幻觉设计

```python
SYSTEM_PROMPT += """
重要规则:
1. 直接输出分析内容，不要寒暄
2. NO HALLUCINATIONS: 如果文本为空或不足，明确说明 "No content found"
   不要基于一般知识编造数据、变量或结果
"""
```

### 5.4 LLM 配置策略

| 用途 | 模型 | 温度 | 说明 |
|-----|------|------|------|
| 文本分段 | deepseek-chat | 0.0 | 结构化输出，精确边界 |
| 论文分类 | deepseek-chat | 0.0 | JSON 分类结果 |
| 深度分析 | deepseek-reasoner | - | Acemoglu 级批判性思维 |
| Dataview 摘要 | deepseek-chat | 0.1 | 快速提取 |
| 元数据提取 | moonshot-v1-auto | 0.0 | 长上下文 (128k) |

---

## 6. 输出目录结构

```
项目根目录/
├── paddleocr_md/              # PaddleOCR 提取结果
│   └── {paper}_paddleocr.md
│
├── pdf_segmented_md/          # 分段后的结构化文本 (QUANT/QUAL 共用)
│   └── {paper}_segmented.md
│
├── deep_reading_results/      # 定量论文分析结果
│   └── {paper_name}/
│       ├── semantic_index.json     # 语义索引
│       ├── section_routing.md      # 章节路由映射
│       ├── 1_Overview.md
│       ├── 2_Theory.md
│       ├── 3_Data.md
│       ├── 4_Variables.md
│       ├── 5_Identification.md
│       ├── 6_Results.md
│       ├── 7_Critique.md
│       └── Final_Deep_Reading_Report.md
│
├── social_science_results_v2/ # 定性论文分析结果
│   └── {paper_name}/
│       ├── {paper}_L1_Context.md
│       ├── {paper}_L2_Theory.md
│       ├── {paper}_L3_Logic.md
│       ├── {paper}_L4_Value.md
│       └── {paper}_Full_Report.md
│
└── processed_papers.json      # 状态持久化文件
```

---

## 7. 使用示例

### 7.1 单文件深度阅读 (定量)
```bash
# 推荐: PaddleOCR 路径
python run_full_pipeline.py "paper.pdf" --use-paddleocr

# 或分步执行
python paddleocr_pipeline.py "paper.pdf" --out_dir paddleocr_md
python paddleocr_segment.py "paddleocr_md/paper_paddleocr.md" --out_dir pdf_segmented_md
python deep_read_pipeline.py "pdf_segmented_md/paper_segmented.md"
```

### 7.2 批量处理 (自动分类)
```bash
python run_batch_pipeline.py "path/to/pdfs/"
```

### 7.3 仅分析定性论文
```bash
python social_science_analyzer.py pdf_segmented_md --filter "keyword"
python link_social_science_docs.py social_science_results_v2
```

---

## 8. 扩展点与未来方向

1. **向量数据库集成**: 将提取的机制图谱、变量定义存入向量库，构建学术知识库
2. **可视化增强**: 机制图谱 (Mermaid) 渲染、引用关系图谱
3. **多语言支持**: 当前强制中文输出，可扩展多语言切换
4. **Stata 代码生成**: `stata_refiner.py` 已有基础，可进一步增强

---

*文档生成时间: 2026-02-02*  
*维护者: Deep Reading Agent Team*
