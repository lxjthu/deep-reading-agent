# L1 Context 层修改总结

**创建时间**: 2026-02-03
**版本**: v2.1 (移除基础元数据提取，专注政策、现状、重要性和文献)

---

## 修改概述

### 背景

**问题**: L1 层（背景层）原本负责提取基础元数据（标题、作者、期刊、年份）、政策背景、现状数据等。但基础元数据现在由专门的视觉识别模型（Qwen-vl-plus）处理，因此 L1 层应该更专注于学术性的信息。

**目标**: 重新设计 L1 层的职责，使其更符合社会科学论文的学术分析需求。

---

## 核心修改

### 1. 移除的字段

| 原字段 | 现状态 | 说明 |
|-------|------|------|------|
| `metadata.title` | ❌ 移除 | 由视觉模型处理 |
| `metadata.authors` | ❌ 移除 | 由视觉模型处理 |
| `metadata.journal` | ❌ 移除 | 由视觉模型处理 |
| `metadata.year` | ❌ 移除 | 由视觉模型处理 |
| `metadata.genre` | ❌ 移除 | 改由 L1 默认值处理 |

### 2. 新增的字段

| 新字段 | 类型 | 说明 |
|-------|------|------|------|
| `research_significance` | 对象 | 研究重要性（包含理论和实践两个维度） |
| `research_significance.theoretical_significance` | 字符串 | 理论意义：本研究在学术理论上的贡献和价值 |
| `research_significance.practical_significance` | 字符串 | 实践意义：本研究对现实世界的影响 |
| `key_literature` | 数组 | 核心文献：识别对本研究有重要启发的文献 |
| `key_literature[].authors` | 字符串 | 作者完整姓名 |
| `key_literature[].year` | 字符串 | 文献年份 |
| `key_literature[].key_insights` | 字符串 | 该文献的核心观点或对本研究的主要启发 |

---

## 修改内容

### 1. L1_Context_Prompt.md（提示词文件）

**文件路径**: `prompts/qual_analysis/L1_Context_Prompt.md`

**角色设定**:
- 具有深厚理论功底和实践经验的社会科学研究学者

**核心要求**:
1. **Genre Classification**: 分类为 5 类之一
2. **Policy Context**: 提取所有政策文件（名称、年份、层级、核心内容）
3. **Status Data**: 提取关键统计数据（数据项、数值、单位、背景）
4. **Research Significance**: 阐述重要性（理论 + 实践双重维度）
5. **Key Literature**: 识别重要文献（作者、年份、核心观点）
6. **Detailed Analysis**: 约 300 字中文综合阐述

**输出格式**:
```json
{
    "policy_context": [...],
    "status_data": [...],
    "research_significance": {
        "theoretical_significance": "...",
        "practical_significance": "..."
    },
    "key_literature": [...],
    "detailed_analysis": "约 300 字的中文综合阐述"
}
```

---

### 2. social_science_analyzer.py（代码实现）

#### 2.1 `analyze_l1_context()` 方法

**修改内容**:
- 移除硬编码的备用提示词中的 `metadata` 提取
- 新增对 `policy_context`、`status_data`、`research_significance`、`key_literature` 的处理
- 调用动态加载的提示词文件

**新增逻辑**:
```python
def analyze_l1_context(self, text_segment: str) -> dict:
    prompt = self._load_prompt_from_file("L1_Context")
    
    if not prompt:
        # 使用备用硬编码提示词（新的，不包含 metadata）
        prompt = """
    你是一位具有深厚理论功底和实践经验的社会科学研究学者...
    ...
    Output JSON:
    {
        "policy_context": [...],
        "status_data": [...],
        "research_significance": {...},
        "key_literature": [...],
        "detailed_analysis": "约 300 字的中文综合阐述"
    }
    """
    
    # 使用动态加载的标记，记录日志
    return self._call_llm(prompt, text_segment, fallback_prompt="L1_Context (FALLBACK)", use_dynamic_prompt=(prompt is not None))
```

#### 2.2 `_call_llm()` 方法增强

**新增参数**: `use_dynamic_prompt: bool`
- 记录日志：`Using dynamically loaded prompt`（如果使用动态加载）
- 记录日志：`Using fallback prompt for: {fallback_prompt}`（如果使用备用）

#### 2.3 `main()` 方法修改

**修改内容**:
```python
# L1 不再返回 genre，使用默认值
genre = "Case Study"  # 默认体裁
```

---

### 3. generate_markdown() 方法更新

**修改位置**: L1 层的 frontmatter 生成部分

**新增逻辑**:
```python
if layer == "L1_Context":
    # 处理新的 L1 字段
    if "policy_context" in data:
        frontmatter.update({
            "key_policies": [p["name"] for p in data.get("policy_context", [])[:5]]
        })
    if "status_data" in data:
        frontmatter.update({
            "status_summary": "; ".join([...])[:3])
        })
    if "research_significance" in data:
        rs = data.get("research_significance", {})
        significance_text = f"理论: {rs.get('theoretical_significance', '')}; 实践: {rs.get('practical_significance', '')}"
        frontmatter.update({"research_significance": significance_text})
    if "key_literature" in data:
        frontmatter.update({
            "key_literature": [lit["authors"] for lit in data.get("key_literature", [])[:5]]
        })
```

