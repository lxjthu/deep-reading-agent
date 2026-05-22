# 文献库 AI 查询实现记录

> 状态：已于 2026-05-22 完成本地验证。  
> 范围：在“我的文献库”中用 DeepSeek 对文献档案做多轮检索问答，并把命中文献联动回列表。

## 1. 功能边界

- 用户在文献库页输入自然语言问题，后端先解析检索意图，再基于当前用户的 `BibEntry` 做数据库召回。
- 支持 `自动 / 全库 / 当前结果` 三种范围模式；自动模式由查询解析提示词判断是否延续上一轮结果。
- 报告生成基于本轮命中的完整元数据与摘要集合，不在前端硬编码提示词。
- 对话把最近几轮问题、报告信息和命中集合传回后端，支持连续收窄或重新扩大范围。

## 2. 前后端实现

### 2.1 后端

- 新增 `backend/routers/library_chat.py`，挂载 `POST /api/library/chat`。
- 路由使用 SSE 依次返回 `intent`、`results`、`citations`、`report`、`done` 或 `error`。
- 检索只访问当前登录用户拥有的 `BibEntry`、`BibReference` 和 `ReadingItem`。
- 文献列表新增 `POST /api/library/entries/by-ids`，用 JSON body 承载 AI 命中 ID 集合，避免把大量 UUID 塞进 GET URL。

### 2.2 前端

- `frontend/src/LibraryTab.tsx` 新增 AI 文献助手面板、多轮 turn 状态、范围切换和 SSE 解析。
- AI 命中 ID 会同步筛选左侧文献列表；恢复全量列表后可回到普通文献库浏览。
- 后端给报告投喂的命中文献按 `[1]`、`[2]` 编号，前端按同一顺序在文献列表和详情区显示编号。
- 报告里的有效 `[n]` 编号会渲染成定位按钮；点击后恢复该轮命中列表、选中目标文献并滚动到列表行。

## 3. 提示词管理

新增 `library_chat` 提示词类型：

| key | 文件 | 用途 |
|---|---|---|
| `query_parser` | `prompts/library_chat/query_parser.md` | 把自然语言问题解析为检索意图 JSON |
| `report_writer` | `prompts/library_chat/report_writer.md` | 基于命中文献与上下文输出中文 Markdown 报告 |

报告提示词要求回答中提到具体文献时沿用输入编号，便于前端和文献列表对照。  
默认提示词仍遵循 `用户覆盖 > 系统默认 > 文件兜底 > 代码兜底`。未被管理员改写的系统默认提示词会在种子同步时跟随托管提示词文件更新。

## 4. 数据库与迁移

- migration：`016_add_library_chat_prompt_type.py`
- 变更：`prompt_templates.prompt_type` 约束加入 `library_chat`
- 数据可移植版本：`backend/services/data_portability.py` 的 `CURRENT_SCHEMA_VERSION` 升到 `016`
- 本功能没有新增用户数据表，`.dra` 导入导出顺序无需增加表项

## 5. 本地验证

已验证：

- `python -m alembic upgrade head`
- `python -m py_compile backend/routers/library.py backend/routers/library_chat.py backend/prompt_service.py backend/main.py`
- `cd frontend && npm run build`
- 本地页面验证 AI 报告流式生成、命中文献同步筛选列表、列表与详情编号显示、报告编号点击定位
