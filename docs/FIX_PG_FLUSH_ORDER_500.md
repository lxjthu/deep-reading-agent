# 修复：PostgreSQL 下文献助手「保存到历史记录」500 错误（SQLAlchemy flush 顺序）

> 日期：2026-05-27
> 影响范围：远端 PostgreSQL 服务器（本地 SQLite 开发环境不受影响）
> 关联：[FIX_LIBRARY_CHAT_SAVE_500.md](FIX_LIBRARY_CHAT_SAVE_500.md)（2026-05-25 SQLite CHECK 约束问题，不同根因）

---

## 现象

在文献库中使用 AI 文献助手生成报告后，点击「保存到历史记录」按钮，远端服务器返回 **500 Internal Server Error**。本地开发环境无此问题。

浏览器控制台：

```
POST http://8.162.14.154:18080/api/history/library-chat/ 500 (Internal Server Error)
```

后端日志（`/var/log/deepreading/api-error.log`）：

```
asyncpg.exceptions.ForeignKeyViolationError: insert or update on table "artifacts"
violates foreign key constraint "artifacts_job_id_fkey"
DETAIL:  Key (job_id)=(3534badd-ba07-4478-845b-b3187aa8af74) is not present in table "jobs".
```

---

## 根因

### 直接原因

`save_library_chat_report`（`history.py:485`）在同一个 session 中先 `db.add(Job(...))` 再 `db.add(Artifact(...))`，最后 `db.commit()`。SQLAlchemy 的 UnitOfWork 在 flush 时**只发出了 Artifact 的 INSERT，没有发出 Job 的 INSERT**：

```
BEGIN (implicit)
INSERT INTO artifacts (job_id, ...) VALUES ($1, ...)   ← 只有这一条！
ROLLBACK
```

Artifact 引用的 `job_id` 在 `jobs` 表中不存在 → 外键违反 → 事务中止 → 500。

### 根本原因：SQLAlchemy UoW flush 顺序

`Job` 和 `Artifact` 模型之间**没有定义 `relationship()`**。SQLAlchemy 的 UnitOfWork 依赖 relationship 来推导对象间的依赖关系和 flush 顺序。没有 relationship 时，UoW 按默认顺序（基本是 add 顺序）flush，但这个顺序**不保证**符合外键约束。

关键代码（`history.py:505-566`，修复前）：

```python
db.add(Job(id=job_id, ...))           # ① 先加 Job
# ... 中间还加了 JobBibEntry ...
db.add(Artifact(job_id=job_id, ...))  # ② 后加 Artifact
await db.commit()                      # ③ commit 时 flush
```

### 为什么 SQLite 不出问题

SQLite 在事务级别做 FK 检查：同一事务内的所有 INSERT 被视为一个原子操作，FK 约束在事务提交时统一校验。因此即使 Artifact 先于 Job 被 INSERT，SQLite 也不会报错——因为它们在同一个事务中。

PostgreSQL 对每条 INSERT 独立做 FK 校验：Artifact INSERT 时，Job 还不存在（未被 flush），立即报 ForeignKeyViolationError。

### 为什么其他端点不受影响

排查了所有 6 个 router 文件（history.py、reading.py、compare.py、filter.py、translation.py、references.py），其他端点都使用了以下安全模式之一：

| 模式 | 使用位置 |
|------|---------|
| Job add 后 `await db.flush()` 再加 Artifact | `save_synthesis`（history.py）、`create_compare_job`（compare.py） |
| Job add 后 `await db.commit()`，Artifact 在独立 session 中创建 | reading.py、filter.py、translation.py、references.py 的后台任务 |

`save_library_chat_report` 是唯一一个在同一 session 中先 add Job 再 add Artifact 且中间没有 flush 的端点。

---

## 数据流链路

```
前端 LibraryTab.tsx:saveChatTurnReport()
  → POST /api/history/library-chat/
    → history.py:save_library_chat_report()
      → db.add(Job(job_type="library_chat"))        ← 加入 session，未 flush
      → db.add(JobBibEntry(role="library_chat_member")) ← 加入 session
      → db.add(Artifact(artifact_type="library_chat_md")) ← 加入 session
      → await db.commit()                             ← flush 时 UoW 顺序错误
        → SQLAlchemy 先 INSERT Artifact（FK 违反！）
        → 整个事务中止
```

