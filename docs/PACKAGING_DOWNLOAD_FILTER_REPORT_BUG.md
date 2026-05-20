# 待修复问题清单（2026-05-18）

## 1. 打包后下载筛选报告 file not found

### 现象

打包后的系统，下载筛选报告（filter_excel）时返回 `file not found`。

### 初步判断

大概率是路径问题。打包后静态资源/产物文件的路径解析与开发环境不同，导致无法定位到实际的 Artifact 文件。

### 状态

- [x] 复现并确认根因
- [x] 修复
- [x] 代码级验证与重新打包
- [ ] 用户打包版本地验证

### 已实施修复

- 新增 `backend/result_storage.py`，统一开发版与 PyInstaller 打包版的结果产物根目录解析。
- 下载、历史、文献库、筛选、精读、对比、参考文献梳理等 Artifact 写入/读取入口改用统一路径解析。
- 批量精读产物下载改为前端鉴权下载，避免直接链接丢失 token。
- 已重新运行 `python build_web_dist.py` 生成 `dist\DeepReadingAgent-Web.zip`。

---

## 2. 文献筛选提示词无法正确读取文本，所有论文输出结果一致（幻觉）

### 现象

用户输入文献筛选提示词后，系统似乎无法正确读取各篇论文的文本内容，导致所有论文的筛选输出结果完全一致——疑似 LLM 在没有读到实际文本时产生的幻觉。

### 初步判断

可能是筛选流程中将论文文本传递给 LLM 的环节出了问题：
- 文本提取失败或传入为空
- 多篇论文共享了同一个文本变量
- prompt 拼接时未正确插入论文内容

### 根因

用户侧提示词写错，非代码问题。

### 状态

- [x] 已确认根因
- [x] 已解决

---

## 3. 文献库批量删除功能

### 需求

文献库页面（LibraryTab）增加批量选择 + 批量删除功能。

### 已实施修复

- 后端：新增 `POST /api/library/entries/batch-delete`，接收 `entry_ids` 数组，处理 `BibReference.matched_bib_entry_id` FK 置空后批量删除。
- 前端：列表头部加全选复选框 + 批量删除按钮，每行加复选框支持多选。
- 涉及文件：`backend/routers/library.py`、`frontend/src/LibraryTab.tsx`。

### 状态

- [x] 后端：批量删除 API
- [x] 前端：批量选择 UI（复选框 + 全选 + 批量操作栏）
- [x] 前端构建验证
- [ ] 用户本地验证

---

## 4. 批量精读进度显示异常 + 日志不够精细

### 现象

1. 进度文字总是显示「正在处理 n+1/n 篇」（off-by-one）
2. 进度条一开始就在 50%，之后不再动
3. 日志只显示「批量任务已创建」，缺少后续过程信息

### 需求

- 修复进度计数 off-by-one 问题
- 修复进度条百分比计算逻辑
- 增加详细日志：每篇开始处理、每篇完成、整体进度等

### 状态

- [ ] 定位前端 `useBatchReadingTracker` 进度计算逻辑
- [ ] 定位后端批量任务状态更新逻辑
- [ ] 修复进度显示
- [ ] 补充日志
- [ ] 验证

---

## 5. 对比综述显示补充期刊名称

### 需求

精读结果对比时，当前只显示作者和年份，希望额外显示期刊名称（journal）。

### 已实施修复

- `AnswerCard.tsx`：`formatAuthors` 增加 `journal` 参数，卡片 meta 行显示 `作者 (年份) · 期刊名`。
- `PaperSelector.tsx`：文献选择卡 meta 行同样补充期刊名显示。
- 后端 `build_compare_response` 已返回 `journal` 字段，无需改动。

### 状态

- [x] 定位对比视图卡片渲染逻辑
- [x] 补充 AnswerCard 期刊名称字段
- [x] 补充 PaperSelector 期刊名称字段
- [x] 前端构建验证

---

## 6. 点评模式：只有输入单个数字才能高亮，多字符/中文不行

### 现象

点评模式下选中文本后：
1. **输入单个数字（如"1"）** → 高亮正常显示，可编辑
2. **输入多字符（如"11"、"a"）** → 无高亮
3. **输入中文** → 无高亮
4. 先输"1"保存得到高亮，再点击高亮编辑改为中文 → 高亮继续，中文正常显示

即：**只有创建时 note 为单个数字才有效，多字符/中文均失败**；但编辑已有 annotation 改为中文则正常。

### 分析

核心逻辑在 `AnswerCard.tsx`：

**创建路径**（`handleCreateAnnotation`，line 221）：POST `/api/compare/annotations` → 后端存储 → `onRefresh()` 重新加载 annotations → `renderAnnotatedContent` 渲染高亮。

**渲染高亮**（`renderAnnotatedContent`，line 294）：
```js
// 关键匹配逻辑
if (ann.selected_text && result.includes(ann.selected_text)) {
    const idx = result.indexOf(ann.selected_text, lastEnd)
    ...
}
```
用 `selected_text`（用户从渲染后的 HTML 中选中的文本）在 `result`（原始 Markdown 文本）中做字符串匹配。

