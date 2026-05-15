# 对比页 AnswerCard 三按钮功能设计

> 日期：2026-05-14
> 状态：已确认，待实施
> 关联文档：[DATABASE_SCHEMA.md](../DATABASE_SCHEMA.md)、[TECHNICAL_OVERVIEW.md](../TECHNICAL_OVERVIEW.md)、[STATE_AND_API_MAP.md](../STATE_AND_API_MAP.md)

## 1. 需求概述

在长文本对比、七步对比、四步对比页面的每张 AnswerCard（单篇文献 × 单个维度）上增加三个操作按钮：

1. **编辑/保存**：直接编辑该维度的精读文本，保存为覆盖层（不破坏原始 AI 精读结果）
2. **点评**：进入点评模式后，可选中文字高亮并输入点评笔记，点评存入全局点评库
3. **AI 总结**：进入 AI 总结模式后，可选中文字点击 AI 总结，AI 将选中文字总结为一句话

按钮放置在 **AnswerCard 级别**（每张卡片独立操作）。

## 2. 模式状态机

AnswerCard 新增一个 `cardMode` 状态，四种互斥模式：

```
              点击「编辑」              点击「点评」             点击「AI总结」
  [普通模式] ──────────▶ [编辑模式]   ──────────▶ [点评模式]  ──────────▶ [AI总结模式]
     ▲                     │  │            │  │             │  │
     │                     │  │            │  │             │  │
     └─────────────────────┘  └────────────┘  └─────────────┘
               保存 / 取消         退出点评         退出 AI 总结
```

- 同一时刻只有一张卡片处于非普通模式（点另一张卡片的按钮时，当前卡片自动回到普通模式）
- 普通模式下不显示任何标注、点评、AI 总结结果（保持原始阅读体验）

### 2.1 显示规则

| cardMode | 显示内容 |
|----------|---------|
| 普通 | 原始精读内容（如有编辑覆盖则显示编辑后的内容），不显示高亮/点评/AI总结 |
| 编辑 | `<textarea>` 加载当前内容（编辑版优先），底部有「保存」「回退到原始」「取消」三个按钮 |
| 点评 | 显示所有用户点评（高亮标注 + 笔记浮标），可选中文字新建点评 |
| AI 总结 | 根据子模式切换显示：只显示总结结果 / 只显示原文 / 同时显示 |

## 3. 功能 1：编辑/保存

### 3.1 交互流程

1. 点击「编辑」按钮 → cardMode 切换为 `editing`
2. 卡片内容区变为 `<textarea>`，加载 `edited_content ?? original_content`
3. 底部出现三个按钮：
   - **保存**：保存当前 textarea 内容到 `reading_item_edits` 表，显示「已编辑」标记，回到普通模式
   - **回退到原始**：删除 `reading_item_edits` 记录，textarea 内容恢复为 `ReadingItem.content`，**保持在编辑模式**（用户可继续基于原始内容编辑）
   - **取消**：不保存，回到普通模式
4. 保存后普通模式下卡片右上角显示小标记「已编辑」，提示用户此内容已被修改

### 3.2 数据存储

使用 `reading_item_edits` 覆盖层表，不修改原始 `ReadingItem.content`。

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

CREATE INDEX idx_rie_owner ON reading_item_edits (owner_user_id);
CREATE INDEX idx_rie_item ON reading_item_edits (reading_item_id);
```

**读取优先级**：`reading_item_edits.edited_content` > `reading_items.content`

### 3.3 API

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/api/compare/reading-items/{item_id}/edit` | 保存或更新编辑覆盖，body: `{ edited_content: string }` |
| DELETE | `/api/compare/reading-items/{item_id}/edit` | 删除编辑覆盖（回退到原始） |

## 4. 功能 2：点评

### 4.1 交互流程

1. 点击「点评」按钮 → cardMode 切换为 `annotating`
2. **进入点评模式后，才显示所有已有的用户点评**：
   - 已有高亮标注（`selected_text`）在文本中以彩色背景高亮
   - 高亮段旁显示笔记图标，hover/click 展开笔记内容
