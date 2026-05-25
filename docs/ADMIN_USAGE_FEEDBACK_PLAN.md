# 管理员用户洞察与反馈后台设计方案

> 日期：2026-05-25  
> 状态：设计方案，待确认后实施  
> 关联文件：`backend/routers/admin.py`、`frontend/src/AdminPage.tsx`、`backend/db/models.py`、`backend/services/data_portability.py`

## 1. 背景与目标

当前管理员后台已经具备基础账号能力：

- 查看用户列表
- 修改用户角色
- 重置密码
- 停用/启用用户
- 生成、查看、删除邀请码

但它还不能回答两个关键运营问题：

1. 用户到底有没有用起来：谁在上传、筛选、精读、翻译、对比、使用 Agent，最近卡在哪些任务。
2. 用户遇到了什么问题：缺少统一反馈入口、反馈状态流转、管理员备注和处理闭环。

本方案设计一个配套的“用户洞察与反馈后台”，让管理员能在不直接窥探用户论文内容的前提下，更好地观察使用情况、发现异常、收集反馈并跟进处理。

## 2. 设计原则

1. **先汇总，后下钻**：默认展示聚合数据和任务状态，只有排障时才进入用户详情。
2. **尽量不看正文内容**：使用情况统计只读元数据、计数、任务状态、耗时、错误摘要，不默认展示论文正文、精读正文或用户 API Key。
3. **不存 DeepSeek Key**：延续现有约定，用户 API Key 仍只在前端 localStorage，后台不收集、不展示。
4. **反馈可闭环**：每条反馈必须有状态、优先级、管理员备注、处理时间线。
5. **普通用户 24h 规则不被破坏**：新增表如包含 normal 用户数据，也要有 `expires_at` 或明确说明不随业务数据清理。
6. **数据库变更三件套**：新增表必须同步 `backend/db/models.py`、Alembic migration、`docs/DATABASE_SCHEMA.md`；涉及用户数据导入导出时同步 `backend/services/data_portability.py`。

## 3. 信息架构

管理员后台从当前单页扩展为四个 Tab：

| Tab | 目标 | 主要用户问题 |
|---|---|---|
| 总览 | 看系统整体健康和增长 | 今天有多少活跃用户？任务是否堆积？错误是否增加？ |
| 用户 | 管理用户和查看单用户使用情况 | 某个用户最近做了什么？数据快过期了吗？是否需要升级 VIP？ |
| 任务与用量 | 看功能使用、成本风险和失败任务 | 哪些功能最常用？哪些任务失败最多？是否有人异常高频调用？ |
| 反馈 | 收集、分派、处理用户意见 | 用户反馈了什么？哪些还没处理？哪些问题反复出现？ |

当前邀请码管理可以并入“用户”Tab 的二级页，或保留在顶部 Tab 旁作为“邀请码”子页面。

## 4. 总览页

### 4.1 核心指标卡

| 指标 | 计算方式 | 数据来源 |
|---|---|---|
| 总用户数 | `users.count()` | `users` |
| 7 日活跃用户 | 最近 7 天 `last_login_at` 或有 Job/File 的用户数 | `users`、`jobs`、`files` |
| 今日新用户 | `created_at >= today` | `users` |
| VIP / normal / admin 分布 | 按 `role` 分组 | `users` |
| 今日任务数 | 今日创建的 jobs | `jobs` |
| 运行中 / 排队任务 | `status in (...)` | `jobs` + 队列状态 |
| 今日失败任务 | `status='failed'` | `jobs` |
| 待处理反馈 | `status in ('open','triaged','in_progress')` | 新表 `user_feedback` |

### 4.2 趋势图

首版只做 7/30 天折线与柱状：

- 新增用户数
- 活跃用户数
- 上传文件数
- 新增文献数
- 精读任务数，按 `reading_long / reading_quant / reading_qual` 拆分
- 翻译任务数
- 对比/综述任务数
- Agent 会话数和执行提案数
- 失败任务数

这些指标可以先实时从现有表聚合；数据量变大后再引入日聚合表。

### 4.3 系统健康

- 队列状态：运行中、排队中、失败、平均等待时间。
- 数据清理：最近一次 cleanup 时间、删除数量、dry-run 状态、最近 20 行 cleanup log。
- 存储占用：上传文件总量、结果文件总量、按用户 Top 10。
- 数据库状态：当前 schema version、Alembic head、PostgreSQL/SQLite 类型。

## 5. 用户页

