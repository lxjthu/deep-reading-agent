# AI 文献助手持久会话、执行确认与结果 UI 改造规划

> 最后更新：2026-05-23  
> 状态：Phase 1/2 已实施基础版；Phase 3 已实施 `scan_input_folder` 业务表格基础版  
> 关联实现文档：[AGENT_ASSISTANT_IMPL.md](AGENT_ASSISTANT_IMPL.md)

## 背景

当前 AI 文献助手已经具备 DeepSeek tool calling、input 文件夹白名单、只读扫描、文献库对比、文件夹导入和批量精读编排能力。但仍有三个明显短板：

1. 会话只存在前端内存中，刷新后丢失，无法可靠引用“刚才那些文献”。
2. 执行型工具缺少二次确认，仍主要依赖系统提示词区分“查看”和“启动”。
3. 工具结果 JSON 以通用递归块展示，信息密度、层次和可操作性都不够好。

本规划目标是把 AI 助手升级为可靠的多轮工作流界面：

- 可恢复会话。
- 可追踪工具调用。
- 可引用上一轮结构化结果。
- 启动导入/精读前必须确认。
- 工具结果从“JSON 块”升级为“研究工作台式结果页”。

## 总体目标

### P0：可靠继续对话

实现持久会话：

- 保存用户消息、AI 回复、工具调用、工具结果。
- 刷新后恢复最近会话。
- 后端可读取最近结构化工具结果，支持“刚才那些不在库里的文献”等指代。

### P1：执行前确认

所有会改变状态或启动长任务的工具改为 proposal-first：

- 先生成执行提案。
- 前端展示确认弹窗。
- 用户确认后，后端再真正导入或启动精读。

### P2：结果 UI 改造

把现在的通用 JSON 卡片替换为面向文献工作的专用视图：

- 文献清单表。
- 文献库匹配状态。
- 筛选统计。
- 批量任务进度。
- 执行提案与确认面板。

## 数据库规划

本规划涉及用户数据表变更，实施时必须同步：

- `backend/db/models.py`
- Alembic migration
- `docs/DATABASE_SCHEMA.md`
- `backend/services/data_portability.py`

### 表：agent_sessions

用途：保存每个用户的 AI 助手会话。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String PK | UUID |
| `owner_user_id` | FK users.id | 用户隔离 |
| `title` | String | 会话标题，可由首条消息生成 |
| `status` | String | `active` / `archived` |
| `last_summary` | Text nullable | 后端压缩后的会话摘要 |
| `last_state_json` | Text | 最近可引用结构化状态 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |
| `expires_at` | DateTime nullable | normal 用户 24h 清理 |

索引：

- `idx_agent_sessions_owner`
- `idx_agent_sessions_updated`
- `idx_agent_sessions_expires`

`last_state_json` 建议结构：

```json
{
  "last_scan": {
    "papers": [],
    "library_counts": {},
    "topic": "*"
  },
  "last_proposal": {
    "proposal_id": "...",
    "action": "import_folder_and_start_reading"
  },
  "last_batch": {
    "batch_id": "...",
    "job_ids": []
  }
}
```

### 表：agent_messages

用途：保存消息、工具调用和工具结果。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String PK | UUID |
| `session_id` | FK agent_sessions.id | 会话 |
| `owner_user_id` | FK users.id | 用户隔离 |
| `role` | String | `user` / `assistant` / `tool` / `system` |
| `event_type` | String | `message` / `tool_call` / `tool_result` / `proposal` / `confirmation` / `error` |
| `tool_name` | String nullable | 工具名 |
| `content` | Text | 用户/AI 文本 |
| `payload_json` | Text nullable | 工具参数或工具结果 |
| `sort_order` | Integer | 会话内顺序 |
| `created_at` | DateTime | 创建时间 |
| `expires_at` | DateTime nullable | normal 用户清理 |

索引：

- `idx_agent_messages_session`
- `idx_agent_messages_owner`
- `idx_agent_messages_expires`

### 表：agent_action_proposals

