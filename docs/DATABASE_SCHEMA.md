# 数据库设计文档

> **版本**: v1.7
> **日期**: 2026-05-22
> **关联文档**: [MULTI_USER_PLAN.md](./MULTI_USER_PLAN.md)、[REFERENCE_CITATION_TAB_PLAN.md](./REFERENCE_CITATION_TAB_PLAN.md)、[CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md](./CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md)、[CUSTOM_DIMENSION_PLAN.md](./CUSTOM_DIMENSION_PLAN.md)、[DIMENSION_TEMPLATE_PLAN.md](./DIMENSION_TEMPLATE_PLAN.md)、[TRANSLATION_INTEGRATION_PLAN.md](./TRANSLATION_INTEGRATION_PLAN.md)

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
   ┌───────────────────────┼──────────────────────────────────────────────┐
   │                       │                                              │
   ▼                       ▼                                              ▼
┌────────┐         ┌──────────────┐           ┌──────────┐          ┌────────────────┐
│ files  │◀──pdf───│ bib_entries  │──┐        │   jobs   │          │ invite_codes   │
│        │         │  ⭐ 枢纽     │  │ N:M    │          │          └────────────────┘
└───┬────┘         └──────┬───────┘  ▼        └────┬─────┘
    │ N:1                 │        ┌──────────┐    │ produces
    │                     │        │job_bib_  │    ▼
    ▼                     │        │ entries  │  ┌──────────┐
upload_batches            │        └──────────┘  │artifacts │
                          │                      └──────────┘
                          │
                          ▼
                  ┌──────────────────┐
                  │  bib_references  │
                  └────────┬─────────┘
                           │ has many citations
                           ▼
                ┌─────────────────────────┐
                │ bib_reference_citations │
                └─────────────────────────┘

┌────────────────┐
│ user_settings  │
└────────────────┘

┌────────────────────┐        ┌──────────────────┐
│ dimension_sets     │        │dimension_templates│
│  (用户维度集合)    │        │ (系统预设模板)    │
└───────┬────────────┘        └───────┬──────────┘
        │ 1:N                         │ 1:N
        ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│ dimension_items  │          │ template_items   │
│  (维度条目)      │          │ (模板维度条目)   │
└──────────────────┘          └──────────────────┘
```

枢纽：`bib_entries`（一篇文献的"档案"，含 v1.3 新增的 volume/issue/pages 字段）  
物理：`files`（PDF / 题录 / MD / DOCX）  
事件：`jobs`（filter / reading_* / compare / synthesis / reference_trace 等）  
产物：`artifacts`（任务输出文件）  
引用：`bib_references` / `bib_reference_citations`（参考文献条目与正文引用命中）  
维度：`dimension_sets` / `dimension_items`（v1.4 用户自定义长文本精读维度集合）  
模板：`dimension_templates` / `template_items`（v1.5 系统预设维度模板，用于快速创建维度集合）

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
    preferences_json     TEXT,           -- 预留：UI 偏好等轻量设置；提示词已独立到 prompt_templates
    updated_at           DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

**v1 暂未启用**，建表占位。  
**API Key 不入库**：DeepSeek API Key 继续保留在前端 `localStorage`，由用户自行管理。普通用户 24h 清理只清服务端文件与档案，**不清前端 key**。前端登录页对普通用户提示"上传文件、文献档案、精读结果将在 24h 后清空，但您的 API Key 保存在浏览器本地，不会被清理；请自行备份产出文件"。

### 3.4 `user_feedback` / `feedback_events` / `admin_audit_logs` — 用户反馈与后台审计

> migration `021_add_feedback_admin_tables.py` 新增。反馈表是管理员查看和处理产品反馈的运营数据，不进入用户 `.dra` 导出/导入；normal 用户 24h 工作区清理也不自动删除反馈。若未来需要隐私删除，单独做匿名化/删除流程。

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
    related_artifact_id INTEGER REFERENCES artifacts(id),
    assigned_admin_id   INTEGER REFERENCES users(id),
    public_reply        TEXT,
    internal_note       TEXT,
    resolved_at         DATETIME,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_user_feedback_owner ON user_feedback(owner_user_id);
CREATE INDEX idx_user_feedback_status ON user_feedback(status);
CREATE INDEX idx_user_feedback_priority ON user_feedback(priority);
CREATE INDEX idx_user_feedback_created ON user_feedback(created_at);
CREATE INDEX idx_user_feedback_job ON user_feedback(related_job_id);
```

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

### 3.5 `prompt_templates` — 提示词模板（系统默认 + 用户覆盖）

> 目的：把固定提示词槽位从文件系统迁入数据库，支持“系统默认提示词 + 用户个人覆盖”，并统一所有分析链路的读取来源。

```sql
CREATE TABLE prompt_templates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    scope               TEXT NOT NULL CHECK (scope IN ('system', 'user')),
    prompt_type         TEXT NOT NULL CHECK (prompt_type IN ('quant', 'qual', 'long', 'filter', 'compare', 'synthesis', 'ai_template', 'translation', 'library_chat', 'card_note')),
    prompt_key          TEXT NOT NULL,
    title               TEXT NOT NULL,
    content             TEXT NOT NULL,
    updated_by_user_id  INTEGER REFERENCES users(id),
    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at          DATETIME NOT NULL DEFAULT (datetime('now')),

    UNIQUE (owner_user_id, prompt_type, prompt_key)
);

CREATE INDEX idx_prompt_templates_scope ON prompt_templates (scope);
CREATE INDEX idx_prompt_templates_owner ON prompt_templates (owner_user_id);
CREATE INDEX idx_prompt_templates_type_key ON prompt_templates (prompt_type, prompt_key);
```

