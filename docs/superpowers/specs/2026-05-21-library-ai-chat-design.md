# 文献库 AI 智能查询设计文档

## 概述

在文献库（LibraryTab）页面内嵌一个可展开/收起的 AI 对话面板，用户用自然语言提问，系统调用 DeepSeek-v4-flash 完成两步流水线：关键词提取 → SQL 查询 → 报告生成。文献列表自动联动筛选结果，支持多轮追问。

## 架构

### 数据流

```
用户输入自然语言
  → DeepSeek-v4-flash 提取关键词（JSON 结构化输出，含同义词扩展）
  → 后端 SQL 查询 BibEntry（ILIKE OR 组合）
  → 后端查询 BibReference（命中集合内部的引用关系）
  → 命中文献结构化信息 + 用户问题 → DeepSeek-v4-flash 生成报告（流式）
  → SSE 推送：keywords → results → citations → report chunks → done
  → 前端：文献列表联动筛选 + 报告 Markdown 渲染 + 引用关系卡片
```

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/routers/library_chat.py` | AI 查询路由（SSE 流式端点） |
| `backend/prompts/library_chat_keywords.md` | 关键词提取提示词模板（可选，也可硬编码） |
| `backend/prompts/library_chat_report.md` | 报告生成提示词模板（可选，也可硬编码） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/main.py` | 注册 library_chat router |
| `frontend/src/LibraryTab.tsx` | 新增 AI 对话面板 UI + 联动逻辑 |

## 后端设计

### 端点

**`POST /api/library/chat`** — 主入口，返回 SSE 流

请求体：
```python
class LibraryChatRequest(BaseModel):
    question: str
    api_key: Optional[str] = None
    context_entry_ids: Optional[list[str]] = None  # 追问时传入上轮筛选结果
```

SSE 事件序列：

| event | data 格式 | 说明 |
|-------|-----------|------|
| `keywords` | `{"keywords": ["人工智能","AI",...], "journal": "管理世界"}` | 提取的关键词 |
| `results` | `{"entry_ids": ["id1","id2",...], "count": 5}` | 筛选命中文献 ID |
| `citations` | `{"links": [{"from_title":"A","to_title":"B"}]}` | 命中集合内引用关系 |
| `report` | `{"content": "## 概览\n..."}` | 报告 Markdown chunk（多次推送） |
| `done` | `{"entry_ids": [...]}` | 完成 |
| `error` | `{"message": "..."}` | 错误 |

### 处理流程

1. **验证 api_key** — `validate_deepseek_key(api_key)`
2. **第一步 LLM：关键词提取**
   - 模型：deepseek-v4-flash
   - `response_format={"type": "json_object"}`
   - 输出 JSON：`{"keywords": [...], "journal": null, "year_from": null, "year_to": null, "authors": []}`
   - 推送 `keywords` 事件
3. **SQL 查询** — 基于提取的条件查询 BibEntry
   - 追问模式：如果 `context_entry_ids` 非空，在上一轮结果内筛选
   - 关键词：对 `title` / `abstract` / `keywords_json` 做 `ILIKE OR` 组合，每个关键词命中任意字段即匹配
   - 期刊/年份/作者附加条件
   - 推送 `results` 事件
4. **引用关系查询** — 对命中的 entry_ids 查 BibReference
   - 查 `source_bib_entry_id IN entry_ids AND matched_bib_entry_id IN entry_ids`
   - 解析出命中集合内部的引用关系对
   - 推送 `citations` 事件
5. **第二步 LLM：报告生成** — 流式输出
   - 打包命中文献的结构化信息（标题、作者、年份、期刊、摘要、精读状态），全量投喂不截断
   - 流式推送 `report` 事件
   - 推送 `done` 事件

### SQL 查询逻辑

```python
stmt = select(BibEntry).where(BibEntry.owner_user_id == user.id)

# 追问模式
if context_entry_ids:
    stmt = stmt.where(BibEntry.id.in_(context_entry_ids))

# 关键词筛选
if keywords:
    keyword_conditions = []
    for kw in keywords:
        like = f"%{kw}%"
        keyword_conditions.append(or_(
            BibEntry.title.ilike(like),
            BibEntry.abstract.ilike(like),
            BibEntry.keywords_json.ilike(like),
        ))
    stmt = stmt.where(or_(*keyword_conditions))

# 期刊
if journal:
    stmt = stmt.where(BibEntry.journal.ilike(f"%{journal}%"))

# 年份范围
if year_from:
    stmt = stmt.where(BibEntry.year >= year_from)
if year_to:
    stmt = stmt.where(BibEntry.year <= year_to)

# 作者
if authors:
    for author in authors:
        stmt = stmt.where(BibEntry.authors_json.ilike(f"%{author}%"))
```

### 引用关系查询逻辑

```python
refs = await db.execute(
    select(BibReference).where(
        BibReference.source_bib_entry_id.in_(entry_ids),
        BibReference.matched_bib_entry_id.in_(entry_ids),
    )
)
links = [
    {
        "from_id": ref.source_bib_entry_id,
        "to_id": ref.matched_bib_entry_id,
        "from_title": id_to_title[ref.source_bib_entry_id],
        "to_title": id_to_title[ref.matched_bib_entry_id],
    }
    for ref in refs.scalars()
]
```

## 提示词设计

### 关键词提取提示词

