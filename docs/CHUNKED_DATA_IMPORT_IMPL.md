# 分片上传导入实现记录

> 类型：实现  
> 日期：2026-05-25  
> 关联文件：`backend/routers/data.py`、`frontend/src/App.tsx`

---

## 1. 背景与目标

原有数据导入（`.dra` 文件）通过单个 `POST /api/data/import/start` 请求将整个文件一次性上传。当导出包较大（数百 MB）时，单次请求容易因超时、Nginx body size 限制或网络不稳定而失败。

本次改动将导入流程改为**前端分片上传 → 后端组装 → 启动后台导入任务**的三阶段协议，保持原有的导入逻辑不变。

## 2. 改动范围

| 文件 | 改动 |
|------|------|
| `backend/routers/data.py` | 新增 3 个分片上传端点 + 辅助函数重构 |
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
| — | `_import_upload_lock` + `_import_upload_sessions` | 分片上传会话存储（内存 dict） |

### 3.4 常量

| 常量 | 值 | 说明 |
|------|----|------|
| `_IMPORT_CHUNK_SIZE_LIMIT` | 10 MB | 单个分片最大大小 |
| `_import_upload_sessions` | dict | 内存中的上传会话，key 为 upload_id |

## 4. 前端实现

### 4.1 分片参数

```typescript
const IMPORT_CHUNK_SIZE = 4 * 1024 * 1024  // 4 MB per chunk
```

### 4.2 流程

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

### 4.3 进度展示

| 阶段 | 进度范围 | current_stage 文案 |
|------|----------|-------------------|
| 创建会话 | 0% | 正在创建分片上传会话... |
| 上传分片 | 0%→20% | 正在上传导入包分片 i/N... |
| 组装启动 | 20% | 正在组装导入包并启动后台任务... |
| 后台导入 | 20%→100% | 沿用原有轮询逻辑 |

## 5. 容错与清理

- **分片临时目录**：每个 upload session 创建独立的 `tempfile.mkdtemp()` 目录，分片以 `{index:08d}.part` 命名。complete 时无论成功失败都 `shutil.rmtree` 清理。
- **upload session**：complete 时从 `_import_upload_sessions` 中移除。若客户端中途放弃，session 会残留在内存中；目前没有过期清理机制（低优先级，服务重启即清空）。
- **组装失败**：删除已拼接的临时 `.dra` 文件，不启动导入任务。

## 6. 向后兼容

- 原有 `POST /import/start` 端点完全保留，可继续使用。
- `POST /import` 端点（兼容别名）也保留。
- 前端现在默认走分片上传；如果需要回退到单文件上传，恢复 `handleImportFile` 即可。