**约定**：

- `owner_user_id IS NULL` + `scope='system'`：系统默认提示词
- `owner_user_id=<当前用户>` + `scope='user'`：该用户自己的提示词覆盖
- 当前阶段仍只允许固定槽位，不开放任意自定义 key
- 运行时优先级：`用户覆盖 → 系统默认 → prompts/ 文件兜底 → 代码内置兜底`
- 首批系统默认值从现有 `prompts/` 目录幂等导入数据库
- `library_chat` 于 migration `016` 加入，当前包含查询解析、报告生成、标签目标选择和逐篇点评保存四个提示词槽位
- `card_note` 于 migration `020` 加入，当前包含 Markdown 选段生成原子阅读卡的提示词槽位
- 系统默认提示词若尚未被管理员编辑，会在默认种子同步时跟随托管提示词文件更新

### 3.5 `files` — 物理文件

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
    abstract_cn     TEXT,                                        -- v1.5 摘要中文翻译
    keywords_json   TEXT NOT NULL DEFAULT '[]',
    venue_type      TEXT,                                        -- journal/conference/book/preprint
    citation_count  INTEGER,                                     -- 预留，可后期填
    volume          TEXT,                                        -- 卷号（CNKI Volume-卷 / WoS VL）
    issue           TEXT,                                        -- 期号（CNKI Period-期 / WoS IS）
    pages           TEXT,                                        -- 页码范围（CNKI PageCount-页码 / WoS BP-EP）
    language        TEXT CHECK (language IS NULL OR language IN
                        ('en', 'zh', 'other')),                  -- 文献语言，供翻译入口筛选

    -- 来源
    source_db       TEXT NOT NULL CHECK (source_db IN
                        ('wos', 'cnki', 'scopus', 'manual',
                         'pdf_extracted', 'md_extracted', 'other')),
    source_filter_job_id TEXT REFERENCES jobs(id),               -- 第一次进入时的筛选 job（可空）

    -- 关联文件（用户为这篇文献提供的可读文件，PDF 或 MD）
    source_file_id  TEXT REFERENCES files(id),                   -- 重命名自原 pdf_file_id
    markdown_source_file_id TEXT REFERENCES files(id),            -- Markdown 原文阅读/制卡专用绑定

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
CREATE INDEX idx_bib_markdown_source ON bib_entries (markdown_source_file_id);
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

> **v1.4 新增字段**：`language` 于 2026-05-21 增加，用于文献库语言标注和全文翻译英文入口筛选；历史文献可保持未标注。
>
> **v1.3 新增字段**：`volume`、`issue`、`pages` 于 2026-05-07 规划，详见 [CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md](./CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md)。这三个字段来源：
> - CNKI 导出：`Volume-卷`、`Period-期`、`PageCount-页码`
> - WoS 导出：`VL`、`IS`、`BP`+`EP`
> - 在线匹配：Crossref/OpenAlex 返回的 volume/issue/pages
> - `metadata_completeness` 计算**不含**这三个字段（它们是补充信息，不影响 full/partial/minimal 判定）

PDF 提取后若为 `partial` 或 `minimal`，前端弹出"请补充元数据"对话框。

**参考文献梳理的轻量聚合字段（规划）**：

- `reference_count`
- `outgoing_citation_count`
- `incoming_citation_count`
- `reference_trace_status`

这些字段首期不保存明细，只作为未来在 `bib_entries` 上做列表聚合和状态展示的轻量补充。

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

### 3.8 `bib_references` — 源文献的参考文献条目

> 目的：保存“某篇源文献的参考文献目录条目”，作为参考文献梳理功能的核心实体。它不等价于正式文献库记录；只有匹配成功或用户确认导入后，才会映射到 `bib_entries`。

```sql
CREATE TABLE bib_references (
    id                  TEXT PRIMARY KEY,                         -- UUID
    owner_user_id       INTEGER NOT NULL REFERENCES users(id),
    source_bib_entry_id TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    source_job_id       TEXT REFERENCES jobs(id) ON DELETE CASCADE,

    reference_order     INTEGER NOT NULL DEFAULT 0,
    raw_text            TEXT NOT NULL,                           -- 参考文献原文
    authors_json        TEXT NOT NULL DEFAULT '[]',
    year                INTEGER,
    title               TEXT,
    journal             TEXT,
    volume              TEXT,
    issue               TEXT,
    pages               TEXT,
    doi                 TEXT,
    language            TEXT,
    dedup_key           TEXT,

    matched_bib_entry_id TEXT REFERENCES bib_entries(id),        -- 命中已有文献库记录时填写
    match_method        TEXT,                                    -- doi_exact/title_author_year/manual/none
    match_score         REAL,
    citation_count      INTEGER NOT NULL DEFAULT 0,

    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_bib_refs_owner ON bib_references (owner_user_id);
CREATE INDEX idx_bib_refs_source_bib ON bib_references (source_bib_entry_id);
CREATE INDEX idx_bib_refs_source_job ON bib_references (source_job_id);
CREATE INDEX idx_bib_refs_matched_bib ON bib_references (matched_bib_entry_id);
CREATE INDEX idx_bib_refs_doi ON bib_references (doi);
CREATE INDEX idx_bib_refs_dedup ON bib_references (dedup_key);
```

**字段语义**：

- `source_bib_entry_id`
  - 当前这条参考文献属于哪篇源文献