### 5.1 用户列表增强

现有列表增加以下列：

| 列 | 说明 |
|---|---|
| 最近登录 | `users.last_login_at` |
| 最近活动 | 最近一次上传、任务、反馈、Agent 消息时间 |
| 文献数 | `bib_entries.count()` |
| 文件数 / 存储 | `files.count()` / `sum(size_bytes)` |
| 任务数 | `jobs.count()`，可按状态筛选 |
| 失败任务数 | 最近 30 天失败 jobs |
| Agent 会话数 | `agent_sessions.count()` |
| 反馈数 | `user_feedback.count()` |
| 数据到期 | normal 用户最早 `expires_at` |

筛选：

- 角色：all / admin / vip / normal
- 状态：active / disabled
- 活跃度：今日活跃 / 7 日活跃 / 30 日未活跃
- 风险：有失败任务 / 数据即将过期 / 存储占用过高 / 待处理反馈

### 5.2 用户详情抽屉

点击用户打开详情抽屉，建议分 5 个区块：

1. **账号信息**：用户名、邮箱、角色、状态、创建时间、最近登录、VIP 到期。
2. **用量摘要**：文献、文件、任务、反馈、Agent 会话、存储占用。
3. **最近任务**：最近 20 个 Job，展示类型、状态、开始/结束时间、耗时、错误摘要。
4. **最近反馈**：该用户提交的反馈列表与当前处理状态。
5. **管理员操作**：改角色、停用、重置密码、强制退出登录、重算保留期、导出该用户 `.dra`。

管理员查看用户内容要有边界：

- 默认不展示论文正文、精读正文、用户上传文件内容。
- 可展示题名、年份、任务类型、状态、错误消息。
- 如未来需要“代用户排障查看内容”，应新增显式按钮和审计日志，而不是默认开放。

## 6. 任务与用量页

### 6.1 功能用量矩阵

按用户和功能聚合：

| 用户 | 上传 | 题录筛选 | 直接导入 | 长文本精读 | 七步 | 四步 | 翻译 | 对比 | AI 综述 | 参考文献 | Agent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

用途：

- 判断用户是否真的完成核心工作流。
- 发现“只上传不精读”“精读失败率高”“Agent 提案未确认”等产品问题。
- 为 VIP 升级和用户访谈提供依据。

### 6.2 任务列表

全局任务表支持：

- 类型筛选：filter / reading_* / compare / synthesis / reference / translation / translate_abstracts
- 状态筛选：queued / running / done / failed / cancelled
- 用户筛选
- 时间范围
- 错误关键字搜索

字段：

- job_id
- owner_user_id / username
- job_type
- status
- progress
- created_at / started_at / finished_at
- duration_seconds
- batch_id
- artifact_count
- error_summary

### 6.3 成本与风险代理指标

由于系统不保存用户 DeepSeek Key，也不直接知道真实 API 账单，后台只展示代理指标：

- LLM 任务次数
- 输入文本字符数估计
- 输出 Markdown 字符数
- 失败重试次数
- 单用户 24h 内任务峰值

后续如果要精确 token 统计，需要在各 LLM 调用点记录 `model / prompt_chars / completion_chars / duration / success`，但不能记录 API Key。

## 7. 用户反馈设计

### 7.1 反馈入口

前端工作台右上角用户菜单新增“反馈”入口，也可以在任务失败提示、Agent 面板、文献库空状态中放轻量入口。

反馈弹窗字段：

| 字段 | 必填 | 说明 |
|---|:-:|---|
| 类型 | 是 | bug / feature / question / data_issue / translation / reading_quality / other |
| 标题 | 是 | 一句话概括 |
| 内容 | 是 | 用户描述 |
| 关联页面 | 否 | 前端自动带上当前 route/tab |
| 关联对象 | 否 | job_id / file_id / bib_entry_id / artifact_id |
| 期望联系 | 否 | 是否愿意被联系；默认使用账号 email |
| 截图/附件 | 后续 | 首版不做附件，避免存储与隐私复杂度 |

任务失败时可以预填：

- `feedback_type='bug'`
- `related_job_id`
- 错误摘要
- 当前页面

### 7.2 管理员反馈列表

反馈列表字段：

- id
- 类型
- 标题
- 用户
- 状态
- 优先级
- 关联对象
- 创建时间
- 更新时间
- 指派给
- 最后一条管理员备注

状态流转：

```text
open -> triaged -> in_progress -> resolved
open -> closed
resolved -> reopened
```

