# 多用户扩展迁移规划

> 适用项目：`deep-reading-agent`  
> 目标规模：10+ 并发用户  
> 规划日期：2026-05-03  
> 预计工期：4-6 周

---

## 1. 迁移目标与约束

### 1.1 目标

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 并发用户数 | 2-3 | 10-15 |
| 同时精读任务 | 1-2 | 5-8 |
| API 响应时间 | <200ms | <100ms |
| 任务成功率 | ~95% | >99% |
| 数据持久化 | 进程重启丢失 | 完全持久化 |

### 1.2 约束

- 服务器资源有限（当前 2 核 4GB 内存）
- 需要保持向后兼容
- 尽量减少停机时间
- 预算有限，优先使用开源方案

---

## 2. 架构演进路线图

### 2.1 当前架构（v1）

```
┌─────────────────────────────────────────────────────────────────┐
│                        当前架构 (v1)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Uvicorn (--workers 1)                                         │
│       │                                                         │
│       ├── FastAPI 主进程                                         │
│       │       │                                                 │
│       │       ├── tasks = {} (内存字典)                          │
│       │       │                                                 │
│       │       └── threading.Thread (后台任务)                    │
│       │                                                         │
│       └── SQLite (单文件数据库)                                   │
│                                                                 │
│   容量: 2-3 并发用户                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目标架构（v2）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              目标架构 (v2)                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   Nginx (负载均衡 + 静态文件)                                                     │
│       │                                                                         │
│       ├── Uvicorn Worker 1 ──┐                                                  │
│       ├── Uvicorn Worker 2 ──┼── FastAPI 进程组                                  │
│       └── Uvicorn Worker 3 ──┘                                                  │
│               │                                                                 │
│               ├── Redis (任务队列 + 缓存)                                        │
│               │       │                                                         │
│               │       ├── Celery Worker 1 ──┐                                   │
│               │       ├── Celery Worker 2 ──┼── 任务执行进程组                   │
│               │       └── Celery Worker 3 ──┘                                   │
│               │                                                                 │
│               └── PostgreSQL (关系数据库)                                        │
│                       │                                                         │
│                       └── 主从复制 (可选)                                        │
│                                                                                 │
│   容量: 10-15 并发用户                                                           │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 分阶段实施计划

### 阶段 1：短期优化（第 1 周）

**目标**：在不大幅改动架构的情况下，提升 50% 并发能力

#### 1.1 启用 SQLite WAL 模式

**文件**：`backend/db/session.py`（新建）

```python
import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """启用 SQLite WAL 模式，提高并发读写能力"""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB 缓存
        cursor.execute("PRAGMA busy_timeout=5000")   # 5 秒超时
        cursor.close()
```

**效果**：
- 读写可以并发进行
- 写入性能提升 2-3 倍
- 减少锁等待时间

#### 1.2 添加任务数量限制

**文件**：`backend/routers/reading.py`

```python
from fastapi import HTTPException

MAX_CONCURRENT_TASKS = 5  # 最大并发任务数

async def start_quant(request, user, db):
    # 检查并发任务数
    running_count = sum(
        1 for t in tasks.values() 
        if t.get("status") == "running" 
        and t.get("owner_user_id") == user.id
    )
    if running_count >= MAX_CONCURRENT_TASKS:
        raise HTTPException(
            status_code=429, 
            detail="您有太多任务正在运行，请等待当前任务完成后再试。"
        )
    
    # 继续原有逻辑...