- `matched_bib_entry_id`
  - 这条参考文献是否已经对应到文献库中的某篇文献
- `citation_count`
  - 在正文中命中的次数

**设计说明**：

- 任何解析出的参考文献都先进入 `bib_references`
- 高置信度命中已有 `bib_entries` 时，填充 `matched_bib_entry_id`
- 未命中时仍保留条目本身，供前端“重新匹配 / 导入文献库”
- 该表不单独设置 `expires_at`，普通用户场景下跟随 `source_bib_entry_id` / `source_job_id` 的级联删除

### 3.9 `bib_reference_citations` — 正文引用命中

> 目的：保存“某条参考文献在正文中的具体命中记录”，包括引用文本、上下文摘录、位置与置信度。这是首期必须入库的明细层。

```sql
CREATE TABLE bib_reference_citations (
    id                  TEXT PRIMARY KEY,                         -- UUID
    owner_user_id       INTEGER NOT NULL REFERENCES users(id),
    source_bib_entry_id TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    bib_reference_id    TEXT NOT NULL REFERENCES bib_references(id) ON DELETE CASCADE,
    source_job_id       TEXT REFERENCES jobs(id) ON DELETE CASCADE,

    citation_index      INTEGER NOT NULL DEFAULT 0,
    page_label          TEXT,
    section_label       TEXT,
    paragraph_label     TEXT,
    quote_text          TEXT NOT NULL,                           -- 命中的原始引用文本
    quote_text_zh       TEXT,                                    -- 可选：双语展示预留
    excerpt             TEXT,                                    -- 上下文摘录
    char_start          INTEGER,
    char_end            INTEGER,
    match_method        TEXT,                                    -- author_year/numeric/title_keyword/llm_verify
    confidence          REAL,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_brc_owner ON bib_reference_citations (owner_user_id);
CREATE INDEX idx_brc_source_bib ON bib_reference_citations (source_bib_entry_id);
CREATE INDEX idx_brc_reference ON bib_reference_citations (bib_reference_id);
CREATE INDEX idx_brc_source_job ON bib_reference_citations (source_job_id);
```

**关键约定**：

- `quote_text`、`excerpt` 是首期必须保存的字段
- `quote_text_zh` 为可选扩展，不要求首期一定填充
- 位置字段允许部分缺失，避免因为页码/段号识别不稳定而阻塞入库
- `bib_reference_citations` 的生命周期跟随所属 `bib_reference_id`、`source_bib_entry_id` 和 `source_job_id`

### 3.10 `jobs` — 任务记录

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
                         'synthesis',
                         'reference_trace',   -- 参考文献梳理全链路
                         'reference_extract', -- 仅抽取参考文献目录
                         'citation_trace',    -- 仅重跑正文引用核验
                          'translation'        -- 全文翻译（中文重述）
                          'translate_abstracts' -- 批量翻译摘要
                         )),
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

**参考文献梳理任务约定**：

- `reference_trace`
  - 端到端执行“参考文献目录提取 + 条目匹配 + 正文引用核验 + 产物生成”
- `reference_extract`
  - 仅抽取参考文献目录并结构化入库
- `citation_trace`
  - 针对已有参考文献条目，仅重跑正文引用候选召回与 LLM 核验

### 3.11 `job_bib_entries` — 任务 ↔ 文献（多对多）

```sql
CREATE TABLE job_bib_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    bib_entry_id    TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN
                        ('target',          -- reading_* 的精读对象
                         'compare_member',  -- compare 的对比成员
                         'synthesis_member',-- synthesis 的综述成员
                         'reference_source' -- reference_trace / citation_trace 的源文献
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
- `reference_trace/reference_extract/citation_trace` 任务必须仅有一个 `role='reference_source'`

### 3.12 `reading_items` — 精读结构化结果

> 目的：把三类精读结果按“模式 / 维度(步骤) / 子问题”拆成结构化记录，供 compare / synthesis / library 直接查询，避免前端继续下载 Markdown 再做字符串解析。

```sql
CREATE TABLE reading_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    bib_entry_id    TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

    mode            TEXT NOT NULL CHECK (mode IN ('long', 'quant', 'qual')),
    section_type    TEXT NOT NULL CHECK (section_type IN ('dimension', 'step', 'subquestion', 'custom')),
    parent_key      TEXT,                                        -- 如 quant.step1 / qual.step2
    item_key        TEXT NOT NULL,                               -- 如 long.research_question / quant.step1.q1
    item_label      TEXT NOT NULL,                               -- 显示名，如“研究问题”“1.研究主题与核心结论”
    sort_order      INTEGER NOT NULL DEFAULT 0,
    content         TEXT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),

    UNIQUE (job_id, item_key)
);

