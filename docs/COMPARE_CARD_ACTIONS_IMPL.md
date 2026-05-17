# 对比页 AnswerCard 三按钮功能实施记录

> **版本**: v1.1  
> **日期**: 2026-05-15  
> **状态**: 已实施  
> **设计文档**: [compare-card-actions-design.md](./superpowers/specs/2026-05-14-compare-card-actions-design.md)

## 1. 概述

在对比分析页面的每张 AnswerCard（单篇文献 × 单个维度）上新增三个操作按钮，让用户可以在对比视图中直接编辑内容、添加点评笔记、调用 AI 总结选中文字。

三个功能围绕统一的模式状态机（`CardMode`）组织，同一时刻只有一张卡片处于非普通模式。

### 实施完成清单

| # | 内容 | 文件 | 状态 |
|---|------|------|------|
| 1 | `reading_item_edits` 表（编辑覆盖层） | `backend/db/models.py` + 迁移 011 | ✅ |
| 2 | `annotations` 表（点评 + AI 总结） | `backend/db/models.py` + 迁移 011 | ✅ |
| 3 | `prompt_templates` CHECK 约束扩展（加 `compare`） | 迁移 011 | ✅ |
| 4 | 提示词注册：`compare.ai_summary` 槽位 | `backend/prompt_registry.py` | ✅ |
| 5 | 默认提示词文件 | `prompts/compare/ai_summary.md` | ✅ |
| 6 | 编辑覆盖 API（PUT / DELETE） | `backend/routers/compare.py` | ✅ |
| 7 | 点评 CRUD API（POST / GET / PUT / DELETE） | `backend/routers/compare.py` | ✅ |
| 8 | AI 总结 API（POST /ai-summary） | `backend/routers/compare.py` | ✅ |
| 9 | reading-data 响应扩展（含 edit / annotations） | `backend/routers/compare.py` | ✅ |
| 10 | AnswerCard 模式状态机 + 三模式 UI | `frontend/src/components/compare/AnswerCard.tsx` | ✅ |
| 11 | AccordionPanel 模式管理（维度级批量切换 + 单卡独立） | `frontend/src/components/compare/AccordionPanel.tsx` | ✅ |
| 12 | CSS 样式（`.compare-root` 作用域） | `frontend/src/components/compare/compare.css` | ✅ |
| 13 | CompareView 传递 apiKey / refetch | `frontend/src/components/CompareView.tsx` | ✅ |
| 14 | useCompareData 类型扩展 | `frontend/src/hooks/useCompareData.ts` | ✅ |

---

## 2. 数据库层

### 2.1 新增表：reading_item_edits（迁移 011）

编辑覆盖层，不修改原始 `reading_items.content`。采用 upsert 语义：每用户每 reading_item 最多一条记录。

```sql
CREATE TABLE reading_item_edits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_item_id INTEGER NOT NULL REFERENCES reading_items(id) ON DELETE CASCADE,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    edited_content  TEXT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (reading_item_id, owner_user_id)
);
```

**读取优先级**：`reading_item_edits.edited_content` > `reading_items.content`

**ORM 模型**：`backend/db/models.py:ReadingItemEdit`

### 2.2 新增表：annotations（迁移 011）

统一存储人工点评和 AI 生成总结。通过 `source_type` 和 `is_ai_generated` 区分类型。

