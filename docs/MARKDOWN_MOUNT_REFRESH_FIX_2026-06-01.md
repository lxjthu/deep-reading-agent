# Markdown 原文挂载后刷新消失问题复盘（2026-06-01）

## 背景

文献库详情页支持为 `BibEntry` 挂载 Markdown 原文：

- 前端入口：`frontend/src/LibraryTab.tsx` 的“挂载 Markdown”按钮
- 后端接口：`POST /api/library/entries/{entry_id}/markdown`
- 关键字段：`bib_entries.markdown_source_file_id`
- 文件表：`files`
- 存储路径：`_uploads/{user_id}/{file_id}.md`

用户反馈：挂载 Markdown 后页面短暂显示成功，但刷新文献库后又变成：

```text
Markdown 原文：未挂载
```

同一轮排查还涉及一个相邻问题：英文原文检索按钮报 `Method Not Allowed`。该问题是 `search_entry_fulltext` 的 `@router.post("/entries/{entry_id}/fulltext-search")` 装饰器在未提交改动中丢失，已单独补回。

## 影响

- 已上传的 Markdown 文件可能真实落盘成功，但 `BibEntry.markdown_source_file_id` 被后续列表刷新误清空。
- 用户看到“挂载成功”后刷新消失，容易误判为上传失败或前端状态丢失。
- 若重复上传同一 Markdown，系统会按 `owner_user_id + md5` 复用 `files` 记录；旧记录的物理文件若曾被清理，也会触发新的异常路径。

## 真实请求链路

线上监控到的操作顺序如下：

```text
POST /api/library/entries/b79935b3-c04e-4652-9357-ac5179a93f02/markdown 200 OK
GET  /api/library/entries/page?reading_status=has_pdf&sort_by=updated&sort_order=desc&page=1&page_size=100 200 OK
GET  /workspace/library 200 OK
GET  /api/library/entries/page?sort_by=updated&sort_order=desc&page=1&page_size=100 200 OK
GET  /api/library/entries/{entry_id} 200 OK
```

关键发现：`POST /markdown` 没有报错，问题发生在随后的列表刷新阶段。

## 根因一：列表接口误清 `markdown_source_file_id`

`backend/routers/library.py` 中 `_list_entries()` 和 `_list_entries_page()` 会遍历列表结果，并调用：

```python
sanitize_entry_source_files(entry, source_file, None)
```

这里第三个参数 `markdown_file` 固定传入 `None`。当某篇文献已经有 `entry.markdown_source_file_id` 时，`sanitize_entry_source_files()` 会执行：

```python
valid_markdown = markdown_file if file_record_exists(markdown_file) else None
if entry.markdown_source_file_id and valid_markdown is None:
    entry.markdown_source_file_id = None
    changed = True
```

因为列表接口没有加载 Markdown 对应的 `File`，`valid_markdown` 永远是 `None`，所以列表刷新会误判“Markdown 文件不存在”，并把数据库绑定清空。

这正好解释了用户看到的现象：

1. `POST /markdown` 成功，后端一度写入 `markdown_source_file_id`
2. 前端调用 `loadEntries()` 刷新列表
3. 列表接口误清 `markdown_source_file_id`
4. 用户刷新详情页后显示“未挂载”

## 根因二：md5 复用旧 File 记录时未验证物理文件

`upload_entry_markdown()` 原逻辑按 `owner_user_id + md5` 查找已有 `File`：

```python
record = await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
```

如果查到旧记录，就复用旧 `record.id`，但没有确认 `record.storage_path` 指向的物理文件是否仍然存在。

如果旧 `files` 记录存在、磁盘文件不存在，则挂载后详情读取会被 `sanitize_entry_source_files()` 清空。这是第二条容易复现“挂载后消失”的路径。

## 修复方案

### 1. 列表接口加载 Markdown File 再清理

修改 `_list_entries()` 和 `_list_entries_page()`：

```python
markdown_file = await db.get(File, entry.markdown_source_file_id) if entry.markdown_source_file_id else None
source_file, markdown_file, repaired = sanitize_entry_source_files(entry, source_file, markdown_file)
```

这样只有在数据库 `File` 行不存在，或 `storage_path` 指向的物理文件确实不存在时，才会清空 `markdown_source_file_id`。

### 2. md5 命中旧记录但文件丢失时重新落盘

修改 `upload_entry_markdown()`：

