# 数据库设计文档

> **版本**: v1.1  
> **日期**: 2026-04-26  
> **关联文档**: [MULTI_USER_PLAN.md](./MULTI_USER_PLAN.md)

## 1. 选型与约定

| 项 | 选择 |
|---|---|
| 数据库 | SQLite 3 |
| ORM | SQLAlchemy 2.0（async + Mapped 风格） |
| 迁移工具 | Alembic |
| 主键 | 业务表用 UUID（TEXT），账号体系表用自增 INTEGER |
| 时间 | 全部 UTC，存 ISO8601 字符串或 SQLite 原生 DATETIME |
| 软删除 | 不做。普通用户的 24h 清理通过物理删除 + 级联完成 |
| 数据库文件位置 | `db/app.sqlite`（加入 `.gitignore`） |
| 备份 | 每日凌晨复制到 `db/backups/YYYY-MM-DD.sqlite`，保留 30 天 |

## 2. 实体关系图（ER 概览）

```
                    ┌─────────────┐
                    │   users     │
                    └──────┬──────┘
                           │ owns
   ┌───────────────────────┼─────────────────────────┐
   │                       │                         │
   ▼                       ▼                         ▼
┌────────┐         ┌──────────────┐           ┌──────────┐
│ files  │◀──pdf───│ bib_entries  │──┐        │   jobs   │
│        │         │  ⭐ 枢纽     │  │ N:M    │          │
└───┬────┘         └──────┬───────┘  ▼        └────┬─────┘
    │ N:1                 │ N:M    ┌──────────┐    │
    │                     │        │job_bib_  │    │ produces
    ▼                     ▼        │ entries  │    ▼
filter_jobs         bib_filter_   └──────────┘  ┌──────────┐
                     links                       │artifacts │
                                                 └──────────┘
                                                  
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ invite_codes   │    │ user_settings  │    │ upload_batches │
└────────────────┘    └────────────────┘    └────────────────┘
```

枢纽：`bib_entries`（一篇文献的"档案"）  
物理：`files`（PDF / 题录 / MD / DOCX）  
事件：`jobs`（filter / reading_* / compare / synthesis）  
产物：`artifacts`（任务输出文件）

## 3. 表定义

### 3.1 `users` — 用户

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'vip', 'normal')),
    vip_expires_at  DATETIME,           -- 预留字段，目前 VIP 永久；未来可做 VIP 到期
    is_active       INTEGER NOT NULL DEFAULT 1,
    token_version   INTEGER NOT NULL DEFAULT 0,   -- P1: refresh token 版本号
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    last_login_at   DATETIME
);

CREATE INDEX idx_users_role ON users (role);
```

**Seed**: `admin` / `XIAojuan@0618wenxian` （`role='admin'`，bcrypt 哈希）

**`token_version` 用途（P1）**：
- 用于严格实现 logout / refresh token 撤销，但不单独维护 `refresh_tokens` 表。
- 签发 `refresh_token` 时，把当前 `users.token_version` 写入 JWT claim。
- 调用 `/api/auth/refresh` 时，除验签和过期校验外，还必须比对 token 内版本号与数据库当前值。
- 调用 `/api/auth/logout` 时，将 `users.token_version = users.token_version + 1`，使该用户此前签发的所有 refresh token 立即失效。
- 调用 `/api/auth/change_password` 时，同样递增 `token_version`，强制旧 refresh token 全部失效。
- 该方案是**用户级撤销**而非**单设备撤销**：一个设备 logout 后，该用户其他设备上的旧 refresh token 也会失效。

### 3.2 `invite_codes` — VIP 邀请码

```sql
CREATE TABLE invite_codes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL UNIQUE,
    created_by_user_id  INTEGER NOT NULL REFERENCES users(id),
    max_uses            INTEGER NOT NULL DEFAULT 1,
    used_count          INTEGER NOT NULL DEFAULT 0,
    expires_at          DATETIME,
    note                TEXT,           -- 备注（如"给王老师"）
    created_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_invite_codes_code ON invite_codes (code);