```sql
CREATE TABLE annotations (
    id              TEXT PRIMARY KEY,                           -- UUID
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    source_type     TEXT NOT NULL CHECK (source_type IN
                        ('compare_card','ai_summary','library_note')),
    source_id       TEXT NOT NULL,                              -- 关联 reading_item_id 的字符串形式
    bib_entry_id    TEXT,                                       -- 冗余字段，按文献聚合
    selected_text   TEXT,                                       -- 选中的原文片段
    note            TEXT NOT NULL,                              -- 点评笔记或 AI 总结
    char_start      INTEGER,                                   -- 字符偏移（尽力计算）
    char_end        INTEGER,
    is_ai_generated INTEGER NOT NULL DEFAULT 0,                -- 0=人工, 1=AI
    color           TEXT,                                       -- 高亮颜色
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**ORM 模型**：`backend/db/models.py:Annotation`

### 2.3 约束变更

`prompt_templates.prompt_type` 的 CHECK 约束从 `('quant','qual','long','filter')` 扩展为 `('quant','qual','long','filter','compare')`。

---

## 3. 后端 API

所有新端点注册在 `backend/routers/compare.py`，挂在 `/api/compare` 前缀下。

### 3.1 编辑覆盖

| 方法 | 路径 | 说明 |
|------|------|------|
| `PUT` | `/api/compare/reading-items/{item_id}/edit` | 保存/更新编辑覆盖（upsert），body: `{ edited_content: string }` |
| `DELETE` | `/api/compare/reading-items/{item_id}/edit` | 删除编辑覆盖（回退到原始） |

**实现要点**：
- 先查询 `ReadingItem` 验证归属（`owner_user_id == user.id`）
- 再查询 `ReadingItemEdit` 决定是 insert 还是 update
- `updated_at` 手动更新为当前时间

### 3.2 点评 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/compare/annotations` | 创建点评，body: `{ source_type, source_id, selected_text, note, ... }` |
| `GET` | `/api/compare/annotations?source_type=&source_id=&is_ai=` | 按条件查询 |
| `PUT` | `/api/compare/annotations/{id}` | 更新笔记内容/颜色 |
| `DELETE` | `/api/compare/annotations/{id}` | 删除点评 |

**实现要点**：
- ID 使用 `uuid.uuid4()`
- `source_type` 在 DB 层 CHECK 约束保证合法性
- 查询接口支持 `source_type`、`source_id`、`is_ai` 三个可选过滤器

### 3.3 AI 总结

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/compare/ai-summary` | body: `{ text, api_key, reading_item_id, bib_entry_id?, char_start?, char_end? }` → `{ summary, annotation_id }` |

**实现要点**：
1. 通过 `prompt_service.get_effective_prompt_text()` 获取 `compare.ai_summary` 的生效提示词（用户覆盖 > 系统默认 > 文件兜底）
2. 替换 `{selected_text}` 占位符为实际选中文本
3. 调用 `deepseek-v4-flash`（temperature=0.3, max_tokens=200）
4. 结果同时存入 `annotations` 表（`is_ai_generated=1`, `source_type='ai_summary'`）
5. 返回总结文本和 annotation_id

### 3.4 reading-data 响应扩展

`GET /api/compare/reading-data?mode=...` 在原有响应基础上：

1. 批量查询 `ReadingItemEdit`（按 `owner_user_id` + `reading_item_id IN (...)`）
2. 批量查询 `Annotation`（按 `owner_user_id` + `source_type IN ('compare_card','ai_summary')` + `source_id IN (...)`）
3. 构建 `edits_map: dict[int, ReadingItemEdit]` 和 `annotations_map: dict[int, list[Annotation]]`
4. 在 `build_compare_response` 中，每个维度项/子问题增加 `edit`、`annotations`、`reading_item_id` 字段

**响应结构变化**（以 long 模式维度为例）：

```json
{
  "id": "theory",
  "label": "理论框架",
  "content": "实际显示的内容（编辑版优先）",
  "reading_item_id": 123,
  "edit": { "edited_content": "...", "updated_at": "2026-05-15T..." },
  "annotations": [
    {
      "id": "uuid-xxx",
      "source_type": "compare_card",
      "selected_text": "原文片段",
      "note": "点评内容",
      "char_start": 42,
      "char_end": 68,
      "is_ai_generated": 0,
      "color": "#fef08a",
      "created_at": "2026-05-15T..."
    }
  ]
}
```

---

## 4. 提示词管理

### 4.1 新增提示词类型

`PROMPT_TYPE_LABELS` 新增 `"compare": "对比分析"`。

`PROMPT_REGISTRY` 新增：

```python
"compare": {
    "ai_summary": {
        "title": "AI 文本总结",
        "file_path": "prompts/compare/ai_summary.md",
    },
},
```

### 4.2 默认提示词

`prompts/compare/ai_summary.md` 内容：

```
你是一位学术文本总结助手。请将用户选中的学术文本片段总结为一句话。

要求：
1. 保留核心信息（研究对象、方法、结论、关键数据等）
2. 语言简洁，不超过 50 个汉字
3. 使用学术语言，避免口语化
4. 不要添加原文中没有的信息

