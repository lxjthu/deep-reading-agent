# Web 前后端分离架构方案

## 目标

将现有 Python 代码拆分为 **REST API 后端** + **独立 Web 前端**，支持多用户并发访问，未来部署到云服务器。

---

## 一、现状分析

### 1.1 现有代码的关键约束

| 维度 | 现状 | 对 Web 化的影响 |
|------|------|-----------------|
| 并发模型 | 全部同步阻塞，零 async 代码 | 单个精读任务需 10-30 分钟，会阻塞进程 |
| 状态管理 | `StateManager` 用单 JSON 文件，无锁 | 多用户同时写入会数据丢失 |
| LLM 调用 | `deepseek-reasoner` 无超时设置，阻塞等待 | 单步可能挂起数分钟 |
| 文件 I/O | 所有中间产物写在本地磁盘固定目录 | 多用户产物会互相覆盖 |
| 进度反馈 | `queue.Queue` + Gradio generator yield | Web 需要 WebSocket 或 SSE 替代 |

### 1.2 不需要改动的部分

核心分析逻辑（7 步深度阅读、4 层金字塔、论文分类）是纯函数式调用，接收文本、返回 Markdown，本身不依赖 Web 框架，可直接复用。

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────┐
│                       用户浏览器                          │
│                    (React / Next.js)                      │
│                                                          │
│  ┌────────┐  ┌────────────┐  ┌───────────┐              │
│  │PDF 提取 │  │ 全流程精读  │  │ 批量处理   │              │
│  └────┬───┘  └─────┬──────┘  └─────┬─────┘              │
│       │            │               │                     │
│       └────────────┴───────────────┘                     │
│                    │  HTTP / SSE                          │
└────────────────────┼─────────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │    Nginx / Caddy     │     反向代理 + 静态文件
          │    (可选, 生产环境)   │
          └──────────┬──────────┘
                     │
     ┌───────────────▼───────────────┐
     │        FastAPI 后端            │
     │                               │
     │  ┌─────────┐  ┌───────────┐  │
     │  │ REST API │  │ SSE 推送   │  │
     │  │ 端点     │  │ 实时日志   │  │
     │  └────┬────┘  └─────┬─────┘  │
     │       │              │        │
     │  ┌────▼──────────────▼────┐  │
     │  │    Celery Worker       │  │     异步任务队列
     │  │    (后台长任务执行)      │  │
     │  └────────────┬───────────┘  │
     │               │              │
     │  ┌────────────▼───────────┐  │
     │  │  现有 Python 分析模块   │  │     不改动核心逻辑
     │  │  paddleocr_pipeline    │  │
     │  │  paddleocr_segment     │  │
     │  │  deep_reading_steps    │  │
     │  │  social_science_*      │  │
     │  │  smart_scholar_lib     │  │
     │  └────────────────────────┘  │
     └───────────────┬───────────────┘
                     │
        ┌────────────▼────────────┐
        │    Redis                 │    任务队列 + 进度缓存
        ├──────────────────────────┤
        │    PostgreSQL / SQLite   │    用户/任务/状态持久化
        ├──────────────────────────┤
        │    对象存储 (S3/MinIO)    │    PDF + 产出文件存储
        └──────────────────────────┘
```

---

## 三、技术选型

### 3.1 后端

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | **FastAPI** | 原生 async、自动 OpenAPI 文档、与 Pydantic 深度集成 |
| 任务队列 | **Celery + Redis** | 长任务异步执行，支持任务取消、重试、进度追踪 |
| 消息代理 | **Redis** | Celery 的 broker，同时用作进度/日志缓存 |
| 数据库 | **PostgreSQL**（生产） / **SQLite**（开发） | 替代现有 JSON 文件，支持并发事务 |
| 文件存储 | **本地磁盘**（开发） / **MinIO/S3**（生产） | PDF 上传 + Markdown 产出 |
| 进程管理 | **Uvicorn + Gunicorn** | 多 worker 进程，提升并发 |

### 3.2 前端

| 组件 | 选型 | 理由 |
|------|------|------|
| 框架 | **Next.js 14+ (App Router)** | SSR/SSG、文件路由、API Route 可做 BFF |
| UI 库 | **shadcn/ui + Tailwind CSS** | 组件质量高、无运行时依赖、样式灵活 |
| 状态管理 | **Zustand** | 轻量，适合中等复杂度 |
| HTTP 客户端 | **fetch API + SSE** | 原生 EventSource 接收实时日志 |
| Markdown 渲染 | **react-markdown + remark-gfm** | 支持 GFM 表格、代码块、数学公式 |
| 文件上传 | **react-dropzone** | 拖拽上传 + 进度条 |

### 3.3 基础设施（云部署）

| 组件 | 选型 | 理由 |
|------|------|------|
| 服务器 | 2 核 4G 起步（如阿里云 ECS、腾讯云 CVM） | Celery worker 可独立扩缩 |
| 容器化 | **Docker Compose**（单机） / **K8s**（规模化） | 一键部署 FastAPI + Celery + Redis + PG |
| 反向代理 | **Caddy** 或 **Nginx** | 自动 HTTPS、静态文件服务 |
| CI/CD | **GitHub Actions** | 自动构建镜像、推送、部署 |

---

## 四、后端 API 设计

### 4.1 目录结构

```
backend/
├── main.py                  # FastAPI 应用入口
├── config.py                # 环境变量、路径配置
├── models.py                # Pydantic 数据模型
├── database.py              # SQLAlchemy / 数据库连接
├── storage.py               # 文件存储抽象层（本地 / S3）
├── api/
│   ├── extraction.py        # Tab 1: PDF 提取接口
│   ├── pipeline.py          # Tab 2: 全流程精读接口
│   ├── batch.py             # Tab 3: 批量处理接口
│   └── tasks.py             # 任务状态查询接口
├── workers/
│   ├── celery_app.py        # Celery 实例配置
│   ├── extraction_task.py   # 提取任务
│   ├── pipeline_task.py     # 全流程任务
│   └── batch_task.py        # 批量任务
├── core/                    # 现有分析模块（符号链接或复制）
│   ├── paddleocr_pipeline.py
│   ├── paddleocr_segment.py
│   ├── deep_read_pipeline.py
│   ├── deep_reading_steps/
│   ├── smart_scholar_lib.py
│   ├── social_science_analyzer_v2.py
│   └── ...
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### 4.2 API 端点

