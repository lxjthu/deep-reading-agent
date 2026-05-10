# AI 文献综述模块设计文档

**日期**：2026-05-10
**状态**：已确认，待实施
**涉及文件**：`backend/routers/compare.py`、`frontend/public/compare_7step.html`、`compare_4step.html`、`compare_long.html`

---

## 1. 背景与目标

### 现有对比功能的局限

现有 `POST /api/compare/analyze` 和 `/analyze_long` 使用 `deepseek-v4-flash` 生成横向对比综述，存在以下不足：

1. **模型能力有限**：v4-flash 无法进行深层次的文献对话和源流分析
2. **参考文献不利用**：仅使用当前参与对比的文献，未利用已提取的 BibReference 数据
3. **Prompt 设计浅层**：只做横向比较，缺乏梳理、源流比较、缺漏分析、新起点等深度维度
4. **引用标注粗糙**：程序化生成 APA 引用目录，非 LLM 生成正文内标注
5. **输出结构固定**：有引言+分节+结论的固定结构，不够灵活

### 新综述模块的目标

在**不破坏现有对比功能**的前提下，新增 AI 综述能力：

- 按**维度名组织小标题**（无引言/结论），专注每个维度下的深度分析
- 五层写作结构：梳理总结 → 源流比较 → 学术对话 → 缺漏分析 → 新起点
- 使用 `deepseek-reasoner`（thinking 模式），获得更深层的推理能力
- 充分利用已提取的参考文献（BibReference），支持**二次引用**
- 正文使用**中文间注法** `(作者, 年份)` 标注，文末附 **GB/T 7714** 参考文献目录

---

## 2. 用户交互流程

```
用户在对比页面选文献 → 选维度/子问题（现有流程不变）
  → 点击「AI 综述」按钮（新增，与现有「对比分析」并列）
  → 前端调用 /api/compare/synthesis 或 /synthesis_long
  → 显示进度（逐维度生成，每个维度 ~15-30s）
  → 完成后在 modal 中展示综述文本
  → 自动保存为 synthesis_md Artifact，出现在历史记录和文献库时间线
```

**不改动的部分**：
- 现有对比分析按钮和功能完全不变
- 文献选择、维度选择表格逻辑不变
- HistoryTab 和 LibraryTab 已有 synthesis_md 的展示支持

---

## 3. API 端点设计

### 3.1 `POST /api/compare/synthesis` — 七步/四步综述

```python
class SynthesisRequest(BaseModel):
    dimensions: list[dict]  # [{"label": "研究问题", "step": "第一步"}, ...]
    bib_entry_ids: list[str]
    paperData: list = []
    api_key: str | None = None
```

### 3.2 `POST /api/compare/synthesis_long` — 长文本综述

```python
class LongSynthesisRequest(BaseModel):
    dimensions: list[str]  # ["理论基础", "研究方法", ...]
    bib_entry_ids: list[str]
    paperData: list = []
    api_key: str | None = None
```

### 3.3 统一响应格式

```python
{
    "synthesis": "完整综述文本（含维度小节+参考文献目录）",
    "job_id": "uuid",
    "output_path": "storage_path",
    "dimension_sections": [
        {"label": "研究问题", "content": "该维度综述内容"},
        ...
    ]
}
```

### 3.4 产物存储

| 字段 | 值 |
|------|------|
| `Job.job_type` | `"synthesis"` |
| `JobBibEntry.role` | `"synthesis_member"` |
| `Artifact.artifact_type` | `"synthesis_md"` |
| 文件名 | `synthesis_{job_id}.md` |

---

## 4. 数据流与 LLM 调用策略

### 4.1 完整数据流

```
resolve_compare_members()     — 复用现有函数
ensure_paper_data()           — 复用现有函数
gather_bib_references()       — 新增：从 BibReference 收集已提取的参考文献
build_author_citation_map()   — 新增：构建「作者→年份→文献」引用索引
create_compare_job()          — 复用，job_type="synthesis", role="synthesis_member"
FOR EACH 维度（串行）:
    build_synthesis_prompt()  — 新增：含文献元数据 + 维度内容 + 二次引用
    deepseek-reasoner 调用    — 启用 thinking
    收集该维度综述文本
assemble_synthesis()          — 新增：拼接所有维度小节
build_gbt7714_references()    — 新增：生成 GB/T 7714 参考文献目录
persist_synthesis_result()    — 新增：保存为 synthesis_md Artifact
返回完整综述
```