```

**效果**：
- 防止单个用户占用过多资源
- 避免系统过载

#### 1.3 队列位置与预估等待时间

**设计目标**：当系统繁忙时，让用户看到自己的排队位置和预估等待时间，而不是直接拒绝。

**文件**：`backend/services/queue_manager.py`（新建）

```python
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class TaskQueueManager:
    """任务队列管理器"""
    
    def __init__(self):
        # 队列: [(task_id, user_id, created_at, task_type), ...]
        self._queue: list[dict] = []
        # 正在运行的任务: {task_id: {start_time, task_type, ...}}
        self._running: dict[str, dict] = {}
        # 历史任务平均耗时（秒）
        self._avg_duration: dict[str, float] = {
            "quant": 600,      # 七步精读约 10 分钟
            "qual": 480,       # 四步精读约 8 分钟
            "long": 720,       # 长文本精读约 12 分钟
            "reference": 300,  # 参考文献梳理约 5 分钟
            "filter": 180,     # 文献筛选约 3 分钟
        }
    
    def enqueue(self, task_id: str, user_id: int, task_type: str) -> dict:
        """将任务加入队列，返回队列信息"""
        entry = {
            "task_id": task_id,
            "user_id": user_id,
            "task_type": task_type,
            "created_at": datetime.now(),
        }
        self._queue.append(entry)
        
        position = self._get_position(task_id)
        estimated_wait = self._estimate_wait_seconds(position, task_type)
        
        logger.info(f"Task {task_id} enqueued at position {position}, "
                    f"estimated wait: {estimated_wait}s")
        
        return {
            "queue_position": position,
            "estimated_wait_seconds": estimated_wait,
            "estimated_wait_minutes": round(estimated_wait / 60, 1),
        }
    
    def dequeue_next(self) -> Optional[dict]:
        """从队列取出下一个任务"""
        if self._queue:
            return self._queue.pop(0)
        return None
    
    def mark_running(self, task_id: str):
        """标记任务为运行中"""
        self._running[task_id] = {
            "start_time": datetime.now(),
        }
        # 从队列中移除（如果还在）
        self._queue = [t for t in self._queue if t["task_id"] != task_id]
    
    def mark_completed(self, task_id: str):
        """标记任务完成"""
        if task_id in self._running:
            start_time = self._running[task_id]["start_time"]
            duration = (datetime.now() - start_time).total_seconds()
            
            # 更新平均耗时（移动平均）
            task_type = self._running[task_id].get("task_type", "quant")
            if task_type in self._avg_duration:
                old_avg = self._avg_duration[task_type]
                self._avg_duration[task_type] = old_avg * 0.8 + duration * 0.2
            
            del self._running[task_id]
            logger.info(f"Task {task_id} completed, duration: {duration}s")
    
    def _get_position(self, task_id: str) -> int:
        """获取任务在队列中的位置"""
        for i, entry in enumerate(self._queue):
            if entry["task_id"] == task_id:
                return i + 1
        return 0
    
    def _estimate_wait_seconds(self, position: int, task_type: str) -> int:
        """预估等待时间（秒）"""
        if position <= 0:
            return 0
        
        avg_duration = self._avg_duration.get(task_type, 600)
        running_count = len(self._running)
        
        # 假设所有运行中的任务平均剩余时间
        avg_remaining = avg_duration / 2
        
        # 等待时间 = 队列前面的任务数 * 平均耗时 / 并发数 + 运行中任务的剩余时间
        if running_count > 0:
            estimated = (position - 1) * avg_duration / max(running_count, 1) + avg_remaining
        else:
            estimated = (position - 1) * avg_duration
        
        return int(estimated)
    
    def get_queue_status(self) -> dict:
        """获取队列状态"""
        return {
            "queue_length": len(self._queue),
            "running_count": len(self._running),
            "running_tasks": [
                {
                    "task_id": tid,
                    "start_time": info["start_time"].isoformat(),
                    "running_seconds": int((datetime.now() - info["start_time"]).total_seconds()),
                }
                for tid, info in self._running.items()
            ],
            "queue_tasks": [
                {
                    "task_id": entry["task_id"],
                    "position": i + 1,
                    "task_type": entry["task_type"],
                    "waiting_seconds": int((datetime.now() - entry["created_at"]).total_seconds()),
                }
                for i, entry in enumerate(self._queue)
            ],
        }
    
    def get_task_queue_info(self, task_id: str) -> Optional[dict]:
        """获取特定任务的队列信息"""
        # 检查是否在队列中
        position = self._get_position(task_id)
        if position > 0:
            entry = self._queue[position - 1]
            estimated_wait = self._estimate_wait_seconds(position, entry["task_type"])
            return {
                "status": "queued",
                "queue_position": position,
                "estimated_wait_seconds": estimated_wait,
                "estimated_wait_minutes": round(estimated_wait / 60, 1),
                "waiting_seconds": int((datetime.now() - entry["created_at"]).total_seconds()),
            }
        
        # 检查是否在运行中
        if task_id in self._running:
            start_time = self._running[task_id]["start_time"]
            return {
                "status": "running",
                "running_seconds": int((datetime.now() - start_time).total_seconds()),
            }
        
        return None

# 全局实例
task_queue = TaskQueueManager()
```

**文件**：`backend/routers/reading.py`（修改）

```python
from services.queue_manager import task_queue

MAX_CONCURRENT_TASKS = 5  # 最大并发任务数
MAX_QUEUE_SIZE = 10       # 最大队列长度

async def start_quant(request, user, db):
    """启动七步精读"""
    # 检查并发任务数
    running_count = sum(
        1 for t in tasks.values() 
        if t.get("status") == "running" 
        and t.get("owner_user_id") == user.id
    )
    
    # 检查队列长度
    queue_status = task_queue.get_queue_status()
    
    if running_count >= MAX_CONCURRENT_TASKS:
        if queue_status["queue_length"] >= MAX_QUEUE_SIZE:
            raise HTTPException(
                status_code=503, 
                detail={
                    "message": "系统繁忙，队列已满，请稍后再试。",
                    "queue_length": queue_status["queue_length"],
                    "running_count": queue_status["running_count"],
                }
            )
        
        # 加入队列而不是直接拒绝
        queue_info = task_queue.enqueue(task_id, user.id, "quant")
        
        # 返回排队信息
        return {
            "task_id": task_id,
            "status": "queued",
            "queue_position": queue_info["queue_position"],
            "estimated_wait_seconds": queue_info["estimated_wait_seconds"],
            "estimated_wait_minutes": queue_info["estimated_wait_minutes"],
            "message": f"您排在第 {queue_info['queue_position']} 位，"
                      f"预计等待 {queue_info['estimated_wait_minutes']} 分钟"
        }
    
    # 直接执行...