CREATE INDEX idx_reading_items_owner ON reading_items (owner_user_id);
CREATE INDEX idx_reading_items_bib ON reading_items (bib_entry_id);
CREATE INDEX idx_reading_items_job ON reading_items (job_id);
CREATE INDEX idx_reading_items_mode ON reading_items (mode);
CREATE INDEX idx_reading_items_parent ON reading_items (parent_key);
```

**入库约定**：

- 长文本精读：
  - `mode='long'`
  - 12 个分析维度写成 `section_type='dimension'`
  - 自定义问题写成 `section_type='custom'`
  - `item_key` 使用稳定 key，例如 `long.research_question`、`long.theory_framework`、`long.custom_question`
- 七步精读：
  - `mode='quant'`
  - 每个步骤先写一条 `section_type='step'`
  - 步骤下按编号子问题继续写 `section_type='subquestion'`
  - 例如 `quant.step1`、`quant.step1.q1`
- 四步精读：
  - `mode='qual'`
  - 同样保留“步骤 -> 子问题”两层
  - 例如 `qual.step1`、`qual.step1.q1`

**设计说明**：

- 不把几十个精读结果字段直接塞进 `bib_entries`
- `reading_items` 保留 job 级历史，支持同一篇文献多次精读
- `artifacts` 继续保存 Markdown 产物，作为下载与人工阅读版本

### 3.13 `artifacts` — 任务产物

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
                         'synthesis_md',     -- 综述 MD
                         'references_excel', -- 参考文献目录 Excel
                         'references_with_citations_excel', -- 含正文引用命中的 Excel
                         'citation_trace_md',-- 引用梳理 Markdown 报告
                         'references_json',  -- 可选：结构化 JSON 产物
                         'translation_md',       -- 全文翻译中文重述 MD
                         'translation_glossary'  -- 全文翻译术语词典 MD
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

**参考文献梳理产物约定**：

- `references_excel`
  - 仅包含参考文献目录及匹配结果
- `references_with_citations_excel`
  - 包含参考文献目录、文献库匹配、正文命中次数与引用摘要
- `citation_trace_md`
  - 用于人工审阅和历史留档的 Markdown 汇总报告
- `references_json`
  - 供调试、审计和潜在前端二次渲染使用

### 3.14 `card_notes` — Markdown 原文/译文卡片笔记（v1.8 新增）

> 目的：保存用户在 Markdown 阅读器中基于选段生成的 AI 原子阅读卡，并同步维护 Obsidian 友好的 Markdown 文件镜像。

```sql
CREATE TABLE card_notes (
    id              TEXT PRIMARY KEY,                            -- UUID
    owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_bib_entry_id TEXT NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    source_version  TEXT NOT NULL CHECK (source_version IN ('original', 'translated')),
    source_markdown_file_id TEXT REFERENCES files(id),           -- 原文卡片来源
    source_translation_artifact_id INTEGER REFERENCES artifacts(id), -- 译文卡片来源
    title           TEXT NOT NULL,
    summary         TEXT,
    tags_json       TEXT NOT NULL DEFAULT '[]',
    selected_text   TEXT NOT NULL,
    context_before  TEXT,
    context_after   TEXT,
    user_prompt     TEXT,
    body_markdown   TEXT NOT NULL,
    storage_path    TEXT,                                        -- cards/card-*.md 镜像
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME
);

CREATE INDEX idx_card_notes_owner ON card_notes (owner_user_id);
CREATE INDEX idx_card_notes_bib ON card_notes (source_bib_entry_id);
CREATE INDEX idx_card_notes_created ON card_notes (created_at);
CREATE INDEX idx_card_notes_expires ON card_notes (expires_at);
CREATE INDEX idx_card_notes_translation ON card_notes (source_translation_artifact_id);
```

**约定**：

- `source_version='original'` 时记录 `source_markdown_file_id`。
- `source_version='translated'` 时记录对应 `translation_md` 的 `source_translation_artifact_id`。
- `.dra` 导出/导入包含该表和 Markdown 镜像，当前 `CURRENT_SCHEMA_VERSION = "021"`。

### 3.15 `dimension_sets` — 用户维度集合（v1.4 新增）

> 目的：支持用户自定义长文本精读的分析维度集合。每个用户可创建多个命名集合（如"计量论文专用"、"理论论文专用"），系统自动为每个用户创建一个不可删除的默认集合。

```sql
CREATE TABLE dimension_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,              -- 集合名称，如"计量论文专用"
    description     TEXT,                       -- 可选描述
    is_default      INTEGER NOT NULL DEFAULT 0, -- 是否为用户当前激活的默认集合（每用户至多 1 个）
    is_system       INTEGER NOT NULL DEFAULT 0, -- 系统内置集合（不可删除、不可改名）
    is_shared       INTEGER NOT NULL DEFAULT 0, -- 是否共享给其他用户（0=私有 1=共享）
    is_available_for_reading INTEGER NOT NULL DEFAULT 1, -- 是否显示在长文本精读集合下拉框
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (owner_user_id, name)               -- 同一用户集合名不重复
);

CREATE INDEX idx_dim_sets_owner ON dimension_sets (owner_user_id);
CREATE INDEX idx_dim_sets_default ON dimension_sets (owner_user_id, is_default);
CREATE INDEX idx_dim_sets_shared ON dimension_sets (is_shared);
```

**字段语义**：

- `is_system=1`：系统内置的默认维度集，不可删除、不可改名，但可通过 `/reset` 端点恢复默认内容
- `is_default=1`：用户当前激活的集合，启动精读时默认使用此集合的维度。每用户至多一个 `is_default=1`
- `is_shared=1`：该集合已共享给其他用户，其他用户可浏览并基于此集合创建自己的副本。共享集合仍由 owner 管理
- `is_available_for_reading=1`：显示在长文本精读页的维度集合下拉框；为 0 时集合保留在模板市场，但不参与当前精读选择
- `name`：用户自定义集合名，系统集默认名为"默认维度集"

**种子数据**：应用启动时自动为每个用户创建系统默认集合，并从 `ANALYSIS_DIMENSIONS` 填充 12+1 个维度条目。

### 3.15 `dimension_items` — 维度条目（v1.4 新增）

> 目的：保存每个维度集合内的具体维度定义，包括名称、描述、提示词和默认问题。系统预置维度和用户自建维度共存。

```sql
CREATE TABLE dimension_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id          INTEGER NOT NULL REFERENCES dimension_sets(id) ON DELETE CASCADE,
    dim_key         TEXT NOT NULL,              -- 维度英文标识
    dim_name        TEXT NOT NULL,              -- 中文显示名，如"研究问题"
    description     TEXT,                       -- 维度描述（tooltip 等）
    prompt_content  TEXT NOT NULL DEFAULT '',    -- 该维度的完整提示词
    default_question TEXT NOT NULL DEFAULT '',   -- 默认分析问题
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_builtin      INTEGER NOT NULL DEFAULT 0, -- 1=系统预置维度 0=用户自建
    group_name      TEXT,                       -- 分组名称（nullable），用于前端按组展示维度
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (set_id, dim_key)                    -- 集合内维度 key 不重复
);