**但 `selected_text` 来自 `window.getSelection()`（line 207），是从已渲染的 HTML DOM 上取的文本，而 `result` 是原始 Markdown。** 两者可能不一致（如 Markdown `**bold**` → 渲染后 `bold`，选中文本不含星号但原始文本含星号）。不过这不解释为什么 note 内容会影响高亮。

**更可能的原因是 `handleCreateAnnotation` 中 fetch 响应未检查**：

```js
// line 224-242
await fetch('/api/compare/annotations', { method: 'POST', ... })
// ❌ 没有 res.ok 检查，没有 await res.json()
setShowAnnotationPopup(false)
setAnnotationNote('')
onRefresh?.()
```

POST 可能返回 4xx/5xx（如数据库写入失败），但代码静默忽略，依然执行 `onRefresh()`。刷新后 annotation 不存在，自然无高亮。

**为什么单个数字能成功？** 需加 `console.log` 确认。可能假设：
- 后端某处对 `note` 字段有长度/内容限制，单字符恰巧通过
- 或 `selected_text` 的匹配仅在特定条件下命中（单数字作为 note 时，React 状态更新的时序恰好正确）
- 也不排除 React 状态竞争：输入多字符时触发了更多 re-render，`selectedText` 在 `handleCreateAnnotation` 闭包中被清空

**编辑路径正常的原因**：`handleUpdateAnnotation`（line 255）走 PUT，只更新 `note` 字段，annotation 已存在，不涉及创建和文本匹配。

### 验证步骤

1. 在 `handleCreateAnnotation` 入口加 `console.log({ annotationNote, selectedText })` 确认多字符输入时 state 值
2. 检查 POST `/api/compare/annotations` 的实际响应状态码
3. 检查后端 `create_annotation` 是否有隐式约束导致写入失败

### 状态

- [x] 加日志确认创建时 note / selectedText 的值
- [x] 检查 POST 响应状态码
- [x] 修复
- [x] 验证

---

## 7. AI总结「只看总结」模式下原文引用截断为80字符，需完整显示

### 现象

AI 总结模式中，每条总结下方显示的原文引用被截断为 80 字符（`AnswerCard.tsx:530`），用户希望完整显示。

### 已实施修复

`AnswerCard.tsx` 去掉 `.slice(0, 80)` 和省略号逻辑，直接显示 `a.selected_text` 完整内容。

### 状态

- [x] 修改并验证

---

## 8. 参考文献梳理中间结果框架太局促，不自适应

### 问题分析

参考文献梳理页中间「梳理结果」表格需要与右侧「正文引用详情」对齐。最终交互要求是：右侧详情区不单独滚动，只给中间表格区设置限高和滚动条；左侧源文献列表不再强制 `max-h-[72vh]`，避免内容不足时出现大片空白。

### 已实施修复

- `ReferenceTraceTab.tsx`：源文献列表去掉 `max-h-[72vh]`，仅保留 `overflow-y-auto`。
- `ReferenceTraceTab.tsx`：中间「梳理结果」卡片改为 `flex flex-col`，表格容器设置 `max-h-[62vh] overflow-auto`。
- `ReferenceTraceTab.tsx`：右侧「正文引用详情」保持不滚动，便于与中间表格顶部对齐。
- 内层 grid 断点从 `xl` 提升到 `2xl`，右侧从 320px 缩至 300px。

### 状态

- [x] 实施修复（中间表格限高滚动 + 右侧不滚动 + 调整 grid 断点）
- [x] 前端构建验证

---

## 9. 参考文献梳理结果支持手动编辑

### 需求

梳理结果表中，AI 未识别或识别不准的参考文献（title 为空、authors 残缺等），用户希望直接在表格内手动修改。

### 涉及改动的部分

#### 后端（`routers/references.py`）

新增 PUT 端点：

```python
@router.put("/references/{ref_id}")
async def update_reference(ref_id: str, body: dict, user, db):
    # 更新 BibReference 的可编辑字段：
    # title, authors_json, year, journal, volume, issue, pages, doi, raw_text
    ...
```

无需数据库迁移，`BibReference` 模型（`models.py:356`）已有全部字段。

#### 前端（`ReferenceTraceTab.tsx`）

1. **表格行内编辑**：点击「标题 / 原文」列的文本时，切换为 inline input/textarea（类似编辑模式的 toggle）
2. **编辑态**：显示 `<input>` （title）+ `<textarea>` （raw_text）+ 其他字段（year、journal 等）的简易编辑区
3. **保存**：失焦或点保存按钮时调用 PUT `/api/references/references/{ref_id}`
4. **UI 参考**：可复用对比综述中 `AnswerCard` 的编辑模式交互（点击进入编辑态，保存/取消）

具体改动点：