```

**文件**：`backend/routers/reading.py`（查询状态）

```python
async def get_task_status(task_id: str, user):
    """查询任务状态"""
    # 先从队列管理器获取信息
    queue_info = task_queue.get_task_queue_info(task_id)
    
    if queue_info:
        if queue_info["status"] == "queued":
            return {
                "status": "queued",
                "progress": 0,
                "stage": f"排队中 (第 {queue_info['queue_position']} 位)",
                "queue_position": queue_info["queue_position"],
                "estimated_wait_seconds": queue_info["estimated_wait_seconds"],
                "estimated_wait_minutes": queue_info["estimated_wait_minutes"],
                "waiting_seconds": queue_info["waiting_seconds"],
                "logs": [
                    f"任务已加入队列",
                    f"排队位置: 第 {queue_info['queue_position']} 位",
                    f"预计等待: {queue_info['estimated_wait_minutes']} 分钟",
                    f"已等待: {queue_info['waiting_seconds']} 秒",
                ],
            }
        elif queue_info["status"] == "running":
            # 继续获取详细的任务进度
            task_data = tasks.get(task_id, {})
            return {
                "status": "running",
                "progress": task_data.get("progress", 0),
                "stage": task_data.get("stage", "处理中..."),
                "logs": task_data.get("logs", []),
                "running_seconds": queue_info["running_seconds"],
            }
    
    # 任务已完成或不存在
    task_data = tasks.get(task_id)
    if not task_data:
        raise HTTPException(404, "任务不存在")
    
    return task_data
```

**前端展示**（`frontend/src/components/TaskProgress.tsx`）：

```tsx
function TaskProgress({ taskStatus }) {
  if (taskStatus.status === "queued") {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <ClockIcon className="w-5 h-5 text-blue-500" />
          <span className="font-medium text-blue-700">排队中</span>
        </div>
        <div className="space-y-2 text-sm text-blue-600">
          <div className="flex justify-between">
            <span>排队位置</span>
            <span className="font-medium">第 {taskStatus.queue_position} 位</span>
          </div>
          <div className="flex justify-between">
            <span>预计等待</span>
            <span className="font-medium">{taskStatus.estimated_wait_minutes} 分钟</span>
          </div>
          <div className="flex justify-between">
            <span>已等待</span>
            <span className="font-medium">{taskStatus.waiting_seconds} 秒</span>
          </div>
        </div>
        {/* 进度条显示队列进度 */}
        <div className="mt-3">
          <div className="h-2 bg-blue-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${Math.max(10, 100 - taskStatus.queue_position * 20)}%` }}
            />
          </div>
        </div>
      </div>
    );
  }
  
  if (taskStatus.status === "running") {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <PlayIcon className="w-5 h-5 text-green-500" />
          <span className="font-medium text-green-700">执行中</span>
        </div>
        <div className="text-sm text-green-600 mb-2">{taskStatus.stage}</div>
        {/* 进度条 */}
        <div className="h-2 bg-green-100 rounded-full overflow-hidden">
          <div 
            className="h-full bg-green-500 transition-all"
            style={{ width: `${taskStatus.progress}%` }}
          />
        </div>
        <div className="mt-2 text-xs text-green-500 text-right">
          {taskStatus.progress}%
        </div>
      </div>
    );
  }
  
  // ... 其他状态
}
```

**效果**：
- 用户可以看到自己在队列中的位置
- 用户可以预估需要等待多长时间
- 用户可以实时看到已等待的时间
- 系统繁忙时不是直接拒绝，而是给用户明确的预期

#### 1.4 内存监控和限制

**文件**：`backend/monitoring.py`（新建）

```python
import psutil
import logging

logger = logging.getLogger(__name__)

def check_memory_usage():
    """检查内存使用情况"""
    memory = psutil.virtual_memory()
    usage_percent = memory.percent
    
    if usage_percent > 85:
        logger.warning(f"内存使用率过高: {usage_percent}%")
        return False
    return True

