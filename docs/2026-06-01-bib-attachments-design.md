# 文献附件系统设计文档

> 日期：2026-06-01
> 状态：已完成（待部署）
> 关联：`020_add_markdown_card_notes`（卡片笔记）、`025_add_bib_attachments`（本次迁移）

## 1. 问题与目标

### 现状

- `BibEntry.markdown_source_file_id` 是单个 FK，只能绑定一个 Markdown 原文
- 一篇文献翻译完成后，可以挂载 Markdown 原文，但只能保留一个
- 用户希望对同一篇文献挂载多个 Markdown 附件（如读书笔记、补充材料、笔记批注版等）
- 每个附件都能进入阅读器进行选文制卡，所有卡片关联到同一篇文献

### 目标

1. 一篇文献支持挂载任意数量的 Markdown 附件
2. 每个附件可独立进入阅读器（MarkdownReader）阅读并制卡
3. 所有卡片（无论来自原文、译文还是附件）统一关联到对应文献
4. 保持现有"挂载 Markdown"（主 Markdown）功能不变，向后兼容

### 约束

- 仅支持 Markdown 文件类型
- 附件数量不限
- 不修改现有 `markdown_source_file_id` 语义（主 Markdown）

## 2. 方案：新增 `bib_attachments` 关联表

### 2.1 数据库变更

新增 `bib_attachments` 表，迁移编号 `025`：

```sql
CREATE TABLE bib_attachments (
    id              VARCHAR PRIMARY KEY,          -- UUID
    bib_entry_id    VARCHAR NOT NULL REFERENCES bib_entries(id) ON DELETE CASCADE,
    file_id         VARCHAR NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    label           VARCHAR(200) NOT NULL,        -- 附件显示名称
    sort_order      INTEGER NOT NULL DEFAULT 0,   -- 排序
    owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP                     -- nullable, normal 用户 24h 过期
);

CREATE INDEX idx_bib_att_entry ON bib_attachments(bib_entry_id);
CREATE INDEX idx_bib_att_owner ON bib_attachments(owner_user_id);
CREATE INDEX idx_bib_att_expires ON bib_attachments(expires_at);
CREATE UNIQUE INDEX uq_bib_att_entry_file ON bib_attachments(bib_entry_id, file_id);  -- 同一文献不能重复绑定同一文件
```

**不修改的字段**：`bib_entries.markdown_source_file_id` 保持不变，继续作为"主 Markdown"。

### 2.2 与现有模型的关系

```
BibEntry
  ├── markdown_source_file_id  →  File (主 Markdown，阅读器 original 视图)
  ├── JobBibEntry → Job → Artifact(translation_md)  (翻译结果，阅读器 translated 视图)
  └── BibAttachment[]  →  File (附件 Markdown，阅读器 attachment:{file_id} 视图)
        └── CardNote (通过 source_markdown_file_id = attachment.file_id 关联)
```

关键点：`CardNote.source_markdown_file_id` 已经指向 `files.id`，附件的 `file_id` 也是 `files.id`，因此**卡片无需修改**——附件制卡时只需将 `source_markdown_file_id` 设为附件的 `file_id` 即可自动关联。

`CardNote.source_version` 的 CHECK 约束目前只允许 `'original'` 和 `'translated'`，需扩展为包含 `'attachment'`。

### 2.3 需修改的 CHECK 约束

```sql
-- 旧
CHECK (source_version IN ('original','translated'))
-- 新
CHECK (source_version IN ('original','translated','attachment'))
```

### 2.4 data_portability 同步

- `CURRENT_SCHEMA_VERSION` 升级为 `"025"`
- 导出时包含 `bib_attachments` 表数据
- 导入时处理 `bib_attachments` 的 id remap（`bib_entry_id`、`file_id`、`owner_user_id`）

## 3. 后端 API

### 3.1 新增端点

| 方法 | 路径 | 函数名 | 说明 |
|------|------|--------|------|
| POST | `/api/library/entries/{entry_id}/attachments` | `upload_attachment` | 上传 Markdown 附件 |
| GET | `/api/library/entries/{entry_id}/attachments` | `list_attachments` | 列出所有附件 |
| DELETE | `/api/library/entries/{entry_id}/attachments/{attachment_id}` | `delete_attachment` | 删除附件 |
| PATCH | `/api/library/entries/{entry_id}/attachments/{attachment_id}` | `update_attachment` | 更新附件标签/排序 |

### 3.2 `upload_attachment` 逻辑

1. 验证 entry 归属当前用户
2. 验证文件为 `.md` / `.markdown`
3. MD5 去重（同用户已有同 MD5 的 File 记录则复用）
4. 持久化到 `files` 表（`file_type="markdown"`）
5. 创建 `BibAttachment` 记录，`label` 默认取文件名
6. `sort_order` 取当前最大值 +1
7. 返回附件列表

### 3.3 Reader 端点扩展

`GET /api/library/entries/{entry_id}/reader` 的 `view` 参数扩展：

| 值 | 含义 |
|----|------|
| `original` | 主 Markdown（`markdown_source_file_id`） |
| `translated` | 翻译结果（Artifact） |
| `attachment:{file_id}` | 指定附件的 Markdown |