- `TraceReference` 类型中编辑相关字段加 `editing?: boolean` 状态
- 表格行（line 401-428）增加编辑态渲染分支
- 新增 `handleUpdateReference` 调用 PUT API
- 操作列（line 419-427）增加「编辑」按钮

### 状态

- [x] 后端：新增 PUT `/references/{ref_id}` 端点
- [x] 前端：表格行内编辑 UI
- [x] 前端：调用 PUT API 保存
- [x] 验证

---

## 10. 参考文献正文引用详情只显示短引用标记，缺少完整句子和前后文

### 现象

在「参考文献梳理」页面点击某条参考文献后，右侧「正文引用详情」中经常只显示类似「张三（等）」或「Smith (2020)」的短引用标记，用户预期看到引用该参考文献的完整句子，并带有前后文。

### 根因

后端 `deepseek_refs.py` 让 DeepSeek 返回 `quote`，但 prompt 没有强约束必须返回完整句子；模型容易只返回作者-年份引用标记。随后代码用 `body_text.find(quote)` 精确定位，再用 `_expand_excerpt()` 截取前后文：

- 当 `quote` 只是短标记时，前端主体展示也会偏向短标记；
- 当模型返回的标记与 OCR 正文格式不一致时（如 `罗映宇等（2023）` vs `罗映宇等，2023`），精确匹配失败，`excerpt` 为空；
- 模型偶尔会把文末注释/参考文献条目误当成正文引用。

### 已实施修复

- 后端：将 `quote` 视为定位锚点，新增归一化匹配和作者-年份模糊匹配；
- 后端：根据命中位置抽取包含引用的完整句子，并附带前一句/后一句作为 `excerpt`；
- 后端：过滤明显的参考文献条目式误命中；
- 前端：`ReferenceTraceTab.tsx` 优先展示 `excerpt`，将 `quote_text` 降级为「命中标记」。

### 验证

使用 `从决策式到生成式：人工智能管理研究的理论框架与未来议题_陆金凤.pdf_by_PaddleOCR.md` 进行两条参考文献小样本测试：

- `罗映宇等（2023）` 可定位到正文 `罗映宇等，2023`，并返回完整句子与前后文；
- `黄、拉斯特，2024` 可返回包含该引用的完整句子与前后文。

### 状态

- [x] 分析根因
- [x] 修复
- [x] 小样本验证
- [ ] 用户打包版本地验证

---

## 11. 模板市场 AI 生成专属模板重新生成命中旧缓存，20 维度生成报错

### 现象

在模板市场上传种子论文后，AI 生成专属模板如果点击“重新生成”，即使维度数从 8/12/16 改为 20，也可能直接返回过去已经生成的结果。选择 20 维度时还经常报 `JSON解析失败`。

### 根因

1. 后端 `/api/dimensions/generate` 的 `_generation_cache` 只用论文前 1000 字做 md5，缓存 key 未包含用户、维度数或其他生成参数，导致同一论文不同维度数会复用旧结果。
2. 前端“重新生成”只是回到配置页，没有告诉后端跳过缓存。
3. `backend/services/ai_template_generator.py` 固定 `max_tokens=4000`。20 维度时 DeepSeek 返回的 JSON 体积明显变大，模型输出在中途因 token 上限被截断，后端解析 JSON 失败。

### 已实施修复

- `backend/routers/dimensions.py`
  - 新增 `force_regenerate: bool = Form(False)`。
  - 缓存 key 改为包含 `user.id`、`dim_count` 和论文文本片段，并从 md5 改为 sha256。
  - `force_regenerate=true` 时跳过旧缓存，并在成功生成后覆盖缓存。
- `frontend/src/TemplateMarket.tsx`
  - “重新生成”会清空旧预览结果，并将下一次请求标记为强制重新生成。
  - 请求表单追加 `force_regenerate`。
- `backend/services/ai_template_generator.py`
  - 根据维度数动态设置输出 token 预算，20 维度最高使用 12000。
  - 如果返回因 `finish_reason=length` 被截断，会用更大预算重试一次。
  - JSON 解析失败时增加 `json_repair` 兜底。

### 验证

- `python -m py_compile backend\services\ai_template_generator.py backend\routers\dimensions.py`
- `cd frontend && npm run build`
- 使用用户提供的 Markdown 论文与 DeepSeek key 直跑 20 维度：返回完整 JSON，`dimensions=20`，不再出现 `JSON解析失败`。
- 已重新运行 `python build_web_dist.py` 生成新的 `dist\DeepReadingAgent-Web.zip`。

### 状态

- [x] 分析根因
- [x] 修复
- [x] 20 维度直跑验证
- [x] 重新打包
- [ ] 用户打包版本地验证

---

## 12. 模板市场维度提示词编辑 + 与长文本精读同步

### 需求

模板市场里，用户自有维度集合的每个维度（dim_name / description / prompt_content / default_question）可以编辑。编辑结果与长文本精读 Tab 中的编辑**实时同步**，因为两边操作的是同一条 `dimension_items` 记录。