#### 认证（可选，后续扩展）

```
POST   /api/auth/login          # 登录获取 JWT
POST   /api/auth/register       # 注册
```

#### PDF 提取

```
POST   /api/extract             # 上传 PDF，创建提取任务
  Request:  multipart/form-data { file, out_dir?, use_table, use_formula, ... }
  Response: { task_id: "uuid", status: "pending" }

GET    /api/extract/{task_id}   # 查询提取结果
  Response: { status, md_path, metadata, error? }

GET    /api/extract/{task_id}/preview   # 获取 Markdown 预览
  Response: { content: "..." }

GET    /api/extract/{task_id}/download  # 下载提取结果文件
  Response: application/octet-stream
```

#### 全流程精读

```
POST   /api/pipeline            # 上传 PDF，创建全流程任务
  Request:  multipart/form-data { file, method: "paddleocr"|"legacy" }
  Response: { task_id: "uuid", status: "pending" }

GET    /api/pipeline/{task_id}          # 查询任务状态
  Response: { status, current_stage, stages_completed[], output_dir? }

GET    /api/pipeline/{task_id}/stream   # SSE 实时日志流
  Response: text/event-stream
    data: {"type": "log",   "message": "Step 2/7: Theory..."}
    data: {"type": "stage", "stage": 3, "name": "Deep Reading"}
    data: {"type": "done",  "output_dir": "..."}

GET    /api/pipeline/{task_id}/report   # 获取最终报告
  Response: { content: "# Deep Reading Report..." }

POST   /api/pipeline/{task_id}/cancel   # 取消任务
  Response: { status: "cancelling" }
```

#### 批量处理

```
POST   /api/batch                # 创建批量任务
  Request:  { folder_path: "E:\\pdf\\002", skip_processed: true }
  Response: { task_id: "uuid", pdf_count: 15 }

GET    /api/batch/{task_id}      # 查询批量进度
  Response: {
    status: "running",
    progress: [
      { file: "paper1", type: "QUANT", status: "Done",    elapsed: "42.3s" },
      { file: "paper2", type: "QUAL",  status: "Running", elapsed: "..." },
      { file: "paper3", type: "-",     status: "Pending",  elapsed: "-" }
    ],
    summary: { total: 15, done: 5, skipped: 3, failed: 0, running: 1 }
  }

GET    /api/batch/{task_id}/stream  # SSE 实时进度流
POST   /api/batch/{task_id}/cancel  # 取消批量任务
```

#### 通用

```
GET    /api/status               # 环境状态（API 密钥是否配置）
  Response: {
    deepseek: true,
    paddleocr: false,
    qwen_vision: false,
    version: "1.0.0"
  }

GET    /api/tasks                # 列出所有任务
  Query:   ?status=running&type=pipeline&page=1&limit=20
  Response: { tasks: [...], total: 42 }
```

### 4.3 数据模型

```python
# models.py
from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class TaskType(str, Enum):
    EXTRACT = "extract"
    PIPELINE = "pipeline"
    BATCH = "batch"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PaperType(str, Enum):
    QUANT = "QUANT"
    QUAL = "QUAL"
    IGNORE = "IGNORE"

class Task(BaseModel):
    id: str                    # UUID
    type: TaskType
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    current_stage: str | None = None
    progress_pct: float = 0.0  # 0-100
    input_filename: str
    input_file_path: str       # 存储路径
    output_dir: str | None = None
    error: str | None = None
    paper_type: PaperType | None = None

# 数据库表 (SQLAlchemy)
class TaskRecord(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    current_stage = Column(String, nullable=True)
    input_filename = Column(String, nullable=False)
    input_file_hash = Column(String, nullable=True, index=True)  # MD5 去重
    input_storage_key = Column(String, nullable=False)           # S3 key 或本地路径
    output_storage_key = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    paper_type = Column(String, nullable=True)
    meta_json = Column(JSON, nullable=True)                      # 灵活元数据
```

---

## 五、核心改造点

### 5.1 文件存储隔离（必须）

**问题**：当前所有任务写入同一个 `paddleocr_md/`、`pdf_segmented_md/` 等目录，多用户会互相覆盖。

**方案**：按 `task_id` 隔离工作目录。

```python
# storage.py
class TaskStorage:
    """每个任务独立的工作目录"""

    def __init__(self, task_id: str, base_dir: str = "/data/tasks"):
        self.root = os.path.join(base_dir, task_id)
        self.upload_dir = os.path.join(self.root, "upload")
        self.extract_dir = os.path.join(self.root, "paddleocr_md")
        self.segment_dir = os.path.join(self.root, "pdf_segmented_md")
        self.result_dir = os.path.join(self.root, "results")

        for d in [self.upload_dir, self.extract_dir,
                  self.segment_dir, self.result_dir]:
            os.makedirs(d, exist_ok=True)
```

需要修改的调用方：
- `paddleocr_pipeline.extract_with_fallback()` 的 `out_dir` 参数 — 已支持，传入即可
- `paddleocr_segment.segment_paddleocr_md()` 的 `out_dir` 参数 — 已支持
- `deep_read_pipeline.py` 的 `--out_dir` 参数 — 已支持
- `inject_obsidian_meta.py`、`inject_dataview_summaries.py` — 已接受目录参数

现有函数签名已预留了 `out_dir` 参数，改造成本低。

### 5.2 Celery 长任务包装（必须）

将现有的同步函数包装为 Celery task：