```python
if record is not None and not file_record_exists(record):
    final_path, storage_path = build_storage_path(user.id, record.id, file_ext)
    shutil.move(str(temp_path), str(final_path))
    record.original_name = original_name
    record.file_type = "markdown"
    record.storage_path = storage_path
    record.size_bytes = size_bytes
    record.expires_at = compute_expires_at(user)
elif record is None:
    ...
```

这样可以复用原 `File.id`，避免违反 `uq_files_owner_md5`，同时恢复物理文件。

### 3. 时间戳兼容 PostgreSQL

同一文件中还将旧的：

```python
entry.updated_at = datetime.now(UTC)
```

替换为：

```python
entry.updated_at = utcnow_naive()
```

原因：生产 PostgreSQL 字段是 `TIMESTAMP WITHOUT TIME ZONE`，传入 timezone-aware datetime 会触发 asyncpg 的 offset-naive / offset-aware 混用错误。

## 回归测试

新增测试：`backend/tests/test_library.py::LibraryRouterTests.test_markdown_upload_recreates_missing_deduped_file`

测试覆盖两个关键场景：

1. 数据库中存在同 md5 的 Markdown `File` 记录，但物理文件缺失时，重新上传同一 Markdown 应重新落盘并保持绑定。
2. 上传成功后调用 `/api/library/entries/page` 模拟前端列表刷新，再查详情，`markdown_source_file_id` 仍应存在。

验证命令：

```powershell
python -m unittest backend.tests.test_library.LibraryRouterTests.test_markdown_upload_recreates_missing_deduped_file
python -m unittest backend.tests.test_library
```

本地验证结果：

```text
Ran 9 tests in 15.011s
OK
```

## 线上验证

部署文件：

```text
/root/deep-reading-agent/backend/routers/library.py
```

部署后验证：

```bash
systemctl restart deepreading-api
systemctl is-active deepreading-api
curl -sS -o /tmp/root.out -w '%{http_code}\n' http://127.0.0.1:18000/
curl -sS -X POST -o /tmp/markdown_route.out -w '%{http_code}\n' http://127.0.0.1:18000/api/library/entries/test/markdown
```

期望结果：

```text
active
200
401
```

`401` 是未登录烟测的正常结果，表示路由已进入鉴权层，不是 404/405/500。

用户重新操作后，生产库只读诊断结果：

```text
ENTRY id=b79935b3-c04e-4652-9357-ac5179a93f02
title=Technical Change, Inequality, and the Labor Market
source_file_id=ddf8626c-6f9a-47cf-a13c-5ee9461565c7
markdown_source_file_id=1eefc7a9-0622-45b4-aeed-717556b136a1
MARKDOWN_FILE id=1eefc7a9-0622-45b4-aeed-717556b136a1
original_name=Technical Change, Inequality, and the Labor Market.pdf_by_PaddleOCR.md
file_type=markdown
storage_path=_uploads/2/1eefc7a9-0622-45b4-aeed-717556b136a1.md
resolved_path=/root/deep-reading-agent/_uploads/2/1eefc7a9-0622-45b4-aeed-717556b136a1.md
path_exists=True is_file=True
```

后续读取也正常：

```text
GET /api/library/entries/b79935b3-c04e-4652-9357-ac5179a93f02/reader?view=original 200 OK
```

## 排查建议

遇到“上传成功但刷新后消失”的问题，不要只看上传接口状态码。按下面顺序查：

1. 监控日志，确认 `POST /markdown` 后是否紧跟 `GET /entries/page` 或 `GET /entries`。
2. 查 `bib_entries.markdown_source_file_id` 在列表刷新后是否被清空。
3. 查 `files` 表中对应 `File.storage_path` 是否存在物理文件。
4. 检查是否有接口调用 `sanitize_entry_source_files(entry, source_file, None)` 这种未加载 Markdown 文件却执行清理的模式。
5. 若是 PostgreSQL，检查是否仍有 `datetime.now(UTC)` 写入 `TIMESTAMP WITHOUT TIME ZONE` 字段。

## 经验教训

- 清理函数必须拿到足够上下文。不能在未加载关联文件的情况下，把“没有传入对象”当成“文件不存在”。
- 列表接口不应带有会误伤详情绑定的修复性副作用；如果需要修复，应确保依赖数据完整。
- md5 去重只说明内容相同，不说明物理文件仍存在。复用文件记录前要验证 `storage_path`。
- 线上验证要观察完整前端请求链，而不是只验证单个 POST 接口。