选中的文本：
{selected_text}
```

`prompt_service.ensure_builtin_prompt_templates` 自动将新槽位导入 `prompt_templates` 表（幂等），前端 PromptsTab 下拉自动出现「对比分析」选项。

---

## 5. 前端实现

### 5.1 AnswerCard 模式状态机

`frontend/src/components/compare/AnswerCard.tsx`

```
type CardMode = 'normal' | 'editing' | 'annotating' | 'ai_summarizing'
type AiDisplayMode = 'summary_only' | 'original_only' | 'both'
```

四种模式互斥，通过 props `cardMode` 和 `isActive` 控制：

| cardMode | 显示内容 |
|----------|---------|
| `normal` | 原始精读内容（有编辑覆盖则显示编辑版），不显示高亮/点评/AI总结。右上角如有编辑覆盖显示「已编辑」标记 |
| `editing` | `<textarea>` 自适应全文高度（`scrollHeight` 动态计算），顶部操作栏（保存 / 撤销 / 回退到原始 / 取消）。保存后**留在编辑模式**，可继续编辑 |
| `annotating` | 显示所有 `is_ai_generated=0` 的高亮标注 + 笔记浮标，可选中文字新建点评。点击已有高亮直接弹出浮窗编辑/删除。保存后**留在点评模式** |
| `ai_summarizing` | 顶部切换条（只看总结 / 只看原文 / 对照），可选中文字触发 AI 总结。总结完成后**留在 AI 总结模式**并自动切到对照视图 |

**关键 props**：

```typescript
interface AnswerCardProps {
  paper: { id, title, authors, year }
  content: string | null
  variant: 'preview' | 'full'
  edit?: EditData
  annotations?: AnnotationData[]
  readingItemId?: number
  cardMode?: CardMode
  onModeChange?: (mode: CardMode) => void
  isActive?: boolean
  apiKey?: string | null
  onRefresh?: () => void
}
```

**编辑模式**：
- `handleSaveEdit` → `PUT /api/compare/reading-items/{id}/edit` → **留在编辑模式** → `onRefresh()`（静默刷新，不卸载组件树）
- `handleRevertEdit` → `DELETE /api/compare/reading-items/{id}/edit` → textarea 恢复原始内容 → 保持在编辑模式
- `handleUndo` → 从 `undoStack` 栈顶弹出上一步内容恢复到 textarea（每次输入变化前推入旧值）
- 取消 → 不保存，直接退出

**点评模式**：
- `handleTextSelect` → 检测 `window.getSelection()` → 弹出浮窗（新建点评）
- 浮窗内可选高亮颜色（6 色板），输入笔记后 `POST /api/compare/annotations` → **留在点评模式**
- 点击已有高亮 → 通过 `useEffect` 监听 `[data-ann-id]` 的 click 事件 → 弹出同一浮窗，可编辑（`PUT`）或删除（`DELETE`）→ **留在点评模式**
- 底部点评列表每条也提供独立的「编辑」「删除」按钮
- 高亮渲染使用 `renderAnnotatedContent`：按 `selected_text` 做文本匹配（而非字符偏移，因为编辑后偏移可能失效）

**AI 总结模式**：
- `handleAiSummary` → `POST /api/compare/ai-summary` → 结果存入 `annotations`（`is_ai_generated=1`）→ **留在 AI 总结模式**并自动切到对照视图（`setAiDisplayMode('both')`）
- 三种子显示模式通过 `AiDisplayMode` 切换

### 5.2 AccordionPanel 模式管理

`frontend/src/components/compare/AccordionPanel.tsx`

管理 `cardModes: Record<string, CardMode>` 状态，每张卡片独立持有模式。支持两种模式切换入口：

**单卡切换**：AnswerCard 内按钮触发 `onModeChange(paperId, mode)`，仅改变对应卡片的模式。

**维度级批量切换**：维度 header 右侧三按钮（编辑/点评/AI总结，仅 `state === 'full'` 时可见）触发 `handleDimModeChange(targetMode)`，将所有卡片同时设为同一模式；再次点击退出。

```typescript
const handleDimModeChange = (targetMode: CardMode) => {
  setCardModes((prev) => {
    const allInTarget = papers.every((p) => prev[p.id] === targetMode)
    if (allInTarget) return {}  // 退出
    const next: Record<string, CardMode> = {}
    for (const p of papers) next[p.id] = targetMode
    return next
  })
}
```

`dimMode` 为计算属性：当所有活跃卡片模式一致时返回该模式（用于按钮高亮），否则返回 `'normal'`。每张 AnswerCard 的 `isActive` 由 `cardModes[paperId] !== 'normal'` 决定，不再限制为单卡活跃。

### 5.3 useCompareData 静默刷新机制

`frontend/src/hooks/useCompareData.ts`

`refetch()` 区分初始加载与静默刷新，避免刷新数据时卸载组件树导致模式状态丢失：

```typescript
const fetchData = useCallback(async (silent = false) => {
  if (!silent) setLoading(true)   // 仅初始加载触发 loading 状态
  // ... fetch & setData ...
  if (!silent) setLoading(false)
}, [mode])