Reader 返回的 `versions` 列表扩展为：

```json
{
  "versions": [
    { "version": "original", "label": "原文", "available": true },
    { "version": "translated", "label": "译文", "available": true },
    { "version": "attachment:uuid-xxx", "label": "读书笔记", "available": true },
    { "version": "attachment:uuid-yyy", "label": "补充材料", "available": true }
  ]
}
```

`current_version` 字段支持 `"attachment:{file_id}"` 格式。

### 3.4 卡片创建适配

`POST /api/cards/from-selection` 无需修改 schema。制卡时：

- `source_version` = `"attachment"`
- `source_markdown_file_id` = 附件的 `file_id`
- `source_bib_entry_id` = 文献 ID

后端 `create_card_from_selection` 需增加对 `source_version == "attachment"` 的处理分支，验证 `source_markdown_file_id` 对应的附件确实属于当前用户的当前文献。

### 3.5 Library Entry Detail 扩展

`GET /api/library/entries/{entry_id}` 返回增加 `attachments` 字段：

```json
{
  "attachments": [
    {
      "id": "uuid",
      "file_id": "uuid",
      "label": "读书笔记",
      "sort_order": 0,
      "file_name": "reading-notes.md",
      "file_size": 12345,
      "created_at": "2026-06-01T12:00:00"
    }
  ]
}
```

## 4. 前端变更

### 4.1 LibraryTab.tsx — 详情面板

在现有"挂载 Markdown"按钮下方新增"添加附件"区域：

- "添加附件"按钮：触发文件选择（`.md` / `.markdown`）
- 附件列表：展示所有已挂载附件，每项包含：
  - 附件名称（可编辑 label）
  - "阅读并制卡"链接 → 跳转到 reader `attachment:{file_id}` 视图
  - 删除按钮

### 4.2 MarkdownReader.tsx — 版本切换

版本切换按钮组从固定的 `original | translated` 扩展为动态列表：

```
[原文] [译文] [读书笔记] [补充材料]
```

每个附件作为一个独立的版本 tab，点击后以 `attachment:{file_id}` 加载内容。

### 4.3 CardLibrary.tsx

卡片的 `source_version` 显示增加"附件"标签（当 `source_version === 'attachment'` 时）。

## 5. 迁移步骤

### Step 1: Alembic migration `025`

```python
# 025_add_bib_attachments.py
def upgrade():
    op.create_table('bib_attachments', ...)
    op.create_index(...)
    # 扩展 card_notes.source_version CHECK 约束
    op.execute("ALTER TABLE card_notes DROP CONSTRAINT ck_card_notes_source_version")
    op.execute("ALTER TABLE card_notes ADD CONSTRAINT ck_card_notes_source_version CHECK (source_version IN ('original','translated','attachment'))")

def downgrade():
    op.drop_table('bib_attachments')
    op.execute("ALTER TABLE card_notes DROP CONSTRAINT ck_card_notes_source_version")
    op.execute("ALTER TABLE card_notes ADD CONSTRAINT ck_card_notes_source_version CHECK (source_version IN ('original','translated'))")
```

### Step 2: ORM 模型

在 `backend/db/models.py` 中新增 `BibAttachment` 类，放置在 `BibEntry` 之后。

### Step 3: 后端路由

在 `backend/routers/library.py` 中新增附件 CRUD 端点，扩展 reader 端点。

在 `backend/routers/cards.py` 中扩展 `source_version` 验证逻辑。

### Step 4: data_portability

`CURRENT_SCHEMA_VERSION` 升级为 `"025"`，导出/导入顺序中加入 `bib_attachments`。

### Step 5: 前端

LibraryTab 添加附件 UI，MarkdownReader 扩展版本切换。

## 6. 不涉及的变更

- 不修改 `BibEntry.markdown_source_file_id` 的语义
- 不修改现有"挂载 Markdown"按钮行为
- 不新增文件类型支持（仅 Markdown）
- 不修改 Obsidian 导出逻辑（附件卡片已通过 `CardNote` 自动纳入）
- 不修改 cleanup 逻辑（附件行的 `expires_at` 随 File 过期清理，BibAttachment 通过 CASCADE 级联删除）

## 7. 文件影响清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/db/models.py` | 新增 | `BibAttachment` 模型 + 修改 `CardNote.source_version` CheckConstraint |
| `backend/migrations/versions/025_add_bib_attachments.py` | 新增 | 迁移脚本 |
| `backend/routers/library.py` | 修改 | 新增附件 CRUD 端点 + 扩展 reader 端点 |
| `backend/routers/cards.py` | 修改 | 扩展 `source_version` 验证 |
| `backend/services/data_portability.py` | 修改 | schema version + 导出/导入 |
| `frontend/src/LibraryTab.tsx` | 修改 | 附件列表 UI + 上传/删除/跳转 |
| `frontend/src/MarkdownReader.tsx` | 修改 | 动态版本切换 + attachment view |
| `frontend/src/CardLibrary.tsx` | 修改 | source_version 显示扩展 |
| `routers/library.py`（根目录镜像） | 同步 | 部署时需同步 |