### 现状分析

#### 数据模型

系统有两组并行的表：

| 层级 | 系统预设 | 用户自有 |
|------|---------|---------|
| 集合 | `dimension_templates`（无 owner） | `dimension_sets`（有 `owner_user_id`） |
| 维度项 | `template_items`（FK → template） | `dimension_items`（FK → set） |

用户通过「导入预设模板」/「AI 生成」/「文档导入」/「共享导入」等方式在模板市场创建 `dimension_sets` + `dimension_items`，这些记录同时出现在模板市场的「我的模板」和长文本精读的下拉列表中（由 `is_available_for_reading` 控制）。

#### 关键事实：两边操作同一记录

**导入精读不是复制，而是标记。** `is_available_for_reading=1` 只决定集合是否出现在精读 Tab 的下拉菜单中，集合本身始终在模板市场可见。

| 操作 | 影响的记录 | 两边同步？ |
|------|-----------|-----------|
| 模板市场「导入精读」 | 更新 `dimension_sets.is_available_for_reading` | 是，同一条记录 |
| 长文本精读编辑维度 | 更新 `dimension_items` 行 | 是，同一条记录 |
| 长文本精读「另存为新集合」 | 深拷贝为新 `dimension_set` + `dimension_items` | 否，新记录 |
| 模板市场编辑维度 | **目前不支持** | — |

#### 当前模板市场详情页（只读）

`TemplateMarket.tsx:476-513` 的维度列表是纯只读渲染，没有编辑按钮/编辑态：

```tsx
// 只展示 dim_name + description，没有 prompt_content、没有编辑入口
<div className="text-sm font-medium text-gray-800">{dim.dim_name}</div>
{dim.description && <div className="text-xs text-gray-500">{dim.description}</div>}
```

#### 当前长文本精读 Tab（完整编辑）

`App.tsx:1225-1410` 有完整的维度编辑能力：
- 内联编辑 dim_name / description / prompt_content / default_question
- 添加/删除/拖拽排序维度
- 「另存为新集合」（clone）
- 创建空集合

### 三种同步场景分析

#### 场景 1：模板已导入精读 → 两边编辑同步

```
模板市场 [我的集合 A] ←── 同一条 dimension_items ──→ 精读 Tab [集合 A]
         (新增编辑能力)                                  (已有编辑能力)
```

- 两边都调用 `PUT /api/dimensions/sets/{set_id}/items/{item_id}`
- 因为是同一条记录，编辑自动同步
- **无需额外同步机制**

#### 场景 2：模板未导入精读 → 只在模板市场编辑

```
模板市场 [我的集合 B] ─── is_available_for_reading=0
         (新增编辑能力)
```

- 集合 B 不出现在精读 Tab 下拉中，自然无法在精读 Tab 编辑
- 只能通过模板市场编辑
- **无需额外机制**

#### 场景 3：精读 Tab 另存为新集合 → 模板市场自动出现新集合

```
精读 Tab [集合 A] ── 另存为新集合 ──→ [集合 A 副本]
                                         │
                                    新 dimension_set 记录
                                    owner = 当前用户
                                    is_available_for_reading = 1（默认）
                                    is_system = 0
                                    is_shared = 0
```

- 现有 `POST /api/dimensions/sets` 已支持 `clone_from_set_id` 参数
- 克隆后的新集合属于当前用户，自动出现在模板市场「我的模板」列表
- **无需额外机制**，当前代码已自然支持
- 但需确认：clone 时 `is_available_for_reading` 是否默认为 1（应在模板市场和精读 Tab 都可见）

### 改动方案

#### 后端（无需改动）

现有 API 已完全覆盖需求：
- `PUT /api/dimensions/sets/{set_id}/items/{item_id}` — 编辑维度（name / description / prompt_content / default_question）
- `GET /api/dimensions/sets/{set_id}/items` — 获取维度列表
- `POST /api/dimensions/sets` (`clone_from_set_id`) — 另存为新集合

无需新增端点。

#### 前端 TemplateMarket.tsx（主要改动）

**改动范围**：用户自有集合的详情页（`panel === 'user-detail'`，line 394-518）

1. **维度列表改为可编辑卡片**

   每个维度卡片增加：
   - 编辑按钮（铅笔图标）
   - 点击进入编辑态：展示 `dim_name`（input）、`description`（input）、`prompt_content`（textarea）、`default_question`（input）
   - 保存/取消按钮
   - 调用 `PUT /api/dimensions/sets/{set_id}/items/{item_id}`
   - 保存后刷新维度列表

2. **维度级别操作按钮**

   - 「添加维度」按钮 → 调用 `POST /api/dimensions/sets/{set_id}/items`
   - 每个维度卡片增加「删除」按钮 → 调用 `DELETE /api/dimensions/sets/{set_id}/items/{item_id}`
   - 可选：拖拽排序（复用精读 Tab 的排序逻辑）