```python
# workers/pipeline_task.py
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=0, time_limit=3600, soft_time_limit=3000)
def run_pipeline_task(self, task_id: str, pdf_path: str, method: str):
    """全流程精读 Celery 任务"""
    storage = TaskStorage(task_id)
    redis = get_redis()

    def update_progress(stage: str, message: str):
        """推送进度到 Redis pub/sub，供 SSE 端点读取"""
        redis.publish(f"task:{task_id}:log", json.dumps({
            "type": "log", "stage": stage, "message": message
        }))
        # 同时更新数据库中的 current_stage
        db_update_stage(task_id, stage)

    try:
        # Stage 1
        update_progress("extraction", "Starting PDF extraction...")
        from core.paddleocr_pipeline import extract_with_fallback
        md_path, metadata = extract_with_fallback(
            pdf_path, out_dir=storage.extract_dir
        )

        # Stage 2
        update_progress("segmentation", "Segmenting text...")
        from core.paddleocr_segment import segment_paddleocr_md
        seg_path = segment_paddleocr_md(md_path, out_dir=storage.segment_dir)

        # Stage 3: 7-step deep reading
        update_progress("deep_reading", "Running 7-step analysis...")
        from core.deep_reading_steps import common, step_1_overview, ...
        sections = common.load_segmented_md(seg_path)
        # ... (逐步调用，每步后 update_progress)

        # Stage 4-6: subprocess 调用
        update_progress("supplemental", "Supplemental check...")
        subprocess.run([...], timeout=600)

        update_progress("done", "All stages complete!")
        db_mark_completed(task_id, storage.result_dir)

    except SoftTimeLimitExceeded:
        db_mark_failed(task_id, "Task timed out (50 min limit)")
    except Exception as e:
        db_mark_failed(task_id, str(e))
```

### 5.3 进度推送：Redis Pub/Sub + SSE（必须）

```python
# api/pipeline.py
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/api/pipeline/{task_id}/stream")
async def stream_logs(task_id: str):
    """SSE 实时日志推送"""
    async def event_generator():
        pubsub = redis.pubsub()
        pubsub.subscribe(f"task:{task_id}:log")
        try:
            while True:
                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    yield {"data": message["data"].decode()}
                # 检查任务是否已结束
                task = db_get_task(task_id)
                if task.status in ("completed", "failed", "cancelled"):
                    yield {"data": json.dumps({"type": "done", "status": task.status})}
                    break
                await asyncio.sleep(0.3)
        finally:
            pubsub.unsubscribe()

    return EventSourceResponse(event_generator())
```

### 5.4 StateManager 替换为数据库（必须）

```python
# 原来的 StateManager 逻辑迁移到 SQLAlchemy
class ProcessedPaper(Base):
    __tablename__ = "processed_papers"
    file_hash = Column(String(32), primary_key=True)  # MD5
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False)            # completed / failed
    paper_type = Column(String, nullable=True)
    output_key = Column(String, nullable=True)         # 存储路径
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    error = Column(Text, nullable=True)
```

### 5.5 LLM 调用超时保护（推荐）

现有 `common.call_deepseek()` 没有设置超时。在 Web 场景必须加：

```python
# 修改 deep_reading_steps/common.py
def call_deepseek(client, system_prompt, user_prompt, max_tokens=8000):
    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[...],
            max_tokens=max_tokens,
            timeout=120,          # 添加：单次 API 调用 120 秒超时
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""
```

---

## 六、前端设计

### 6.1 页面结构

```
/                           # 首页 / Dashboard
├── /extract                # Tab 1: PDF 提取
├── /pipeline               # Tab 2: 全流程精读
│   └── /pipeline/{id}      # 单个任务详情 + 实时日志
├── /batch                  # Tab 3: 批量处理
│   └── /batch/{id}         # 批量任务进度
├── /tasks                  # 任务历史列表
│   └── /tasks/{id}         # 任务详情 + 产出文件浏览
└── /settings               # 环境配置检查
```

### 6.2 关键组件

```
components/
├── layout/
│   ├── Sidebar.tsx           # 侧边导航
│   └── Header.tsx            # 顶部状态栏（API 配置状态）
├── extract/
│   ├── ExtractForm.tsx       # 参数表单
│   └── ExtractResult.tsx     # 结果预览
├── pipeline/
│   ├── PipelineForm.tsx      # 上传 + 提取方式选择
│   ├── StageProgress.tsx     # 6 阶段进度条
│   ├── LiveLog.tsx           # 实时日志滚动区（SSE 驱动）
│   └── ReportViewer.tsx      # Markdown 报告渲染
├── batch/
│   ├── BatchForm.tsx         # 路径输入 + 验证
│   ├── ProgressTable.tsx     # 文件进度表格
│   └── BatchSummary.tsx      # 总体统计
├── shared/
│   ├── PdfUploader.tsx       # 拖拽上传组件
│   ├── MarkdownRenderer.tsx  # Markdown 预览（支持数学公式）
│   ├── JsonViewer.tsx        # JSON 元数据展示
│   └── TaskStatusBadge.tsx   # 状态徽章
```

### 6.3 SSE 实时日志对接

```typescript
// hooks/useTaskStream.ts
export function useTaskStream(taskId: string) {
  const [logs, setLogs] = useState<string[]>([]);
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState<"running" | "done" | "error">("running");

  useEffect(() => {
    if (!taskId) return;

    const source = new EventSource(`/api/pipeline/${taskId}/stream`);

    source.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "log":
          setLogs((prev) => [...prev.slice(-500), data.message]);
          break;
        case "stage":
          setStage(data.name);
          break;
        case "done":
          setStatus(data.status === "completed" ? "done" : "error");
          source.close();
          break;
      }
    };

    source.onerror = () => {
      setStatus("error");
      source.close();
    };

    return () => source.close();
  }, [taskId]);

  return { logs, stage, status };
}
```

### 6.4 报告渲染

```tsx
// components/pipeline/ReportViewer.tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export function ReportViewer({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
```

---

## 七、部署方案

### 7.1 Docker Compose（推荐起步方案）