3. 用户选中文字 → 松开鼠标后弹出浮窗：
   - 显示选中的文字片段
   - 输入框填写点评笔记
   - 可选颜色标记
   - 确认保存 → POST 创建 annotation → 刷新卡片内高亮
4. 点击已有标注 → 可编辑或删除
5. 点击「退出点评」→ 回到普通模式，高亮和笔记全部隐藏

### 4.2 全局点评库

点评存入独立 `annotations` 表，是全局的——用户可在「我的点评」页面查看和搜索所有点评。

```sql
CREATE TABLE annotations (
    id              TEXT PRIMARY KEY,                           -- UUID
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    source_type     TEXT NOT NULL CHECK (source_type IN
                        ('compare_card', 'ai_summary', 'library_note')),
    source_id       TEXT NOT NULL,                              -- 关联的 reading_item_id 或其他实体 ID
    bib_entry_id    TEXT,                                       -- 冗余字段，加速按文献查询
    selected_text   TEXT,                                       -- 选中的原文片段
    note            TEXT NOT NULL,                              -- 点评笔记或 AI 总结文本
    char_start      INTEGER,                                    -- 选中文字在 content 中的起始位置
    char_end        INTEGER,                                    -- 选中文字在 content 中的结束位置
    is_ai_generated INTEGER NOT NULL DEFAULT 0,                 -- 0=人工点评, 1=AI 生成
    color           TEXT,                                       -- 高亮颜色标记
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_annotations_owner ON annotations (owner_user_id);
CREATE INDEX idx_annotations_source ON annotations (source_type, source_id);
CREATE INDEX idx_annotations_bib ON annotations (bib_entry_id);
CREATE INDEX idx_annotations_ai ON annotations (is_ai_generated);
```

**字段说明**：

- `source_type`：点评来源类型，`compare_card`=人工点评, `ai_summary`=AI总结, `library_note`=文献库笔记（预留）
- `source_id`：关联的业务实体 ID（点评模式下是 `reading_item.id` 的字符串形式）
- `bib_entry_id`：冗余字段，方便按文献维度聚合点评
- `char_start`/`char_end`：基于 Markdown 纯文本的字符偏移，尽力计算；编辑覆盖后可能失效（标注为 stale）
- `is_ai_generated`：区分人工点评和 AI 总结，点评模式下只显示 `is_ai_generated=0` 的记录

### 4.3 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/annotations` | 创建点评，body: `{ source_type, source_id, selected_text, note, char_start?, char_end?, color?, bib_entry_id? }` |
| GET | `/api/annotations?source_type=&source_id=&is_ai=` | 按条件查询点评 |
| PUT | `/api/annotations/{id}` | 更新点评内容/颜色 |
| DELETE | `/api/annotations/{id}` | 删除点评 |

## 5. 功能 3：AI 总结

### 5.1 交互流程

1. 点击「AI 总结」按钮 → cardMode 切换为 `ai_summarizing`
2. **进入 AI 总结模式后，才显示 AI 总结结果**
3. AI 总结模式有三种子显示模式，通过卡片顶部切换条切换：
   - **只显示总结结果**：隐藏原文，只显示 AI 生成的总结文本
   - **只显示原文**：显示原文（用于参考和继续选择新片段做总结）
   - **同时显示**：左右分栏或上下排列，原文和总结对照
4. 用户选中文字 → 松开鼠标后出现「AI 总结」按钮 → 点击：
   - 调用 `POST /api/compare/ai-summary`，传入选中文字和 api_key
   - 后端调用 `deepseek-v4-flash` 生成一句话总结
   - 同时存入 `annotations` 表（`is_ai_generated=1`）
   - 前端刷新显示
5. 点击「退出 AI 总结」→ 回到普通模式，AI 总结结果全部隐藏

### 5.2 提示词管理

在 `prompt_registry.py` 中新增：