### 4.2 调用顺序：串行逐维度

- 串行调用（非并行），后一个维度可利用前面维度的发现
- 每个维度一次 reasoner 调用，约 15-30 秒

### 4.3 二次引用数据来源

对每个参与综述的 BibEntry，查询其关联的 `BibReference`（已通过参考文献提取功能获得），构建参考文献池。在 prompt 中以结构化格式呈现给 LLM。

### 4.4 Reasoner thinking 处理

`deepseek-reasoner` 返回 `reasoning_content` 和 `content`，只取 `content` 作为综述文本。thinking 过程不保存。

---

## 5. Prompt 设计

### 5.1 系统提示词（所有调用共享，固定不变以命中缓存）

```
你是一位资深的学术文献综述专家。你的任务是根据已完成的精读分析，撰写高质量的
文献综述段落。你必须严格基于所提供的文献内容，不得捏造任何数据或结论。

你的综述风格要求：
- 不写引言和结论，直接以维度名作为小标题开始
- 专注每个维度下文献之间的梳理、总结、源流比较和学术对话
- 分析现有研究的缺漏和新研究的起点
- 引用格式使用间注法：（作者，年份），如（张三等，2024）或（Smith & Jones, 2023）
- 转引标注为：（原作者，年份，转引自 引用者，年份）
- 不要写参考文献目录，系统会自动生成
```

### 5.2 用户 Prompt 结构（缓存优化）

Prompt 分为**固定前缀**（文献元数据，多次调用间相同，命中缓存）和**变化后缀**（维度名和内容）：

```
[固定部分 — 文献元数据]

以下是 {N} 篇文献的元信息，用于引用标注：

━━━ 文献 1 ━━━
标题：{title}
作者：{author1}, {author2}, ...
年份：{year}
期刊：{journal}
引用标注：(第一作者姓等, 年份)

━━━ 文献 2 ━━━
（同上格式）

[固定部分 — 二次引用信息]

以下文献在原文中引用了这些参考文献，你可以使用转引方式引用：

━━━ (Smith等, 2023) 引用了： ━━━
1. (Wang, 2020) — 标题：XXX
2. (Li & Chen, 2019) — 标题：XXX

━━━ (张三等, 2024) 引用了： ━━━
1. (Jones et al., 2021) — 标题：XXX

[变化部分 — 维度内容]

【当前综述维度】{维度名}

【写作任务】
请撰写该维度的综述段落，包含以下层次：
1. **梳理与总结**：概述各文献在该维度的核心观点和发现
2. **源流比较**：比较不同文献的研究路径、方法论来源、理论根基的异同
3. **学术对话**：呈现文献间的共识与分歧，构建观点的交锋与呼应
4. **缺漏分析**：识别该维度下现有研究的盲区、方法局限或数据空白
5. **新起点**：基于以上分析，指出未来研究可突破的方向

【引用要求】
- 正文使用间注法：（第一作者姓等，年份）
- 可使用转引：（被引作者, 年份, 转引自 引用作者, 年份）
- 不要写参考文献目录

【各文献在该维度的精读内容】

━━━ 文献 1 (Smith等, 2023) ━━━
{该维度的精读内容，上限3000字符}

━━━ 文献 2 (张三等, 2024) ━━━
{该维度的精读内容}
```

### 5.3 缓存命中策略

- System prompt 在所有维度调用中完全一致
- 用户 prompt 前缀（文献元数据 + 二次引用）保持固定顺序
- 仅维度名和维度内容变化
- DeepSeek API 通过 prefix matching 自动缓存重复部分

---

## 6. 参考文献目录生成

### 6.1 正文引用标注格式

- 单作者：`(张三, 2024)`
- 两作者：`(Smith & Jones, 2023)`
- 三作者及以上：`(王五等, 2023)` 或 `(Smith et al., 2023)`
- 二次引用：`(Wang, 2020, 转引自 Smith等, 2023)`

### 6.2 文末参考文献目录格式（GB/T 7714）

分为两部分：