CREATE INDEX idx_dim_items_set ON dimension_items (set_id);
CREATE INDEX idx_dim_items_builtin ON dimension_items (set_id, is_builtin);
```

**dim_key 命名规则**：

- **系统内置维度**：沿用 `ANALYSIS_DIMENSIONS` 的 key（`overview`, `theory`, `methodology` 等）
- **用户自建维度**：使用 `{set_name_prefix}_{uuid_short}` 格式（如 `计量论文_a3f2`），确保：
  - 不与系统内置 key 冲突
  - 可追溯属于哪个集合
  - 在 `ReadingItem.item_key` 中形成 `long.计量论文_a3f2`，与历史数据格式兼容

**`group_name` 字段**：

- 可选分组标签，用于前端将维度按组折叠展示
- 同一集合内的维度可共享相同的 `group_name`，属于同一组的维度连续排列
- 为 NULL 时表示不分组，平铺展示

**与 prompt_templates 的关系**：

- 系统内置维度的提示词覆盖继续走 `prompt_templates` 表（用户覆盖 > 系统默认 > 文件兜底 > 代码兜底）
- 用户自建维度的提示词直接存在 `prompt_content` 字段，不经过 `prompt_templates`
- 详细设计见 [CUSTOM_DIMENSION_PLAN.md](./CUSTOM_DIMENSION_PLAN.md)

### 3.16 `dimension_templates` — 系统预设维度模板（v1.5 新增）

> 目的：保存系统预设的维度模板，供用户快速创建维度集合。模板由管理员维护，用户不能直接修改模板，但可以基于模板创建自己的维度集合副本。

```sql
CREATE TABLE dimension_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,              -- 模板名称，如"计量经济学论文"
    description     TEXT,                       -- 模板描述
    category        TEXT NOT NULL,              -- 分类，如"quantitative"/"qualitative"/"mixed"
    dim_count       INTEGER NOT NULL,           -- 包含的维度数量
    preview_json    TEXT,                       -- 预览用 JSON（维度列表摘要）
    group_config    TEXT,                       -- 分组配置 JSON
    is_featured     INTEGER NOT NULL DEFAULT 1, -- 是否精选模板（前端优先展示）
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_dim_tpl_category ON dimension_templates (category);
CREATE INDEX idx_dim_tpl_featured ON dimension_templates (is_featured);
```

**字段语义**：

- `category`：模板分类标签，用于前端筛选。常见值：`quantitative`（计量/定量）、`qualitative`（定性）、`mixed`（综合）、`theory`（理论）、`case_study`（案例研究）等
- `dim_count`：模板包含的维度数量，冗余字段避免每次 COUNT 查询
- `preview_json`：格式如 `[{"key":"rq","name":"研究问题"},{"key":"theory","name":"理论框架"}]`，用于前端模板卡片预览
- `group_config`：分组配置，格式如 `{"groups":[{"name":"基本信息","keys":["overview","rq"]},{"name":"方法","keys":["method","data"]}]}`，`group_name` 来源
- `is_featured=1`：精选模板，前端模板选择页置顶展示

**种子数据**：系统启动时从代码或 JSON 文件幂等导入预设模板，管理员可通过 API 增删改模板。

### 3.17 `template_items` — 模板维度条目（v1.5 新增）

> 目的：保存每个预设模板包含的具体维度定义，结构与 `dimension_items` 类似，但不绑定用户，属于系统级数据。

```sql
CREATE TABLE template_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     INTEGER NOT NULL REFERENCES dimension_templates(id) ON DELETE CASCADE,
    dim_key         TEXT NOT NULL,              -- 维度英文标识
    dim_name        TEXT NOT NULL,              -- 中文显示名
    description     TEXT,                       -- 维度描述
    prompt_content  TEXT NOT NULL DEFAULT '',    -- 该维度的完整提示词
    default_question TEXT NOT NULL DEFAULT '',   -- 默认分析问题
    sort_order      INTEGER NOT NULL DEFAULT 0,
    group_name      TEXT,                       -- 分组名称（nullable），与 dimension_items.group_name 对应
    is_builtin      INTEGER NOT NULL DEFAULT 1, -- 预设模板条目默认为系统内置
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (template_id, dim_key)               -- 模板内维度 key 不重复
);