- 类型：`compare`
- 槽位：`ai_summary`
- 标题：「AI 文本总结」
- 默认提示词文件：`prompts/compare/ai_summary.md`

默认提示词内容：

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

`PROMPT_TYPE_LABELS` 新增 `"compare": "对比分析"`。

### 5.3 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/compare/ai-summary` | AI 总结，body: `{ text: string, api_key: string, reading_item_id: string, bib_entry_id?: string, char_start?: int, char_end?: int }` → 返回 `{ summary: string, annotation_id: string }` |

后端处理流程：
1. 从 `prompt_service` 获取 `compare.ai_summary` 的生效提示词
2. 替换 `{selected_text}` 占位符
3. 调用 `deepseek-v4-flash`（复用现有 OpenAI client 封装）
4. 创建 `annotations` 记录（`is_ai_generated=1`）
5. 返回总结文本和 annotation_id

## 6. 后端 API 汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/api/compare/reading-items/{item_id}/edit` | 保存编辑覆盖 |
| DELETE | `/api/compare/reading-items/{item_id}/edit` | 删除编辑覆盖（回退到原始） |
| POST | `/api/annotations` | 创建点评/AI总结 |
| GET | `/api/annotations?source_type=&source_id=&is_ai=` | 按条件查询点评 |
| PUT | `/api/annotations/{id}` | 更新点评 |
| DELETE | `/api/annotations/{id}` | 删除点评 |
| POST | `/api/compare/ai-summary` | AI 总结选中文字 |

修改现有端点：
- `GET /api/compare/reading-data`：响应中每个 paper 的每个 dimension/subQuestion 增加 `edit` 字段（如有覆盖）和 `annotations` 数组

## 7. 前端变更

### 7.1 新增/修改文件

| 文件 | 变更 |
|------|------|
| `AnswerCard.tsx` | 核心变更：新增 `cardMode` 状态、三个按钮、编辑模式(textarea+三个操作按钮)、点评模式(高亮+浮窗)、AI总结模式(三种子视图切换) |
| `AccordionPanel.tsx` | 传递 `apiKey` 和 `onModeChange` 回调给 AnswerCard，管理同一时间只有一张卡片处于非普通模式 |
| `useCompareData.ts` | 响应数据结构扩展：每个维度项增加 `edit` 和 `annotations` 字段 |
| `compare.css` | 新增按钮/高亮/浮窗/子视图切换条样式（全部在 `.compare-root` 作用域下） |
| `App.tsx` PromptsTab | 提示词类型下拉新增 `compare` 选项 |

### 7.2 AnswerCard 内部状态

```typescript
type CardMode = 'normal' | 'editing' | 'annotating' | 'ai_summarizing'
type AiDisplayMode = 'summary_only' | 'original_only' | 'both'

interface AnswerCardState {
  cardMode: CardMode
  aiDisplayMode: AiDisplayMode
  editText: string                // textarea 内容
  isSaving: boolean
  // 点评模式
  showAnnotationPopup: boolean
  popupPosition: { x: number; y: number }
  selectedText: string
  selectedRange: { start: number; end: number } | null
  // AI 总结模式
  isAiLoading: boolean
}
```

### 7.3 AccordionPanel 模式互斥

AccordionPanel 管理一个 `activeCardMode` 状态：

```typescript
const [activeModeCard, setActiveModeCard] = useState<string | null>(null)
// activeModeCard = paper.id 表示哪张卡片处于非普通模式

const handleModeChange = (paperId: string, mode: CardMode) => {
  if (mode === 'normal') {
    setActiveModeCard(null)
  } else {
    setActiveModeCard(paperId)
  }
}
```

传递给每张 AnswerCard：

```typescript
<AnswerCard
  ...
  forcedMode={activeModeCard === p.id ? cardMode : 'normal'}
  onModeChange={(mode) => handleModeChange(p.id, mode)}
  isActive={activeModeCard === p.id}
/>
```

## 8. 数据库迁移