用途：保存待确认执行提案。也可以先不建表，放在 `agent_messages.event_type="proposal"` 中；但独立表更利于状态管理。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String PK | UUID |
| `session_id` | FK agent_sessions.id | 会话 |
| `owner_user_id` | FK users.id | 用户隔离 |
| `action_type` | String | `start_reading` / `start_batch_reading` / `import_folder_and_start_reading` |
| `status` | String | `pending` / `confirmed` / `rejected` / `expired` / `executed` / `failed` |
| `arguments_json` | Text | 原始工具参数 |
| `preview_json` | Text | 给用户确认的文献/任务预览 |
| `result_json` | Text nullable | 执行结果 |
| `created_at` | DateTime | 创建时间 |
| `confirmed_at` | DateTime nullable | 确认时间 |
| `expires_at` | DateTime nullable | 过期时间 |

索引：

- `idx_agent_proposals_session`
- `idx_agent_proposals_status`
- `idx_agent_proposals_owner`

## 后端 API 规划

文件建议：继续使用 `backend/routers/agent.py`，必要时拆出 `backend/services/agent_state.py` 和 `backend/services/agent_tools.py`。

### 会话 API

- `GET /api/agent/sessions`
  - 列出当前用户最近会话。

- `POST /api/agent/sessions`
  - 新建会话。

- `GET /api/agent/sessions/{session_id}`
  - 获取会话详情和最近消息。

- `PATCH /api/agent/sessions/{session_id}`
  - 重命名或归档。

- `DELETE /api/agent/sessions/{session_id}`
  - 删除或软归档。

### 对话 API

现有：

- `POST /api/agent/chat`

建议改造为：

请求新增：

```json
{
  "session_id": "...",
  "message": "...",
  "api_key": "sk-...",
  "history": []
}
```

行为：

1. 若无 `session_id`，自动创建会话。
2. 保存 user message。
3. 从 `agent_messages` 和 `agent_sessions.last_state_json` 构造上下文。
4. 执行工具调用。
5. 保存 tool_call、tool_result、assistant answer。
6. 更新 `last_state_json`。

SSE 事件新增：

- `session`
  - 返回 `session_id`、`title`。

- `state_update`
  - 返回当前会话可引用状态摘要。

### 确认 API

- `POST /api/agent/proposals/{proposal_id}/confirm`
  - 用户确认执行。
  - 后端执行真实导入/精读任务。

- `POST /api/agent/proposals/{proposal_id}/reject`
  - 用户拒绝。

- `GET /api/agent/proposals/{proposal_id}`
  - 读取确认详情。

## 工具改造规划

### 工具分级

#### 只读工具

这些工具可以直接执行：

- `search_library`
- `get_entry_detail`
- `get_reading_context`
- `scan_input_folder`
- `get_job_status`

#### 执行型工具

这些工具必须 proposal-first：

- `start_reading`
- `start_batch_reading`
- `import_folder_and_start_reading`

### 新增工具：prepare_import_folder_reading_proposal

替代直接执行的 `import_folder_and_start_reading` 第一阶段。

输入：

```json
{
  "topic": "*",
  "mode": "quant",
  "recursive": false,
  "max_files": 50,
  "conflict_resolution": "skip"
}
```

输出：

```json
{
  "proposal_id": "...",
  "action_type": "import_folder_and_start_reading",
  "summary": {
    "will_import": 12,
    "will_start_reading": 9,
    "already_in_library": 3,
    "possible_matches": 2
  },
  "papers": []
}
```

### 新增工具：prepare_batch_reading_proposal

用于已有 `file_ids` 或上一轮扫描结果。

### 执行函数

确认后执行，不再由 LLM 直接触发：

- `execute_start_reading_proposal(proposal_id)`
- `execute_batch_reading_proposal(proposal_id)`
- `execute_import_folder_reading_proposal(proposal_id)`

## 前端规划

文件当前入口：[frontend/src/App.tsx](../frontend/src/App.tsx)

后续建议拆分组件，避免 `App.tsx` 继续膨胀：

```text
frontend/src/agent/
  AgentTab.tsx
  AgentComposer.tsx
  AgentTimeline.tsx
  AgentResultRenderer.tsx
  AgentJsonView.tsx
  AgentPaperTable.tsx
  AgentLibraryMatchBadge.tsx
  AgentProposalDialog.tsx
  AgentSessionSidebar.tsx
  agent-types.ts
```