CREATE INDEX idx_tpl_items_template ON template_items (template_id);
```

## 4. 级联删除规则

| 触发 | 行为 |
|---|---|
| 删除 `users` | 级联删除该用户的 settings/files/bib_entries/jobs/reading_items/artifacts/upload_batches/invite_codes/bib_references/bib_reference_citations/dimension_sets（DB ON DELETE CASCADE，dimension_sets 级联删除 dimension_items） + 物理删除 `_uploads/{user_id}/` 和 `deep_reading_results/{user_id}/` |
| 删除 `bib_entries` | DB 级联删 bib_filter_links、job_bib_entries、reading_items、以其为 `source_bib_entry_id` 的 `bib_references / bib_reference_citations`（**只删关联/结构化结果**）；通过应用层逻辑清理仅由本档案独占的 jobs/artifacts |
| 删除 `files` | 应用层处理：清空所有引用该 file 的 `bib_entries.source_file_id`；若 file 是 filter job 的 input，禁止删除（除非任务已完成） |
| 删除 `jobs` | DB 级联删 job_bib_entries、reading_items、artifacts，以及以其为 `source_job_id` 的 `bib_references / bib_reference_citations`；不动 bib_entries 本身 |
| 删除 `dimension_templates` | DB 级联删 `template_items`（ON DELETE CASCADE） |

**应用层级联清理 bib_entries 时的逻辑**：
```python
# 删除 bib_entry B5 时：
# 1. 找出所有 role='target' 且唯一指向 B5 的 reading job → 这些是 B5 独占的，删
# 2. 找出 compare/synthesis/reference_* job 中包含 B5 的 → 把 B5 移出成员，job 本身保留
# 3. B5 关联的 source_file（PDF）→ 询问用户是否一并删除（前端弹窗）
# 4. 级联删除以 B5 为 source_bib_entry_id 的 bib_references / bib_reference_citations
```

## 5. 24 小时清理任务（普通用户）

**实现位置**：`backend/cleanup.py`，APScheduler 注册 `interval=1h`。

**清理逻辑**：

```python
def cleanup_expired() -> None:
    now = datetime.utcnow()
    # 1. 清理过期 artifacts（物理 + 数据库）
    # 2. 清理过期 jobs
    # 3. 清理过期 bib_entries（级联清理 bib_references / bib_reference_citations 等依赖）
    # 4. 清理过期 files（物理 + 数据库）
    # 5. 清理过期 upload_batches
    # 6. 清理空目录 _uploads/{uid}/、deep_reading_results/{uid}/
```

**`expires_at` 计算**（在创建/更新时设置）：

| 角色 | files | bib_entries | jobs | reading_items | artifacts |
|---|---|---|---|---|---|
| normal | created+24h | created+24h | created+24h | created+24h | created+24h |
| vip | NULL | NULL | NULL | NULL | NULL |
| admin | NULL | NULL | NULL | NULL | NULL |

**API Key 不入清理范围**：DeepSeek API Key 仅存储于用户浏览器 `localStorage`，服务端不持有，故 24h 任务不涉及 key。

**用户角色变更**（normal → vip 或反之）时，需要批量更新 `expires_at`。在 `auth.py` 升降级接口中处理。

**参考文献梳理明细的保留策略**：

- `bib_references` / `bib_reference_citations` 不单独设置 `expires_at`
- 普通用户数据到期时，依赖 `source_bib_entry_id` 或 `source_job_id` 的级联删除一并清理
- 这样可以避免多处重复维护到期时间，同时保证引用明细不会脱离源文献长期残留

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

-- 源文献 B5 的参考文献条目列表（含命中状态）
SELECT r.reference_order, r.title, r.year, r.doi, r.citation_count, r.matched_bib_entry_id
FROM bib_references r
WHERE r.source_bib_entry_id = 'B5'
ORDER BY r.reference_order;

-- 参考文献 R8 在正文中的全部引用命中
SELECT c.quote_text, c.excerpt, c.page_label, c.section_label, c.confidence
FROM bib_reference_citations c
WHERE c.bib_reference_id = 'R8'
ORDER BY c.citation_index;

-- 用户 U1 当前激活的维度集合及其维度条目（v1.4）
SELECT s.name AS set_name, i.dim_key, i.dim_name, i.is_builtin, i.sort_order
FROM dimension_sets s
JOIN dimension_items i ON s.id = i.set_id
WHERE s.owner_user_id = 1 AND s.is_default = 1
ORDER BY i.sort_order;

-- 用户 U1 的所有维度集合（含维度数量统计）（v1.4）
SELECT s.id, s.name, s.is_default, s.is_system, COUNT(i.id) AS item_count
FROM dimension_sets s
LEFT JOIN dimension_items i ON s.id = i.set_id
WHERE s.owner_user_id = 1
GROUP BY s.id
ORDER BY s.sort_order;

-- 所有精选维度模板（含维度数量验证）（v1.5）
SELECT t.id, t.name, t.category, t.dim_count, COUNT(ti.id) AS actual_count
FROM dimension_templates t
LEFT JOIN template_items ti ON t.id = ti.template_id
WHERE t.is_featured = 1
GROUP BY t.id
ORDER BY t.sort_order;

-- 模板 T1 的完整维度列表（含分组）（v1.5）
SELECT ti.dim_key, ti.dim_name, ti.group_name, ti.sort_order
FROM template_items ti
WHERE ti.template_id = 1
ORDER BY ti.sort_order;
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
    keywords_json: Mapped[str] = mapped_column(String, default="[]")
    venue_type: Mapped[Optional[str]] = mapped_column(String)
    citation_count: Mapped[Optional[int]] = mapped_column(Integer)
    volume: Mapped[Optional[str]] = mapped_column(String)      # v1.3 新增
    issue: Mapped[Optional[str]] = mapped_column(String)       # v1.3 新增
    pages: Mapped[Optional[str]] = mapped_column(String)       # v1.3 新增
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


class DimensionSet(Base):
    __tablename__ = "dimension_sets"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_dim_sets_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_shared: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_available_for_reading: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class DimensionItem(Base):
    __tablename__ = "dimension_items"
    __table_args__ = (
        UniqueConstraint("set_id", "dim_key", name="uq_dim_items_set_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_sets.id", ondelete="CASCADE"), nullable=False
    )
    dim_key: Mapped[str] = mapped_column(String, nullable=False)
    dim_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_question: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    group_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class DimensionTemplate(Base):
    __tablename__ = "dimension_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    dim_count: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    items: Mapped[list["TemplateItem"]] = relationship("TemplateItem", back_populates="template", cascade="all, delete-orphan")


class TemplateItem(Base):
    __tablename__ = "template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "dim_key", name="uq_tpl_items_template_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_templates.id", ondelete="CASCADE"), nullable=False
    )
    dim_key: Mapped[str] = mapped_column(String, nullable=False)
    dim_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_question: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    group_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    template: Mapped["DimensionTemplate"] = relationship("DimensionTemplate", back_populates="items")
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
├── 003_add_reading_items.py     # 精读结构化结果表，供 compare / library 直接查询
├── 004_add_prompt_templates.py  # 提示词模板表（系统默认 + 用户覆盖）
├── 005_add_reference_trace_tables.py  # bib_references / bib_reference_citations + jobs/artifacts 扩展
├── 006_add_bib_entry_volume_issue_pages.py  # bib_entries 新增 volume/issue/pages 字段
├── 007_add_dimension_sets_and_items.py  # dimension_sets + dimension_items（用户自定义维度集合）
├── 008_add_dimension_shared_and_group.py  # dimension_sets 新增 is_shared，dimension_items 新增 group_name
├── 009_add_dimension_templates.py  # dimension_templates + template_items（系统预设维度模板）
├── 010_seed_dimension_templates.py  # 预设模板种子数据导入
├── 011_add_edits_and_annotations.py  # reading_item_edits + annotations
├── 012_add_dimension_set_reading_availability.py  # dimension_sets 新增 is_available_for_reading
├── 014_add_translation_prompt_type.py  # prompt_templates 增加 translation
├── 015_add_bib_entry_language.py  # bib_entries 增加 language
├── 016_add_library_chat_prompt_type.py  # prompt_templates 增加 library_chat
├── 017_add_bib_entry_abstract_cn.py  # bib_entries 新增 abstract_cn（摘要中文翻译）
├── 018_add_translate_abstracts_job_type.py  # jobs CHECK 约束新增 translate_abstracts
├── 019_add_agent_sessions.py  # Agent assistant 会话持久化
├── 020_add_markdown_card_notes.py  # Markdown 原文绑定 + card_notes + card_note 提示词类型
└── 021_add_feedback_admin_tables.py  # 用户反馈、反馈事件、管理员审计日志
```