#### 3.4 Key Elements 部分更新

**修改内容**:
```python
if layer == "L1_Context":
    lines.append("\n### Policy Context")
    for p in data.get("policy_context", []):
        lines.append(f"- **{p.get('name')}** ({p.get('year')}) [{p.get('level')}]")
        lines.append(f"  - {p.get('content')}")
    
    lines.append("\n### Status Data")
    for d in data.get("status_data", []):
        lines.append(f"- **{d.get('item')}**: {d.get('value')} {d.get('unit', '')}")
        if d.get('context'):
            lines.append(f"  - Context: {d.get('context')}")
    
    if "research_significance" in data:
        lines.append("\n### Research Significance")
        rs = data.get("research_significance", {})
        lines.append(f"- **Theoretical Significance**: {rs.get('theoretical_significance', '')}")
        lines.append(f"- **Practical Significance**: {rs.get('practical_significance', '')}")
    
    if "key_literature" in data:
        lines.append("\n### Key Literature")
        for lit in data.get("key_literature", [])[:5]:
            lines.append(f"- **{lit.get('authors')}** ({lit.get('year')}): {lit.get('key_insights')}")
```

---

### 4. generate_full_report() 方法更新

**修改位置**: L1 层的总报告生成部分

**修改内容**:
```python
# 移除对 metadata 的依赖
lines.append(f"title: {basename}")
lines.append(f"authors: {l1.get('policy_context', [{}])[0].get('name', '') if l1.get('policy_context') else ''}")
lines.append(f"journal: {l1.get('status_data', [{}])[0].get('item', '') if l1.get('status_data') else ''}")
lines.append(f"year: {l1.get('key_literature', [{}])[0].get('year', '') if l1.get('key_literature') else ''}")
lines.append(f"tags: #SocialScience #DeepReading")

lines.append(f"\n# 深度阅读报告：{basename}\n")

lines.append("## 1. 基础情报")
lines.append(l1.get("detailed_analysis", ""))

# 关键政策
if l1.get("policy_context"):
    for p in l1.get("policy_context", [])[:5]:
        lines.append(f"- **{p.get('name')}** ({p.get('year')}): {p.get('content')}")

# 研究重要性
if l1.get("research_significance"):
    rs = l1.get("research_significance", {})
    lines.append(f"- **理论意义**: {rs.get('theoretical_significance', '')}")
    lines.append(f"- **实践意义**: {rs.get('practical_significance', '')}")

# 核心文献
if l1.get("key_literature"):
    for lit in l1.get("key_literature", [])[:5]:
        lines.append(f"- **{lit.get('authors')}** ({lit.get('year')}): {lit.get('key_insights')}")
```

---

## 输出格式对比

### 旧版本输出（v2.0）

```yaml
---
title: "论文标题"
authors: [...]
journal: "期刊名称"
year: "2024"
genre: "Case Study"
tags: [..., "LayerReport", "L1_Context"]
key_policies: ["政策1", "政策2", ...]
status_summary: "数据1: xxx; 数据2: yyy"
---
```

### 新版本输出（v2.1）

```yaml
---
title: "论文标题"
authors: ""  # 由视觉模型注入
journal: ""  # 由视觉模型注入
year: ""  # 由视觉模型注入
tags: ["SocialScience", "Paper", "LayerReport", "L1_Context"]
key_policies: ["政策1", "政策2", ...]
status_summary: "数据1: xxx; 数据2: yyy"
research_significance: 理论: xxx; 实践: xxx
key_literature: ["作者1 (2020)", "作者2 (2021)", ...]
---
```

---

## 测试方式

### 测试动态加载功能

```bash
# 测试提示词加载
python -c "from social_science_analyzer import SocialScienceAnalyzer; analyzer = SocialScienceAnalyzer(); test = 'Test Context'; result = analyzer.analyze_l1_context(test); print('Dynamic prompt loaded:', 'prompt' in result if result.get('policy_context') else 'Using fallback')"

# 测试完整流程
python social_science_analyzer.py "pdf_segmented_md/xxx_segmented.md"
```

### 验证日志

- ✅ `"Loaded prompt from file: L1_Context"` - 动态加载成功
- ⚠️  `"Using fallback prompt for: L1_Context (FALLBACK)" - 文件不存在时使用备用提示词

---

## 版本历史

### v2.1 (2026-02-03)
- ✅ 移除基础元数据提取（title/authors/journal/year）
- ✅ 新增研究重要性字段（理论意义 + 实践意义）
- ✅ 新增核心文献字段（作者 + 年份 + 核心观点）
- ✅ 优化角色设定（资深学者）
- ✅ 实现动态提示词加载
- ✅ 更新所有相关代码方法

### v2.0 (2026-02-03)
- ✅ 创建 L1_Context_Prompt.md 提示词文件
- ✅ 实现基础版本的研究重要性提取

---

**文档结束**

*最后更新: 2026-02-03*
*维护者: Deep Reading Agent Team*