优先级：

- P0：系统不可用、数据丢失、安全问题
- P1：核心流程失败，如无法上传、无法精读、无法下载
- P2：结果质量、交互阻塞、明显误导
- P3：体验建议、文案、低频问题

### 7.3 反馈详情

详情页展示：

- 用户提交内容
- 关联任务/文献/文件的元数据摘要
- 系统自动捕获的上下文：浏览器 UA、前端版本、后端版本、route、job status、错误摘要
- 管理员内部备注
- 状态变更时间线
- 处理结论

用户侧可在“我的反馈”中看到：

- 自己提交的反馈
- 当前状态
- 管理员公开回复
- 解决时间

管理员内部备注和公开回复要分开，避免把排障细节或敏感信息展示给用户。

## 8. 数据库设计

### 8.1 首版新增表

#### `user_feedback`

```sql
CREATE TABLE user_feedback (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feedback_type       TEXT NOT NULL CHECK (feedback_type IN (
                            'bug','feature','question','data_issue',
                            'translation','reading_quality','other'
                        )),
    title               TEXT NOT NULL,
    content             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
                            'open','triaged','in_progress','resolved','closed','reopened'
                        )),
    priority            TEXT NOT NULL DEFAULT 'P3' CHECK (priority IN ('P0','P1','P2','P3')),
    route               TEXT,
    user_agent          TEXT,
    app_version         TEXT,
    related_job_id      TEXT REFERENCES jobs(id),
    related_file_id     TEXT REFERENCES files(id),
    related_bib_entry_id TEXT REFERENCES bib_entries(id),
    related_artifact_id TEXT REFERENCES artifacts(id),
    assigned_admin_id   INTEGER REFERENCES users(id),
    public_reply        TEXT,
    internal_note       TEXT,
    resolved_at         DATETIME,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at          DATETIME
);

CREATE INDEX idx_user_feedback_owner ON user_feedback(owner_user_id);
CREATE INDEX idx_user_feedback_status ON user_feedback(status);
CREATE INDEX idx_user_feedback_priority ON user_feedback(priority);
CREATE INDEX idx_user_feedback_created ON user_feedback(created_at);
```

是否随 normal 用户 24h 清理：

- 建议首版 **不随业务数据 24h 清理自动删除**，因为反馈本身是产品改进资产。
- 为避免保留过多正文，可在用户提交时明确提示“反馈内容会被管理员保留用于排障和改进”。
- 如果用户要求删除账号或未来有隐私要求，再提供匿名化策略：保留反馈类型、状态、问题分类，清空 `content` 和用户关联。

因此 `user_feedback` 是否加入 `.dra`：

- 不加入 `.dra` 导出/导入。反馈是管理员/产品侧查看和处理的运营记录，不属于用户研究工作区数据。
- `feedback_events`、`admin_audit_logs` 同样不加入 `.dra`。
- `backend/services/data_portability.py` 只更新 `CURRENT_SCHEMA_VERSION` 并写明排除原因，不把三张表加入导出/导入顺序。

#### `feedback_events`

```sql
CREATE TABLE feedback_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id     INTEGER NOT NULL REFERENCES user_feedback(id) ON DELETE CASCADE,
    actor_user_id   INTEGER REFERENCES users(id),
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'created','status_changed','priority_changed',
                        'assigned','commented','public_replied','closed','reopened'
                    )),
    old_value       TEXT,
    new_value       TEXT,
    note            TEXT,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_feedback_events_feedback ON feedback_events(feedback_id);
CREATE INDEX idx_feedback_events_actor ON feedback_events(actor_user_id);
```

#### `admin_audit_logs`

```sql
CREATE TABLE admin_audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id   INTEGER NOT NULL REFERENCES users(id),
    action          TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    target_id       TEXT,
    summary         TEXT NOT NULL,
    payload_json    TEXT,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_admin_audit_admin ON admin_audit_logs(admin_user_id);
CREATE INDEX idx_admin_audit_target ON admin_audit_logs(target_type, target_id);
CREATE INDEX idx_admin_audit_created ON admin_audit_logs(created_at);
```

用于记录：

- 改用户角色
- 停用/启用用户
- 重置密码
- 删除邀请码
- 改反馈状态/优先级
- 查看用户敏感详情（如果后续开放）

### 8.2 可选日聚合表

首版可以实时聚合。若 PostgreSQL 迁移后数据增长明显，再加入：