> 说明：`admin` 账号继续通过 `backend/scripts/seed_admin.py` 初始化，不放入 Alembic 迁移。

### 8.3 历史数据迁移脚本

`backend/scripts/migrate_legacy_data.py`：
- 扫描 `_uploads/`、`deep_reading_results/` 现有文件
- 全部归到 `admin` 名下（owner_user_id=1）
- 物理移动到 `_uploads/1/`、`deep_reading_results/1/`
- 在 DB 中建立对应 `files` / `jobs` / `artifacts` 记录（尽力而为，元数据不全的标记 `metadata_completeness='minimal'`）

`backend/scripts/backfill_reading_items.py`：
- 扫描已有 `reading_long / reading_quant / reading_qual` 任务
- 读取 `artifacts(reading_final)` 对应 Markdown
- 按当前标题规则拆分并回填 `reading_items`
- 支持 `--dry-run`
- 若某个 job 已有 `reading_items`，则直接跳过，保证幂等

## 9. 未来扩展点（已在 schema 中预留）

| 需求 | 预留方式 |
|---|---|
| MD 文档作为精读输入 | `files.file_type='markdown'` + `bib_entries.source_db='md_extracted'` |
| 文件夹批量上传 | `upload_batches` 表 + `files.batch_id` |
| 批量精读 | `jobs.batch_id` |
| 文献标签/笔记 | `bib_entries.user_tags_json`, `user_note`, `is_pinned` |
| 引文计数/h-index | `bib_entries.citation_count` |
| 参考文献梳理与正文引用对齐 | `bib_references` + `bib_reference_citations` + `jobs.job_type/artifacts.artifact_type` 扩展 |
| 全文翻译（中文重述） | `jobs.job_type='translation'` + `artifacts.artifact_type` 新增 `translation_md`/`translation_glossary` + `prompt_templates.prompt_type` 新增 `translation`（v1.6 migration 014） |
| 文献库 AI 查询 | `prompt_templates.prompt_type` 新增 `library_chat`（v1.7 migration 016）；命中集合复用 `bib_entries`、`bib_references`、`reading_items`；标签复用 `bib_entries.user_tags_json`，保存点评复用 `annotations(source_type='library_note')` |
| Markdown 卡片笔记 | `bib_entries.markdown_source_file_id` + `card_notes` + `prompt_templates.prompt_type='card_note'`；导出包包含 cards/papers Markdown |
| 引用网络分析 / 共引分析 | 依赖 `bib_references.source_bib_entry_id -> matched_bib_entry_id` 关系继续向上扩展 |
| VIP 试用期 | `users.vip_expires_at` |
| 团队/共享空间 | 不在本期，需要新增 `workspaces` 中间层（暂不规划） |
| 用户自定义精读维度集合 | `dimension_sets` + `dimension_items`（v1.4 已建表，详见 [CUSTOM_DIMENSION_PLAN.md](./CUSTOM_DIMENSION_PLAN.md)） |
| 系统预设维度模板 | `dimension_templates` + `template_items`（v1.5 已建表，详见 [DIMENSION_TEMPLATE_PLAN.md](./DIMENSION_TEMPLATE_PLAN.md)） |