```yaml
# docker-compose.yml
version: "3.9"

services:
  # ---------- 后端 API ----------
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/deepreading
      - REDIS_URL=redis://redis:6379/0
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - PADDLEOCR_REMOTE_URL=${PADDLEOCR_REMOTE_URL}
      - PADDLEOCR_REMOTE_TOKEN=${PADDLEOCR_REMOTE_TOKEN}
      - STORAGE_DIR=/data/tasks
    volumes:
      - task_data:/data/tasks
    depends_on:
      - db
      - redis
    command: >
      gunicorn main:app
      --worker-class uvicorn.workers.UvicornWorker
      --workers 2
      --bind 0.0.0.0:8000
      --timeout 120

  # ---------- Celery Worker ----------
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/deepreading
      - REDIS_URL=redis://redis:6379/0
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - PADDLEOCR_REMOTE_URL=${PADDLEOCR_REMOTE_URL}
      - PADDLEOCR_REMOTE_TOKEN=${PADDLEOCR_REMOTE_TOKEN}
      - STORAGE_DIR=/data/tasks
    volumes:
      - task_data:/data/tasks
    depends_on:
      - db
      - redis
    command: >
      celery -A workers.celery_app worker
      --loglevel=info
      --concurrency=2
      --max-tasks-per-child=50

  # ---------- 前端 ----------
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://api:8000

  # ---------- 基础设施 ----------
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: deepreading
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

  # ---------- 反向代理 ----------
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on:
      - api
      - frontend

volumes:
  task_data:
  redis_data:
  pg_data:
  caddy_data:
```

### 7.2 Caddyfile

```
your-domain.com {
    # 前端
    handle /* {
        reverse_proxy frontend:3000
    }

    # API
    handle /api/* {
        reverse_proxy api:8000
    }

    # SSE 长连接
    handle /api/*/stream {
        reverse_proxy api:8000 {
            flush_interval -1
        }
    }
}
```

### 7.3 后端 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 项目代码
COPY . .

# 数据目录
RUN mkdir -p /data/tasks

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 7.4 服务器配置建议

| 场景 | 配置 | 估算 |
|------|------|------|
| 个人使用 (1-2 并发) | 2 核 4G, 50G SSD | 阿里云约 80 元/月 |
| 小团队 (5-10 并发) | 4 核 8G, 100G SSD | 约 200 元/月 |
| 实验室级 (20+ 并发) | 8 核 16G, 200G SSD, worker 独立节点 | 约 500 元/月 |

主要资源消耗在 Celery worker 的内存（每个任务约 200-500MB）和 DeepSeek API 的 token 费用。

---

## 八、实施路线

### 第一阶段：后端 API 化

| 步骤 | 内容 |
|------|------|
| 1 | 创建 `backend/` 目录，初始化 FastAPI 项目 |
| 2 | 将现有分析模块复制到 `backend/core/`，验证 import 正常 |
| 3 | 实现 `TaskStorage`（文件隔离）和数据库模型 |
| 4 | 包装 PDF 提取为 Celery task + REST 端点 |
| 5 | 实现 Redis pub/sub + SSE 日志推送 |
| 6 | 包装全流程精读为 Celery task，带阶段进度上报 |
| 7 | 包装批量处理，迁移 StateManager 到数据库 |
| 8 | 添加 LLM 调用超时保护 |
| 9 | Docker Compose 本地联调 |

### 第二阶段：前端开发

| 步骤 | 内容 |
|------|------|
| 1 | 初始化 Next.js 项目 + shadcn/ui |
| 2 | 实现布局框架（Sidebar + Header + 状态指示） |
| 3 | 实现 PDF 提取页（表单 + 文件上传 + 结果预览） |
| 4 | 实现 `useTaskStream` Hook（SSE 对接） |
| 5 | 实现全流程精读页（阶段进度 + 实时日志 + 报告预览） |
| 6 | 实现批量处理页（路径验证 + 进度表 + 统计） |
| 7 | 实现任务历史页（列表 + 筛选 + 详情） |
| 8 | 响应式适配 + 深色模式 |

### 第三阶段：部署上线

| 步骤 | 内容 |
|------|------|
| 1 | 编写 Dockerfile + docker-compose.yml |
| 2 | 配置 Caddy 反向代理 + HTTPS |
| 3 | GitHub Actions CI/CD 流水线 |
| 4 | 云服务器部署 + 环境变量配置 |
| 5 | 监控告警（日志收集 + API 健康检查） |

---

## 九、与现有 Gradio GUI 的关系

| 维度 | Gradio GUI (`app.py`) | Web 前后端分离 |
|------|------------------------|----------------|
| 定位 | 本地单人开发调试工具 | 多用户远程服务 |
| 并发 | 1 个用户 | 多用户并发 |
| 部署 | `python app.py` 即用 | Docker Compose |
| 状态 | JSON 文件 | PostgreSQL |
| 进度推送 | Gradio generator yield | SSE / WebSocket |
| 文件隔离 | 无（共用目录） | 每任务独立目录 |

两者可以**共存**。`app.py` 继续作为轻量级本地工具保留，Web 版作为正式部署方案独立开发。核心分析模块 (`deep_reading_steps/`、`paddleocr_pipeline.py` 等) 两边共享，不需要重复维护。

---

## 十、阿里云 ECS 部署指南（Alibaba Cloud Linux 3）

> 目标服务器：阿里云 ECS + ESSD 云盘，操作系统 Alibaba Cloud Linux 3.2104（基于 RHEL/CentOS，使用 `dnf`/`yum` 包管理器）。

### 10.1 服务器规格建议

| 用途 | 推荐规格 | 说明 |
|------|----------|------|
| 个人/小团队 (1-5 并发) | ecs.c7.large (2 vCPU, 4 GiB) | 够用，Celery 并发设 1-2 |
| 课题组 (5-15 并发) | ecs.c7.xlarge (4 vCPU, 8 GiB) | Celery 并发设 2-3 |
| 实验室级 (15+ 并发) | ecs.c7.2xlarge (8 vCPU, 16 GiB) | Celery 并发设 4，或拆分 worker 节点 |

**云盘**：ESSD PL0 起步，50 GiB 系统盘 + 100 GiB 数据盘（挂载到 `/data`，存放任务产出和数据库）。

**网络**：分配弹性公网 IP（EIP），带宽按量计费 1-5 Mbps（主要是 API 调用出站流量，用户只传 PDF 上来和取 Markdown 回去，带宽需求不大）。

### 10.2 安全组配置

在 ECS 控制台 → 安全组 → 入方向规则中放行以下端口：

| 端口 | 协议 | 授权对象 | 用途 |
|------|------|----------|------|
| 22 | TCP | 你的 IP / 0.0.0.0/0 | SSH 登录 |
| 80 | TCP | 0.0.0.0/0 | HTTP（Caddy 自动跳转到 HTTPS） |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