```sql
CREATE TABLE user_usage_daily (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stat_date           DATE NOT NULL,
    uploads_count       INTEGER NOT NULL DEFAULT 0,
    uploaded_bytes      INTEGER NOT NULL DEFAULT 0,
    bib_entries_count   INTEGER NOT NULL DEFAULT 0,
    jobs_count          INTEGER NOT NULL DEFAULT 0,
    failed_jobs_count   INTEGER NOT NULL DEFAULT 0,
    reading_jobs_count  INTEGER NOT NULL DEFAULT 0,
    translation_jobs_count INTEGER NOT NULL DEFAULT 0,
    compare_jobs_count  INTEGER NOT NULL DEFAULT 0,
    agent_messages_count INTEGER NOT NULL DEFAULT 0,
    feedback_count      INTEGER NOT NULL DEFAULT 0,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, stat_date)
);
```

首版不建议直接上这张表，避免在 PostgreSQL/Redis 迁移前增加定时聚合复杂度。

## 9. 后端 API 规划

所有接口均挂在 `/api/admin` 或 `/api/feedback`，并使用现有 `require_admin` / `current_user`。

### 9.1 管理员统计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/overview` | 总览指标卡、趋势数据、系统健康 |
| GET | `/api/admin/users/usage` | 用户列表 + 用量摘要 |
| GET | `/api/admin/users/{user_id}/usage` | 单用户详情 |
| GET | `/api/admin/jobs` | 全局任务列表 |
| GET | `/api/admin/storage` | 存储占用摘要 |
| GET | `/api/admin/audit-logs` | 管理员操作审计 |

### 9.2 反馈

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/feedback` | 登录用户 | 提交反馈 |
| GET | `/api/feedback/my` | 登录用户 | 查看自己的反馈 |
| GET | `/api/admin/feedback` | admin | 反馈列表 |
| GET | `/api/admin/feedback/{id}` | admin | 反馈详情 |
| PATCH | `/api/admin/feedback/{id}` | admin | 修改状态、优先级、指派、回复 |
| POST | `/api/admin/feedback/{id}/events` | admin | 添加内部备注或公开回复 |

### 9.3 响应模型建议

`AdminUserUsageSummary`：

```json
{
  "user": { "id": 2, "username": "alice", "role": "vip", "is_active": 1 },
  "last_activity_at": "2026-05-25T10:00:00",
  "counts": {
    "files": 12,
    "bib_entries": 80,
    "jobs": 31,
    "failed_jobs_30d": 2,
    "agent_sessions": 4,
    "feedback_open": 1
  },
  "storage": {
    "upload_bytes": 12345678,
    "artifact_bytes": 23456789
  },
  "retention": {
    "earliest_expires_at": null,
    "is_expiring_soon": false
  }
}
```

`FeedbackResponse`：

```json
{
  "id": 12,
  "feedback_type": "reading_quality",
  "title": "七步精读第三步结果太短",
  "status": "open",
  "priority": "P2",
  "owner": { "id": 2, "username": "alice" },
  "related_job_id": "job-uuid",
  "route": "/workspace",
  "created_at": "2026-05-25T10:00:00",
  "updated_at": "2026-05-25T10:00:00"
}
```

## 10. 前端设计

### 10.1 页面结构

`frontend/src/AdminPage.tsx` 目前已经比较长，建议拆分：

```text
frontend/src/admin/
  AdminPage.tsx
  AdminOverview.tsx
  AdminUsers.tsx
  AdminUserDrawer.tsx
  AdminJobs.tsx
  AdminFeedback.tsx
  AdminInvites.tsx
  admin-api.ts
  types.ts