3. **编辑态 UI 设计**

   ```
   ┌─────────────────────────────────────────┐
   │ ● 研究问题                         [✏️][🗑️] │
   │   本研究探讨的核心问题是什么？              │
   │                                         │
   │   [编辑态展开]                           │
   │   名称: [研究问题_____________]           │
   │   描述: [本研究探讨..._________]          │
   │   提示词:                               │
   │   ┌──────────────────────────┐          │
   │   │ 请分析本文的研究问题...    │          │
   │   └──────────────────────────┘          │
   │   默认提问: [本文的研究问题是什么?__]     │
   │                          [保存] [取消]   │
   └─────────────────────────────────────────┘
   ```

4. **预设模板详情（只读）**

   `panel === 'detail'`（系统预设模板）保持只读不变，只有「一键导入」按钮。用户需先导入为自有集合才能编辑。

5. **需要新增的 state**

   ```ts
   const [editingItemId, setEditingItemId] = useState<number | null>(null)
   const [editForm, setEditForm] = useState({ dim_name: '', description: '', prompt_content: '', default_question: '' })
   const [saving, setSaving] = useState(false)
   ```

6. **与精读 Tab 的交互一致性**

   - 模板市场编辑保存后，如果用户同时在精读 Tab 使用该集合，精读 Tab 下次加载维度列表时会自动拿到最新数据（因为刷新时重新请求 `GET /sets/{id}/items`）
   - 不需要 WebSocket / 实时推送，用户切换 Tab 时自然会刷新

#### 确认项

- [ ] 确认 `clone_from_set_id` 创建的新集合 `is_available_for_reading` 默认值是否为 1
- [ ] 确认系统预设模板详情页是否需要展示 `prompt_content`（只读预览，帮助用户决定是否导入）

### 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/src/TemplateMarket.tsx` | 维度列表增加编辑态 UI + 调用现有 PUT/POST/DELETE API |
| `backend/routers/dimension_sets.py` | 可能无需改动（确认 clone 默认值） |
| `backend/db/models.py` | 无需改动 |

### 状态

- [x] 分析现状与数据流
- [x] 确认同步机制（同记录 = 自动同步）
- [x] 制定前端改动方案
- [ ] 实施前端编辑 UI
- [ ] 验证场景 1/2/3
- [ ] 重新打包

---

## 13. AI 综述 & AI 模板生成提示词提取至提示词管理

### 需求

将 AI 文献综述（synthesis）和 AI 生成专属模板（ai_template_generator）中硬编码的提示词提取到 `prompt_registry` + 文件系统，纳入提示词管理页面的用户覆盖机制，并提供「恢复默认」功能。

### 现状审计

#### 已注册的提示词（27 个槽位）

| type | 槽位数 | 说明 |
|------|--------|------|
| `quant` | 7 | 七步精读（定量） |
| `qual` | 4 | 四步精读（定性） |
| `long` | 12 | 长文本精读 |
| `filter` | 3 | 文献筛选（探索者/评审者/实证主义者） |
| `compare` | 1 | AI 文本总结（`ai_summary`） |

以上全部可在提示词管理页面编辑/覆盖/恢复默认。

#### 未注册的硬编码提示词（12 个）

##### A. AI 文献综述 — `backend/routers/compare.py`（10 个）

| # | 变量/函数 | 行号 | 用途 | 可提取性 |
|---|----------|------|------|---------|
| 1 | `SYNTHESIS_SYSTEM_PROMPT` | 51-61 | 综述系统角色人设（3 个 synthesis 函数共用） | 高：纯文本，无动态变量 |
| 2 | `SYSTEM_PROMPT` | 1060-1067 | 对比综述系统角色人设（analyze 用） | 高：纯文本 |
| 3 | `build_synthesis_dimension_prompt()` | 817-854 | AI 综述逐维度写作指令模板 | 中：模板骨架固定，只有 `dim_label` 是动态的 |
| 4 | `build_paper_metadata_block()` | 747-796 | 文献元信息格式化（引用标注前缀） | 低：纯格式化逻辑，无提示词性质 |
| 5 | `build_single_prompt()` | 1070-1099 | 对比综述-单子问题维度写作 | 中：`label` / `n` 是动态 |
| 6 | `build_multi_prompt()` | 1102-1135 | 对比综述-多子问题维度写作 | 中：`label` / `sub_questions` / `n` 是动态 |
| 7 | `build_cross_dim_prompt()` | 1168-1225 | 对比综述-跨维度写作 | 中：动态参数多 |
| 8 | `build_long_single_prompt()` | 1138-1165 | 长文本对比-单维度写作 | 中 |
| 9 | `build_long_multi_prompt()` | 1228-1253 | 长文本对比-多维度写作 | 中 |
| 10 | `_build_secondary_ref_check_prompt()` | 697-718 | 二次引用筛选 | 低：纯指令性，非核心创作提示词 |