```

注册时校验：`used_count < max_uses` 且 `(expires_at IS NULL OR expires_at > now())`。

### 3.3 `user_settings` — 用户配置（预留扩展点）

```sql
CREATE TABLE user_settings (
    user_id              INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    preferences_json     TEXT,           -- 预留：UI 偏好、默认 prompt 等
    updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**v1 暂未启用**，建表占位。  
**API Key 不入库**：DeepSeek API Key 继续保留在前端 `localStorage`，由用户自行管理。普通用户 24h 清理只清服务端文件与档案，**不清前端 key**。前端登录页对普通用户提示"上传文件、文献档案、精读结果将在 24h 后清空，但您的 API Key 保存在浏览器本地，不会被清理；请自行备份产出文件"。

### 3.4 `files` — 物理文件

```sql
CREATE TABLE files (
    id              TEXT PRIMARY KEY,                            -- UUID
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    original_name   TEXT NOT NULL,
    file_type       TEXT NOT NULL CHECK (file_type IN
                        ('pdf', 'bibliography', 'markdown', 'docx', 'txt')),
    storage_path    TEXT NOT NULL,                               -- 相对路径
    size_bytes      INTEGER NOT NULL,
    md5             TEXT NOT NULL,
    batch_id        TEXT REFERENCES upload_batches(id),          -- 批量上传时填
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME,                                    -- normal 用户=created+24h；vip/admin=NULL
    UNIQUE (owner_user_id, md5)                                  -- 同用户内 MD5 去重
);

CREATE INDEX idx_files_owner ON files (owner_user_id);
CREATE INDEX idx_files_expires ON files (expires_at);
CREATE INDEX idx_files_batch ON files (batch_id);
```

**file_type 路由**：
- `pdf` → 现有 paddleocr / pdfplumber 提取链路
- `bibliography` → `parsers.py`，可触发 filter
- `markdown` → 直接进入 `deep_read_pipeline.py`（跳过提取）
- `docx` → 现有 docx 处理
- `txt` → 题录或自由文本（按内容嗅探）

**存储路径规则**：`_uploads/{owner_user_id}/{file_id}.{ext}`  
**注意**：`UNIQUE(owner_user_id, md5)` 是软去重，重复上传时返回已有 file_id 而非报错。

### 3.5 `upload_batches` — 批量上传（文件夹上传场景）

```sql
CREATE TABLE upload_batches (
    id              TEXT PRIMARY KEY,                            -- UUID
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    source_type     TEXT NOT NULL CHECK (source_type IN
                        ('single', 'folder', 'multi_select')),
    total_files     INTEGER NOT NULL DEFAULT 0,
    succeeded       INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',             -- pending/uploading/done/failed
    note            TEXT,                                        -- 用户备注（如"2026春季实证一组"）
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME
);

CREATE INDEX idx_upload_batches_owner ON upload_batches (owner_user_id);
```

**目的**：把"一次文件夹拖拽上传 N 个 PDF + 1 个题录"作为一个语义单元，便于：  
- 前端展示"批次进度"  
- 批次内自动联动（题录 → 解析 → 自动匹配 PDF 给 bib_entries）  
- 批量精读时按 batch 调度  
首版可只建表不实现，等单文件流跑通后再开放。

### 3.6 `bib_entries` ⭐ — 文献档案（枢纽表）

```sql
CREATE TABLE bib_entries (
    id              TEXT PRIMARY KEY,                            -- UUID
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),

    -- 文献元数据
    title           TEXT NOT NULL,
    authors_json    TEXT NOT NULL DEFAULT '[]',                  -- ["张三", "李四"]
    year            INTEGER,
    doi             TEXT,
    journal         TEXT,
    abstract        TEXT,
    keywords_json   TEXT NOT NULL DEFAULT '[]',
    venue_type      TEXT,                                        -- journal/conference/book/preprint
    citation_count  INTEGER,                                     -- 预留，可后期填

    -- 来源
    source_db       TEXT NOT NULL CHECK (source_db IN
                        ('wos', 'cnki', 'scopus', 'manual',
                         'pdf_extracted', 'md_extracted', 'other')),
    source_filter_job_id TEXT REFERENCES jobs(id),               -- 第一次进入时的筛选 job（可空）

    -- 关联文件（用户为这篇文献提供的可读文件，PDF 或 MD）
    source_file_id  TEXT REFERENCES files(id),                   -- 重命名自原 pdf_file_id

    -- 用户标记
    user_tags_json  TEXT NOT NULL DEFAULT '[]',                  -- 标签数组
    user_note       TEXT,                                        -- 自由笔记
    is_pinned       INTEGER NOT NULL DEFAULT 0,                  -- 收藏置顶

    -- 状态机
    reading_status  TEXT NOT NULL DEFAULT 'none' CHECK (reading_status IN
                        ('none', 'has_pdf', 'reading', 'read')),
    metadata_completeness TEXT NOT NULL DEFAULT 'partial'        -- 给前端用：哪些字段缺
                        CHECK (metadata_completeness IN ('full', 'partial', 'minimal')),

    -- 去重
    dedup_key       TEXT NOT NULL,                               -- normalize(doi) 或 normalize(first_author+year+title)

    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME,                                    -- 跟随 owner

    UNIQUE (owner_user_id, dedup_key)
);

CREATE INDEX idx_bib_owner ON bib_entries (owner_user_id);
CREATE INDEX idx_bib_status ON bib_entries (reading_status);
CREATE INDEX idx_bib_doi ON bib_entries (doi);
CREATE INDEX idx_bib_expires ON bib_entries (expires_at);
```

**`dedup_key` 计算规则**：

```python
def compute_dedup_key(doi: str | None, title: str, authors: list[str], year: int | None) -> str:
    if doi:
        return "doi:" + doi.strip().lower().replace("https://doi.org/", "")
    first_author = (authors[0] if authors else "unknown").lower()
    title_norm = re.sub(r'[^\w]+', '', title.lower())[:60]
    return f"sig:{first_author}:{year or 0}:{title_norm}"
```

**`reading_status` 状态机**：

```
       上传题录                上传PDF/MD             开始精读           完成精读
[none] ─────────▶ [none] ──────────▶ [has_pdf] ──────▶ [reading] ──────▶ [read]
                                                          │
                                                          ▼
                                                      （失败回 has_pdf）
```

**`metadata_completeness`**：用于前端"PDF 提取后提示用户补全"流程。
- `full`: title/authors/year/doi/journal/abstract 全有
- `partial`: 至少 title + authors
- `minimal`: 只有 title

PDF 提取后若为 `partial` 或 `minimal`，前端弹出"请补充元数据"对话框。

### 3.7 `bib_filter_links` — 文献 ↔ 筛选任务（多对多）

```sql
CREATE TABLE bib_filter_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bib_entry_id    TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    filter_job_id   TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    passed          INTEGER NOT NULL,                            -- 1=通过筛选, 0=未通过
    score           REAL,                                        -- LLM 给的相关性分（如有）
    reason          TEXT,                                        -- LLM 给的理由
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bib_entry_id, filter_job_id)
);

CREATE INDEX idx_bfl_bib ON bib_filter_links (bib_entry_id);
CREATE INDEX idx_bfl_filter ON bib_filter_links (filter_job_id);
```

**用途**：  
- "这篇文献被哪几次筛选打过分？"→ 跨任务追踪核心  
- "这次筛选输出了哪些文献？"→ 重建筛选 Excel  

### 3.8 `jobs` — 任务记录

```sql
CREATE TABLE jobs (
    id              TEXT PRIMARY KEY,                            -- UUID（复用现有 task_id）
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    job_type        TEXT NOT NULL CHECK (job_type IN
                        ('filter',
                         'reading_long',
                         'reading_quant',
                         'reading_qual',
                         'compare',
                         'synthesis')),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                        ('pending', 'running', 'success', 'failed', 'canceled')),

    -- 输入：filter 用题录文件，其它通过 job_bib_entries 指向文献
    input_file_id   TEXT REFERENCES files(id),                   -- filter 专用

    params_json     TEXT NOT NULL DEFAULT '{}',                  -- prompt 名、维度选择、模型参数
    progress        INTEGER NOT NULL DEFAULT 0,                  -- 0-100
    current_stage   TEXT,                                        -- 给 WebSocket 用
    error_msg       TEXT,

    batch_id        TEXT,                                        -- 批量精读用，预留
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    started_at      DATETIME,
    finished_at     DATETIME,
    expires_at      DATETIME
);

CREATE INDEX idx_jobs_owner ON jobs (owner_user_id);
CREATE INDEX idx_jobs_status ON jobs (status);
CREATE INDEX idx_jobs_type ON jobs (job_type);
CREATE INDEX idx_jobs_expires ON jobs (expires_at);
```

### 3.9 `job_bib_entries` — 任务 ↔ 文献（多对多）

```sql
CREATE TABLE job_bib_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    bib_entry_id    TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN
                        ('target',          -- reading_* 的精读对象
                         'compare_member',  -- compare 的对比成员
                         'synthesis_member' -- synthesis 的综述成员
                        )),
    sort_order      INTEGER NOT NULL DEFAULT 0,                  -- 在多成员任务中的顺序
    UNIQUE (job_id, bib_entry_id, role)
);

CREATE INDEX idx_jbe_job ON job_bib_entries (job_id);
CREATE INDEX idx_jbe_bib ON job_bib_entries (bib_entry_id);
```

**约束**：
- `reading_long/quant/qual` 任务必须**仅有一个** `role='target'`
- `compare` 任务有 ≥2 个 `role='compare_member'`
- `synthesis` 任务有 ≥1 个 `role='synthesis_member'`

### 3.10 `artifacts` — 任务产物

```sql
CREATE TABLE artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),       -- 冗余，加速查询
    artifact_type   TEXT NOT NULL CHECK (artifact_type IN
                        ('reading_step',     -- 精读单步 MD
                         'reading_final',    -- Final Report
                         'reading_extract',  -- 提取后的中间 MD（PaddleOCR 输出）
                         'filter_excel',     -- 筛选 Excel
                         'compare_excel',    -- 对比 Excel
                         'compare_md',       -- 对比 MD（如有）
                         'synthesis_md'      -- 综述 MD
                        )),
    filename        TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    size_bytes      INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0,                  -- 多 step 时排序
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME
);

CREATE INDEX idx_artifacts_job ON artifacts (job_id);
CREATE INDEX idx_artifacts_owner ON artifacts (owner_user_id);
CREATE INDEX idx_artifacts_expires ON artifacts (expires_at);
```

**存储路径规则**：`deep_reading_results/{owner_user_id}/{job_id}/{filename}`

## 4. 级联删除规则

| 触发 | 行为 |
|---|---|
| 删除 `users` | 级联删除该用户的 settings/files/bib_entries/jobs/artifacts/upload_batches/invite_codes（DB ON DELETE CASCADE） + 物理删除 `_uploads/{user_id}/` 和 `deep_reading_results/{user_id}/` |
| 删除 `bib_entries` | DB 级联删 bib_filter_links、job_bib_entries（**只删关联**）；通过应用层逻辑清理仅由本档案独占的 jobs/artifacts |
| 删除 `files` | 应用层处理：清空所有引用该 file 的 `bib_entries.source_file_id`；若 file 是 filter job 的 input，禁止删除（除非任务已完成） |
| 删除 `jobs` | DB 级联删 job_bib_entries、artifacts；不动 bib_entries 本身 |

**应用层级联清理 bib_entries 时的逻辑**：
```python
# 删除 bib_entry B5 时：
# 1. 找出所有 role='target' 且唯一指向 B5 的 reading job → 这些是 B5 独占的，删
# 2. 找出 compare/synthesis job 中包含 B5 的 → 把 B5 移出成员，job 本身保留
# 3. B5 关联的 source_file（PDF）→ 询问用户是否一并删除（前端弹窗）
```

## 5. 24 小时清理任务（普通用户）

**实现位置**：`backend/cleanup.py`，APScheduler 注册 `interval=1h`。

**清理逻辑**：

```python
def cleanup_expired() -> None:
    now = datetime.utcnow()
    # 1. 清理过期 artifacts（物理 + 数据库）
    # 2. 清理过期 jobs
    # 3. 清理过期 bib_entries（级联清理空依赖）
    # 4. 清理过期 files（物理 + 数据库）
    # 5. 清理过期 upload_batches
    # 6. 清理空目录 _uploads/{uid}/、deep_reading_results/{uid}/
```

**`expires_at` 计算**（在创建/更新时设置）：

| 角色 | files | bib_entries | jobs | artifacts |
|---|---|---|---|---|
| normal | created+24h | created+24h | created+24h | created+24h |
| vip | NULL | NULL | NULL | NULL |
| admin | NULL | NULL | NULL | NULL |

**API Key 不入清理范围**：DeepSeek API Key 仅存储于用户浏览器 `localStorage`，服务端不持有，故 24h 任务不涉及 key。

**用户角色变更**（normal → vip 或反之）时，需要批量更新 `expires_at`。在 `auth.py` 升降级接口中处理。

## 6. 关键查询示例

```sql
-- 用户 U1 的所有文献（带阅读状态）
SELECT * FROM bib_entries
WHERE owner_user_id = 1
ORDER BY is_pinned DESC, updated_at DESC;

-- 文献 B5 的完整事件链
SELECT j.id, j.job_type, j.status, j.created_at, jbe.role
FROM jobs j
JOIN job_bib_entries jbe ON j.id = jbe.job_id
WHERE jbe.bib_entry_id = 'B5'
ORDER BY j.created_at;

-- 文献 B5 的所有产物文件
SELECT a.*
FROM artifacts a
JOIN job_bib_entries jbe ON a.job_id = jbe.job_id
WHERE jbe.bib_entry_id = 'B5';

-- 第 J1 次筛选导出的所有文献（含通过状态和打分）
SELECT b.*, l.passed, l.score, l.reason
FROM bib_entries b
JOIN bib_filter_links l ON b.id = l.bib_entry_id
WHERE l.filter_job_id = 'J1';

-- 这篇文献被哪几次筛选打过分（跨任务追踪 ⭐）
SELECT j.id, j.created_at, l.passed, l.score
FROM bib_filter_links l
JOIN jobs j ON l.filter_job_id = j.id
WHERE l.bib_entry_id = 'B5'
ORDER BY j.created_at;

-- 用户进度仪表板
SELECT reading_status, COUNT(*) as n
FROM bib_entries
WHERE owner_user_id = 1
GROUP BY reading_status;

-- 给 compare/synthesis 任务找输入：B5/B12/B33 的最新 reading_final
SELECT a.*
FROM artifacts a
JOIN jobs j ON a.job_id = j.id
JOIN job_bib_entries jbe ON j.id = jbe.job_id
WHERE jbe.bib_entry_id IN ('B5', 'B12', 'B33')
  AND jbe.role = 'target'
  AND a.artifact_type = 'reading_final'
  AND j.status = 'success'
ORDER BY a.created_at DESC;
```

## 7. SQLAlchemy 2.0 模型骨架（参考）

```python
# backend/db/models.py
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    vip_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    __table_args__ = (CheckConstraint("role IN ('admin','vip','normal')"),)


class BibEntry(Base):
    __tablename__ = "bib_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    authors_json: Mapped[str] = mapped_column(String, default="[]")
    year: Mapped[Optional[int]] = mapped_column(Integer)
    doi: Mapped[Optional[str]] = mapped_column(String)
    journal: Mapped[Optional[str]] = mapped_column(String)
    abstract: Mapped[Optional[str]] = mapped_column(String)
    source_db: Mapped[str] = mapped_column(String)
    source_file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("files.id"))
    reading_status: Mapped[str] = mapped_column(String, default="none")
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    source_file = relationship("File", foreign_keys=[source_file_id])

    __table_args__ = (
        UniqueConstraint("owner_user_id", "dedup_key", name="uq_bib_dedup"),
    )

# ... 其它模型省略，模式相同
```

## 8. 迁移管理

### 8.1 Alembic 初始化

```bash
cd backend
alembic init -t async migrations
# 配置 alembic.ini → sqlalchemy.url
# 编辑 migrations/env.py → target_metadata = Base.metadata
```

### 8.2 迁移产出

```
backend/migrations/versions/
├── 001_initial_schema.py        # 创建全部表
├── 002_add_users_token_version.py  # P1: users.token_version，用于严格 logout
└── (后续新增字段时追加)
```

> 说明：`admin` 账号继续通过 `backend/scripts/seed_admin.py` 初始化，不放入 Alembic 迁移。

### 8.3 历史数据迁移脚本

`backend/scripts/migrate_legacy_data.py`：
- 扫描 `_uploads/`、`deep_reading_results/` 现有文件
- 全部归到 `admin` 名下（owner_user_id=1）
- 物理移动到 `_uploads/1/`、`deep_reading_results/1/`
- 在 DB 中建立对应 `files` / `jobs` / `artifacts` 记录（尽力而为，元数据不全的标记 `metadata_completeness='minimal'`）

## 9. 未来扩展点（已在 schema 中预留）

| 需求 | 预留方式 |
|---|---|
| MD 文档作为精读输入 | `files.file_type='markdown'` + `bib_entries.source_db='md_extracted'` |
| 文件夹批量上传 | `upload_batches` 表 + `files.batch_id` |
| 批量精读 | `jobs.batch_id` |
| 文献标签/笔记 | `bib_entries.user_tags_json`, `user_note`, `is_pinned` |
| 引文计数/h-index | `bib_entries.citation_count` |
| VIP 试用期 | `users.vip_expires_at` |
| 团队/共享空间 | 不在本期，需要新增 `workspaces` 中间层（暂不规划） |

## 10. 风险与注意事项

1. **SQLite 并发**：开启 WAL 模式（`PRAGMA journal_mode=WAL`），写并发足够支撑当前规模；用 `aiosqlite` 驱动。
2. **物理文件与 DB 一致性**：所有"文件 + DB 记录"操作走 try/finally，DB 失败时回滚物理写入。
3. **API Key 不入库**：DeepSeek API Key 完全在前端 `localStorage` 由用户自管，服务端不存、不清理、不审计。优点：泄漏面缩小；缺点：用户清浏览器缓存就要重输。
4. **dedup_key 冲突**：理论上仍可能误合并不同文献。前端"我的文献"页提供"取消合并 / 拆分"功能（v1.1 再做）。
5. **24h 清理误删**：清理任务需写日志到 `db/cleanup.log`，保留 7 天，便于事故复盘。