**主要参考文献**（当前参与对比的文献）：
```
[1] 张三, 李四. 论文标题[J]. 期刊名, 2024, 15(3): 45-67.
[2] Smith J, Jones M. Paper Title[J]. Journal Name, 2023, 10(2): 123-145.
```

**二次引用文献**（从 BibReference 提取的）：
```
[3] Wang L. Referenced Title[J]. Another Journal, 2020, 5(1): 78-90. (转引自: 张三等, 2024)
```

### 6.3 编号规则

按在综述正文中**首次出现的顺序**编号。程序化处理：
1. 扫描综述正文中的所有 `(作者, 年份)` 标注
2. 按出现顺序去重编号
3. 匹配到文献元数据或 BibReference 数据
4. 生成 GB/T 7714 格式条目

---

## 7. 代码改动清单

### 7.1 后端 `backend/routers/compare.py`（新增约 300 行）

**新增函数**：

| 函数 | 职责 |
|------|------|
| `SynthesisRequest` | 七步/四步综述请求体 |
| `LongSynthesisRequest` | 长文本综述请求体 |
| `gather_bib_references()` | 从 BibReference 收集已提取的参考文献 |
| `build_author_citation_map()` | 构建引用索引 |
| `build_synthesis_system_prompt()` | 综述专用系统提示词 |
| `build_synthesis_dimension_prompt()` | 单维度综述 prompt（含缓存优化结构） |
| `build_gbt7714_references()` | GB/T 7714 参考文献目录生成 |
| `persist_synthesis_result()` | 保存 synthesis_md 产物 |
| `POST /synthesis` | 七步/四步综述端点 |
| `POST /synthesis_long` | 长文本综述端点 |

**复用函数**（不改动）：
- `resolve_compare_members()`
- `build_structured_paper_data()`
- `ensure_paper_data()`
- `create_compare_job()`
- `get_api_key()` / `compute_expires_at()` / `get_results_dir()` / `build_storage_path()`
- `parse_paper_authors()` / `bib_entry_to_paper_data()`

**不改动**：现有 `/analyze` 和 `/analyze_long` 端点

### 7.2 前端（改动 3 个 HTML 文件）

| 文件 | 改动 |
|------|------|
| `compare_7step.html` | 增加「AI 综述」按钮，调用 `/synthesis` |
| `compare_4step.html` | 增加「AI 综述」按钮，调用 `/synthesis` |
| `compare_long.html` | 增加「AI 综述」按钮，调用 `/synthesis_long` |

每个文件的改动：
1. 在现有「生成对比」按钮旁增加「AI 综述」按钮
2. 新增 `doAISynthesis()` 函数，构建请求并调用新端点
3. 新增进度显示（逐维度进度）
4. 在 modal 中展示结果

### 7.3 不需要改动的部分

- `db/models.py`：所有需要的类型（synthesis、synthesis_md、synthesis_member）已定义
- `prompt_registry.py`：暂不集成（未来可扩展）
- `LibraryTab.tsx`：已有 synthesis_md 的展示支持
- `HistoryTab`：已有 synthesis 子 tab
- `main.py`：compare router 已注册

---

## 8. 与现有功能的隔离保证

| 保证项 | 措施 |
|--------|------|
| 现有对比端点不受影响 | 新增独立端点，不修改 `/analyze` 和 `/analyze_long` |
| 现有数据结构不受影响 | 复用已有的 synthesis job_type 和 synthesis_md artifact_type |
| 前端对比按钮不受影响 | 新增按钮，不修改现有按钮的逻辑 |
| 数据库无需迁移 | 所有字段类型已在约束中定义 |
| LLM 调用互不干扰 | 综述用 reasoner，对比用 v4-flash，各端点独立选择模型 |

---

## 9. 已知限制与未来扩展

1. **串行调用延迟**：N 个维度需要 N×15-30 秒，未来可改为并行+最终整合
2. **Prompt 注册**：暂不集成 prompt_registry，未来可注册 synthesis 类型槽位让用户自定义
3. **流式输出**：当前返回完整结果，未来可改为 SSE 流式返回
4. **参考文献去重**：二次引用可能和主要文献重叠，需要去重逻辑
5. **长文本截取**：单维度 3000 字符上限可能不够，未来可根据 reasoner 上下文窗口动态调整