def get_system_stats():
    """获取系统统计信息"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_used_mb": psutil.virtual_memory().used / 1024 / 1024,
        "memory_total_mb": psutil.virtual_memory().total / 1024 / 1024,
        "disk_usage_percent": psutil.disk_usage('/').percent,
    }
```

**效果**：
- 实时监控系统资源
- 在资源不足时提前告警

---

### 阶段 2：任务队列改造（第 2-3 周）

**目标**：将后台任务从线程迁移到 Celery，支持任务持久化和分布式执行

#### 2.1 安装依赖

**文件**：`backend/requirements.txt`

```txt
# 新增依赖
celery[redis]>=5.3.0
redis>=5.0.0
flower>=2.0.0  # Celery 监控工具
```

#### 2.2 配置 Celery

**文件**：`backend/celery_app.py`（新建）

```python
from celery import Celery
from celery.schedules import crontab
import os

# 创建 Celery 实例
celery_app = Celery(
    "deep_reading_agent",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "tasks.reading",
        "tasks.filter",
        "tasks.references",
    ]
)

# Celery 配置
celery_app.conf.update(
    # 序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,
    
    # 任务超时
    task_soft_time_limit=1800,  # 30 分钟软超时
    task_time_limit=2400,       # 40 分钟硬超时
    
    # 任务重试
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # 结果过期
    result_expires=3600,  # 1 小时后过期
    
    # Worker 配置
    worker_prefetch_multiplier=1,  # 每次只预取 1 个任务
    worker_max_tasks_per_child=50,  # 每个 worker 最多执行 50 个任务后重启
    
    # 并发限制
    worker_concurrency=2,  # 每个 worker 2 个并发
)

# 定时任务（可选）
celery_app.conf.beat_schedule = {
    "cleanup-expired-tasks": {
        "task": "tasks.cleanup.cleanup_expired_tasks",
        "schedule": crontab(hour=0, minute=0),  # 每天凌晨执行
    },
}
```

#### 2.3 定义任务

**文件**：`backend/tasks/reading.py`（新建）

```python
from celery_app import celery_app
from services.deepseek_refs import extract_references_deepseek, trace_citations_deepseek
import logging

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="tasks.reading.run_quant_task")
def run_quant_task(
    self,
    task_id: str,
    user_id: int,
    bib_entry_id: str,
    file_path: str,
    prompt_overrides: dict,
    api_key: str = None,
):
    """七步精读任务"""
    try:
        # 更新任务状态
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": 10,
                "stage": "提取 PDF...",
                "logs": ["[步骤 1/7] 提取 PDF..."]
            }
        )
        
        # 执行任务逻辑...
        # 注意：这里需要将原来 run_quant_task 的逻辑迁移过来
        
        return {
            "status": "completed",
            "progress": 100,
            "stage": "完成",
            "result": {...}
        }
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise

@celery_app.task(bind=True, name="tasks.reading.run_qual_task")
def run_qual_task(self, ...):
    """四步精读任务"""
    # 类似实现...

@celery_app.task(bind=True, name="tasks.reading.run_long_context_task")
def run_long_context_task(self, ...):
    """长文本精读任务"""
    # 类似实现...
```

**文件**：`backend/tasks/references.py`（新建）

```python
from celery_app import celery_app
from services.deepseek_refs import extract_references_deepseek, trace_citations_deepseek

@celery_app.task(bind=True, name="tasks.references.run_reference_trace_task")
def run_reference_trace_task(
    self,
    task_id: str,
    user_id: int,
    source_bib_entry_id: str,
    file_path: str,
    source_title: str,
    api_key: str = None,
):
    """参考文献梳理任务"""
    try:
        # 更新进度
        self.update_state(
            state="PROGRESS",
            meta={"progress": 10, "stage": "读取 PDF..."}
        )
        
        # 提取参考文献
        references = extract_references_deepseek(file_path, api_key=api_key)
        
        # 追踪引用
        self.update_state(
            state="PROGRESS",
            meta={"progress": 50, "stage": "追踪正文引用..."}
        )
        references = trace_citations_deepseek(file_path, references, api_key=api_key)
        
        # 写入数据库...
        
        return {"status": "completed", "references": references}
        
    except Exception as e:
        logger.error(f"Reference trace task {task_id} failed: {e}")
        raise
```

#### 2.4 修改路由层

**文件**：`backend/routers/reading.py`

```python
from celery_app import celery_app
from tasks.reading import run_quant_task, run_qual_task

async def start_quant(request, user, db):
    """启动七步精读"""
    # 创建任务记录...
    
    # 提交到 Celery
    celery_task = run_quant_task.delay(
        task_id=task_id,
        user_id=user.id,
        bib_entry_id=bib_entry.id,
        file_path=file_path,
        prompt_overrides=prompt_overrides,
        api_key=request.api_key,
    )
    
    # 存储 Celery 任务 ID
    tasks[task_id] = {
        "celery_task_id": celery_task.id,
        "owner_user_id": user.id,
        "status": "queued",
        ...
    }
    
    return {"task_id": task_id, "status": "queued"}

async def get_task_status(task_id, user):
    """查询任务状态"""
    task_info = tasks.get(task_id)
    if not task_info:
        raise HTTPException(404, "任务不存在")
    
    # 从 Celery 获取最新状态
    celery_task = celery_app.AsyncResult(task_info["celery_task_id"])
    
    if celery_task.state == "PROGRESS":
        return {
            "status": "running",
            "progress": celery_task.info.get("progress", 0),
            "stage": celery_task.info.get("stage", ""),
            "logs": celery_task.info.get("logs", []),
        }
    elif celery_task.state == "SUCCESS":
        return {
            "status": "completed",
            "progress": 100,
            "result": celery_task.result,
        }
    elif celery_task.state == "FAILURE":
        return {
            "status": "failed",
            "error": str(celery_task.result),
        }
    else:
        return {
            "status": "queued",
            "progress": 0,
        }
```

#### 2.5 Redis 配置

**文件**：`.env`

```bash
# Redis 配置
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=your_redis_password

# Celery 配置
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

**安装 Redis**：

```bash
# Ubuntu
sudo apt update
sudo apt install redis-server

# 启动 Redis
sudo systemctl start redis
sudo systemctl enable redis

# 验证
redis-cli ping
# 应该返回 PONG
```

---

### 阶段 3：数据库迁移（第 3-4 周）

**目标**：从 SQLite 迁移到 PostgreSQL，彻底解决并发写入问题

#### 3.1 安装 PostgreSQL

```bash
# Ubuntu
sudo apt update
sudo apt install postgresql postgresql-contrib

# 启动 PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 创建数据库和用户
sudo -u postgres psql
```

```sql
-- 创建用户
CREATE USER deepreading WITH PASSWORD 'your_password';

-- 创建数据库
CREATE DATABASE deepreading OWNER deepreading;

-- 授权
GRANT ALL PRIVILEGES ON DATABASE deepreading TO deepreading;

-- 退出
\q
```

#### 3.2 更新依赖

**文件**：`backend/requirements.txt`

```txt
# 替换 SQLite 依赖
# aiosqlite>=0.19.0  # 移除

# 添加 PostgreSQL 依赖
asyncpg>=0.29.0
psycopg2-binary>=2.9.9
alembic>=1.13.0
```

#### 3.3 更新数据库配置

**文件**：`backend/db/session.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

# PostgreSQL 连接字符串
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://deepreading:your_password@localhost:5432/deepreading"
)

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,           # 连接池大小
    max_overflow=10,        # 最大溢出连接
    pool_timeout=30,        # 连接超时
    pool_recycle=1800,      # 连接回收时间
    echo=False,             # 不打印 SQL
)

# 创建异步会话
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with async_session() as session:
        yield session
```

#### 3.4 数据迁移脚本

**文件**：`scripts/migrate_sqlite_to_postgres.py`（新建）

```python
"""
SQLite → PostgreSQL 数据迁移脚本