### 会话 UI

建议增加：

- 左侧窄会话栏
  - 最近会话列表。
  - 新建会话。
  - 重命名/归档。

- 主对话区
  - 用户消息。
  - 工具调用时间线。
  - 结果卡片。
  - 最终回答。

- 底部输入区
  - 固定在页面底部。
  - 支持 Ctrl/Cmd + Enter 发送。

## 执行前确认弹窗规划

组件名建议：

- `AgentProposalDialog`

触发：

- 收到 SSE `proposal` 事件。

弹窗内容：

- 操作类型
  - 导入文件
  - 启动七步法
  - 启动四步法
  - 长文本精读

- 影响范围
  - 将导入 N 篇。
  - 将启动 M 个任务。
  - 已在库中 K 篇。
  - 疑似匹配 P 篇。
  - 跳过 S 篇。

- 文献表
  - 标题
  - 文件名
  - 文献库状态
  - 相关性
  - 将执行动作

- 选项
  - 跳过已精读。
  - 跳过疑似匹配。
  - 只导入不精读。
  - 导入并精读。

- 按钮
  - 确认执行
  - 取消
  - 只保存提案

安全规则：

- 弹窗确认前，后端不得创建精读任务。
- 取消后 proposal 状态置为 `rejected`。
- 过期 proposal 不允许执行。

## JSON 页面显示优化方案

当前 `JsonHtmlView` 是通用递归 JSON 渲染，问题是：

- 每层都是相似卡片，视觉噪声大。
- 没有把 `papers`、`library_match`、`batch` 等业务字段转成专用布局。
- 用户看不到重点：哪些在库里、哪些不在、下一步能做什么。
- 大 JSON 滚动体验差。

### 设计方向

采用“研究工作台 / 审稿台”风格，而不是聊天机器人调试面板。

视觉原则：

- 安静、密集、可扫描。
- 少用大色块，重点使用状态徽标和表格。
- 以文献表为主，工具调用只是可折叠元信息。
- 卡片圆角不超过 8px。
- 避免嵌套卡片套卡片。

### 结果渲染策略

新增统一入口：

- `AgentResultRenderer`

根据 payload shape 分流：

| payload 特征 | 组件 |
|---|---|
| `papers` + `library_counts` | `FolderScanResult` |
| `selected` + `batch` | `ImportReadingResult` |
| `batch_id` + `tasks` | `BatchStatusResult` |
| `entries` | `LibrarySearchResult` |
| `items` + `entries` | `ReadingContextResult` |
| 未识别 JSON | `AgentJsonInspector` |

### FolderScanResult

用于 `scan_input_folder`。

布局：

1. 顶部统计条
   - 扫描总数
   - 相关文献
   - 已在库中
   - 疑似匹配
   - 不在库中

2. 筛选工具条
   - 全部
   - 只看不在库
   - 只看疑似匹配
   - 只看相关

3. 文献表
   - 状态
   - 标题
   - 文件名
   - 文献库匹配
   - 相关性
   - 理由

4. 行操作
   - 查看详情
   - 加入待导入
   - 排除

### 状态徽标

组件：

- `AgentLibraryMatchBadge`

状态文案：

- `in_library`：已在库
- `possible_match`：疑似匹配
- `not_in_library`：未入库
- `file_exists_no_bib_entry`：文件已存在

颜色建议：

- 已在库：绿色
- 疑似匹配：琥珀色
- 未入库：蓝色
- 文件已存在未绑定：灰色

### JSON Inspector 保留但降级

原始 JSON 仍可查看，但放在折叠区：

- 默认显示业务组件。
- “查看原始 JSON”按钮展开。
- 原始 JSON 使用等宽字体和行缩进，不作为主视图。

### 前端组件拆分建议

```text
AgentResultRenderer.tsx
  detectResultType(payload)
  render by result type

FolderScanResult.tsx
  stats
  filters
  table

ImportReadingResult.tsx
  selected/rejected/batch summary

BatchStatusResult.tsx
  progress table

AgentJsonInspector.tsx
  fallback raw JSON viewer
```