##### B. AI 模板生成 — `backend/services/ai_template_generator.py`（2 个）

| # | 变量/函数 | 行号 | 用途 | 可提取性 |
|---|----------|------|------|---------|
| 11 | `META_PROMPT_TEMPLATE` | 15-71 | 元提示词：从论文生成维度体系 | 高：`{paper_text}` 和 `{dim_count}` 两个占位符 |
| 12 | system message | 104-107 | 模板生成系统角色人设 | 高：纯文本 |

### 提取策略

#### 哪些该提取，哪些不该

| 类别 | 决定 | 理由 |
|------|------|------|
| 系统角色人设（#1, #2, #12） | **提取** | 用户可能想调整风格/语气/语言 |
| 写作指令模板（#3, #5-#9） | **提取** | 用户可能想调整综述结构要求、段落格式 |
| 二次引用筛选（#10） | **不提取** | 纯功能性指令，用户无修改动机 |
| 元信息格式化（#4） | **不提取** | 纯格式化逻辑，非提示词 |
| 元提示词（#11） | **提取** | 用户可能想调整维度生成策略 |

#### 新增槽位设计

在 `prompt_registry.py` 中注册两个新 type：`synthesis` 和 `ai_template`。

##### type: `synthesis`（AI 文献综述）

| key | title | 文件路径 | 对应原代码 |
|-----|-------|---------|-----------|
| `system_role` | AI 综述：系统角色 | `prompts/synthesis/system_role.md` | `SYNTHESIS_SYSTEM_PROMPT` (compare.py:51) |
| `compare_system_role` | 对比综述：系统角色 | `prompts/synthesis/compare_system_role.md` | `SYSTEM_PROMPT` (compare.py:1060) |
| `dimension_prompt` | AI 综述：逐维度写作指令 | `prompts/synthesis/dimension_prompt.md` | `build_synthesis_dimension_prompt` (compare.py:817) |
| `single_prompt` | 对比综述：单维度写作 | `prompts/synthesis/single_prompt.md` | `build_single_prompt` (compare.py:1070) |
| `multi_prompt` | 对比综述：多子问题写作 | `prompts/synthesis/multi_prompt.md` | `build_multi_prompt` (compare.py:1102) |
| `cross_dim_prompt` | 对比综述：跨维度写作 | `prompts/synthesis/cross_dim_prompt.md` | `build_cross_dim_prompt` (compare.py:1168) |
| `long_single_prompt` | 长文本对比：单维度写作 | `prompts/synthesis/long_single_prompt.md` | `build_long_single_prompt` (compare.py:1138) |
| `long_multi_prompt` | 长文本对比：多维度写作 | `prompts/synthesis/long_multi_prompt.md` | `build_long_multi_prompt` (compare.py:1228) |

##### type: `ai_template`（AI 模板生成）

| key | title | 文件路径 | 对应原代码 |
|-----|-------|---------|-----------|
| `meta_prompt` | 模板生成：元提示词 | `prompts/ai_template/meta_prompt.md` | `META_PROMPT_TEMPLATE` (ai_template_generator.py:15) |
| `system_role` | 模板生成：系统角色 | `prompts/ai_template/system_role.md` | system message (ai_template_generator.py:104) |

#### 模板占位符处理

写作指令模板（#3, #5-#9）包含动态参数（维度名、文献数、子问题列表等）。提取为文件后，用 `{placeholder}` 标记，运行时用 `.format()` 或 `str.replace()` 注入。

| 占位符 | 含义 | 使用位置 |
|--------|------|---------|
| `{dim_label}` | 当前维度名 | dimension_prompt |
| `{n}` | 文献数量 | single/multi/cross_dim/long_* |
| `{label}` | 维度名 | single_prompt |
| `{sub_questions_list}` | 子问题列表文本 | multi_prompt |
| `{sub_count}` | 子问题数量 | multi_prompt |
| `{step_list}` | 维度列表文本 | cross_dim_prompt |
| `{step_count}` | 维度数量 | cross_dim_prompt |
| `{dimensions}` | 维度列表文本 | long_multi_prompt |

元提示词占位符：

| 占位符 | 含义 | 使用位置 |
|--------|------|---------|
| `{paper_text}` | 论文文本 | meta_prompt |
| `{dim_count}` | 目标维度数 | meta_prompt |

#### 用户覆盖时的注意事项

用户编辑含占位符的模板时：
- 前端提示词编辑器需要**显示占位符说明**（如"请保留 `{dim_label}` 占位符"）
- 后端不做占位符完整性校验（用户可能故意删除某些指令段），但 `system_content`（默认值）始终包含完整模板
- 「恢复默认」直接删除 user override，回退到文件/内置默认

### 改动方案

#### Step 1：创建提示词文件

