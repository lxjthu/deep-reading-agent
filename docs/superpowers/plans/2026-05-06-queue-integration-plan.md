# 任务队列接入路由层 + 前端排队提示 — 实施计划

> 日期: 2026-05-06
> 预计工期: 半天
> 前置: `backend/services/queue_manager.py` 已实现，30 个单元测试通过
> 关联: [PENDING_PLANS.md](../../PENDING_PLANS.md) 2.5 节

## 1. 当前状态

### 已完成

- `backend/services/queue_manager.py`：`TaskQueueManager` 类 + 全局实例 `task_queue`
- `backend/tests/test_queue_manager.py`：30 个单元测试全通过
- 支持 5 种任务类型：`quant / qual / long / reference / filter`

### 未完成（本计划范围）

1. `reading.py` 精读启动时接入 `task_queue`
2. `reading.py` 状态查询接入 `task_queue.get_task_queue_info()`
3. 后台线程开始/结束时调用 `mark_running()` / `mark_completed()`
4. 前端 `applyStatus()` 处理 `status=queued` 状态
5. 前端排队提示 UI

---

## 2. 实施步骤

### 步骤 1：后端 — `reading.py` 接入队列管理器

**改动文件**: `backend/routers/reading.py`

#### 1.1 新增导入和常量

在文件头部新增：

```python
from services.queue_manager import task_queue

MAX_CONCURRENT_READING = 2  # 最大并发精读任务数（全局）
```

#### 1.2 修改三个 start 函数

在 `start_long_context`、`start_quant`、`start_qual` 三个函数中，**在创建线程之前**插入队列检查逻辑。

插入位置：在 `tasks[task_id] = init_task_payload(...)` 之后、`thread = threading.Thread(...)` 之前。

```python
# 队列管理：检查并发数
queue_info = task_queue.enqueue(task_id, user.id, "long")  # 或 "quant" / "qual"
```

三个函数的 task_type 映射：

| 函数 | task_type |
|------|-----------|
| `start_long_context` | `"long"` |
| `start_quant` | `"quant"` |
| `start_qual` | `"qual"` |

#### 1.3 后台线程首尾调用 mark_running / mark_completed

在三个 `run_*_task` 函数中：

- **线程开始时**（函数体第一行有效代码之前）：
  ```python
  task_queue.mark_running(task_id)
  ```

- **线程成功结束时**（函数体正常 return 之前）：
  ```python
  task_queue.mark_completed(task_id)
  ```

- **线程异常结束时**（except 块中，在记录错误之后）：
  ```python
  task_queue.mark_completed(task_id)
  ```

#### 1.4 修改 `get_task_status` 返回排队信息

在 `get_task_status` 函数中，**在现有 `if task_id in tasks` 判断之前**，先查询队列状态：

```python
queue_info = task_queue.get_task_queue_info(task_id)

if queue_info and queue_info.get("status") == "queued":
    return JSONResponse(content={
        "status": "queued",
        "progress": 0,
        "stage": f"排队中 (第 {queue_info['queue_position']} 位，"
                 f"预计等待 {queue_info['estimated_wait_minutes']} 分钟)",
        "logs": [
            "任务已加入队列",
            f"排队位置: 第 {queue_info['queue_position']} 位",
            f"预计等待: {queue_info['estimated_wait_minutes']} 分钟",
        ],
        "queue_position": queue_info["queue_position"],
        "estimated_wait_seconds": queue_info["estimated_wait_seconds"],
        "estimated_wait_minutes": queue_info["estimated_wait_minutes"],
    })

# ... 原有 if task_id in tasks 逻辑不变 ...
```

### 步骤 2：前端 — 处理 queued 状态

**改动文件**: `frontend/src/App.tsx`

#### 2.1 扩展 `applyStatus` 处理 queued

在 `applyStatus` 函数中，在现有的 `completed / failed / cancelled` 判断之前，新增 `queued` 分支：

```typescript
// 在 statusData.status === 'completed' 判断之前插入
if (statusData.status === 'queued') {
  setProgress(0)
  setStage(statusData.stage || '排队中...')
  setIsRunning(true)
  if (Array.isArray(statusData.logs) && statusData.logs.length > 0) {
    setLogs(statusData.logs)
  }
  return  // 不终止轮询，继续等待
}
```

**关键**：`queued` 状态不终止轮询，前端继续每秒 poll，直到后端返回 `running`（progress > 0）或 `completed/failed/cancelled`。

#### 2.2 排队提示 UI

在三个精读 Tab 的进度展示区域（LongTab、QuantTab、QualTab），新增排队状态的条件渲染。

插入位置：在现有 `"处理进度"` card 内部，进度条之前。