使用方法:
    python scripts/migrate_sqlite_to_postgres.py --dry-run  # 先测试
    python scripts/migrate_sqlite_to_postgres.py            # 正式迁移
"""

import sqlite3
import asyncio
import asyncpg
import argparse
from datetime import datetime

# 表迁移顺序（考虑外键依赖）
TABLES_TO_MIGRATE = [
    "users",
    "invite_codes",
    "files",
    "bib_entries",
    "bib_references",
    "bib_reference_citations",
    "bib_filter_links",
    "jobs",
    "job_bib_entries",
    "artifacts",
    "reading_items",
    "prompt_templates",
]

async def migrate_table(sqlite_conn, pg_conn, table_name, dry_run=False):
    """迁移单个表"""
    print(f"\n📦 迁移表: {table_name}")
    
    # 从 SQLite 读取数据
    cursor = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    
    print(f"   找到 {len(rows)} 条记录")
    
    if dry_run:
        print(f"   [DRY RUN] 跳过写入")
        return
    
    if not rows:
        print(f"   表为空，跳过")
        return
    
    # 构建 INSERT 语句
    placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
    columns_str = ", ".join(columns)
    insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
    
    # 批量插入
    success_count = 0
    error_count = 0
    
    for row in rows:
        try:
            await pg_conn.execute(insert_sql, *row)
            success_count += 1
        except Exception as e:
            error_count += 1
            print(f"   ⚠️ 插入失败: {e}")
    
    print(f"   ✅ 成功: {success_count}, ❌ 失败: {error_count}")

async def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 迁移")
    parser.add_argument("--dry-run", action="store_true", help="测试模式，不实际写入")
    parser.add_argument("--sqlite-path", default="db/app.sqlite", help="SQLite 数据库路径")
    parser.add_argument("--pg-url", default="postgresql://deepreading:your_password@localhost:5432/deepreading", help="PostgreSQL 连接 URL")
    args = parser.parse_args()
    
    print("=" * 60)
    print("📊 SQLite → PostgreSQL 数据迁移")
    print("=" * 60)
    print(f"源数据库: {args.sqlite_path}")
    print(f"目标数据库: {args.pg_url.split('@')[1]}")  # 隐藏密码
    print(f"模式: {'DRY RUN' if args.dry_run else '正式迁移'}")
    print("=" * 60)
    
    # 连接数据库
    sqlite_conn = sqlite3.connect(args.sqlite_path)
    pg_conn = await asyncpg.connect(args.pg_url)
    
    try:
        # 按顺序迁移表
        for table in TABLES_TO_MIGRATE:
            await migrate_table(sqlite_conn, pg_conn, table, args.dry_run)
        
        print("\n" + "=" * 60)
        print("✅ 迁移完成！")
        print("=" * 60)
        
    finally:
        sqlite_conn.close()
        await pg_conn.close()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 3.5 Alembic 迁移

```bash
# 初始化 Alembic（如果还没有）
cd backend
alembic init migrations

# 生成迁移脚本
alembic revision --autogenerate -m "migrate_to_postgresql"

# 执行迁移
alembic upgrade head
```

---

### 阶段 4：多 Worker 部署（第 4-5 周）

**目标**：部署多个 Uvicorn Worker，提高 API 并发处理能力

#### 4.1 更新启动脚本

**文件**：`start.sh`

```bash
#!/bin/bash
# Deep Reading Agent 启动脚本 (v2)
set -e

echo "=== 停止旧进程 ==="
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "celery" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 2

echo "=== 启动 Redis ==="
sudo systemctl start redis

echo "=== 启动后端 (FastAPI + 多 Worker) ==="
cd /root/.openclaw/workspace/deep-reading-agent/backend
source ../venv/bin/activate
nohup uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 3 \
    --worker-class uvicorn.workers.UvicornWorker \
    --limit-concurrency 100 \
    --limit-max-requests 1000 \
    --timeout-keep-alive 30 \
    > /tmp/fastapi.log 2>&1 &
echo "Backend PID: $!"

echo "=== 启动 Celery Worker ==="
nohup celery -A celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --max-tasks-per-child=50 \
    > /tmp/celery.log 2>&1 &
echo "Celery Worker PID: $!"

echo "=== 启动 Celery Beat (定时任务) ==="
nohup celery -A celery_app beat \
    --loglevel=info \
    > /tmp/celery_beat.log 2>&1 &
echo "Celery Beat PID: $!"

echo "=== 启动 Flower (Celery 监控) ==="
nohup celery -A celery_app flower \
    --port=5555 \
    --basic-auth=admin:your_password \
    > /tmp/flower.log 2>&1 &
echo "Flower PID: $!"

echo "=== 启动前端 (Vite) ==="
cd /root/.openclaw/workspace/deep-reading-agent/frontend
nohup npm run dev > /tmp/vite.log 2>&1 &
echo "Frontend PID: $!"

echo "=== 启动 Tunnel ==="
nohup cloudflared tunnel --config /root/.cloudflared/config.yml run > /tmp/cloudflared.log 2>&1 &
echo "Tunnel PID: $!"

sleep 5
echo ""
echo "=== 健康检查 ==="
curl -s http://localhost:8000/health && echo " ✅ Backend"
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ && echo " ✅ Frontend"
curl -s -o /dev/null -w "%{http_code}" https://deepreading.qzz.io/ && echo " ✅ Tunnel"
redis-cli ping && echo " ✅ Redis"
celery -A celery_app status && echo " ✅ Celery"
echo ""
echo "=== 监控地址 ==="
echo "Flower (Celery 监控): http://localhost:5555"
echo "全部启动完成。"
```

#### 4.2 共享状态管理

由于多个 Worker 不能共享内存中的 `tasks` 字典，需要改用 Redis 存储任务状态：

**文件**：`backend/state/redis_state.py`（新建）

```python
import redis
import json
from typing import Optional
import os

class TaskStateManager:
    """基于 Redis 的任务状态管理"""
    
    def __init__(self):
        self.redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD"),
            db=0,
            decode_responses=True,
        )
        self.prefix = "task:"
        self.default_ttl = 3600 * 24  # 24 小时过期
    
    def _key(self, task_id: str) -> str:
        return f"{self.prefix}{task_id}"
    
    def set_task(self, task_id: str, task_data: dict):
        """设置任务状态"""
        key = self._key(task_id)
        self.redis.setex(
            key,
            self.default_ttl,
            json.dumps(task_data, ensure_ascii=False, default=str)
        )
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        key = self._key(task_id)
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    def update_task(self, task_id: str, updates: dict):
        """更新任务状态"""
        task_data = self.get_task(task_id)
        if task_data:
            task_data.update(updates)
            self.set_task(task_id, task_data)
    
    def delete_task(self, task_id: str):
        """删除任务状态"""
        key = self._key(task_id)
        self.redis.delete(key)
    
    def get_user_tasks(self, user_id: int) -> list:
        """获取用户的所有任务"""
        pattern = f"{self.prefix}*"
        tasks = []
        for key in self.redis.scan_iter(match=pattern):
            data = self.redis.get(key)
            if data:
                task = json.loads(data)
                if task.get("owner_user_id") == user_id:
                    tasks.append(task)
        return tasks
    
    def get_running_count(self, user_id: int) -> int:
        """获取用户正在运行的任务数"""
        tasks = self.get_user_tasks(user_id)
        return sum(1 for t in tasks if t.get("status") == "running")

# 全局实例
task_state = TaskStateManager()
```

#### 4.3 更新路由层使用 Redis

**文件**：`backend/routers/reading.py`

```python
from state.redis_state import task_state

async def start_quant(request, user, db):
    """启动七步精读"""
    # 检查并发任务数
    running_count = task_state.get_running_count(user.id)
    if running_count >= MAX_CONCURRENT_TASKS:
        raise HTTPException(429, "任务数过多，请等待当前任务完成")
    
    # 创建任务记录...
    
    # 初始化任务状态
    task_state.set_task(task_id, {
        "task_id": task_id,
        "owner_user_id": user.id,
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "created_at": datetime.now().isoformat(),
    })
    
    # 提交到 Celery...
    
    return {"task_id": task_id, "status": "queued"}

async def get_task_status(task_id, user):
    """查询任务状态"""
    task_data = task_state.get_task(task_id)
    if not task_data:
        raise HTTPException(404, "任务不存在")
    
    # 验证权限
    if task_data["owner_user_id"] != user.id:
        raise HTTPException(403, "无权访问此任务")
    
    return task_data
```

---

### 阶段 5：监控与告警（第 5-6 周）

**目标**：建立完善的监控体系，及时发现和处理问题

#### 5.1 系统监控

**文件**：`backend/monitoring/system_monitor.py`（新建）

```python
import psutil
import redis
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SystemMonitor:
    """系统监控"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.metrics_key = "system:metrics"
    
    def collect_metrics(self) -> dict:
        """收集系统指标"""
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": cpu,
            "memory_percent": memory.percent,
            "memory_used_mb": memory.used / 1024 / 1024,
            "memory_total_mb": memory.total / 1024 / 1024,
            "disk_percent": disk.percent,
            "disk_used_gb": disk.used / 1024 / 1024 / 1024,
            "disk_total_gb": disk.total / 1024 / 1024 / 1024,
        }
    
    def store_metrics(self, metrics: dict):
        """存储指标到 Redis"""
        # 存储最新指标
        self.redis.hset(self.metrics_key, mapping=metrics)
        
        # 存储历史指标（保留 24 小时）
        history_key = f"metrics:history:{datetime.now().strftime('%Y%m%d%H')}"
        self.redis.lpush(history_key, str(metrics))
        self.redis.expire(history_key, 86400)
    
    def check_alerts(self, metrics: dict) -> list:
        """检查告警条件"""
        alerts = []
        
        if metrics["cpu_percent"] > 90:
            alerts.append({
                "level": "critical",
                "message": f"CPU 使用率过高: {metrics['cpu_percent']}%"
            })
        elif metrics["cpu_percent"] > 80:
            alerts.append({
                "level": "warning",
                "message": f"CPU 使用率较高: {metrics['cpu_percent']}%"
            })
        
        if metrics["memory_percent"] > 90:
            alerts.append({
                "level": "critical",
                "message": f"内存使用率过高: {metrics['memory_percent']}%"
            })
        elif metrics["memory_percent"] > 80:
            alerts.append({
                "level": "warning",
                "message": f"内存使用率较高: {metrics['memory_percent']}%"
            })
        
        if metrics["disk_percent"] > 90:
            alerts.append({
                "level": "critical",
                "message": f"磁盘使用率过高: {metrics['disk_percent']}%"
            })
        
        return alerts
    
    async def run(self, interval=60):
        """运行监控循环"""
        logger.info("系统监控启动")
        while True:
            try:
                metrics = self.collect_metrics()
                self.store_metrics(metrics)
                
                alerts = self.check_alerts(metrics)
                for alert in alerts:
                    logger.warning(f"[{alert['level'].upper()}] {alert['message']}")
                    # 这里可以添加告警通知逻辑（邮件、钉钉等）
                    
            except Exception as e:
                logger.error(f"监控异常: {e}")
            
            await asyncio.sleep(interval)
