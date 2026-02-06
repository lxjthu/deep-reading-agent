# QUAL 元数据提取工具

## 概述

本工具用于为 QUAL（社会科学 4 层金字塔分析）论文自动提取和注入元数据。

## 功能

### 两次提取逻辑

1. **第一次提取**：从生成的 MD 报告中提取
   - 输入：L1_Context.md, L2_Theory.md, L3_Logic.md, L4_Value.md
   - 提取：`## 数字. 标题` 格式的小标题
   - 处理：DeepSeek 30-50字总结

2. **第二次提取**：从原始 PDF 文件中提取
   - 输入：原始 PDF 文件
   - 提取：标题、作者、期刊、年份
   - 工具：Qwen-vl-plus 视觉模型 + pymupdf

3. **元数据合并**：PDF 元数据优先覆盖 MD 元数据

4. **注入 Frontmatter**：生成 YAML Frontmatter 并注入到各层文件

5. **添加导航**：在文件末尾添加导航链接

## 文件结构

```
qual_metadata_extractor/
├── __init__.py          # 包初始化
├── extractor.py         # 主提取逻辑
├── md_extractor.py      # MD 提取（第一次提取）
├── pdf_extractor.py     # PDF 提取（第二次提取）
├── merger.py            # 元数据合并
└── injector.py          # Frontmatter 注入
```

## 使用方法

### 直接使用

```bash
python -m qual_metadata_extractor.extractor <paper_dir> <pdf_dir>
```

### 示例

```bash
python -m qual_metadata_extractor.extractor \
    "social_science_results_v2/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径" \
    "E:/pdf/001"
```

### 作为模块使用

```python
from qual_metadata_extractor import extract_qual_metadata

extract_qual_metadata(
    paper_dir="social_science_results_v2/论文名称",
    pdf_dir="E:/pdf/001"
)
```

## 环境变量

在 `.env` 文件中配置：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
```

## 输出示例

注入后的 L1_Context.md：

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
3. 政策文件: 党的二十大报告提出精细化服务理念，为AI赋能乡村文化服务提供
4. 现状数据: ChatGPT月活破亿，算力消耗巨大，凸显AI高成本与城乡"算力鸿沟"挑战。
5. 理论重要性: 本研究拓展了技术社会学与乡村文化振兴理论。
6. 实践重要性: 本研究为政府、基层实践者及企业提供AI赋能乡村文化的决策参考。
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

注入后的 L2_Theory.md（只包含自己的小标题）：

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
1. 经典理论回顾: 本研究运用技术接受模型和数字鸿沟理论进行分析。
2. 核心构念: 本研究探讨类ChatGPT技术如何赋能乡村文化振兴。
3. 构念关系: 数字基础设施、农民素养、内容适配性促进技术赋能。
4. 理论框架: 该论文构建了"机遇-挑战-条件"辩证框架。
5. 理论贡献: 本研究拓展了技术接受与数字鸿沟理论。
6. 详细分析: 该论文构建了技术赋能乡村文化的系统框架。
---

## 1. 经典理论回顾
...
```

注入后的 Full_Report.md（只有基础元数据，无小标题，无导航）：

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

# 社会科学深度阅读报告...
```

## 测试

运行测试脚本：

```bash
python test_qual_metadata_extractor.py
```

测试内容：
- 环境变量检查
- 文件路径验证
- 提取流程测试
- 输出结果验证

## 设计文档

详细设计请参考：[QUAL_METADATA_EXTRACTOR_DESIGN.md](../QUAL_METADATA_EXTRACTOR_DESIGN.md)

## 实现状态

- [x] MD 提取逻辑（正则 + DeepSeek 30字总结）
- [x] PDF 提取逻辑（pymupdf + Qwen-vl-plus）
- [x] 元数据合并逻辑（每个文档只包含自己的小标题）
- [x] Frontmatter 注入逻辑（扁平结构，Obsidian 可读）
- [x] 导航链接添加（L1-L4 层级文档，Full_Report 无导航）
- [x] 完整测试

## 元数据结构说明

- **L1_Context.md, L2_Theory.md, L3_Logic.md, L4_Value.md**:
  - 包含基础元数据（title, authors, journal, year, tags）
  - 包含该层的小标题元数据（扁平结构，直接在顶层）
  - 包含导航链接（返回总报告 + 其他层级）

- **Full_Report.md**:
  - 只包含基础元数据（title, authors, journal, year, tags）
  - 不包含小标题元数据
  - 不包含导航链接

这种结构确保 Obsidian Dataview 可以正确读取每个文档的元数据。