**不要**对外暴露 5432 (PostgreSQL)、6379 (Redis)、8000 (FastAPI)、3000 (Next.js)。这些端口只在 Docker 内部网络通信，Caddy 统一对外。

### 10.3 域名与 DNS（可选但推荐）

如果需要 HTTPS（推荐），需要一个域名：

1. 在阿里云「域名注册」购买域名（或使用已有域名）
2. 在「云解析 DNS」添加 A 记录：

```
类型   主机记录   记录值            TTL
A      @         <你的ECS公网IP>    600
A      www       <你的ECS公网IP>    600
```

3. 如果域名在阿里云且未备案，需要先完成 ICP 备案（境内服务器必须）
4. 没有域名也可以用 IP 直接访问（HTTP only，无 HTTPS）

### 10.4 SSH 登录与初始安全加固

```bash
# 从本地连接（替换为你的 EIP）
ssh root@<你的ECS公网IP>

# ---------- 创建部署用户（不要用 root 跑服务） ----------
useradd -m -s /bin/bash deploy
passwd deploy                       # 设置密码
usermod -aG wheel deploy            # 加入 sudo 组

# 允许 deploy 用户 sudo 免密（可选，方便部署）
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy

# 复制 SSH 公钥到 deploy 用户
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# ---------- 禁用 root SSH 登录（加固） ----------
sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

# 之后都用 deploy 用户操作
# ssh deploy@<你的ECS公网IP>
```

### 10.5 系统初始化

以下命令以 `deploy` 用户执行（需要 sudo 的地方已标注）：

```bash
# ---------- 系统更新 ----------
sudo dnf update -y

# ---------- 安装基础工具 ----------
sudo dnf install -y \
    git \
    vim \
    htop \
    curl \
    wget \
    unzip \
    tar \
    lsof \
    net-tools \
    firewalld \
    tmux

# ---------- 设置时区 ----------
sudo timedatectl set-timezone Asia/Shanghai
timedatectl                         # 确认输出 Asia/Shanghai

# ---------- 配置系统防火墙（firewalld） ----------
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --reload
sudo firewall-cmd --list-all       # 确认 http https ssh 已放行
```

### 10.6 挂载数据盘

> 如果你单独购买了数据盘（推荐），需要格式化并挂载。如果只有系统盘则跳过此节，直接在系统盘上创建 `/data` 目录。

```bash
# 查看磁盘（假设数据盘设备名为 /dev/vdb，具体以 ECS 控制台显示为准）
lsblk

# 如果 /dev/vdb 没有分区且未格式化：
sudo mkfs.ext4 /dev/vdb

# 创建挂载点
sudo mkdir -p /data

# 挂载
sudo mount /dev/vdb /data

# 写入 fstab 开机自动挂载
echo '/dev/vdb /data ext4 defaults 0 2' | sudo tee -a /etc/fstab

# 验证
df -h /data                         # 应显示 /dev/vdb 挂载在 /data

# 设置目录权限
sudo mkdir -p /data/deepreading
sudo chown -R deploy:deploy /data/deepreading
```

### 10.7 安装 Docker + Docker Compose

Alibaba Cloud Linux 3 自带 `Alibaba Cloud Linux 3` 的 dnf 仓库，可直接安装 Docker：

```bash
# ---------- 方法一：使用阿里云官方源（推荐，速度快） ----------

# 安装 dnf 工具
sudo dnf install -y dnf-utils

# 添加阿里云 Docker CE 镜像源
sudo dnf config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo

# 替换源地址为阿里云镜像（加速）
sudo sed -i 's+download.docker.com+mirrors.aliyun.com/docker-ce+' \
    /etc/yum.repos.d/docker-ce.repo

# 安装 Docker CE + Compose 插件
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# ---------- 启动 Docker ----------
sudo systemctl enable --now docker

# 验证
sudo docker version                 # 应显示 Client 和 Server 版本
sudo docker compose version         # 应显示 Docker Compose v2.x

# ---------- 将 deploy 用户加入 docker 组（免 sudo） ----------
sudo usermod -aG docker deploy

# 重新登录使组生效（或执行 newgrp docker）
exit
ssh deploy@<你的ECS公网IP>

# 验证免 sudo
docker ps                           # 不需要 sudo，应返回空列表
```

#### 配置 Docker 镜像加速（国内必须）

```bash
# 创建 Docker 配置文件
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
    "registry-mirrors": [
        "https://docker.1ms.run",
        "https://docker.xuanyuan.me"
    ],
    "data-root": "/data/docker",
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "50m",
        "max-file": "3"
    },
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 65536,
            "Soft": 65536
        }
    }
}
EOF

# 重启 Docker
sudo systemctl daemon-reload
sudo systemctl restart docker

# 验证加速器生效
docker info | grep -A5 "Registry Mirrors"
```

> **说明**：`"data-root": "/data/docker"` 将 Docker 的镜像和容器数据存放在数据盘，避免撑爆系统盘。

### 10.8 上传项目代码

```bash
# ---------- 方法一：Git 克隆（推荐） ----------
cd /data/deepreading
git clone https://github.com/<你的用户名>/deep-reading-agent.git
cd deep-reading-agent

# ---------- 方法二：从本地上传（Windows PowerShell） ----------
# 在你的 Windows 开发机上执行：
scp -r D:\code\deepagent\deep-reading-agent deploy@<ECS_IP>:/data/deepreading/
```

### 10.9 创建生产环境配置文件

```bash
cd /data/deepreading/deep-reading-agent

# ---------- 创建 .env 文件（存放所有密钥） ----------
cat > .env <<'ENVEOF'
# ====== DeepSeek（必须） ======
DEEPSEEK_API_KEY=sk-你的密钥

# ====== PaddleOCR（推荐） ======
PADDLEOCR_REMOTE_URL=https://你的paddleocr端点
PADDLEOCR_REMOTE_TOKEN=你的token

# ====== Qwen Vision（可选） ======
# QWEN_API_KEY=sk-你的密钥

# ====== PostgreSQL ======
POSTGRES_USER=deepreading
POSTGRES_PASSWORD=这里换成你自己生成的强密码
POSTGRES_DB=deepreading
DATABASE_URL=postgresql://deepreading:同上的密码@db:5432/deepreading

# ====== Redis ======
REDIS_URL=redis://redis:6379/0

# ====== 文件存储 ======
STORAGE_DIR=/data/tasks

# ====== 域名（用于 Caddy HTTPS） ======
DOMAIN=your-domain.com
ENVEOF

# 限制权限，防止其他用户读取密钥
chmod 600 .env
```