```

#### 5.2 任务监控

**文件**：`backend/monitoring/task_monitor.py`（新建）

```python
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class TaskMonitor:
    """任务监控"""
    
    def __init__(self, task_state, redis_client):
        self.task_state = task_state
        self.redis = redis_client
    
    def get_task_stats(self) -> dict:
        """获取任务统计"""
        # 从 Celery 获取统计
        # 这里简化实现，实际需要调用 Celery API
        
        return {
            "total_tasks": 0,
            "running_tasks": 0,
            "queued_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "avg_duration_seconds": 0,
        }
    
    def check_stuck_tasks(self, timeout_minutes=30):
        """检查卡住的任务"""
        # 实现检查逻辑...
        pass
    
    def cleanup_old_tasks(self, days=7):
        """清理旧任务"""
        # 实现清理逻辑...
        pass
```

#### 5.3 监控 API

**文件**：`backend/routers/monitoring.py`（新建）

```python
from fastapi import APIRouter, Depends, HTTPException
from auth.dependencies import require_admin
from monitoring.system_monitor import SystemMonitor
from monitoring.task_monitor import TaskMonitor

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

@router.get("/system")
async def get_system_metrics(admin=Depends(require_admin)):
    """获取系统指标（仅管理员）"""
    monitor = SystemMonitor(redis_client)
    metrics = monitor.collect_metrics()
    return metrics

