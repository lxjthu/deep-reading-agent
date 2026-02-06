# QUAL 论文全流程技术文档

**创建时间**: 2026-02-04  
**版本**: v1.0 (集成 QUAL 元数据提取工具)  
**状态**: ✅ 生产就绪

---

## 目录

1. [系统概述](#系统概述)
2. [架构设计](#架构设计)
3. [核心模块详解](#核心模块详解)
4. [完整数据流](#完整数据流)
5. [API 接口](#api-接口)
6. [测试指南](#测试指南)

---

## 系统概述

### 功能说明

本系统实现了 QUAL（定性社会科学）论文的自动化深度分析流水线，包含以下核心功能：

1. **PDF 文本提取**：使用 PaddleOCR 远程 API 提取 PDF 内容
2. **智能分段路由**：基于 LLM 自动识别并分段论文内容
3. **4 层金字塔分析**：使用 DeepSeek 进行深度理论分析
4. **元数据自动提取**：从分析结果和 PDF 中提取结构化元数据
5. **Obsidian 注入**：生成兼容 Obsidian Dataview 的 Markdown 文件

### 支持的论文类型

- ✅ **理论构建** (Theoretical)
- ✅ **案例研究** (Case Study)
- ✅ **定性比较分析** (QCA)
- ✅ **文献综述** (Review)
- ✅ **定性实证** (Qualitative Empirical)

---

## 架构设计

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    run_batch_pipeline.py                    │
│                    (批量入口，任务调度)                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│                      smart_scholar_lib.py                   │
│              (SmartScholar: 核心调度器)                     │
│  - ensure_segmented_md()    # 提取 + 分段                   │
│  - classify_paper()         # 类型分类                     │
│  - run_command()            # 子进程调用                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ↓                               ↓
┌──────────────────┐          ┌──────────────────┐
│  PaddleOCR       │          │  Legacy (pdfplumber)│
│  (推荐路径)      │          │  (降级方案)       │
└────────┬─────────┘          └────────┬─────────┘
         │                             │
         └──────────┬──────────────────┘
                    │
                    ↓
┌─────────────────────────────────────────────────────────────┐
│                  smart_segment_router.py                    │
│              (SmartSegmentRouter: 智能分段)                 │
│  - extract_headings()       # 提取章节标题                  │
│  - classify_headings()      # LLM 分类标题                  │
│  - segment_by_routing()     # 代码切分内容                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              *_segmented.md (结构化分段输出)                 │
│  - L1: Context (背景层)                                      │
│  - L2: Theory (理论层)                                       │
│  - L3: Logic (逻辑层)                                        │
│  - L4: Value (价值层)                                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              social_science_analyzer_v2.py                  │
│              (SocialScienceAnalyzerV2: 4层分析)            │
│  - analyze_l1_context()      # 背景层分析                   │
│  - analyze_l2_theory()       # 理论层分析                   │
│  - analyze_l3_logic()        # 逻辑层分析 (体裁自适应)      │
│  - analyze_l4_value()        # 价值层分析                   │
│  - generate_full_report()    # 总报告生成                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              social_science_results_v2/论文名/              │
│  ├── L1_Context.md         # 背景层分析                     │
│  ├── L2_Theory.md          # 理论层分析                     │
│  ├── L3_Logic.md           # 逻辑层分析                     │
│  ├── L4_Value.md           # 价值层分析                     │
│  └── 论文名_Full_Report.md  # 总报告                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│            qual_metadata_extractor.extractor                │
│            (元数据提取与注入工具)                           │
│  - md_extractor.py         # MD 提取 (DeepSeek 30字总结)    │
│  - pdf_extractor.py        # PDF 提取 (Qwen-vl-plus)       │
│  - merger.py               # 元数据合并                     │
│  - injector.py             # Frontmatter 注入               │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              最终输出（Obsidian 兼容）                       │
│  每个 MD 文档包含：                                         │
│  - YAML Frontmatter (title, authors, journal, year, tags)   │
│  - 扁平化子章节元数据 (如 "1. 论文分类": "30字摘要")        │
│  - 导航链接 (返回总报告 + 其他层级)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心模块详解

### 模块 1: PDF 文本提取

**文件**: `paddleocr_pipeline.py`

**核心类**: `PaddleOCRPDFExtractor`

**主要方法**:

```python
def extract_pdf_with_paddleocr(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    download_images: bool = False
) -> dict
```

**功能**:
- 调用远程 PaddleOCR Layout Parsing API
- 提取 PDF 的文本内容和结构信息
- 生成带 YAML Frontmatter 的 Markdown 文件

**输出示例** (`*_paddleocr.md`):

```markdown
---
title: 论文标题
extractor: paddleocr
abstract: 摘要内容
keywords: [关键词1, 关键词2]
sections: [章节列表]
---

## 1. Introduction
### 1.1 Background
内容...

## 2. Literature Review
内容...
```

**环境变量**:
```env
PADDLEOCR_REMOTE_URL=https://your-paddleocr-api-endpoint
PADDLEOCR_REMOTE_TOKEN=your-token
```

**降级方案**: 如果 PaddleOCR 不可用，自动降级到 `anthropic_pdf_extract_raw.py`

---

### 模块 2: 智能分段路由

**文件**: `smart_segment_router.py`

**核心类**: `SmartSegmentRouter`

**QUAL 分段定义**:

```python
QUAL_STEPS = {
    "L1": "L1_Context (背景层) - 摘要、引言、政策背景、现状数据",
    "L2": "L2_Theory (理论层) - 文献综述、理论框架、核心构念",
    "L3": "L3_Logic (逻辑层) - 方法设计、案例分析、机制路径、实证结果",
    "L4": "L4_Value (价值层) - 结论、讨论、研究缺口、理论贡献、实践启示"
}
```

**主要方法**:

#### 2.1 提取章节标题

```python
def extract_headings(self, content: str) -> List[Heading]
```

**逻辑**:
1. 优先提取 `###` 三级章节标题
2. 如果 `###` 数量 < 3，回退到 `##` 二级标题
3. 记录每个标题的位置信息

**返回值**:
```python
[
    Heading(level=3, title="1. Introduction", start_pos=100, end_pos=500),
    Heading(level=3, title="2. Literature Review", start_pos=500, end_pos=800),
    ...
]
```

#### 2.2 LLM 标题分类

```python
def classify_headings(
    self, 
    headings: List[Heading], 
    mode: str = "auto"
) -> Dict[str, List[str]]
```

**System Prompt** (QUAL 模式):
```
你是学术论文智能分段专家。
将以下章节标题映射到 4 个分析层级。

4个层级定义:
L1: Context (背景层) - 摘要、引言、政策背景、现状数据
L2: Theory (理论层) - 文献综述、理论框架、核心构念
L3: Logic (逻辑层) - 方法设计、案例分析、机制路径、实证结果
L4: Value (价值层) - 结论、讨论、研究缺口、理论贡献、实践启示

规则:
- 一个章节可以属于多个层级
- 无法分类的章节归为 "0" (忽略)
- 返回 JSON 格式
```

**API 调用**:
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

**返回值**:
```python
{
    "L1": ["1. Introduction", "2. Policy Background"],
    "L2": ["3. Literature Review", "4. Theoretical Framework"],
    "L3": ["5. Methodology", "6. Case Analysis"],
    "L4": ["7. Conclusion", "8. Discussion"]
}
```

#### 2.3 代码切分内容

```python
def segment_by_routing(
    self,
    content: str,
    headings: List[Heading],
    routing: Dict[str, List[str]],
    steps_def: Dict
) -> Dict[str, str]
```

**逻辑**:
```python
for layer_id, title_list in routing.items():
    layer_texts = []
    for title in title_list:
        heading = next((h for h in headings if h.title == title), None)
        if heading:
            # 根据 start_pos/end_pos 从 content 中切片
            text = content[heading.start_pos:heading.end_pos]
            layer_texts.append(text)
    layer_contents[layer_id] = "\n\n".join(layer_texts)
```

**自动填充空层**:
```python
def _fill_empty_steps(layer_contents: dict, order: list) -> dict:
    for i, layer_id in enumerate(order):
        if not layer_contents.get(layer_id):
            # 从前一个或后一个层级复制
            if i > 0:
                prev_layer = order[i-1]
                layer_contents[layer_id] = layer_contents.get(prev_layer, "")
```

**输出格式** (`*_segmented.md`):
```markdown
# 论文原文结构化分段（Smart Router）

- Source: paddleocr_md/xxx_paddleocr.md
- Mode: qual
- Generated: 2026-02-04T10:30:00

## 路由映射

- L1: Context (背景层)
- L2: Theory (理论层)
- L3: Logic (逻辑层)
- L4: Value (价值层)

## L1: Context (背景层)

```text
【原文：1. Introduction】
...
```

## L2: Theory (理论层)
...
```

---

### 模块 3: 4 层金字塔分析

**文件**: `social_science_analyzer_v2.py`

**核心类**: `SocialScienceAnalyzerV2`

**关键特性**:
- ✅ 直接 Markdown 输出（无需 JSON 解析）
- ✅ 动态加载外部提示词文件
- ✅ L3 层体裁自适应
- ✅ 自动体裁提取

#### 3.1 动态提示词加载

```python
def _load_prompt_from_file(self, layer: str) -> str:
    """从 prompts/qual_analysis/ 目录加载提示词"""
    prompt_file = f"prompts/qual_analysis/{layer}_Prompt.md"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read()
```

**支持的提示词文件**:
- `prompts/qual_analysis/L1_Context_Prompt.md`
- `prompts/qual_analysis/L2_Theory_Prompt.md`
- `prompts/qual_analysis/L3_Logic_Prompt.md`
- `prompts/qual_analysis/L4_Value_Prompt.md`

#### 3.2 LLM Markdown 调用

```python
def _call_llm_markdown(self, prompt: str) -> str:
    """直接返回 Markdown，无需 JSON"""
    response = self.client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": "你是一个社会科学分析专家。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content
```

**优势对比**:

| 维度 | v1 (JSON) | v2 (Markdown) | 改进 |
|------|-----------|---------------|------|
| 稳定性 | 可能 JSON 格式错误 | 直接输出，格式稳定 | ✅ 无需 json_repair |
| 解析复杂度 | 需要解析+错误处理 | 无需解析，直接可用 | ✅ 简化 50% |
| 可读性 | 需要转换查看 | 直接可读 | ✅ 用户体验提升 |
| 元数据提取 | JSON 键值对 | 正则表达式 `## 数字.` | ✅ 统一格式 |
| 人工审阅 | 需要 JSON 工具 | 任何文本编辑器 | ✅ 便捷性提升 |

#### 3.3 体裁提取与自适应

```python
def _extract_genre_from_l1_markdown(self, l1_markdown: str) -> str:
    """从 L1 输出中提取体裁"""
    match = re.search(r'\*\*(Theoretical|Case Study|QCA|Quantitative|Review)\*\*', l1_markdown)
    if match:
        return match.group(1)
    return "Theoretical"  # 默认值
```

**支持的体裁**:
- **Theoretical**: 理论构建（概念体系、逻辑推演、模型构建、命题提出）
- **Case Study**: 案例研究（关键阶段、整体流程、相互作用、因果关系）
- **QCA**: 定性比较分析（因果路径、条件组合、组间比较、路径效应）
- **Quantitative**: 定量研究（研究假设、变量关系、模型设定、回归结果）
- **Review**: 文献综述（整合框架、理论谱系、演进阶段、跨域对话）

**L3 自适应调用**:
```python
genre = self._extract_genre_from_l1_markdown(l1_markdown)
l3_markdown = self.analyze_l3_logic(text_l3, genre=genre)
```

#### 3.4 分析输出格式

**L1_Context.md**:

```markdown
## 1. 论文分类
**Theoretical** (理论构建)。本文的核心任务...

## 2. 核心问题
本文旨在系统探究...

## 3. 政策文件
- **name**: 党的二十大报告
- **year**: 2022
- **level**: Central
- **content**: 明确提出"精细化服务"理念...

## 4. 现状数据
- **item**: ChatGPT月活跃用户数
- **value**: 破亿
- **unit**: 人
- **context**: ChatGPT推出仅两个月后达到...

## 5. 理论重要性
本研究的理论意义重大...

## 6. 实践重要性
本研究的实践意义直接指向...

## 7. 关键文献
- **authors**: [作者]
- **year**: [年份]
- **key_insights**: 该文献将ChatGPT理解为...
```

**L3_Logic.md** (Theoretical 格式):

```markdown
## 1. 研究体裁
Theoretical

## 2. 逻辑类型
理论逻辑

## 3. 核心问题
本论文试图解决的核心机制问题是...

## 4. 概念体系
论文构建了一个由核心驱动要素...

## 5. 逻辑推演
论文的理论构建遵循一个辩证的...

## 6. 模型构建
论文构建了一个"技术赋能-风险制约-系统整合"...

## 7. 命题提出
基于上述模型，论文隐含地提出了一系列...

## 8. 理论贡献
1. 理论视角创新...
2. 机制系统化梳理...

## 9. 应用价值
为地方政府、乡村文化工作者...

## 10. 理论依据
论文的分析建立在多个理论传统之上...

## 11. 详细分析
本论文的核心机制是一个关于...
```

---

### 模块 4: 元数据提取与注入

**目录**: `qual_metadata_extractor/`

**文件结构**:
```
qual_metadata_extractor/
├── __init__.py          # 导出 extract_qual_metadata
├── extractor.py         # 主提取逻辑
├── md_extractor.py      # MD 提取（第一次提取）
├── pdf_extractor.py     # PDF 提取（第二次提取）
├── merger.py            # 元数据合并
└── injector.py          # Frontmatter 注入
```

#### 4.1 两次提取逻辑

**第一次提取：从 MD 报告中提取**

**文件**: `md_extractor.py`

**核心方法**:

```python
def extract_sections_from_markdown(md_content: str) -> dict:
    """提取 `## 数字. 标题` 格式的章节"""
    sections = {}
    current_num = None
    current_title = None
    current_content = []
    
    for line in md_content.split('\n'):
        # 匹配 ## 数字. 标题
        match = re.match(r'^##\s+(\d+)\.\s+(.+)$', line)
        if match:
            # 保存上一个章节
            if current_num and current_title:
                key = f"{current_num}. {current_title}"
                sections[key] = '\n'.join(current_content).strip()
            
            # 开始新章节
            current_num = match.group(1)
            current_title = match.group(2).strip()
            current_content = []
        elif line.startswith('#'):
            continue
        else:
            if current_num and current_title:
                current_content.append(line)
    
    return sections
```

**DeepSeek 30字总结**:

```python
def summarize_section_with_deepseek(
    client, 
    title: str, 
    content: str
) -> str:
    """用 DeepSeek 将章节内容总结为 30-50 字中文"""
    target_length = min(50, max(30, len(content) // 10))
    
    prompt = f"""请将以下内容总结为{target_length}字以内的一句话：
标题：{title}
内容：{content}

要求：
- 中文输出
- {target_length}字以内
- 抓住核心要点
- 保持学术准确性
"""
    
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一个精确的学术内容总结专家。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=150
    )
    
    return resp.choices[0].message.content.strip()
```

**输出示例**:
```python
{
    "L1_Context": {
        "1. 论文分类": "本文构建类ChatGPT技术赋能乡村文化振兴的理论分析框架。",
        "2. 核心问题": "本文探讨类ChatGPT技术如何为乡村文化振兴带来机遇与挑战。",
        "3. 政策文件": "党的二十大报告提出精细化服务理念，为AI赋能乡村文化提供政策指引。",
        ...
    },
    "L2_Theory": {...},
    "L3_Logic": {...},
    "L4_Value": {...}
}
```

**第二次提取：从 PDF 文件中提取**

**文件**: `pdf_extractor.py`

**核心方法**:

```python
def convert_pdf_to_images(pdf_path: str, max_pages: int = 2) -> list:
    """将 PDF 前几页转换为图片（base64）"""
    doc = pymupdf.open(pdf_path)
    images = []
    
    for page_num in range(min(max_pages, len(doc))):
        page = doc.load_page(page_num)
        mat = pymupdf.Matrix(pymupdf.Identity)
        pix = page.get_pixmap(matrix=mat, dpi=200)
        
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        images.append(img_base64)
    
    doc.close()
    return images
```

**Qwen-vl-plus 视觉提取**:

```python
def extract_pdf_metadata_with_qwen(images: list) -> dict:
    """用 Qwen-vl-plus 从 PDF 图片中提取元数据"""
    client = OpenAI(
        api_key=os.getenv("QWEN_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    
    prompt = """请从以下论文图片中提取以下元数据：
1. 论文标题（完整）
2. 作者列表（所有作者，用逗号分隔）
3. 发表期刊（期刊全名）
4. 发表年份（仅4位数字）

请以 JSON 格式返回：
{
    "title": "...",
    "authors": ["...", "..."],
    "journal": "...",
    "year": "..."
}
"""
    
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
    
    # 提取 JSON
    response_content = resp.choices[0].message.content
    if "```json" in response_content:
        start_idx = response_content.find("```json") + 7
        end_idx = response_content.find("```", start_idx)
        json_str = response_content[start_idx:end_idx].strip()
    else:
        json_str = response_content.strip()
    
    return json.loads(json_str)
```

**输出示例**:
```python
{
    "title": "类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径",
    "authors": ["曹银山", "邹照斌"],
    "journal": "中国学术期刊电子出版物",
    "year": "2024"
}
```

#### 4.2 元数据合并

**文件**: `merger.py`

**核心方法**:

```python
def create_base_metadata(pdf_metadata: dict) -> dict:
    """创建基础元数据（PDF 元数据 + tags）"""
    return {
        "title": pdf_metadata.get("title", ""),
        "authors": pdf_metadata.get("authors", []),
        "journal": pdf_metadata.get("journal", ""),
        "year": pdf_metadata.get("year", ""),
        "tags": ["paper", "qual", "deep-reading"]
    }

def create_layer_metadata(base_metadata: dict, subsections: dict, layer_name: str) -> dict:
    """为单个层级创建元数据（基础元数据 + 该层的子章节）"""
    layer_metadata = base_metadata.copy()
    # 直接将 subsections 合并到顶层（扁平结构）
    layer_metadata.update(subsections)
    return layer_metadata
```

**合并策略**:
- PDF 元数据优先覆盖 MD 元数据
- 子章节元数据采用扁平结构（方便 Obsidian Dataview 读取）
- 每个层级文件只包含自己的子章节

#### 4.3 Frontmatter 注入

**文件**: `injector.py`

**核心方法**:

```python
def inject_qual_frontmatter(md_content: str, metadata: dict) -> str:
    """为 QUAL 分析文件注入 YAML Frontmatter"""
    # 直接使用提供的元数据，不与现有 frontmatter 合并
    yaml_str = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    frontmatter_block = f"---\n{yaml_str}\n---\n\n"
    
    # 移除现有 frontmatter（如果有）
    body_content = md_content
    if md_content.startswith("---\n"):
        end_idx = md_content.find("\n---\n", 4)
        if end_idx != -1:
            body_content = md_content[end_idx + 5:]
    
    return frontmatter_block + body_content
```

**导航链接添加**:

```python
def add_qual_navigation_links(md_content: str, layer: str, paper_name: str, all_layers: list) -> str:
    """为 QUAL 分析文件添加导航链接"""
    # Full_Report 不添加导航
    if layer == "Full_Report" or not all_layers:
        return md_content
    
    # 检查是否已有导航
    if "## 导航" in md_content or "## Navigation" in md_content:
        return md_content
    
    # 生成导航段落
    navigation = "\n\n## 导航\n\n"
    
    # 链接到总报告
    full_report_name = f"{paper_name}_Full_Report"
    navigation += f"**返回总报告**：[[{full_report_name}]]\n\n"
    
    # 链接到其他层级
    other_layers = [l for l in all_layers if l != layer]
    if other_layers:
        navigation += "**其他层级**：\n"
        for l in other_layers:
            navigation += f"- [[{l}]]\n"
    
    return md_content + navigation
```

#### 4.4 输出示例

**L1_Context.md** (注入后):

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
7. 关键文献: 关键文献从技术范式、实时检索、艺术应用、算力消耗及意识形态风险等方面进行分析。
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

**Full_Report.md** (注入后):

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

## 完整数据流

### 输入阶段

```
PDF 文件 (E:\pdf\001\xxx.pdf)
├─ 原始学术内容
├─ 多栏布局
├─ 图表、公式
└─ 参考文献
```

### 阶段 1: PDF → Markdown

**工具**: `paddleocr_pipeline.py`

**输出**: `paddleocr_md/xxx_paddleocr.md`

```markdown
---
title: xxx
extractor: paddleocr
---

## 1. Introduction
### 1.1 Background
...
```

### 阶段 2: Markdown → 分段 Markdown

**工具**: `smart_segment_router.py`

**输出**: `pdf_segmented_md/xxx_segmented.md`

```markdown
# 论文原文结构化分段（Smart Router）

## L1: Context (背景层)
【原文：1. Introduction】
...

## L2: Theory (理论层)
【原文：2. Literature Review】
...
```

### 阶段 3: 分段 MD → 4 层分析

**工具**: `social_science_analyzer_v2.py`

**输出**: `social_science_results_v2/xxx/`

```
L1_Context.md     (背景层分析)
L2_Theory.md      (理论层分析)
L3_Logic.md       (逻辑层分析，体裁自适应)
L4_Value.md       (价值层分析)
xxx_Full_Report.md (总报告)
```

### 阶段 4: 分析 MD → 元数据注入

**工具**: `qual_metadata_extractor/`

**输出**: 更新后的 `social_science_results_v2/xxx/`

每个文件添加：
- YAML Frontmatter (title, authors, journal, year, tags)
- 扁平化子章节元数据
- 导航链接

---

## API 接口

### 命令行接口

#### 批量处理

```bash
python run_batch_pipeline.py <pdf_dir>
```

**参数**:
- `pdf_dir`: 包含 PDF 文件的目录

**示例**:
```bash
python run_batch_pipeline.py "E:/pdf/001"
```

#### 单个 QUAL 分析

```bash
python social_science_analyzer_v2.py <segmented_md_path>
```

**参数**:
- `segmented_md_path`: 分段后的 Markdown 文件路径

#### 元数据提取

```bash
python -m qual_metadata_extractor.extractor <paper_dir> <pdf_dir>
```

**参数**:
- `paper_dir`: 论文输出目录（包含 L1_Context.md 等）
- `pdf_dir`: PDF 文件目录

**示例**:
```bash
python -m qual_metadata_extractor.extractor \
    "social_science_results_v2/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径" \
    "E:/pdf/001"
```

### Python API

```python
from qual_metadata_extractor import extract_qual_metadata

# 提取单个论文的元数据
extract_qual_metadata(
    paper_dir="social_science_results_v2/论文名称",
    pdf_dir="E:/pdf/001"
)
```

---

## 测试指南

### 环境配置

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
PADDLEOCR_REMOTE_URL=https://your-paddleocr-api-endpoint
PADDLEOCR_REMOTE_TOKEN=your-token
```

### 测试用例

**测试论文**:
1. `类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径.pdf`
2. `短视频与直播赋能乡村振兴的内在逻辑与路径分析.pdf`
3. `关于机器学习在农业经济领域应用的若干思考.pdf`

### 测试步骤

#### 1. 单模块测试

**测试 PDF 提取**:
```bash
python paddleocr_pipeline.py "E:/pdf/001/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径.pdf"
```

**测试智能分段**:
```bash
python smart_segment_router.py "paddleocr_md/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径_paddleocr.md" --mode qual
```

**测试 4 层分析**:
```bash
python social_science_analyzer_v2.py "pdf_segmented_md/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径_segmented.md"
```

**测试元数据提取**:
```bash
python -m qual_metadata_extractor.extractor \
    "social_science_results_v2/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径" \
    "E:/pdf/001"
```

#### 2. 全流程测试

```bash
python run_batch_pipeline.py "E:/pdf/001"
```

### 验证检查点

**检查点 1: PDF 提取**
- [ ] `*_paddleocr.md` 文件生成
- [ ] YAML Frontmatter 正确
- [ ] 文本内容完整

**检查点 2: 智能分段**
- [ ] `*_segmented.md` 文件生成
- [ ] 4 个层级都有内容
- [ ] 路由映射合理

**检查点 3: 4 层分析**
- [ ] `L1_Context.md` 生成（7 个子章节）
- [ ] `L2_Theory.md` 生成（6 个子章节）
- [ ] `L3_Logic.md` 生成（11 个子章节，体裁自适应）
- [ ] `L4_Value.md` 生成（6 个子章节）
- [ ] `*_Full_Report.md` 生成

**检查点 4: 元数据注入**
- [ ] YAML Frontmatter 正确
- [ ] 子章节元数据扁平化（无嵌套）
- [ ] 每个文件只包含自己的子章节
- [ ] 导航链接正确
- [ ] Full_Report 无导航

**检查点 5: Obsidian 兼容性**
- [ ] Dataview 可读取元数据
- [ ] Wikilinks 可点击跳转
- [ ] 标签正确显示

---

## 性能指标

### 处理时间

| 阶段 | 单篇论文时间 | 说明 |
|------|-------------|------|
| PDF 提取 | 10-30 秒 | 取决于 PDF 页数 |
| 智能分段 | 20-40 秒 | LLM 分类标题 |
| 4 层分析 | 3-5 分钟 | 4 次 DeepSeek 调用 |
| 元数据提取 | 1-2 分钟 | MD 提取 + PDF 视觉 |
| **总计** | **4-7 分钟** | 不包括排队等待 |

### 并发处理

- 支持 PDF 级别并发（多论文同时处理）
- 单篇论文内部串行（确保状态一致性）

### 成本估算

**DeepSeek API**:
- 智能分段: ~500 tokens × 2 次
- 4 层分析: ~8000 tokens × 4 次
- 元数据总结: ~300 tokens × 29 次
- **总计**: ~35,000 tokens/篇
- **成本**: ~0.5 元/篇（DeepSeek 定价）

**Qwen API**:
- PDF 视觉提取: 2 张图片
- **成本**: ~0.01 元/篇

---

## 故障排查

### 常见问题

**问题 1: PaddleOCR 提取失败**
```
Error: PaddleOCR API unavailable
```
**解决方案**: 自动降级到 Legacy 提取（pdfplumber）

**问题 2: LLM 分类失败**
```
Error: Failed to classify paper
```
**解决方案**: 检查 DEEPSEEK_API_KEY 是否正确

**问题 3: 体裁提取失败**
```
Warning: Genre extraction failed, using default 'Theoretical'
```
**解决方案**: 正常，使用默认值不影响分析

**问题 4: PDF 视觉提取失败**
```
Error: Qwen VL extraction failed
```
**解决方案**: 检查 QWEN_API_KEY，或跳过 PDF 视觉提取

**问题 5: 元数据嵌套**
```
Error: Metadata still nested in layer_subsections
```
**解决方案**: 确保使用最新的 merger.py（扁平结构）

---

## 扩展指南

### 添加新的体裁

**步骤**:
1. 在 `prompts/qual_analysis/L3_Logic_Prompt.md` 中添加新体裁的提示词
2. 在 `social_science_analyzer_v2.py` 的 `_extract_genre_from_l1_markdown()` 中添加体裁识别
3. 在 `QUAL_METADATA_EXTRACTOR_DESIGN.md` 中更新 L3 格式定义

### 自定义元数据字段

**步骤**:
1. 在 `merger.py` 的 `create_base_metadata()` 中添加新字段
2. 在 `pdf_extractor.py` 的 `extract_pdf_metadata_with_qwen()` 中添加提取逻辑
3. 更新 `injector.py` 的 `inject_qual_frontmatter()` 以包含新字段

---

**维护者**: Deep Reading Agent Team  
**最后更新**: 2026-02-04