const refetch = useCallback(() => fetchData(true), [fetchData])
```

**为什么需要静默刷新**：`CompareView` 在 `loading === true` 时渲染 loading 页面，会卸载所有 `AccordionPanel`，导致其 `cardModes` 状态丢失。`refetch` 使用 `silent=true` 确保 `loading` 不变，组件树保持挂载。

### 5.4 CompareView 数据传递

`frontend/src/components/CompareView.tsx`

- 从 `useCompareData` 获取 `refetch` 回调（静默刷新）
- 传递 `apiKey` 和 `onRefresh={refetch}` 给 AccordionPanel
- AccordionPanel 再传递给每张 AnswerCard

### 5.5 useCompareData 类型扩展

`frontend/src/hooks/useCompareData.ts`

接口新增字段：

```typescript
interface DimItem {
  id: string
  label: string
  content: string
  reading_item_id?: number
  edit?: EditData
  annotations?: AnnotationData[]
}
```

### 5.6 CSS 样式

所有新增样式在 `frontend/src/components/compare/compare.css` 中，严格限定在 `.compare-root` 作用域下：

- `.compare-card-mode-buttons` — 按钮行
- `.compare-mode-btn` — 模式切换按钮（含 `.compare-mode-btn-exit` 退出样式）
- `.compare-edited-badge` — 「已编辑」标记
- `.compare-edit-area` / `.compare-edit-textarea` — 编辑区（textarea `overflow: hidden`，`useEffect` 监听内容变化自动调整 `scrollHeight`）
- `.compare-edit-top-bar` — 编辑模式顶部操作栏（保存 / 撤销 / 回退到原始 / 取消）
- `.compare-annotate-wrapper` — 点评模式外层容器
- `.compare-annotation-popup` — 点评弹窗（绝对定位，新建和编辑共用）
- `.compare-annotation-popup-label` — 编辑点评时的「编辑点评」标题
- `.compare-annotation-item` — 点评列表条目
- `.compare-annotation-item-delete` — 点评列表删除按钮
- `.compare-ai-toggle` / `.compare-ai-toggle-btn` — AI 总结子视图切换条
- `.compare-ai-summaries` / `.compare-ai-summary-item` — AI 总结结果展示

---

## 6. 数据流

### 6.1 读取流程

```
CompareView
  → useCompareData(mode)
    → GET /api/compare/reading-data?mode=...
      → 查 ReadingItem
      → 查 ReadingItemEdit（同批 reading_item_id）
      → 查 Annotation（同批 reading_item_id，source_type IN ('compare_card','ai_summary')）
      → 组装：content = edit?.edited_content ?? readingItem.content
    → 返回 papers（含 edit / annotations / reading_item_id）
  → AnswerCard 渲染：
    - displayContent = edit?.edited_content ?? content
    - annotations = 过滤当前 reading_item 的标注
    - 根据 cardMode 决定显示内容