```
prompts/
├── synthesis/                         ← 新目录
│   ├── system_role.md                 ← SYNTHESIS_SYSTEM_PROMPT 原文
│   ├── compare_system_role.md         ← SYSTEM_PROMPT 原文
│   ├── dimension_prompt.md            ← build_synthesis_dimension_prompt 骨架
│   ├── single_prompt.md               ← build_single_prompt 骨架
│   ├── multi_prompt.md                ← build_multi_prompt 骨架
│   ├── cross_dim_prompt.md            ← build_cross_dim_prompt 骨架
│   ├── long_single_prompt.md          ← build_long_single_prompt 骨架
│   └── long_multi_prompt.md           ← build_long_multi_prompt 骨架
├── ai_template/                       ← 新目录
│   ├── meta_prompt.md                 ← META_PROMPT_TEMPLATE 原文
│   └── system_role.md                 ← system message 原文
```

#### Step 2：注册到 prompt_registry.py

```python
# prompt_registry.py 新增
SYNTHESIS_SLOTS = [
    SlotDef("synthesis", "system_role",          "AI 综述：系统角色"),
    SlotDef("synthesis", "compare_system_role",  "对比综述：系统角色"),
    SlotDef("synthesis", "dimension_prompt",     "AI 综述：逐维度写作指令"),
    SlotDef("synthesis", "single_prompt",        "对比综述：单维度写作"),
    SlotDef("synthesis", "multi_prompt",         "对比综述：多子问题写作"),
    SlotDef("synthesis", "cross_dim_prompt",     "对比综述：跨维度写作"),
    SlotDef("synthesis", "long_single_prompt",   "长文本对比：单维度写作"),
    SlotDef("synthesis", "long_multi_prompt",    "长文本对比：多维度写作"),
]

AI_TEMPLATE_SLOTS = [
    SlotDef("ai_template", "meta_prompt",  "模板生成：元提示词"),
    SlotDef("ai_template", "system_role",  "模板生成：系统角色"),
]
```

#### Step 3：后端改造 — compare.py

每个 build_* 函数改造为：

```python
# 改造前（硬编码）
def build_synthesis_dimension_prompt(dim_label, papers, content_field="subQuestions"):
    parts = ["【当前综述维度】{dim_label}", ...]  # 硬编码
    ...

# 改造后（从 prompt_service 加载）
async def build_synthesis_dimension_prompt(dim_label, papers, content_field="subQuestions", user_id=None, db=None):
    template = await get_prompt_payload(db, "synthesis", "dimension_prompt", user_id=user_id)
    scaffold = template["effective_content"]  # 用户覆盖 > 系统默认 > 文件兜底
    parts = [scaffold.format(dim_label=dim_label)]
    # ... 后续动态拼接文献内容不变
```

同理，`SYNTHESIS_SYSTEM_PROMPT` / `SYSTEM_PROMPT` 变量改为函数内从 prompt_service 动态获取。

#### Step 4：后端改造 — ai_template_generator.py

```python
# 改造后
async def generate_template_from_paper(paper_text, dim_count, user_id=None, db=None):
    meta_template = await get_prompt_payload(db, "ai_template", "meta_prompt", user_id=user_id)
    system_role = await get_prompt_payload(db, "ai_template", "system_role", user_id=user_id)

    prompt_text = meta_template["effective_content"].format(
        paper_text=paper_text[:CHAR_LIMIT],
        dim_count=dim_count,
    )
    messages = [
        {"role": "system", "content": system_role["effective_content"]},
        {"role": "user", "content": prompt_text},
    ]
    ...
```

注意：`ai_template_generator.py` 中的函数当前是同步的，需要改为 async（或把 prompt_service 调用提到上层 router 中提前解析好再传入）。

#### Step 5：前端 PromptsTab — 新增两个 type

`App.tsx` PromptsEditor 的 `TYPES` 数组新增：

```ts
{ key: 'synthesis', label: 'AI 综述', icon: '📝' },
{ key: 'ai_template', label: 'AI 模板生成', icon: '🤖' },
```

对于含占位符的提示词，编辑器上方显示提示文字：

```
💡 此提示词包含动态占位符（如 {dim_label}、{n}），请保留所需占位符以确保正常运行。
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/prompt_registry.py` | 新增 `synthesis`（8 槽位）+ `ai_template`（2 槽位） |
| `backend/routers/compare.py` | 10 处硬编码提示词改为从 prompt_service 加载 |
| `backend/services/ai_template_generator.py` | 2 处硬编码提示词改为从 prompt_service 加载 |
| `frontend/src/App.tsx` | PromptsEditor TYPES 新增 2 个 type |
| `prompts/synthesis/*.md` | 新建 8 个提示词文件 |
| `prompts/ai_template/*.md` | 新建 2 个提示词文件 |
| `DeepReadingAgent.spec` | datas 新增 `prompts/synthesis` 和 `prompts/ai_template` |

### 不改动的部分

- `build_paper_metadata_block()` — 纯格式化逻辑，非提示词
- `_build_secondary_ref_check_prompt()` — 纯功能性指令，用户无修改动机
- `compare.ai_summary` — 已在 registry 中，不动
- 数据库模型 — 无需新增表或字段

