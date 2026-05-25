# 分片上传导入实现记录

> 类型：实现  
> 日期：2026-05-25（初版）、2026-05-25（v2 会话持久化）  
> 关联文件：`backend/routers/data.py`、`frontend/src/App.tsx`

---

## 1. 背景与目标

原有数据导入（`.dra` 文件）通过单个 `POST /api/data/import/start` 请求将整个文件一次性上传。当导出包较大（数百 MB）时，单次请求容易因超时、Nginx body size 限制或网络不稳定而失败。

本次改动将导入流程改为**前端分片上传 → 后端组装 → 启动后台导入任务**的三阶段协议，保持原有的导入逻辑不变。

## 2. 改动范围

| 文件 | 改动 |
|------|------|
| `backend/routers/data.py` | 新增 3 个分片上传端点 + 会话持久化到文件系统 |
| `frontend/src/App.tsx` | `handleImportFile` 改为分片上传流程 |

无数据库 schema 变更，无新增 migration。

## 3. 后端 API 设计

### 3.1 新增端点

#### `POST /import/chunk/init`

初始化分片上传会话。

| 参数 | 类型 | 说明 |
|------|------|------|
| `filename` | Form | 文件名（必须 `.dra`） |
| `total_size` | Form(int) | 文件总字节数 |
| `total_chunks` | Form(int) | 分片总数 |

返回：

```json
{ "upload_id": "uuid" }
```

校验：频率限制（3 次/天）、文件扩展名、文件大小 ≤ 1GB、无进行中的导入任务。

#### `POST /import/chunk`

上传单个分片。

| 参数 | 类型 | 说明 |
|------|------|------|
| `upload_id` | Form | init 返回的 upload_id |
| `chunk_index` | Form(int) | 分片序号（0-based） |
| `chunk` | File | 分片二进制数据 |

返回：

```json
{ "upload_id": "...", "received": 5, "total_chunks": 10 }
```

校验：upload_id 属于当前用户、chunk_index 在范围内、单个分片 ≤ 10MB。

#### `POST /import/chunk/complete`

组装所有分片并启动后台导入任务。

| 参数 | 类型 | 说明 |
|------|------|------|
| `upload_id` | Form | init 返回的 upload_id |

流程：
1. 校验所有分片已到齐
2. 按 chunk_index 顺序拼接写入临时 `.dra` 文件
3. 校验拼接后文件大小 == total_size
4. 清理分片临时目录和 upload session
5. 调用 `_start_import_from_path()` 启动后台导入线程

返回与原 `/import/start` 一致：

```json
{ "job_id": "...", "status": "pending", "message": "导入任务已开始。" }
```

### 3.2 原有端点

`POST /import/start`（单文件上传）**保留不动**，仍可用于小文件场景。前端现在默认走分片流程，但该端点不删除。

### 3.3 代码重构

| 原函数 | 重构后 | 说明 |
|--------|--------|------|
| `_start_import_data()` 内联的频率检查、冲突检查 | `_ensure_import_allowed()` | 供 init 和 complete 复用 |
| `_start_import_data()` 内联的任务创建+线程启动 | `_start_import_from_path()` | 供单文件上传和 chunk/complete 共用 |
| — | `_check_active_import()` | 从 `_start_import_data` 中提取的冲突检查 |
| — | `_save_session_meta()` / `_load_session_meta()` | 会话元数据文件系统读写 |

### 3.4 常量

| 常量 | 值 | 说明 |
|------|----|------|
| `_IMPORT_CHUNK_SIZE_LIMIT` | 10 MB | 单个分片最大大小 |
| `_UPLOAD_SESSIONS_ROOT` | `/tmp/dra_upload_sessions` | 会话元数据根目录 |

## 4. 会话持久化设计（v2）

### 4.1 问题

v1 将 upload session 存在 Python 进程内存 dict `_import_upload_sessions` 中。服务器部署链路为：

```
Cloudflare Tunnel → Nginx → uvicorn (可能多 worker)
```

- `start.sh` 用 `--workers 1`，但旧版 `health_check.sh` 用 `--workers 2`
- `healthcheck.sh` cron 每分钟执行，若 FastAPI 宕机会调用 `start.sh` 重启
- 多 worker 场景：init 请求被 worker-A 处理，chunk 请求被 worker-B 处理 → worker-B 内存中没有该 upload_id → 404 "分片上传会话不存在"

### 4.2 解决方案

将会话元数据从**内存 dict** 迁移到**文件系统 JSON 文件**，所有 worker 共享同一磁盘路径。

```
/tmp/dra_upload_sessions/
  └── {upload_id}/
      ├── _session.json          ← 会话元数据
      ├── 00000000.part          ← 分片 0
      ├── 00000001.part          ← 分片 1
      └── ...
```

