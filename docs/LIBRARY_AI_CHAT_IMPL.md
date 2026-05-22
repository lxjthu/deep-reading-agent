# 文献库 AI 查询实现记录

> 状态：已于 2026-05-22 完成本地验证。  
> 范围：在“我的文献库”中用 DeepSeek 对文献档案做多轮检索问答，把命中文献联动回列表，并对确认后的标签与点评做受控写库。

## 1. 功能边界

- 用户在文献库页输入自然语言问题，后端先解析检索意图，再基于当前用户的 `BibEntry` 做数据库召回。
- 支持 `自动 / 全库 / 当前结果` 三种范围模式；自动模式由查询解析提示词判断是否延续上一轮结果。
- 报告生成基于本轮命中的完整元数据与摘要集合，不在前端硬编码提示词。
- 对话把最近几轮问题、报告信息和命中集合传回后端，支持连续收窄或重新扩大范围。
- 会话轮次暂不持久化；刷新页面后聊天报告会丢失，只有用户确认的标签操作与保存的 AI 点评进入数据库。
- 文献助手可识别“给这些文献加标签/移除标签”请求，先展示影响范围，再由用户确认后调用确定性批量标签接口。
- 每轮报告可单独点击“保存本轮 AI 点评”；保存时后端重新生成逐篇结构化点评，只写入对该轮筛选有条目价值的点评，排除“并不回答本轮问题”的否定说明。

## 2. 前后端实现

### 2.1 后端

- 新增 `backend/routers/library_chat.py`，挂载 `POST /api/library/chat`。
- 路由使用 SSE 依次返回 `intent`、`results`、`citations`、`report`、`done` 或 `error`。
- 检索只访问当前登录用户拥有的 `BibEntry`、`BibReference` 和 `ReadingItem`。
- 文献列表新增 `POST /api/library/entries/by-ids`，用 JSON body 承载 AI 命中 ID 集合，避免把大量 UUID 塞进 GET URL。
- 标签能力新增 `GET /api/library/tags` 与 `POST /api/library/entries/batch-tags`；标签筛选参数复用 `/api/library/entries` 与 `/api/library/entries/by-ids`。
- 标签动作在“当前结果”范围内会先保留上一轮候选全集，再用 `tag_target_selector` 做结构化目标选择；避免字面关键词召回只命中标题最像的一篇，而把报告语义上已筛出的相关文献漏掉。
- 点评能力新增 `POST /api/library/chat/comments`：以当前 turn 的问题、报告和命中文献为输入，按批生成逐篇 JSON 点评。
- AI 点评复用 `annotations`：`source_type='library_note'`、`is_ai_generated=1`、`source_id=<turn_id>`；同一轮重复保存会替换该轮旧点评。
- 文献库专用点评编辑接口为 `PATCH /api/library/ai-comments/{comment_id}` 与 `DELETE /api/library/ai-comments/{comment_id}`，只允许操作当前用户的 AI 文献库点评。

### 2.2 前端

- `frontend/src/LibraryTab.tsx` 新增 AI 文献助手面板、多轮 turn 状态、范围切换和 SSE 解析。
- AI 命中 ID 会同步筛选左侧文献列表；恢复全量列表后可回到普通文献库浏览。
- 后端给报告投喂的命中文献按 `[1]`、`[2]` 编号，前端按同一顺序在文献列表和详情区显示编号。
- 报告里的有效 `[n]` 编号会渲染成定位按钮；点击后恢复该轮命中列表、选中目标文献并滚动到列表行。
- 标签筛选框为搜索下拉框，预置当前用户全部标签；输入会自动匹配候选，选中的多个标签按同时命中筛选。
- 文献详情新增 AI 点评区，显示已保存点评、本轮问题与时间，支持逐条编辑和删除。

## 3. 提示词管理

新增 `library_chat` 提示词类型：

| key | 文件 | 用途 |
|---|---|---|
| `query_parser` | `prompts/library_chat/query_parser.md` | 把自然语言问题解析为检索意图 JSON |
| `report_writer` | `prompts/library_chat/report_writer.md` | 基于命中文献与上下文输出中文 Markdown 报告 |
| `tag_target_selector` | `prompts/library_chat/tag_target_selector.md` | 在候选结果中为标签确认卡选择真实目标文献 ID |
| `paper_comment_writer` | `prompts/library_chat/paper_comment_writer.md` | 保存点评时输出值得写入条目的逐篇 JSON 点评 |

报告提示词要求回答中提到具体文献时沿用输入编号，便于前端和文献列表对照。  
默认提示词仍遵循 `用户覆盖 > 系统默认 > 文件兜底 > 代码兜底`。未被管理员改写的系统默认提示词会在种子同步时跟随托管提示词文件更新。

## 4. 数据库与迁移

- migration：`016_add_library_chat_prompt_type.py`
- 变更：`prompt_templates.prompt_type` 约束加入 `library_chat`
- 数据可移植版本：`backend/services/data_portability.py` 的 `CURRENT_SCHEMA_VERSION` 升到 `016`
- 标签筛选和批量标签复用 `bib_entries.user_tags_json`；AI 点评复用 migration `011` 已有的 `annotations`
- 本轮扩展没有新增用户数据表，`.dra` 导入导出顺序无需增加表项
- 合并到 `online` 后仍需在线上数据库执行 `alembic upgrade head`，以确保 `014`、`015`、`016` 已落库

## 5. 本地验证

已验证：

- `python -m alembic upgrade head`
- `python -m py_compile backend/routers/library.py backend/routers/library_chat.py backend/prompt_registry.py backend/prompt_service.py backend/main.py`
- `cd frontend && npm run build`
- `cd frontend && npx eslint src/LibraryTab.tsx`
- 本地页面验证 AI 报告流式生成、命中文献同步筛选列表、列表与详情编号显示、报告编号点击定位
- 本地页面验证标签搜索下拉筛选、AI 标签提议确认、保存本轮 AI 点评、点评编辑删除和否定点评跳过
- 标签确认卡 hotfix 验证：报告按语义筛出多篇文献时，当前结果内标签提议不再因字面关键词召回漏掉目标文献