**生成强密码**（用于 PostgreSQL）：

```bash
openssl rand -base64 24
# 输出类似: aB3dE7fGhI9jKlMnO1pQrS2t
# 复制到 .env 中的 POSTGRES_PASSWORD 和 DATABASE_URL
```

### 10.10 编写生产 Docker Compose

```bash
cat > docker-compose.prod.yml <<'COMPOSEEOF'
version: "3.9"

services:
  # ==================== 反向代理 ====================
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"     # HTTP/3
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - api
      - frontend
    networks:
      - web

  # ==================== FastAPI 后端 ====================
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: .env
    environment:
      - STORAGE_DIR=/data/tasks
    volumes:
      - task_data:/data/tasks
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      gunicorn main:app
      --worker-class uvicorn.workers.UvicornWorker
      --workers 2
      --bind 0.0.0.0:8000
      --timeout 120
      --graceful-timeout 30
      --access-logfile -
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/status"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - web
      - internal

  # ==================== Celery Worker ====================
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: .env
    environment:
      - STORAGE_DIR=/data/tasks
    volumes:
      - task_data:/data/tasks
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      celery -A workers.celery_app worker
      --loglevel=info
      --concurrency=2
      --max-tasks-per-child=50
      --without-heartbeat
    # Celery worker 内存限制（防止 OOM）
    deploy:
      resources:
        limits:
          memory: 2G
    networks:
      - internal

  # ==================== 前端 ====================
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - NEXT_PUBLIC_API_URL=
    networks:
      - web

  # ==================== PostgreSQL ====================
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    # 不对外暴露端口，只在 internal 网络通信
    networks:
      - internal

  # ==================== Redis ====================
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - internal

volumes:
  task_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/deepreading/tasks    # ESSD 数据盘
  pg_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/deepreading/postgres
  redis_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/deepreading/redis
  caddy_data:
  caddy_config:

networks:
  web:        # Caddy ↔ API/Frontend
  internal:   # API/Worker ↔ DB/Redis（不对外暴露）
COMPOSEEOF
```

### 10.11 编写 Caddyfile

```bash
mkdir -p deploy

# ---------- 有域名版本（自动 HTTPS） ----------
cat > deploy/Caddyfile <<'CADDYEOF'
{
    email your-email@example.com
}

your-domain.com {
    # API（需在前端路由之前匹配）
    handle /api/* {
        reverse_proxy api:8000
    }

    # SSE 长连接（禁用缓冲）
    handle /api/*/stream {
        reverse_proxy api:8000 {
            flush_interval -1
            transport http {
                read_timeout 0
            }
        }
    }

    # 前端
    handle {
        reverse_proxy frontend:3000
    }

    # 安全头
    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
        -Server
    }

    # 日志
    log {
        output file /data/access.log {
            roll_size 50MiB
            roll_keep 5
        }
    }
}
CADDYEOF

# ---------- 无域名版本（纯 IP，HTTP only） ----------
# 如果暂时没有域名，把上面的文件替换为：
# cat > deploy/Caddyfile <<'CADDYEOF'
# :80 {
#     handle /api/* {
#         reverse_proxy api:8000
#     }
#     handle /api/*/stream {
#         reverse_proxy api:8000 {
#             flush_interval -1
#         }
#     }
#     handle {
#         reverse_proxy frontend:3000
#     }
# }
# CADDYEOF
```

> 将 `your-domain.com` 和 `your-email@example.com` 替换为真实值。Caddy 会自动从 Let's Encrypt 申请 HTTPS 证书并续期。

### 10.12 创建数据目录

```bash
# 在数据盘上创建持久化目录
sudo mkdir -p /data/deepreading/{tasks,postgres,redis}
sudo chown -R deploy:deploy /data/deepreading
```

### 10.13 构建与启动

```bash
cd /data/deepreading/deep-reading-agent

# ---------- 首次构建（拉取基础镜像 + 构建应用镜像） ----------
docker compose -f docker-compose.prod.yml build

# ---------- 启动所有服务 ----------
docker compose -f docker-compose.prod.yml up -d

# ---------- 查看所有容器状态 ----------
docker compose -f docker-compose.prod.yml ps

# 预期输出（全部 healthy / running）：
# NAME        SERVICE     STATUS
# caddy       caddy       running
# api         api         running (healthy)
# worker      worker      running
# frontend    frontend    running
# db          db          running (healthy)
# redis       redis       running (healthy)

# ---------- 查看日志（排查启动问题） ----------
docker compose -f docker-compose.prod.yml logs -f           # 全部服务
docker compose -f docker-compose.prod.yml logs -f api       # 只看 API
docker compose -f docker-compose.prod.yml logs -f worker    # 只看 Worker
docker compose -f docker-compose.prod.yml logs -f caddy     # 只看 Caddy
```

### 10.14 验证部署

```bash
# 1. 检查 API 健康
curl http://localhost:8000/api/status
# 预期: {"deepseek":true,"paddleocr":false,...}

# 2. 从外部浏览器访问
#    有域名: https://your-domain.com
#    无域名: http://<你的ECS公网IP>

# 3. 检查 HTTPS 证书（有域名时）
curl -vI https://your-domain.com 2>&1 | grep "SSL certificate"

# 4. 检查 Redis
docker compose -f docker-compose.prod.yml exec redis redis-cli ping
# 预期: PONG

# 5. 检查 PostgreSQL
docker compose -f docker-compose.prod.yml exec db psql -U deepreading -c "SELECT 1;"
# 预期: ?column? = 1
```

### 10.15 数据库初始化

首次启动后需要创建表结构：

```bash
# 进入 API 容器执行数据库迁移
docker compose -f docker-compose.prod.yml exec api python -c "
from database import engine, Base
Base.metadata.create_all(bind=engine)
print('Tables created successfully.')
"
```