```tsx
{status === 'queued' || (stage && stage.startsWith('排队中')) ? (
  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-3">
    <div className="flex items-center gap-2 mb-2">
      <span className="text-blue-600 font-medium">排队中</span>
    </div>
    <div className="text-sm text-blue-600">{stage}</div>
    <div className="mt-2 h-2 bg-blue-100 rounded-full overflow-hidden">
      <div className="h-full bg-blue-400 rounded-full animate-pulse" style={{ width: '30%' }} />
    </div>
  </div>
) : null}
```

需要在各 Tab 的 tracker 解构中额外取出 `stage`（已取出）来判断。

判断条件：`stage.startsWith('排队中')`，这是最简单且不增加额外状态的方案。

### 步骤 3：`mark_running` 中记录 task_type

**问题**：当前 `task_queue.enqueue()` 接收 `task_type`，但 `mark_running()` 不传 `task_type`，导致 `mark_completed()` 中无法获取 `task_type` 来更新平均耗时。

**修复**：在 `enqueue` 时把 `task_type` 写入 entry，`mark_running` 时把 `task_type` 转移到 `_running`。

**改动文件**: `backend/services/queue_manager.py`

```python
def mark_running(self, task_id: str):
    # 从队列中找到 entry 获取 task_type
    task_type = None
    for entry in self._queue:
        if entry["task_id"] == task_id:
            task_type = entry.get("task_type")
            break
    self._running[task_id] = {
        "start_time": datetime.now(),
        "task_type": task_type,
    }
    self._queue = [t for t in self._queue if t["task_id"] != task_id]
```

同步更新 `mark_completed` 中取 `task_type` 的逻辑（已有 `self._running[task_id].get("task_type")` 但之前 always None，修复后会有值）。

---

## 3. 测试用例

### 3.1 后端测试（新增 `backend/tests/test_queue_integration.py`）

| 编号 | 用例名 | 测试内容 | 预期结果 |
|------|--------|---------|---------|
| T1 | `test_reading_start_registers_in_queue` | 调用 `POST /api/reading/quant/start` | `task_queue.get_task_queue_info(task_id)` 返回 `status=running`（因为线程立即开始） |
| T2 | `test_queued_status_returned_when_polling` | 任务排队中时调用 `GET /api/reading/task/{task_id}/status` | 返回 `status=queued`、`queue_position`、`estimated_wait_seconds` |
| T3 | `test_queue_mark_running_called_by_worker` | 精读线程启动后 | `task_queue.get_task_queue_info(task_id)` 返回 `status=running` |
| T4 | `test_queue_mark_completed_on_success` | 精读线程成功完成 | `task_queue.get_task_queue_info(task_id)` 返回 `None`（已从队列移除） |
| T5 | `test_queue_mark_completed_on_failure` | 精读线程抛异常 | `task_queue.get_task_queue_info(task_id)` 返回 `None`（已从队列移除） |
| T6 | `test_mark_running_preserves_task_type` | enqueue + mark_running | `_running[task_id]["task_type"]` 正确记录，mark_completed 后 `_avg_duration` 被更新 |

### 3.2 前端测试（手动验证清单）

| 编号 | 用例名 | 操作步骤 | 预期结果 |
|------|--------|---------|---------|
| F1 | 排队状态蓝色 UI | 系统繁忙时启动精读 | 进度区域显示蓝色卡片"排队中"，含排队位置和预估等待时间 |
| F2 | 排队到运行自动切换 | 排队中的任务被调度开始 | 蓝色卡片自动消失，显示正常绿色进度条 |
| F3 | 排队到完成正常结束 | 排队后正常完成精读 | 显示结果预览和下载按钮 |
| F4 | 排队中可取消 | 排队中点击取消按钮 | 停止轮询，恢复初始状态 |

### 3.3 回归测试

运行全部现有测试确保不破坏：

```bash
.\venv\Scripts\python.exe -m unittest backend.tests.test_queue_manager -v
.\venv\Scripts\python.exe -m unittest backend.tests.test_reading -v
.\venv\Scripts\python.exe -m unittest backend.tests.test_auth backend.tests.test_upload backend.tests.test_filter -v
```

---

## 4. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/services/queue_manager.py` | 修改 | `mark_running` 保留 `task_type` |
| `backend/routers/reading.py` | 修改 | 导入 + 三个 start 函数接入队列 + get_task_status 返回排队信息 + 三个 worker 首尾调用 mark |
| `backend/tests/test_queue_integration.py` | 新增 | 6 个集成测试 |
| `frontend/src/App.tsx` | 修改 | `applyStatus` 处理 queued + 三个 Tab 新增排队 UI |

---

## 5. 不做的事

| 项 | 原因 |
|----|------|
| filter.py 接入队列 | 筛选任务已有自己的内存 tasks 管理，首期不改，避免范围膨胀 |
| references.py 接入队列 | 同上 |
| 前端 TaskProgress 抽成独立组件 | 三个 Tab 的进度 UI 各不相同，抽组件收益不大 |
| 队列持久化（重启恢复） | 当前是内存队列，重启后丢失是预期行为 |
