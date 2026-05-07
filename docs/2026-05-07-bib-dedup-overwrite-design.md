# 文献重复覆盖功能设计

## 需求

1. **题录覆盖**：筛选导入时，如果已存在（题目、作者、发表期刊、发表年份）相同的论文，直接覆盖题录元数据
2. **精读覆盖**：重复精读一篇论文时，先提示用户已精读过，用户确认则覆盖，取消则中止

## 现状

- `persist_filter_results`（filter.py）按 `dedup_key` 匹配已有 BibEntry，匹配到时只更新 `updated_at`，不覆盖元数据
- `start_long/quant/qual` 端点不检查 `reading_status`，每次都创建新 Job
- 前端三个 Tab 的 `handleStart` 不处理重复情况

## 方案

### 1. 题录覆盖（筛选导入）

**文件**：`backend/routers/filter.py` — `persist_filter_results`

匹配到已有条目时，用新数据覆盖以下字段：

- title, authors_json, year, doi, journal, abstract, keywords_json, venue_type, citation_count

`dedup_key` 保持不变（`sig:{first_author}:{year}:{title_norm}`），无需改数据库约束。

### 2. 精读覆盖（重复精读提示确认）

**后端** — `backend/routers/reading.py`：

- 三个 start 端点（`start_long_context`, `start_quant`, `start_qual`）在 `get_or_create_bib_entry` 之后检查 `bib_entry.reading_status`
- 如果是 `"reading"` 或 `"read"` 且请求未带 `force_overwrite=True`：
  - 返回 **409 Conflict**，body：`{ "detail": "already_read", "bib_entry": { "id": "...", "title": "...", "reading_status": "..." } }`
- 如果 `force_overwrite=True`：
  - 删除该 bib entry 关联的旧 ReadingItem、Artifact（含物理文件）、Job、JobBibEntry
  - 然后创建新 Job 正常启动精读
- Request model 新增 `force_overwrite: bool = False` 字段

**前端** — `frontend/src/App.tsx`：

- 三个 Tab 的 `handleStart` 捕获 409 响应
- 用 `window.confirm()` 提示："该论文已经精读过（标题：xxx），是否覆盖？"
- 确认 → 带 `force_overwrite: true` 重发请求
- 取消 → 中止

## 改动范围

| 文件 | 改动 |
|------|------|
| `backend/routers/reading.py` | 三个 start 端点加重复检测 + 清理旧数据函数 + request model 加 `force_overwrite` |
| `backend/routers/filter.py` | `persist_filter_results` 匹配到旧条目时覆盖元数据 |
| `frontend/src/App.tsx` | 三个 Tab 的 `handleStart` 加 409 处理 |