如果使用 Alembic 做数据库迁移管理（推荐）：

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### 10.16 日常运维命令

```bash
cd /data/deepreading/deep-reading-agent

# ==================== 服务管理 ====================

# 停止所有服务
docker compose -f docker-compose.prod.yml down

# 停止但保留数据（不删除 volume）
docker compose -f docker-compose.prod.yml stop

# 重启单个服务（不影响其他容器）
docker compose -f docker-compose.prod.yml restart api
docker compose -f docker-compose.prod.yml restart worker

# ==================== 更新部署 ====================

# 拉取最新代码
git pull origin main

# 重新构建并滚动更新（不停机）
docker compose -f docker-compose.prod.yml build api worker frontend
docker compose -f docker-compose.prod.yml up -d --no-deps api worker frontend

# ==================== 查看日志 ====================

# 实时跟踪（Ctrl+C 退出）
docker compose -f docker-compose.prod.yml logs -f --tail=100 api

# 查看 Worker 任务执行情况
docker compose -f docker-compose.prod.yml logs -f worker | grep -E "Task|ERROR"

# ==================== 进入容器调试 ====================

docker compose -f docker-compose.prod.yml exec api bash
docker compose -f docker-compose.prod.yml exec db psql -U deepreading
docker compose -f docker-compose.prod.yml exec redis redis-cli

# ==================== 清理 ====================

# 清理悬空镜像（释放磁盘）
docker image prune -f

# 清理构建缓存
docker builder prune -f

# 查看磁盘占用
docker system df
df -h /data
```

### 10.17 备份策略

```bash
# ---------- 创建备份脚本 ----------
cat > /data/deepreading/backup.sh <<'BACKUPEOF'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/data/deepreading/backups"
DATE=$(date +%Y%m%d_%H%M%S)
COMPOSE_FILE="/data/deepreading/deep-reading-agent/docker-compose.prod.yml"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# 1. PostgreSQL 数据库备份
echo "Backing up PostgreSQL..."
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U deepreading deepreading \
    | gzip > "$BACKUP_DIR/db_${DATE}.sql.gz"

# 2. 任务产出文件备份（增量）
echo "Backing up task data..."
tar czf "$BACKUP_DIR/tasks_${DATE}.tar.gz" \
    -C /data/deepreading tasks/ \
    --newer-mtime="7 days ago" 2>/dev/null || true

# 3. 环境配置
echo "Backing up config..."
cp /data/deepreading/deep-reading-agent/.env \
    "$BACKUP_DIR/env_${DATE}.bak"

# 4. 清理 30 天前的备份
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.bak" -mtime +30 -delete

echo "[$(date)] Backup complete."
ls -lh "$BACKUP_DIR"/db_${DATE}* "$BACKUP_DIR"/tasks_${DATE}*
BACKUPEOF

chmod +x /data/deepreading/backup.sh

# ---------- 设置 crontab 每日凌晨 3 点自动备份 ----------
(crontab -l 2>/dev/null; echo "0 3 * * * /data/deepreading/backup.sh >> /data/deepreading/backups/backup.log 2>&1") | crontab -

# 验证
crontab -l
```

**阿里云快照备份**（整盘级别，推荐同时启用）：

1. ECS 控制台 → 云盘 → 选择数据盘 → 创建自动快照策略
2. 策略：每天凌晨 2:00，保留 7 天
3. 关联到数据盘

### 10.18 监控与告警

#### 系统资源监控

```bash
# ---------- 安装阿里云云监控插件（推荐） ----------
# 在 ECS 控制台 → 云监控 → 主机监控 → 安装插件
# 或手动安装：
sudo bash -c "$(curl -sS https://cms-agent-cn-hangzhou.oss-cn-hangzhou.aliyuncs.com/cms-go-agent/cms_go_agent_install-China.sh)"

# 安装后可在阿里云控制台看到 CPU / 内存 / 磁盘 / 网络监控图表
```

在阿里云「云监控」控制台创建告警规则：

| 指标 | 阈值 | 通道 |
|------|------|------|
| CPU 使用率 | > 85% 持续 5 分钟 | 短信/钉钉 |
| 内存使用率 | > 90% 持续 5 分钟 | 短信/钉钉 |
| 磁盘使用率 | > 85% | 短信/钉钉 |
| ECS 状态 | 非 Running | 短信 |

#### 应用层健康检查

```bash
# ---------- 创建健康检查脚本 ----------
cat > /data/deepreading/healthcheck.sh <<'HCEOF'
#!/bin/bash

API_URL="http://localhost:8000/api/status"
ALERT_FILE="/tmp/deepreading_alert_sent"

check_api() {
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$API_URL")
    if [ "$HTTP_CODE" != "200" ]; then
        echo "[WARN] API returned HTTP $HTTP_CODE"
        return 1
    fi
    return 0
}

check_containers() {
    cd /data/deepreading/deep-reading-agent
    UNHEALTHY=$(docker compose -f docker-compose.prod.yml ps --format json \
        | python3 -c "
import sys, json
for line in sys.stdin:
    c = json.loads(line)
    if c.get('Health','') == 'unhealthy' or c.get('State','') != 'running':
        print(c.get('Service','unknown'))
" 2>/dev/null)

    if [ -n "$UNHEALTHY" ]; then
        echo "[WARN] Unhealthy containers: $UNHEALTHY"
        return 1
    fi
    return 0
}

check_disk() {
    USAGE=$(df /data --output=pcent | tail -1 | tr -d '% ')
    if [ "$USAGE" -gt 85 ]; then
        echo "[WARN] Disk usage at ${USAGE}%"
        return 1
    fi
    return 0
}

# 执行检查
ERRORS=""
check_api      || ERRORS="$ERRORS API_DOWN"
check_containers || ERRORS="$ERRORS CONTAINER_UNHEALTHY"
check_disk     || ERRORS="$ERRORS DISK_HIGH"

if [ -n "$ERRORS" ]; then
    echo "[$(date)] Health check FAILED: $ERRORS"
    # 尝试自动重启
    if echo "$ERRORS" | grep -q "API_DOWN\|CONTAINER_UNHEALTHY"; then
        echo "Attempting auto-restart..."
        cd /data/deepreading/deep-reading-agent
        docker compose -f docker-compose.prod.yml restart api worker
    fi
else
    echo "[$(date)] All checks passed."
    rm -f "$ALERT_FILE"
fi
HCEOF

chmod +x /data/deepreading/healthcheck.sh

# 每 5 分钟执行一次
(crontab -l 2>/dev/null; echo "*/5 * * * * /data/deepreading/healthcheck.sh >> /data/deepreading/backups/healthcheck.log 2>&1") | crontab -
```