```

`RootApp.tsx` 继续保护 `/admin`，非 admin 显示 403。

### 10.2 UI 风格

后台是操作工具，不做营销式大卡片。建议：

- 顶部用紧凑 Tab：总览 / 用户 / 任务与用量 / 反馈 / 邀请码。
- 指标卡控制在一行 4-6 个，信息密度高但留足空白。
- 表格优先，支持排序、筛选、搜索。
- 用户详情、反馈详情用右侧抽屉，避免频繁跳页。
- 危险操作必须二次确认：停用用户、重置密码、删除邀请码、关闭反馈。

### 10.3 用户侧反馈入口

工作台右上角用户菜单新增：

```text
反馈问题
我的反馈
```

任务失败 Toast 中增加“提交反馈”按钮，自动带上 `job_id`。

## 11. 实施计划

### Phase 1：只读用量洞察

范围：

- 后端新增 `/api/admin/overview`
- 后端新增 `/api/admin/users/usage`
- 前端 AdminPage 拆 Tab
- 总览页、用户用量列表

不新增数据库表，全部从现有表聚合。

验收：

- admin 能看到 7/30 天活跃、任务、失败任务、上传、文献数量。
- admin 能按角色、活跃度、失败任务筛用户。
- normal/vip 访问 admin API 仍为 403。

### Phase 2：反馈闭环

范围：

- 新增 `user_feedback`、`feedback_events`、`admin_audit_logs`
- 新增 `/api/feedback` 与 `/api/admin/feedback`
- 前端用户反馈弹窗
- 管理员反馈列表与详情抽屉
- 同步 `DATABASE_SCHEMA.md`、`data_portability.py` 的 schema version 与排除说明

验收：

- 用户可提交反馈并查看自己的反馈。
- admin 可筛选、改状态、改优先级、写内部备注、写公开回复。
- 反馈关联 job/file/bib/artifact 时，admin 能看到元数据摘要。
- `.dra` 导出/导入不包含反馈记录，`data_portability.py` 明确排除原因。

### Phase 3：任务与成本风险

范围：

- 新增 `/api/admin/jobs`
- 全局任务列表、失败任务排查视图
- 存储占用 Top 用户
- 可选记录 LLM 调用代理指标

验收：

- admin 能按类型/状态/用户/时间筛选任务。
- admin 能快速定位失败任务及错误摘要。
- admin 能发现异常高频使用和存储占用。

### Phase 4：日聚合与运营报表

范围：

- PostgreSQL 迁移稳定后新增 `user_usage_daily`
- 定时聚合每日用量
- 导出 CSV
- 月度用户健康分层：活跃、沉默、高失败、高反馈、高价值

验收：

- 总览页查询不随 jobs/files 增长明显变慢。
- admin 能导出指定时间范围的用户用量报表。

## 12. 权限与隐私

- 所有 admin API 必须使用 `require_admin`。
- 用户反馈 API 只能访问自己的反馈。
- 管理员操作写入 `admin_audit_logs`。
- 默认不展示用户上传文件正文、论文全文、精读全文。
- 错误摘要需要截断，避免把超长 LLM 输出或用户文本塞入后台。
- 反馈内容保留策略要在提交弹窗中明示。

## 13. 测试策略

后端：

- admin overview 聚合计数正确。
- 非 admin 访问 admin API 返回 403。
- 用户只能看到自己的反馈。
- admin 可更新反馈状态并生成 `feedback_events`。
- `data_portability.py` 导出/导入反馈时 owner remap 正确。

前端：

- admin 能切换 Tab。
- 用户列表筛选不丢状态。
- 反馈弹窗提交成功后能在“我的反馈”看到。
- 任务失败入口能自动带上 job_id。

手动验收：

1. normal 用户提交反馈。
2. admin 登录后台，在反馈列表看到该条反馈。
3. admin 改为 P1、in_progress，写公开回复。
4. normal 用户在“我的反馈”看到状态和公开回复。
5. admin 查看该用户详情，能看到反馈数、任务数、失败任务数。

## 14. 风险与取舍

| 风险 | 说明 | 处理 |
|---|---|---|
| 后台查询变慢 | 实时聚合 jobs/files/artifacts 可能随数据增长变慢 | 首版加时间范围和索引，后续上 `user_usage_daily` |
| 隐私边界模糊 | admin 可能看到过多用户内容 | 默认只显示元数据和错误摘要，内容查看后续单独设计审计 |
| 反馈正文长期保留 | normal 用户业务数据 24h 清理，但反馈可能保留 | 提交时明示；后续提供匿名化/删除机制 |
| AdminPage 继续膨胀 | 当前 `AdminPage.tsx` 已是单文件实现 | Phase 1 先拆模块，再加新页面 |
| PostgreSQL 迁移分支污染 | 后台方案涉及新表和前端页面 | 与数据库迁移分支分开实施，不顺手清 lint |

## 15. 推荐落地顺序

建议先做 Phase 1 + Phase 2：

1. Phase 1 不改数据库，能立刻让管理员看见用户使用情况。
2. Phase 2 增加反馈闭环，是用户运营最直接的增益。
3. Phase 3/4 等 PostgreSQL 迁移和多 worker 稳定后再做，避免在 SQLite 阶段把实时聚合压得过重。