新增 Alembic 迁移脚本（顺序编号接当前最新）：

1. 创建 `reading_item_edits` 表
2. 创建 `annotations` 表及索引

级联删除规则：
- 删除 `reading_items` → 级联删除 `reading_item_edits`（ON DELETE CASCADE）
- 删除 `reading_items` → 应用层删除关联 `annotations`（按 `source_id` 清理）
- 删除 `users` → 级联删除 `reading_item_edits` + `annotations`（应用层或 FK）
- 24h 清理：普通用户过期时，`reading_item_edits` 跟随 `reading_items` 级联清理；`annotations` 按 `owner_user_id` 清理

## 9. 数据流变更

### 9.1 读取流程

```
CompareView
  → useCompareData(mode)
    → GET /api/compare/reading-data?mode=...
      → compare.py.get_reading_data():
          1. 查 ReadingItem（现有逻辑不变）
          2. 查 ReadingItemEdit（同一批 reading_item_id）
          3. 查 Annotation（同一批 reading_item_id，source_type IN ('compare_card','ai_summary')）
          4. 组装响应：每个维度项增加 edit 和 annotations
      → 返回 papers（含 edits 覆盖和 annotations）
  → AnswerCard 渲染：
    - displayContent = edit?.edited_content ?? readingItem.content
    - annotations = 过滤当前 reading_item 的标注
    - 根据 cardMode 决定显示什么
```

### 9.2 编辑流程

```
用户点「编辑」→ cardMode = 'editing'
→ textarea 加载 displayContent
→ 用户编辑
→ 点「保存」→ PUT /api/compare/reading-items/{id}/edit
  → 后端 upsert reading_item_edits
  → 前端刷新
→ 点「回退到原始」→ DELETE /api/compare/reading-items/{id}/edit
  → 后端删除 edit 记录
  → textarea 内容恢复为 ReadingItem.content（保持在编辑模式）
→ 点「取消」→ cardMode = 'normal'，不保存
```

### 9.3 点评流程

```
用户点「点评」→ cardMode = 'annotating'
→ 显示所有 is_ai_generated=0 的 annotations（高亮 + 笔记图标）
→ 用户选中文字 → mouseup 检测选区
→ 弹出浮窗（选中文字 + 输入框）
→ 输入笔记 → POST /api/annotations
  → 后端创建 annotation 记录
  → 前端追加高亮
→ 点击已有标注 → 可编辑(PUT)或删除(DELETE)
→ 点「退出点评」→ cardMode = 'normal'
```

### 9.4 AI 总结流程

```
用户点「AI 总结」→ cardMode = 'ai_summarizing'
→ 显示所有 is_ai_generated=1 的 annotations
→ 顶部切换条：只显示总结 / 只显示原文 / 同时显示
→ 用户选中文字 → mouseup 检测选区
→ 出现「总结」按钮 → 点击
→ POST /api/compare/ai-summary { text, api_key, reading_item_id, ... }
  → 后端调 deepseek-v4-flash + 存 annotations
  → 返回 { summary, annotation_id }
→ 前端追加到总结列表
→ 点「退出 AI 总结」→ cardMode = 'normal'
```

## 10. 注意事项

1. **CSS 隔离**：所有新增样式必须在 `.compare-root` 作用域下，禁止全局选择器
2. **Keyframes 前缀**：新增动画加 `compare-` 前缀避免冲突
3. **char_start/char_end 失效处理**：编辑覆盖后原有标注的偏移可能失效，前端渲染时需检测：如果 edit 存在，标注按 `selected_text` 做文本匹配而非偏移定位
4. **API Key**：AI 总结需要用户在前端设置 DeepSeek Key，与现有精读/综述一致
5. **提示词槽位新增**：`prompt_registry.py` 新增 `compare` 类型后，`prompt_service.py` 的 `ensure_builtin_prompt_templates` 需幂等导入新槽位的默认提示词
6. **router 完整性**：编辑 compare.py 时注意不要误删相邻路由，改完用 `python -c` 验证