```

### 6.2 编辑流程

```
用户点「编辑」→ cardMode = 'editing'
→ textarea 加载 displayContent（自适应全文高度）
→ 点「保存」→ PUT /api/compare/reading-items/{id}/edit → refetch()（静默）→ 留在编辑模式
→ 点「撤销」→ 从 undoStack 弹出上一步内容 → textarea 恢复
→ 点「回退到原始」→ DELETE /api/compare/reading-items/{id}/edit → textarea 恢复原始 → 留在编辑模式
→ 点「取消」→ cardMode = 'normal'
```

### 6.3 点评流程

```
用户点「点评」→ cardMode = 'annotating'
→ 显示 is_ai_generated=0 的 annotations（高亮 + 笔记列表）
→ 选中文字 → mouseup → 弹出浮窗（选中文字 + 笔记输入框 + 颜色选择）
→ 输入笔记 → POST /api/annotations → refetch()（静默）→ 留在点评模式
→ 点击已有高亮 → click 事件（[data-ann-id]）→ 弹出编辑浮窗（笔记输入 + 保存/删除/取消）→ 留在点评模式
→ 底部列表 → 点击「编辑」→ 弹出编辑浮窗；点击「删除」→ DELETE → 留在点评模式
→ 点「退出点评」→ cardMode = 'normal'
```

### 6.4 AI 总结流程

```
用户点「AI 总结」→ cardMode = 'ai_summarizing'
→ 显示 is_ai_generated=1 的 annotations
→ 顶部切换条：只看总结 / 只看原文 / 对照
→ 选中文字 → mouseup → 弹出「AI总结」按钮
→ 点击 → POST /api/compare/ai-summary { text, api_key, reading_item_id, ... }
  → 后端获取 compare.ai_summary 提示词 → 替换 {selected_text}
  → 调用 deepseek-v4-flash → 存 annotations(is_ai_generated=1)
  → 返回 { summary, annotation_id }
→ 前端追加到 AI 总结列表 → 自动切到对照视图（both）→ 留在 AI 总结模式
→ 点「退出 AI 总结」→ cardMode = 'normal'
```

---

## 7. 文件变更清单

### 后端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/db/models.py` | 新增 | `ReadingItemEdit`、`Annotation` 模型；`PromptTemplate` CHECK 约束扩展 |
| `backend/migrations/versions/011_add_edits_and_annotations.py` | 新增 | 创建两张表 + 修改约束 |
| `backend/prompt_registry.py` | 修改 | 新增 `compare` 类型 + `ai_summary` 槽位 |
| `backend/routers/compare.py` | 修改 | 7 个新端点 + `get_reading_data` 扩展 |
| `prompts/compare/ai_summary.md` | 新增 | AI 总结默认提示词 |

### 前端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/components/compare/AnswerCard.tsx` | 重写 | 卡片模式状态机 + 编辑/点评/AI总结 UI（v1.1：编辑顶部操作栏+撤销栈、点评高亮点击编辑/删除、保存后保持模式） |
| `frontend/src/components/compare/AccordionPanel.tsx` | 重写 | 模式互斥管理 + 传递 apiKey/onRefresh |
| `frontend/src/components/compare/compare.css` | 修改 | 新增约 280 行样式（v1.1：`.compare-edit-top-bar`、`.compare-annotate-wrapper`、`.compare-annotation-item-delete`、`.compare-annotation-popup-label`） |
| `frontend/src/components/CompareView.tsx` | 修改 | 传递 apiKey、refetch |
| `frontend/src/hooks/useCompareData.ts` | 修改 | 类型扩展 + 静默刷新机制（`silent` 参数避免 refetch 卸载组件树） |

---

## 8. 注意事项

1. **迁移必须执行**：部署后需 `alembic upgrade head` 创建新表和更新约束
2. **CSS 隔离**：所有样式在 `.compare-root` 下，keyframes 带 `compare-` 前缀
3. **高亮定位**：编辑覆盖后字符偏移可能失效，前端使用 `selected_text` 文本匹配而非偏移量定位
4. **API Key**：AI 总结需要用户在前端设置 DeepSeek Key
5. **提示词可定制**：用户可在 PromptsTab 的「对比分析」分类下自定义 AI 总结提示词
6. **路由注册验证**：`compare.py` 改完后用 `python -c "from routers.compare import router; [print(r.path) for r in router.routes]"` 验证所有端点完整
7. **24h 过期清理**：`reading_item_edits` 跟随 `reading_items` 级联删除；`annotations` 需按 `owner_user_id` 应用层清理
8. **静默刷新**：`useCompareData.refetch()` 使用 `silent=true` 避免设置 `loading` 状态，防止 `CompareView` 卸载组件树导致 `AccordionPanel` 的模式状态丢失
9. **撤销栈**：编辑模式维护 `undoStack: string[]`，每次 `onChange` 前推入旧值（通过 `pushUndo` 中间函数），撤销时弹出栈顶恢复。栈在进入编辑模式和回退到原始时清空
