# 修复：文献助手报告保存到历史记录远端 500 错误

> 日期：2026-05-25
> 影响范围：远端服务器（本地开发环境不受影响）

---

## 现象

在文献库中使用 AI 文献助手生成报告后，点击「保存到历史记录」按钮，远端服务器返回 **500 Internal Server Error**，前端显示"请求失败"。本地开发环境无此问题。

浏览器 F12 控制台报错：

```
POST https://deepreading.qzz.io/api/history/library-chat/ 500 (Internal Server Error)
```

后端日志：

```
sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) CHECK constraint failed: ck_jbe_role
[SQL: INSERT INTO job_bib_entries (job_id, bib_entry_id, role, sort_order) VALUES (?, ?, ?, ?)]
[parameters: (..., 'library_chat_member', 0)]
```

---

## 根因

### 直接原因

`job_bib_entries` 表的 `ck_jbe_role` CHECK 约束缺少 `'library_chat_member'` 值：

```sql
-- 服务器实际（错误）：
CHECK (role IN ('target','compare_member','synthesis_member','reference_source'))

-- 应该是：
CHECK (role IN ('target','compare_member','synthesis_member','reference_source','library_chat_member'))
```

当 `save_library_chat_report` (`history.py:485`) 插入 `role='library_chat_member'` 的记录时，SQLite 拒绝写入。

### 根本原因

Migration 022 (`022_add_library_chat_history`) 使用 Alembic 的 `batch_alter_table` 修改 CHECK 约束：

```python
with op.batch_alter_table("job_bib_entries") as batch_op:
    batch_op.drop_constraint("ck_jbe_role", type_="check")
    batch_op.create_check_constraint("ck_jbe_role", f"role IN ({JBE_ROLES})")
```

**SQLite 不持久化 CHECK 约束名称**。`drop_constraint("ck_jbe_role")` 无法按名称定位约束，静默失败。随后 `create_check_constraint` 添加了新约束，但在 `batch_alter_table` 重建表时，旧约束仍保留在表定义中，最终旧约束覆盖了新约束。

Alembic 的 `alembic_version` 表正常更新到了 `023`，掩盖了 022 实际未生效的事实。

### 为什么本地没问题

本地开发时 migration 是逐个执行的，且 SQLite 数据库可能从最新的 `models.py` 直接创建（`create_all`），跳过了有问题的 migration。

### 为什么 `jobs` 和 `artifacts` 表没问题

Migration 023 (`023_add_ref_format_generation`) 也更新了 `jobs` 和 `artifacts` 的 CHECK 约束（添加 `ref_format` 相关值）。023 的 `batch_alter_table` 虽然存在同样的 SQLite 约束名匹配问题，但由于它在 022 之后运行，对 `jobs` 和 `artifacts` 起到了"二次修复"的作用。而 `job_bib_entries` 只被 022 触及过，没有后续 migration 再碰它。

---

## 数据流链路

```
前端 LibraryTab.tsx:saveChatTurnReport()
  → POST /api/history/library-chat/
    → history.py:save_library_chat_report()
      → db.add(Job(job_type="library_chat"))        ← jobs 表，约束已正确 ✓
      → db.add(JobBibEntry(role="library_chat_member")) ← job_bib_entries 表，约束缺失 ✗
      → db.add(Artifact(artifact_type="library_chat_md")) ← artifacts 表，约束已正确 ✓
      → await db.commit()                             ← 此处触发 CHECK 约束失败
```

---

## 修复措施

### 1. 服务器紧急修复（已执行）

通过 Python 脚本直接重建 `job_bib_entries` 表，添加正确的约束：

```python
import sqlite3
conn = sqlite3.connect('db/app.sqlite')
conn.execute('CREATE TABLE _tmp_jbe (...)')  # 包含 library_chat_member 的约束
conn.execute('INSERT INTO _tmp_jbe SELECT * FROM job_bib_entries')
conn.execute('DROP TABLE job_bib_entries')
conn.execute('ALTER TABLE _tmp_jbe RENAME TO job_bib_entries')
conn.commit()
conn.close()
```

### 2. 修复 Migration 022 代码（待推送）

文件：`backend/migrations/versions/022_add_library_chat_history.py`

已将 `job_bib_entries` 表的约束修改从 `batch_alter_table` 改为 SQLite 专用的表重建逻辑（`ALTER TABLE RENAME` + 重建 + 数据迁移），绕过 `drop_constraint` 按名称匹配不到的问题。`jobs` 和 `artifacts` 表不受影响（已被 migration 023 二次修复）。

当前服务器已手动修复，推送后新环境部署不会再出此问题。

---

## 经验教训

### 1. SQLite + Alembic `batch_alter_table` 修改 CHECK 约束不可靠

SQLite 不存储 CHECK 约束名称，`drop_constraint(name)` 无法按名称定位约束。当需要修改 CHECK 约束时，应直接重建表而非依赖 `batch_alter_table` 的 `drop_constraint` + `create_check_constraint`。

**推荐做法**：对 SQLite 的 CHECK 约束修改，在 migration 中检测 dialect，对 SQLite 使用手动的表重建：

```python
def upgrade() -> None:
    ctx = op.get_context()
    if ctx.dialect.name == "sqlite":
        # 直接重建表，绕过 batch_alter_table 的约束名匹配问题
        bind = op.get_bind()
        bind.execute("ALTER TABLE xxx RENAME TO _xxx_old")
        bind.execute("CREATE TABLE xxx (...)")
        bind.execute("INSERT INTO xxx SELECT * FROM _xxx_old")
        bind.execute("DROP TABLE _xxx_old")
    else:
        # PostgreSQL 等，正常使用 batch_alter_table
        with op.batch_alter_table("xxx") as batch_op:
            ...
```

### 2. `alembic current` 不等于 migration 实际生效

Alembic 只记录版本号，不验证数据库 schema 是否与 migration 描述一致。`alembic upgrade head` 成功退出只能说明版本号更新了，不能保证所有 SQL 操作都正确执行了。

**建议**：对关键表结构变更，部署后可通过脚本验证：

```bash
python -c "
import sqlite3
conn = sqlite3.connect('db/app.sqlite')
cur = conn.execute(\"SELECT sql FROM sqlite_master WHERE type='table'\")
for row in cur.fetchall():
    if 'CHECK' in (row[0] or ''):
        print(row[0])
        print('---')
conn.close()
"
```

### 3. deploy.sh 的 `|| echo` 掩盖了 migration 错误

```bash
alembic upgrade head || echo "警告：数据库迁移失败，请手动检查"
```

这行让 migration 失败时脚本继续执行，服务照常重启，但数据库 schema 可能不正确。

**建议**：关键 migration 失败时应当阻止服务重启，至少打印更醒目的警告。

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/migrations/versions/022_add_library_chat_history.py` | 修改，SQLite 下 `job_bib_entries` 约束改用表重建 |
| `docs/FIX_LIBRARY_CHAT_SAVE_500.md` | 本文档 |