### 状态

- [x] 审计所有硬编码提示词（12 个）
- [x] 确定提取范围（10 个提取，2 个不提取）
- [x] 设计槽位方案（synthesis 8 + ai_template 2）
- [x] 制定占位符策略
- [x] 制定前后端改动方案
- [ ] 创建提示词文件（10 个 .md）
- [ ] 注册到 prompt_registry.py
- [ ] 改造 compare.py（10 处）
- [ ] 改造 ai_template_generator.py（2 处）
- [ ] 前端 PromptsTab 新增 type
- [ ] 更新 DeepReadingAgent.spec
- [ ] 验证用户覆盖/恢复默认
- [ ] 重新打包

---

## 14. 删除分析维度报 500 Internal Server Error

### 现象

在前端删除维度集合中的某个具体维度时，报错 `❌ Unexpected token 'I', "Internal S"... is not valid JSON`。即使「另存为新集合」后仍无法删除。

### 根因

两处缺陷叠加：

1. **后端 `dimensions.py:680-681` — `scalar()` 重复调用**：`used.scalar()` 被调用了两次（一次在 `if` 判断，一次在 `detail` 字符串）。SQLAlchemy 的 `Result.scalar()` 只能调用一次，第二次返回 `None`，导致 500 Internal Server Error。

   ```python
   # 修复前
   if (used.scalar() or 0) > 0:
       raise HTTPException(status_code=409, detail=f"...{used.scalar()}...")
   ```

2. **前端 `App.tsx:1340` — JSON 解析无兜底**：500 响应体是纯文本 `"Internal Server Error"`，前端直接 `await res.json()` 解析失败，抛出 `SyntaxError`，错误信息是 JSON 解析异常而非后端原始错误。

### 已实施修复

- 后端：`used.scalar()` 改为单次调用存入变量 `used_count`
- 前端：非 200 响应的 JSON 解析加 try-catch 兜底

### 状态

- [x] 定位根因
- [x] 修复
- [x] 代码编译验证
- [ ] 用户本地验证

---

## 15. 对比综述页面增加文献筛选

### 需求

在长文本对比、七步对比、四步对比页面的 PaperSelector 上方，增加筛选控件，支持按维度集合、期刊、主题关键词、文献名筛选。三个模式复用同一套筛选组件。

### 现状

- `PaperSelector.tsx`（41 行）：纯水平滚动卡片列表，点击 toggle 选择，无任何筛选
- `useCompareData.ts`：`GET /api/compare/reading-data?mode=xxx` 返回所有论文，后端无筛选参数
- API 已返回但前端未使用的字段：`journal`（BibEntry.journal）、`dim_set_name`（长文本维度集合名称）
- 七步/四步模式无维度集合概念（步骤固定），筛选只对期刊/文献名有效

### 可筛选维度

| 筛选维度 | 数据来源 | long | quant | qual |
|---------|---------|------|-------|------|
| 维度集合 | `paper.dimensions[].dim_set_name` | ✅ | — | — |
| 期刊 | `paper.journal` | ✅ | ✅ | ✅ |
| 关键词 | `paper.title` 模糊搜索 | ✅ | ✅ | ✅ |
| 文献名 | `paper.title` 模糊搜索 | ✅ | ✅ | ✅ |

### 方案：纯前端筛选

后端 API 已返回全部所需字段，筛选在前端完成。无需修改后端。

#### 筛选 UI 设计

在 `PaperSelector` 上方增加一个筛选条（filter bar），包含：

```
[维度集合: 全部 ▾] [期刊: 全部 ▾] [🔍 搜索文献名/关键词...] [重置]
```

- **维度集合下拉**：从 `papers` 中提取所有 `dim_set_name` 去重，加"全部"选项。仅 `mode=long` 时显示。
- **期刊下拉**：从 `papers` 中提取所有 `journal` 去重，加"全部"选项。空期刊合并为"未填写"。
- **搜索框**：对 `title` 做模糊匹配。
- **重置按钮**：清空所有筛选条件。

#### 改动文件

| 文件 | 改动 |
|------|------|
| `PaperSelector.tsx` | 接收 `mode` + 筛选 state，在卡片列表上方渲染筛选条，过滤 `papers` |
| `CompareView.tsx` | 新增筛选 state（`filterDimSet`、`filterJournal`、`filterSearch`），传递给 PaperSelector，筛选后传给后续逻辑 |

### 状态

- [x] 分析现状
- [x] 制定纯前端筛选方案
- [x] 实施 PaperSelector 筛选条 UI
- [x] 实施 CompareView 筛选 state 传递
- [x] 修复搜索框闪退 bug（空状态守卫误用过滤后 `papers`）
- [x] 验证三种模式筛选效果
- [x] 前端构建验证

---

## 记录时间

2026-05-18，更新于 2026-05-19，再次更新于 2026-05-19（修复 #3/#5/#7/#8）