### 10.19 性能调优

#### 内核参数（ESSD 优化）

```bash
# ---------- 针对高 I/O 和网络连接的内核参数 ----------
sudo tee /etc/sysctl.d/99-deepreading.conf <<'SYSEOF'
# 文件描述符限制
fs.file-max = 1048576

# TCP 连接优化（支持更多并发 SSE 连接）
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15

# 内存（防止 OOM killer 杀 Docker 进程）
vm.overcommit_memory = 1
vm.swappiness = 10
SYSEOF

sudo sysctl --system

# ---------- 用户级文件描述符限制 ----------
sudo tee /etc/security/limits.d/99-deepreading.conf <<'LIMEOF'
deploy  soft  nofile  65536
deploy  hard  nofile  65536
deploy  soft  nproc   32768
deploy  hard  nproc   32768
LIMEOF
```

#### Docker 资源限制

在 `docker-compose.prod.yml` 中的 `deploy.resources` 已设置 worker 内存限制。根据实际服务器规格调整：

| 服务 | 2C4G 服务器 | 4C8G 服务器 | 8C16G 服务器 |
|------|-------------|-------------|--------------|
| API (gunicorn workers) | 2 | 2 | 4 |
| Worker (celery concurrency) | 1 | 2 | 4 |
| Worker 内存限制 | 1.5G | 2G | 4G |
| PostgreSQL shared_buffers | 默认 | 256MB | 512MB |
| Redis maxmemory | 128mb | 256mb | 512mb |

### 10.20 HTTPS 证书说明

Caddy 在有域名配置时**全自动处理** HTTPS：

1. 首次启动时自动向 Let's Encrypt 申请证书
2. 证书存储在 `caddy_data` volume 中
3. 到期前自动续期（无需人工干预）
4. HTTP 自动 301 跳转到 HTTPS

**注意事项**：

- 域名的 A 记录必须先解析到 ECS 公网 IP，否则证书申请失败
- 阿里云安全组必须放行 80 和 443 端口
- 如果使用阿里云 CDN/WAF，需要在 CDN 层配置证书而不是 Caddy
- 首次申请可能需要 30-60 秒，期间访问会报错，等待即可

### 10.21 故障排查清单

| 现象 | 排查步骤 |
|------|----------|
| 浏览器无法访问 | 1. `curl localhost:80` 测试本机 → 2. 检查安全组 80/443 是否放行 → 3. `firewall-cmd --list-all` 检查防火墙 → 4. `docker compose ps` 检查 Caddy 是否运行 |
| API 返回 502 | 1. `docker compose logs api` 查看后端日志 → 2. `docker compose restart api` 重启 → 3. 检查 `.env` 中 `DATABASE_URL` 是否正确 |
| Worker 不执行任务 | 1. `docker compose logs worker` → 2. 检查 Redis 是否健康：`docker compose exec redis redis-cli ping` → 3. `docker compose restart worker` |
| HTTPS 证书申请失败 | 1. 确认域名 A 记录已解析到正确 IP → 2. `docker compose logs caddy` 查看错误 → 3. 暂时切换到无域名 Caddyfile 用 HTTP 访问 |
| 磁盘空间不足 | 1. `df -h /data` → 2. `docker system df` 查看 Docker 占用 → 3. `docker image prune -af` 清理无用镜像 → 4. 清理旧任务产出 |
| 数据库连接失败 | 1. `docker compose exec db pg_isready` → 2. `docker compose logs db` → 3. 检查 `POSTGRES_PASSWORD` 在 `.env` 和 `DATABASE_URL` 中是否一致 |
| 内存不足 / OOM | 1. `docker stats` 查看各容器内存 → 2. 减小 `worker` 的 `--concurrency` → 3. 降低 Redis `maxmemory` → 4. 考虑升级服务器规格 |
| DeepSeek API 调用失败 | 1. `curl https://api.deepseek.com/v1/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"` 测试连通性 → 2. 检查 API 余额 → 3. 确认 `.env` 中密钥正确 |

### 10.22 完整部署检查清单

按顺序逐项确认：

```
[ ] 1.  ECS 实例已创建，Alibaba Cloud Linux 3
[ ] 2.  ESSD 数据盘已挂载到 /data
[ ] 3.  安全组已放行 22/80/443
[ ] 4.  deploy 用户已创建，已加入 docker 组
[ ] 5.  系统已更新 (dnf update)
[ ] 6.  Docker CE + Compose 已安装
[ ] 7.  Docker 镜像加速已配置
[ ] 8.  Docker data-root 指向 /data/docker
[ ] 9.  项目代码已上传到 /data/deepreading/deep-reading-agent
[ ] 10. .env 文件已创建，密钥已填写，权限 600
[ ] 11. /data/deepreading/{tasks,postgres,redis} 目录已创建
[ ] 12. docker-compose.prod.yml 已就绪
[ ] 13. deploy/Caddyfile 已就绪（域名或 IP 模式）
[ ] 14. 域名 A 记录已解析到 ECS 公网 IP（如使用域名）
[ ] 15. docker compose build 成功
[ ] 16. docker compose up -d 成功
[ ] 17. 所有容器 running / healthy
[ ] 18. curl localhost:8000/api/status 返回正常
[ ] 19. 浏览器可访问前端页面
[ ] 20. HTTPS 证书自动签发成功（如使用域名）
[ ] 21. 数据库表已初始化
[ ] 22. 备份 crontab 已设置
[ ] 23. 健康检查 crontab 已设置
[ ] 24. 阿里云云监控插件已安装
[ ] 25. 内核参数已优化
```
