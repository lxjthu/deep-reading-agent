# 批量精读冲突预检方案

> 日期：2026-05-17
> 状态：待实施

## 问题

批量精读（文件夹上传）时，前端三处请求均硬编码 `conflict_resolution: 'overwrite'`，不检查文件是否已有精读结果，直接覆盖：

- 长文本：`App.tsx:1552`
- 七步(quant)：`App.tsx:2112`
- 四步(qual)：`App.tsx:2486`

对比单篇精读流程：先发 start → 收到 409 → 调 `/check-conflict` → 弹 `ConflictDialog` → 用户选择 → 带 `conflict_resolution` 重发。批量完全跳过了这个流程。

## 设计目标

1. 批量精读启动前，先批量检测哪些文件有冲突
2. 无冲突 → 直接启动
3. 有冲突 → 弹出确认对话框，展示冲突列表，让用户选择全局策略
4. 用户确认后，带统一的 `conflict_resolution` 启动批量任务

## 方案

### 1. 后端：新增批量冲突检测接口

**端点**：`POST /api/reading/batch/check-conflict`

**请求体**：
```json
{
  "file_ids": ["id1", "id2", "id3"],
  "mode": "long",
  "analysis_dims": ["研究问题", "理论框架"]
}
```

**逻辑**：遍历 `file_ids`，对每个文件复用 `check_conflict` 的逻辑（查 BibEntry → 查已有 Job → 算 incremental_dims），返回每个文件的冲突状态。

**响应**：
```json
{
  "conflicts": [
    {
      "file_id": "id1",
      "file_name": "xxx.pdf",
      "has_conflict": true,
      "bib_entry": { "id": "...", "title": "...", "reading_status": "read" },
      "existing_job": { "job_id": "...", "job_type": "reading_long", "created_at": "...", "dimensions": ["研究问题"], "mode_label": "长文本精读" },
      "incremental_dims": ["理论框架"]
    },
    {
      "file_id": "id2",
      "file_name": "yyy.pdf",
      "has_conflict": false
    }
  ],
  "total": 3,
  "conflict_count": 1
}
```

**实现要点**：
- 复用 `CheckConflictRequest` 的 Pydantic 模型，新增 `BatchCheckConflictRequest(file_ids: list[str], mode: str, analysis_dims: list[str] | None)`
- 内部循环调用与 `check_conflict` 相同的查询逻辑，但封装为内部函数 `check_single_conflict(db, user, file_id, mode, analysis_dims)` 避免代码重复
- 单次请求最多 50 个文件，与批量精读一致

### 2. 前端：批量冲突确认对话框

**新组件**：`BatchConflictDialog.tsx`

**职责**：展示有冲突的文件列表，让用户选择全局策略。

**布局**：

```
┌─────────────────────────────────────────────────┐
│  批量精读冲突检测                                  │
│                                                   │
│  以下 N 个文件已有精读结果：                        │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │ 📄 paper1.pdf                             │    │
│  │   已有：长文本精读（2026-05-16 完成）       │    │
│  │   已分析维度：研究问题、理论框架             │    │
│  ├──────────────────────────────────────────┤    │
│  │ 📄 paper2.pdf                             │    │
│  │   已有：长文本精读（2026-05-15 完成）       │    │
│  └──────────────────────────────────────────┘    │
│                                                   │
│  M 个文件无冲突，将直接精读。                       │
│                                                   │
│  ○ 覆盖重跑（删除旧结果，全部重新精读）             │
│  ○ 增量补充（仅长文本可用，跳过已有维度）            │
│  ○ 跳过已有（保留旧结果，只精读新文件）              │
│                                                   │
│               [取消]  [确认开始]                    │
└─────────────────────────────────────────────────┘
```

**Props**：
```typescript
interface BatchConflictDialogProps {
  conflicts: BatchConflictItem[]
  noConflictCount: number
  mode: 'long' | 'quant' | 'qual'
  onResolve: (resolution: 'overwrite' | 'new' | 'incremental') => void
  onCancel: () => void
}
```

**选项逻辑**：
- "覆盖重跑" — 始终可选，对应 `overwrite`
- "增量补充" — 仅 `mode === 'long'` 且有文件存在 incremental_dims 时可选，对应 `incremental`
- "跳过已有" — 始终可选，对应 `new`（后端对 `new` 的处理是保留旧结果、创建新 Job）

### 3. 前端：修改批量启动流程

三个 Tab 的 `handleBatchStart` 函数修改流程：

```
原流程：上传全部文件 → POST /batch/start (conflict_resolution: 'overwrite')
新流程：上传全部文件 → POST /batch/check-conflict → 检查结果
  → 无冲突：直接 POST /batch/start
  → 有冲突：弹出 BatchConflictDialog → 用户选择 → POST /batch/start (带选择的 conflict_resolution)
```

**改动点**（三处相同模式）：

1. 上传文件后，在调 `/batch/start` 之前，先调 `/batch/check-conflict`
2. 检查 `conflict_count > 0`，是则设置 `batchConflictInfo` state 并 return，等待用户操作
3. 新增 `handleBatchConflictResolve(resolution)` 回调，带用户选择的 resolution 发起 `/batch/start`
4. 删除硬编码的 `conflict_resolution: 'overwrite'`

### 4. 后端：`start_batch_reading` 调整

不需要大改，当前逻辑已经支持 `conflict_resolution` 参数。只需确保：

- `conflict_resolution: 'incremental'` 时，传递给 worker 函数（`run_long_context_task` 等），让 worker 内部做增量逻辑
- `conflict_resolution: 'new'` 时，跳过有冲突的文件（当前 `check` 模式已经是这个行为，line 1807-1809）

但要注意：当前 `default="overwrite"`（line 1804），前端不传 `conflict_resolution` 时默认覆盖。新流程中前端一定会传，所以 default 不影响。但为安全起见，建议改为 `default="check"`（跳过），防止遗漏。

### 5. 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/routers/reading.py` | 新增 `batch_check_conflict` 端点；`start_batch_reading` 的 default 改为 `"check"` |
| `frontend/src/components/BatchConflictDialog.tsx` | **新建** |
| `frontend/src/App.tsx` | 三个 Tab 的 `handleBatchStart` 增加预检步骤；新增 `batchConflictInfo` state + `handleBatchConflictResolve` |

### 6. 边界情况

- **全部有冲突**：用户选择"跳过已有" → 所有文件被 skip → 返回空 batch，前端提示"所有文件已有结果"
- **全部无冲突**：不弹对话框，直接启动
- **长文本 + 无 analysis_dims**：`incremental_dims` 为空，不显示"增量补充"选项
- **API Key 未设置**：预检前先检查 Key（与当前单篇流程一致）
- **上传失败**：预检只对上传成功的 file_ids 进行

### 7. 实施顺序

1. 后端：新增 `POST /batch/check-conflict` 端点
2. 后端：`start_batch_reading` 的 `resolve_conflict_mode` default 改为 `"check"`
3. 前端：新建 `BatchConflictDialog.tsx`
4. 前端：修改三个 Tab 的批量启动流程（长文本 → 七步 → 四步）
5. 端到端验证：上传含已精读文件的文件夹 → 确认弹窗出现 → 选择策略 → 验证结果