```
你是一个学术文献库的检索助手。用户会用自然语言描述他想查找的文献，你需要从中提取结构化的检索条件。

## 表字段说明
- title: 论文标题
- abstract: 摘要
- keywords_json: 作者关键词（JSON 数组）
- journal: 期刊/来源名称
- year: 发表年份
- authors_json: 作者列表
- user_tags_json: 用户自定义标签

## 输出格式（JSON）
{
  "keywords": ["关键词1", "关键词2", ...],
  "journal": null,
  "year_from": null,
  "year_to": null,
  "authors": []
}

## 关键规则
1. **同义词必须充分扩展**——每个核心概念至少给出 3-6 个同义/近义/缩写表达，包括：
   - 中文全称、英文全称、常见缩写
   - 上位词（如"深度学习"→ 也包含"机器学习"、"人工智能"）
   - 下位词（如"人工智能"→ 也包含"深度学习"、"神经网络"、"大语言模型"、"LLM"）
   - 中英文双语都要覆盖
   - 学科内常见的替换说法（如"差异-in-differences"也涵盖"DID"、"双重差分"）
2. journal 字段：用户提到具体期刊时填写，否则 null
3. year_from / year_to：用户提到时间范围时填写，否则 null
4. authors：用户提到具体作者时填写姓名，否则空数组
5. keywords 数组中的每个词都会被用于 ILIKE 模糊匹配（%keyword%），所以给出变体即可，不需要加通配符
6. 只返回 JSON，不要任何解释文字

## 示例
用户问："管理世界发表的几篇和人工智能相关的论文"
输出：
{
  "keywords": ["人工智能", "AI", "artificial intelligence", "机器学习", "machine learning", "深度学习", "deep learning", "神经网络", "neural network", "大语言模型", "LLM", "large language model", "智能", "intelligent", "算法", "algorithm"],
  "journal": "管理世界",
  "year_from": null,
  "year_to": null,
  "authors": []
}
```

### 报告生成提示词

```
你是一个学术文献库的分析助手。用户提出了一个研究问题，系统已经根据检索条件筛选出了相关文献。请你基于以下文献信息，生成一份结构化的查询报告。

## 用户问题
{question}

## 筛选命中的文献（共 {count} 篇）

{papers}

## 报告要求

请用中文撰写报告，包含以下部分：

### 1. 概览
- 简要说明数据库中与用户问题相关的文献有几篇，整体研究主题分布如何

### 2. 各论文核心内容
- 逐篇概述每篇论文的研究问题、方法、主要发现（基于标题和摘要）
- 标注每篇的精读状态（已精读 / 未精读）

### 3. 精读状态与建议
- 列出哪些论文已经完成了精读
- 根据与用户问题的相关程度，建议哪些论文值得进一步精读，并说明理由

### 4. 研究缺口与建议
- 基于现有文献，指出该主题下可能存在的研究缺口
- 建议用户可以补充搜索哪些方向的文献

## 注意事项
- 严格基于提供的数据撰写，不要编造论文内容
- 如果某篇论文缺少摘要，注明"摘要缺失，建议补充元数据后重新查询"
- 报告使用 Markdown 格式
```

## 前端设计

### UI 布局

在 LibraryTab 现有两栏布局下方，新增可展开/收起的 AI 对话面板：

```
┌─────────────────────────────────────────────────┐
│  现有筛选栏（搜索、期刊、状态、排序...）            │
├──────────────────┬──────────────────────────────┤
│  文献列表        │  详情与时间线                  │
│  （筛选联动）    │                               │
├──────────────────┴──────────────────────────────┤
│  🤖 AI 文献助手（点击展开/收起）                   │
│  ┌─────────────────────────────────────────────┐│
│  │ 引用关系卡片（如有）                          ││
│  │ 报告区（Markdown 渲染）                      ││
│  └─────────────────────────────────────────────┤│
│  ┌─────────────────────────────────────────────┐│
│  │ 输入框 + 发送按钮             [清空对话]     ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### 状态管理

全部在 LibraryTab 内部 useState，不新增 store：

```typescript
const [chatOpen, setChatOpen] = useState(false)
const [chatQuestion, setChatQuestion] = useState('')
const [chatLoading, setChatLoading] = useState(false)
const [chatReport, setChatReport] = useState('')
const [chatKeywords, setChatKeywords] = useState<string[]>([])
const [chatCitations, setCitations] = useState<{from_title: string, to_title: string}[]>([])
const [chatFilteredIds, setChatFilteredIds] = useState<string[] | null>(null)
const [chatHistory, setChatHistory] = useState<{role: string, content: string}[]>([])
```

### 联动机制

- SSE 收到 `results` 事件 → `setChatFilteredIds(entry_ids)` → 文献列表只显示这些 ID 的文献
- 文献列表 `loadEntries` 增加参数：`chatFilteredIds` 非空时，用 `entry_ids` 查询参数过滤
- 点击"清空对话" → `setChatFilteredIds(null)` → 文献列表恢复全量

### SSE 调用

- 使用 `fetch` + `ReadableStream` 手动解析 SSE
- `context_entry_ids` 传入 `chatFilteredIds`（追问模式）
- 追问时报告区追加而非覆盖（或清空后重新展示完整历史）

### 交互细节

- 默认收起，点击标题栏展开
- 输入框 Enter 发送、Shift+Enter 换行
- 报告区 Markdown 渲染（复用现有渲染逻辑）
- 引用关系在报告上方用卡片列表："《论文A》 引用了 《论文B》"
- 加载中 spinner + "正在分析..."
- 错误在面板内红色提示

## 不做的事（YAGNI）

- 不持久化对话历史到数据库（v1 内存中保留，刷新页面清空）
- 不新增数据表
- 不新增 Alembic migration
- 不生成独立的 Job（直接 SSE 流式返回）
- 不做引用关系图谱可视化（v1 简单列表展示）