@router.get("/tasks")
async def get_task_stats(admin=Depends(require_admin)):
    """获取任务统计（仅管理员）"""
    monitor = TaskMonitor(task_state, redis_client)
    stats = monitor.get_task_stats()
    return stats

@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
    }
```

#### 5.4 配置 Nginx 监控

**文件**：`/etc/nginx/conf.d/deepreading-monitor.conf`

```nginx
# Flower 监控（仅内网访问）
server {
    listen 5555;
    server_name localhost;
    
    location / {
        proxy_pass http://127.0.0.1:5555;
        proxy_set_header Host $host;
        
        # IP 白名单
        allow 127.0.0.1;
        allow 10.0.0.0/8;
        deny all;
    }
}
```

---

## 4. 服务器资源规划

### 4.1 当前配置

| 资源 | 当前值 |
|------|--------|
| CPU | 2 核 |
| 内存 | 4 GB |
| 磁盘 | 40 GB |
| 带宽 | 5 Mbps |

### 4.2 推荐配置（10+ 用户）

| 资源 | 推荐值 | 说明 |
|------|--------|------|
| CPU | 4 核 | 支持多 Worker 并行 |
| 内存 | 8 GB | PostgreSQL + Redis + 多 Worker |
| 磁盘 | 100 GB | 数据库 + 文件存储 |
| 带宽 | 10 Mbps | 多用户并发上传下载 |

### 4.3 成本估算

| 云服务商 | 配置 | 月费（约） |
|----------|------|------------|
| 阿里云 | ecs.c7.xlarge (4C8G) | ¥300-400 |
| 腾讯云 | S5.MEDIUM4 (4C8G) | ¥250-350 |
| AWS | t3.large (2C8G) | $60-80 |

---

## 5. 迁移检查清单

### 5.1 阶段 1 检查清单

- [ ] SQLite WAL 模式已启用
- [ ] 任务数量限制已添加
- [ ] 任务超时机制已实现
- [ ] 内存监控已部署
- [ ] 压力测试通过（3 并发用户）

### 5.2 阶段 2 检查清单

- [ ] Redis 已安装并运行
- [ ] Celery 已配置并测试
- [ ] 任务已迁移到 Celery
- [ ] Flower 监控已部署
- [ ] 压力测试通过（5 并发用户）

### 5.3 阶段 3 检查清单

- [ ] PostgreSQL 已安装并配置
- [ ] 数据迁移脚本已测试
- [ ] 数据迁移已完成
- [ ] Alembic 迁移已执行
- [ ] 应用已切换到 PostgreSQL
- [ ] 压力测试通过（8 并发用户）

### 5.4 阶段 4 检查清单

- [ ] 多 Worker 已部署
- [ ] Redis 状态管理已实现
- [ ] 路由层已更新
- [ ] 负载均衡已配置
- [ ] 压力测试通过（10 并发用户）

### 5.5 阶段 5 检查清单

- [ ] 系统监控已部署
- [ ] 任务监控已部署
- [ ] 告警规则已配置
- [ ] 监控面板已创建
- [ ] 文档已更新

---

## 6. 风险与回滚方案

### 6.1 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 数据迁移失败 | 中 | 高 | 先在测试环境验证，保留原数据库备份 |
| PostgreSQL 性能不如预期 | 低 | 中 | 性能测试，必要时回退到 SQLite |
| Redis 服务中断 | 低 | 中 | 配置 Redis 持久化，添加哨兵 |
| Celery 任务丢失 | 低 | 中 | 启用任务确认机制，配置重试 |
| 多 Worker 状态不同步 | 中 | 高 | 使用 Redis 存储共享状态 |

### 6.2 回滚方案

**阶段 1 回滚**：
```bash
# 禁用 WAL 模式
PRAGMA journal_mode=DELETE;
```

**阶段 2 回滚**：
```bash
# 停止 Celery
pkill -f celery