## 10. 业务与表对应速查

| 业务模块 | 核心表 | 辅助表 |
|---|---|---|
| 用户认证 | `users` | `invite_codes`、`user_settings` |
| 文件管理 | `files` | `upload_batches` |
| 文献档案 | `bib_entries` ⭐ | — |
| 题录筛选 | `jobs(filter)`、`bib_filter_links` | `artifacts(filter_excel)` |
| 精读（长文本/七步/四步） | `jobs(reading_*)`、`reading_items` | `artifacts(reading_final)` |
| 对比综述 | `jobs(compare/synthesis)`、`job_bib_entries` | `artifacts(compare_md/synthesis_md)` |
| 参考文献梳理 | `bib_references`、`bib_reference_citations` | `artifacts(references_excel/citation_trace_md)` |
| 提示词管理 | `prompt_templates` | — |
| 文献库 AI 查询 | `bib_entries` | `bib_references`、`reading_items`、`prompt_templates(library_chat)`、`annotations(library_note)` |
| Markdown 卡片笔记 | `card_notes` | `bib_entries`、`files(markdown)`、`artifacts(translation_md)`、`prompt_templates(card_note)` |
| 用户反馈与后台审计 | `user_feedback` | `feedback_events`、`admin_audit_logs` |
| 维度集合（用户自建） | `dimension_sets`、`dimension_items` | — |
| 维度模板（系统预设） | `dimension_templates`、`template_items` | — |

## 11. 风险与注意事项

1. **SQLite 并发**：开启 WAL 模式（`PRAGMA journal_mode=WAL`），写并发足够支撑当前规模；用 `aiosqlite` 驱动。
2. **物理文件与 DB 一致性**：所有"文件 + DB 记录"操作走 try/finally，DB 失败时回滚物理写入。
3. **API Key 不入库**：DeepSeek API Key 完全在前端 `localStorage` 由用户自管，服务端不存、不清理、不审计。优点：泄漏面缩小；缺点：用户清浏览器缓存就要重输。
4. **dedup_key 冲突**：理论上仍可能误合并不同文献。前端"我的文献"页提供"取消合并 / 拆分"功能（v1.1 再做）。
5. **24h 清理误删**：清理任务需写日志到 `db/cleanup.log`，保留 7 天，便于事故复盘。
## 2026-05-23 Agent assistant persistence tables

Migration: `019_add_agent_sessions.py`

These tables persist the AI literature assistant conversation, tool events, and execution proposals. They are user data and are included in `.dra` export/import via `backend/services/data_portability.py` with `CURRENT_SCHEMA_VERSION = "021"`.

### `agent_sessions`

```sql
CREATE TABLE agent_sessions (
    id              TEXT PRIMARY KEY,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id),
    title           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','archived')),
    last_summary    TEXT,
    last_state_json TEXT NOT NULL DEFAULT '{}',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME
);

CREATE INDEX idx_agent_sessions_owner ON agent_sessions(owner_user_id);
CREATE INDEX idx_agent_sessions_updated ON agent_sessions(updated_at);
CREATE INDEX idx_agent_sessions_expires ON agent_sessions(expires_at);
```

`last_state_json` stores compact reusable state such as the most recent folder scan, pending proposal, or execution result so later turns can reference "the previous list".

### `agent_messages`

```sql
CREATE TABLE agent_messages (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    role         TEXT NOT NULL CHECK (role IN ('user','assistant','tool','system')),
    event_type   TEXT NOT NULL CHECK (
        event_type IN ('message','tool_call','tool_result','proposal','confirmation','error')
    ),
    tool_name    TEXT,
    content      TEXT NOT NULL DEFAULT '',
    payload_json TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at   DATETIME
);

CREATE INDEX idx_agent_messages_session ON agent_messages(session_id);
CREATE INDEX idx_agent_messages_owner ON agent_messages(owner_user_id);
CREATE INDEX idx_agent_messages_expires ON agent_messages(expires_at);
```

### `agent_action_proposals`

```sql
CREATE TABLE agent_action_proposals (
    id             TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    owner_user_id  INTEGER NOT NULL REFERENCES users(id),
    action_type    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','confirmed','rejected','expired','executed','failed')),
    arguments_json TEXT NOT NULL DEFAULT '{}',
    preview_json   TEXT NOT NULL DEFAULT '{}',
    result_json    TEXT,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at   DATETIME,
    expires_at     DATETIME
);

CREATE INDEX idx_agent_proposals_session ON agent_action_proposals(session_id);
CREATE INDEX idx_agent_proposals_status ON agent_action_proposals(status);
CREATE INDEX idx_agent_proposals_owner ON agent_action_proposals(owner_user_id);
CREATE INDEX idx_agent_proposals_expires ON agent_action_proposals(expires_at);
```

Execution tools such as folder import and batch reading must create a pending proposal first. Jobs are created only after `/api/agent/proposals/{proposal_id}/confirm` succeeds.