### 设计实现注意

- 表格列宽固定或使用 `minmax`，避免长标题撑破布局。
- 长标题最多两行，悬停显示完整内容。
- `reason` 放在次级文本，避免挤占主标题。
- 大列表使用分页或前端虚拟滚动，避免一次渲染 100 篇卡片。
- 工具调用事件可折叠，默认只展示结果。

## 实施步骤

### Phase 1：会话表与消息持久化

1. 新增 ORM 模型。
2. 新增 Alembic migration。
3. 更新 `docs/DATABASE_SCHEMA.md`。
4. 更新 `backend/services/data_portability.py`。
5. `/api/agent/chat` 接入 `session_id`。
6. 保存消息、工具调用、工具结果。

验收：

- 刷新页面后能恢复最近会话。
- 后端能读取上一轮工具结果。

### Phase 2：执行前确认

1. 新增 proposal 数据结构。
2. 执行型工具改成生成 proposal。
3. 新增 confirm/reject API。
4. 前端实现 `AgentProposalDialog`。

验收：

- 用户只说“看看”不会启动任务。
- 用户说“开始精读”时先出现确认弹窗。
- 未确认前数据库不新增精读 Job。

### Phase 3：结果 UI 改造

1. 拆出 `frontend/src/agent/` 组件。
2. 新增 `AgentResultRenderer`。
3. 实现 `FolderScanResult`。
4. 实现 `ImportReadingResult`。
5. 实现 `BatchStatusResult`。
6. 原始 JSON 放入折叠 inspector。

验收：

- 文件夹扫描结果以表格展示。
- 一眼能看出已入库、疑似、不在库。
- JSON 不再作为主视觉。

### Phase 4：更可靠的指代执行

1. `last_state_json` 记录最近扫描结果。
2. 支持“只导入刚才不在库里的文献”。
3. 支持“疑似匹配先排除”。
4. 支持“对上一轮相关文献启动七步法”。

验收：

- 刷新后仍能继续引用上一轮扫描结果。

## 风险与约束

- 数据库表变更必须同步导入导出，否则 `.dra` 迁移会丢失会话。
- 执行确认不能只放前端，后端也要用 proposal 状态约束。
- 不要让 LLM 直接传任意路径；仍然只用后端保存的 input 白名单。
- 只读工具和执行工具必须在代码层分开，不能只靠提示词。
- 大工具结果要分页或摘要，否则会话上下文会膨胀。

## 推荐下一步

优先实施顺序：

1. Phase 1：持久会话和消息保存。
2. Phase 2：执行前确认。
3. Phase 3：结果 UI 改造。

原因：

- 没有持久会话，确认弹窗和“刚才那些文献”都不稳定。
- 没有执行确认，继续扩展 Agent 工具风险较高。
- UI 改造可以独立推进，但最好复用持久化后的 payload 类型。

## 2026-05-23 实施记录

已完成基础版：

- 新增 `agent_sessions`、`agent_messages`、`agent_action_proposals`。
- 新增 migration `019_add_agent_sessions.py`。
- `CURRENT_SCHEMA_VERSION` 更新为 `019`，并将 Agent 表加入 `.dra` 导出/导入顺序。
- `/api/agent/chat` 支持 `session_id`，保存消息和工具事件。
- 新增会话接口：`GET/POST /api/agent/sessions`、`GET /api/agent/sessions/{session_id}`。
- 新增确认接口：`POST /api/agent/proposals/{proposal_id}/confirm` 和 `/reject`。
- 执行型工具改为 proposal-first。
- 前端 `AgentTab` 支持恢复最近会话和显示确认执行面板。
- `scan_input_folder` 结果已增加专用表格展示。

仍待加强：

- 会话侧栏、重命名、归档尚未实现。
- proposal 弹窗仍是基础面板，尚未提供逐篇勾选、跳过疑似匹配等高级选项。
- `AgentResultRenderer` 还没有拆成独立文件；目前仍在 `App.tsx` 中。
- 只有 `scan_input_folder` 有业务表格，`batch.tasks`、`selected/rejected` 等结果还需专用组件。