# 恢复线程模式（需要代码回滚）
git checkout HEAD~1 backend/routers/reading.py
```

**阶段 3 回滚**：
```bash
# 恢复 SQLite
cp db/backups/app.sqlite.bak db/app.sqlite

# 恢复配置
git checkout HEAD~1 backend/db/session.py
```

**阶段 4 回滚**：
```bash
# 恢复单 Worker
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## 7. 时间表

```
第 1 周: 阶段 1 - 短期优化
    ├── 周一-周二: SQLite WAL 模式 + 任务限制
    ├── 周三-周四: 任务超时 + 内存监控
    └── 周五: 测试验证

第 2-3 周: 阶段 2 - 任务队列改造
    ├── 周一-周三: Redis + Celery 配置
    ├── 周四-周五: 任务迁移
    └── 周六-周日: 测试验证

第 3-4 周: 阶段 3 - 数据库迁移
    ├── 周一-周三: PostgreSQL 配置
    ├── 周四-周五: 数据迁移
    └── 周六-周日: 测试验证

第 4-5 周: 阶段 4 - 多 Worker 部署
    ├── 周一-周三: Worker 配置
    ├── 周四-周五: 状态管理
    └── 周六-周日: 压力测试

第 5-6 周: 阶段 5 - 监控与告警
    ├── 周一-周三: 监控部署
    ├── 周四-周五: 告警配置
    └── 周六-周日: 文档更新 + 最终测试
```

---

## 8. 总结

### 迁移收益

| 指标 | 迁移前 | 迁移后 | 提升 |
|------|--------|--------|------|
| 并发用户 | 2-3 | 10-15 | 5x |
| 任务可靠性 | ~95% | >99% | +4% |
| API 响应时间 | <200ms | <100ms | 2x |
| 数据持久化 | 进程重启丢失 | 完全持久化 | ∞ |
| 可观测性 | 无 | 完整监控 | ∞ |

### 投入产出比

- **投入**：4-6 周开发时间 + 服务器升级成本（约 ¥300-400/月）
- **产出**：支持 10+ 用户并发，系统可靠性大幅提升，具备扩展能力

### 下一步

1. 确认服务器配置和预算
2. 选择云服务商和服务器规格
3. 开始阶段 1 实施
4. 逐步推进各阶段

---

**文档版本**: v1.0  
**最后更新**: 2026-05-03  
**维护者**: Deep Reading Agent Team