---

## 修复措施

### 代码修改

**`backend/routers/history.py`**：

1. `save_library_chat_report`（line 524）：在 `db.add(Job(...))` 之后加 `await db.flush()`
2. `save_synthesis`（line 389）：预防性修复，同样加 `await db.flush()`

```python
db.add(Job(id=job_id, ...))
await db.flush()  # 强制先写入 Job，确保 job_id 对后续 INSERT 可见

for sort_order, entry in enumerate(members):
    db.add(JobBibEntry(job_id=job_id, ...))

db.add(Artifact(job_id=job_id, ...))
await db.commit()
```

### 为什么用 flush 而不是加 relationship

加 `relationship()` 是更"正确"的长期方案，但：

1. 项目中所有模型均未定义 relationship，全部依赖显式外键列 + 手动 join
2. 加 relationship 会影响 ORM 行为（级联删除、lazy loading 等），需要全面回归测试
3. `await db.flush()` 是最小改动，不影响其他代码路径，与 compare.py 中 `create_compare_job` 的模式一致

---

## 验证

### 复现脚本（修复前）

```python
# 在 PostgreSQL 上直接复现
async with AsyncSessionLocal() as db:
    db.add(Job(id="test-123", owner_user_id=2, job_type="library_chat", ...))
    db.add(Artifact(job_id="test-123", owner_user_id=2, artifact_type="library_chat_md", ...))
    await db.commit()
    # → ForeignKeyViolationError: job_id not present in jobs
```

### 修复后验证

```python
async with AsyncSessionLocal() as db:
    db.add(Job(id="test-456", ...))
    await db.flush()  # 先 flush Job
    db.add(Artifact(job_id="test-456", ...))
    await db.commit()
    # → 成功
```

---

## 经验教训

### 1. SQLite FK 检查时机与 PostgreSQL 不同

SQLite 的 FK 约束在事务提交时统一检查，PostgreSQL 对每条 DML 独立检查。在 SQLite 上通过的代码，在 PostgreSQL 上可能因 flush 顺序问题失败。

**规则**：在同一 session 中先创建父记录再创建子记录时，必须在子记录 `db.add()` 之前 `await db.flush()` 父记录。

### 2. SQLAlchemy 无 relationship 时 flush 顺序不可靠

没有 `relationship()` 定义时，SQLAlchemy 无法自动推导对象依赖。flush 顺序取决于内部实现细节（add 顺序、mapper 拓扑排序等），不应依赖。

**规则**：涉及外键依赖的同 session 多表 INSERT，必须显式 flush 父记录。

### 3. 线上 SQLite → PostgreSQL 迁移需全面回归同 session 事务

项目从 SQLite 迁移到 PostgreSQL 后，所有"同一 session 中先 add 父后 add 子"的代码路径都可能有此隐患。本次 `save_library_chat_report` 是第一个触发的，`save_synthesis` 做了预防性修复。

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/routers/history.py` | `save_library_chat_report` 和 `save_synthesis` 加 `await db.flush()` |
| `docs/FIX_PG_FLUSH_ORDER_500.md` | 本文档 |

---

## 与前次修复的关系

2026-05-25 的 [FIX_LIBRARY_CHAT_SAVE_500.md](FIX_LIBRARY_CHAT_SAVE_500.md) 是**不同根因**的同类症状：

| 维度 | 05-25 问题 | 05-27 问题（本次） |
|------|-----------|-------------------|
| 数据库 | SQLite | PostgreSQL |
| 根因 | Migration 022 的 `drop_constraint` 在 SQLite 上静默失败，CHECK 约束未更新 | SQLAlchemy UoW flush 顺序错误，Artifact 先于 Job 被 INSERT |
| 错误类型 | `IntegrityError: CHECK constraint failed` | `ForeignKeyViolationError: job_id not present in jobs` |
| 修复 | 重建 `job_bib_entries` 表 + 修改 migration 代码 | 加 `await db.flush()` 强制 flush 顺序 |