### 4.3 会话元数据格式

`_session.json` 内容：

```json
{
  "upload_id": "uuid",
  "user_id": 1,
  "filename": "export_20260525_user.dra",
  "total_size": 52428800,
  "total_chunks": 13,
  "upload_dir": "/tmp/dra_upload_sessions/uuid",
  "received": [0, 1, 2, 5],
  "created_at": "2026-05-25T10:00:00",
  "updated_at": "2026-05-25T10:00:05"
}
```

- `received`：已接收的分片序号列表（JSON 序列化时 sorted，读取时还原为 set）
- 每次 chunk 上传成功后原子写入（`.tmp` → `replace`）

### 4.4 关键实现细节

| 细节 | 实现 |
|------|------|
| 原子写入 | `_save_session_meta()` 先写 `.tmp` 再 `Path.replace()`，避免读到半写状态 |
| set 序列化 | `received` 在 JSON 中存为 sorted list，`_load_session_meta()` 还原为 set |
| 无需进程内锁 | 文件系统本身就是跨进程共享状态，不再需要 `_import_upload_lock` |
| 容错读取 | `_load_session_meta()` 捕获 JSONDecodeError / OSError，返回 None |
| 清理 | `complete` 时 `shutil.rmtree(upload_dir)` 一次性清除元数据和分片文件 |

### 4.5 附带修复

| 文件 | 修复 |
|------|------|
| `health_check.sh` | `--workers 2` → `--workers 1`，与 `start.sh` 统一 |
| `start.sh` | 已是 `--workers 1`，无需修改 |
| `scripts/healthcheck.sh` | 调用 `bash start.sh`，无需修改 |

## 5. 前端实现

### 5.1 分片参数

```typescript
const IMPORT_CHUNK_SIZE = 4 * 1024 * 1024  // 4 MB per chunk
```

### 5.2 流程

```
用户选择 .dra 文件
  → 计算分片数 totalChunks = ceil(fileSize / 4MB)
  → POST /import/chunk/init（filename, total_size, total_chunks）
  → 循环上传每个分片：
      → POST /import/chunk（upload_id, chunk_index, chunk blob）
      → 更新进度条：0%~20%（分片上传阶段）
  → POST /import/chunk/complete（upload_id）
  → 拿到 job_id，进入原有的轮询逻辑（20%~100%）
```

### 5.3 进度展示

| 阶段 | 进度范围 | current_stage 文案 |
|------|----------|-------------------|
| 创建会话 | 0% | 正在创建分片上传会话... |
| 上传分片 | 0%→20% | 正在上传导入包分片 i/N... |
| 组装启动 | 20% | 正在组装导入包并启动后台任务... |
| 后台导入 | 20%→100% | 沿用原有轮询逻辑 |

## 6. 容错与清理

- **分片临时目录**：每个 upload session 创建独立目录 `$_UPLOAD_SESSIONS_ROOT/{upload_id}/`，分片以 `{index:08d}.part` 命名。complete 时无论成功失败都 `shutil.rmtree` 清理。
- **upload session**：元数据存为 `_session.json`，complete 时随目录一起删除。若客户端中途放弃，目录和 JSON 会残留在 `/tmp` 中；可由系统 tmpwatch/tmpreaper 或定期清理脚本处理。
- **组装失败**：删除已拼接的临时 `.dra` 文件，不启动导入任务。
- **进程重启**：upload session 持久化在文件系统中，进程重启不丢失；但 `_import_tasks`（导入任务状态）仍在内存中，重启会导致进行中的任务状态丢失（这是原有行为，未改变）。

## 7. 向后兼容

- 原有 `POST /import/start` 端点完全保留，可继续使用。
- `POST /import` 端点（兼容别名）也保留。
- 前端现在默认走分片上传；如果需要回退到单文件上传，恢复 `handleImportFile` 即可。

## 8. 故障排查指南

| 现象 | 可能原因 | 排查方式 |
|------|----------|----------|
| 404 "分片上传会话不存在" | upload_dir 被清理或 init 未调用 | 检查 `/tmp/dra_upload_sessions/{upload_id}/_session.json` 是否存在 |
| 413 "单个分片超过 10MB" | 前端分片大小设置错误 | 检查前端 `IMPORT_CHUNK_SIZE` 是否为 4MB |
| 400 "分片尚未上传完成" | 网络中断导致部分分片丢失 | 检查 `_session.json` 中 `received` 列表 |
| complete 后文件大小不匹配 | 分片内容在上传过程中被截断 | 检查 Nginx `client_max_body_size` 配置 |
