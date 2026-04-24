# Deep Reading Agent - 前端设计文档

## 1. 项目概述

### 1.1 目标
为 Deep Reading Agent 构建一个自定义前端，替代 Gradio，解决 Tab 切换卡死、样式受限、移动端体验差等问题。

### 1.2 核心原则
- **白底青绿主题**：延续当前确认的配色方案
- **响应式布局**：桌面端为主，移动端可用
- **实时反馈**：进度条、日志流、状态更新
- **稳定性**：彻底解决 Tab 切换和并发问题

---

## 2. 技术栈

| 层级 | 技术 | 版本 | 用途 |
|---|---|---|---|
| **前端框架** | React 18 | ^18.2 | UI 组件化 |
| **构建工具** | Vite | ^5.0 | 快速开发构建 |
| **样式** | Tailwind CSS | ^3.4 | 原子化样式 |
| **UI 组件** | shadcn/ui | latest | 基础组件库 |
| **状态管理** | Zustand | ^4.5 | 轻量状态管理 |
| **Markdown** | react-markdown | ^9.0 | 报告渲染 |
| **代码高亮** | react-syntax-highlighter | ^15.5 | 代码块高亮 |
| **表格** | TanStack Table | ^8.13 | 高级表格 |
| **HTTP 请求** | Axios | ^1.6 | REST API |
| **实时通信** | Socket.IO Client | ^4.7 | WebSocket 进度推送 |
| **后端框架** | FastAPI | ^0.110 | REST + WebSocket API |
| **进程管理** | Celery + Redis | latest | 异步任务队列 |

---

## 3. 页面结构

### 3.1 整体布局

```
┌─────────────────────────────────────────────────────────┐
│  Header (品牌 + 环境状态徽章)                              │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tabs Navigation (5 Tabs)                         │  │
│  ├───────────────────────────────────────────────────┤  │
│  │                                                   │  │
│  │  Tab Content Area                                 │  │
│  │  ┌──────────────────┐ ┌────────────────────────┐  │  │
│  │  │  Left Sidebar    │ │  Right Main Content    │  │  │
│  │  │  - Upload        │ │  - Progress            │  │  │
│  │  │  - Settings      │ │  - Logs                │  │  │
│  │  │  - Parameters    │ │  - Results             │  │  │
│  │  └──────────────────┘ └────────────────────────┘  │  │
│  │                                                   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Tab 定义

| # | ID | 名称 | 图标 | 功能 |
|---|---|---|---|---|
| 0 | `filter` | 文献筛选 | □ | WoS/CNKI 题录上传 → AI 打分 → Excel 导出 |
| 1 | `long` | 长文本精读 | ➤ | PDF 上传 → 多维度分析 → Markdown 报告 |
| 2 | `quant` | 七步精读 | △ | 定量论文 → 7 步深度分析 → 综合报告 |
| 3 | `qual` | 四步精读 | ◉ | 定性论文 → 4 步深度分析 → 综合报告 |
| 4 | `prompts` | 提示词管理 | ⚙ | 编辑/保存所有提示词模板 |

---

## 4. 组件设计

### 4.1 全局组件

#### Header
```
┌─────────────────────────────────────────────────────────┐
│  ❤️‍🔥 Deep Reading Agent        [DeepSeek ✓] [KIMI v3]  │
│      学术论文深度精读系统                                  │
└─────────────────────────────────────────────────────────┘
```
- 左侧：品牌图标 + 标题 + 副标题
- 右侧：环境状态徽章（DeepSeek API 状态、版本号）
- 高度：64px
- 背景：白色，底部 1px 边框

#### Tab Navigation
- 样式：底部边框 Tab 导航
- 激活态：青绿色下划线 + 文字加粗
- 未激活态：灰色文字
- 图标 + 文字并排
- 移动端：可横向滚动

### 4.2 Tab 0: 文献筛选

#### Left Sidebar (scale: 1)
```
┌──────────────────┐
│ □ 上传文献题录    │
│ ┌──────────────┐ │
│ │  拖拽上传区   │ │
│ │  .txt 文件   │ │
│ └──────────────┘ │
│ Web of Science    │
│ 或 CNKI 导出文件  │
├──────────────────┤
│ ★ 筛选设置       │
│ ○ 探索者模式     │
│ ○ 评审者模式     │
│ ○ 实证主义者     │
│ ──────────────── │
│ 研究主题          │
│ [____________]   │
│ ──────────────── │
│ 最小年份: 2015   │
│ ──────────────── │
│ 关键词过滤        │
│ [____________]   │
├──────────────────┤
│ [开始筛选]       │
│ [停止]           │
└──────────────────┘
```

#### Right Content (scale: 2)
```
┌────────────────────────────────┐
│ ■ 处理进度                      │
│ 当前阶段: AI 评估中...          │
│ ████████░░ 80%                 │
├────────────────────────────────┤
│ ■ 运行日志                      │
│ ┌────────────────────────────┐ │
│ │ [1/4] 解析文献题录...       │ │
│ │ ✓ 解析完成: 50 篇文献       │ │
│ │ [2/4] 基础过滤...           │ │
│ │ ...                         │ │
│ └────────────────────────────┘ │
├────────────────────────────────┤
│ ★ 筛选结果                      │
│ ┌─────────────────────────────────────┐ │
│ │ 标题 │ 作者 │ 期刊 │ 年份 │ 评分 │ 理由 │
│ ├─────────────────────────────────────┤ │
│ │ xxx  │ xxx  │ xxx  │ 2023 │ 8.5  │ ... │
│ │ ...  │ ...  │ ...  │ ...  │ ...  │ ... │
│ └─────────────────────────────────────┘ │
│ 共 50 篇，按评分降序排列              │
├────────────────────────────────┤
│ ↓ 下载结果                      │
│ [filtered_explorer_xxx.xlsx]   │
└────────────────────────────────┘
```

### 4.3 Tab 1: 长文本精读

#### Left Sidebar
```
┌──────────────────┐
│ ↗ 上传论文        │
│ ┌──────────────┐ │
│ │   拖拽 PDF   │ │
│ └──────────────┘ │
├──────────────────┤
│ ★ 分析维度       │
│ ☑ 研究问题       │
│ ☑ 理论框架       │
│ ☑ 识别策略       │
│ ☐ 稳健性检验     │
│ ☐ ...            │
├──────────────────┤
│ ✉ 自定义问题      │
│ [____________]   │
├──────────────────┤
│ [开始精读]       │
│ [停止]           │
└──────────────────┘
```

#### Right Content
- 进度条 + 阶段显示
- 实时日志流（自动滚动到底部）
- Markdown 预览区（支持标题折叠）
- 下载按钮（生成后显示）

### 4.4 Tab 2: 七步精读 (QUANT)

#### Left Sidebar
```
┌──────────────────┐
│ ↗ 上传论文        │
│ ┌──────────────┐ │
│ │   拖拽 PDF   │ │
│ └──────────────┘ │
├──────────────────┤
│ ★ 提取方式       │
│ ○ 完整文本提取   │
│ ○ 快速预览       │
├──────────────────┤
│ [开始精读]       │
│ [停止]           │
└──────────────────┘
```

#### Right Content
- 7 步进度指示器（步骤条）
  ```
  ① → ② → ③ → ④ → ⑤ → ⑥ → ⑦
  ```
- 每步完成时展开显示摘要
- 最终报告预览 + 下载

### 4.5 Tab 3: 四步精读 (QUAL)

类似 Tab 2，但步骤为 4 个：
```
① 背景与语境 → ② 理论框架 → ③ 论证逻辑 → ④ 价值与启示
```

### 4.6 Tab 4: 提示词管理

```
┌─────────────────────────────────────────────────────────┐
│ 类型: [七步精读 ▼]  步骤: [Step 1 研究概览 ▼]           │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 提示词编辑器                                         │ │
│ │                                                     │ │
│ │ ┌─────────────────────────────────────────────────┐ │ │
│ │ │                                                 │ │ │
│ │ │  (Markdown 编辑器，支持语法高亮)                 │ │ │
│ │ │                                                 │ │ │
│ │ └─────────────────────────────────────────────────┘ │ │
│ │                                                     │ │
│ │ [加载提示词]  [保存到文件]  [重置默认]               │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 5. API 接口规范

### 5.1 REST API

#### 文件上传
```http
POST /api/upload
Content-Type: multipart/form-data

file: <binary>
type: "pdf" | "txt"
```

Response:
```json
{
  "success": true,
  "file_id": "uuid-string",
  "filename": "paper.pdf",
  "size": 123456,
  "message": "上传成功"
}
```

#### 文献筛选
```http
POST /api/filter/start
Content-Type: application/json

{
  "file_id": "uuid-string",
  "mode": "explorer" | "reviewer" | "empiricist",
  "topic": "数字普惠金融",
  "min_year": 2015,
  "keywords": "数字经济,金融"
}
```

Response:
```json
{
  "task_id": "task-uuid",
  "status": "queued"
}
```

#### 获取任务状态
```http
GET /api/task/{task_id}/status
```

Response:
```json
{
  "task_id": "task-uuid",
  "status": "running" | "completed" | "failed" | "cancelled",
  "progress": 80,
  "stage": "AI 评估中...",
  "logs": ["[1/4] 解析完成", "..."],
  "result": {
    "output_path": "/path/to/result.xlsx",
    "preview": [...]
  }
}
```

#### 取消任务
```http
POST /api/task/{task_id}/cancel
```

#### 下载结果
```http
GET /api/download/{file_path}
```

#### 提示词管理
```http
GET /api/prompts?type=quant&step=step_1
PUT /api/prompts
{
  "type": "quant",
  "step": "step_1",
  "content": "新的提示词内容..."
}
```

### 5.2 WebSocket API

连接：`wss://deepreading.qzz.io/ws/{task_id}`

事件流：
```json
// 进度更新
{
  "type": "progress",
  "progress": 45,
  "stage": "AI 评估中..."
}

// 日志推送
{
  "type": "log",
  "message": "✓ 解析完成: 50 篇文献",
  "timestamp": "2024-01-01T12:00:00Z"
}

// 结果推送
{
  "type": "result",
  "data": {
    "output_path": "...",
    "preview": [...]
  }
}

// 错误
{
  "type": "error",
  "message": "解析失败: 不支持的文件格式"
}
```

---

## 6. 样式规范

### 6.1 颜色系统

```css
:root {
  /* 主色调 - 青绿 */
  --primary-50: #ecfdf5;
  --primary-100: #d1fae5;
  --primary-200: #a7f3d0;
  --primary-300: #6ee7b7;
  --primary-400: #34d399;
  --primary-500: #10b981;  /* 主色 */
  --primary-600: #059669;  /* 按钮渐变起始 */
  --primary-700: #047857;
  
  /* 中性色 */
  --gray-50: #f9fafb;
  --gray-100: #f3f4f6;
  --gray-200: #e5e7eb;
  --gray-300: #d1d5db;
  --gray-400: #9ca3af;
  --gray-500: #6b7280;
  --gray-600: #4b5563;
  --gray-700: #374151;
  --gray-800: #1f2937;
  --gray-900: #111827;
  
  /* 功能色 */
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
  --info: #3b82f6;
  
  /* 背景 */
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --bg-card: #ffffff;
  
  /* 文字 */
  --text-primary: #111827;
  --text-secondary: #4b5563;
  --text-muted: #9ca3af;
}
```

### 6.2 按钮样式

**主按钮（开始/确认）**
```css
.btn-primary {
  background: linear-gradient(135deg, #059669, #10b981);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 10px 24px;
  font-weight: 500;
  transition: all 0.2s;
  box-shadow: 0 1px 3px rgba(5, 150, 105, 0.2);
}
.btn-primary:hover {
  background: linear-gradient(135deg, #047857, #059669);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(5, 150, 105, 0.3);
}
```

**危险按钮（停止/删除）**
```css
.btn-danger {
  background: #fee2e2;
  color: #dc2626;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 10px 24px;
}
.btn-danger:hover {
  background: #fecaca;
}
```

### 6.3 卡片样式

```css
.card {
  background: white;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
```

### 6.4 上传区样式

```css
.upload-zone {
  border: 2px dashed #d1d5db;
  border-radius: 12px;
  padding: 40px;
  text-align: center;
  transition: all 0.2s;
  background: #f9fafb;
}
.upload-zone:hover,
.upload-zone.drag-over {
  border-color: #10b981;
  background: #ecfdf5;
}
```

---

## 7. 状态管理 (Zustand)

```typescript
// store.ts
interface AppState {
  // 全局状态
  activeTab: string;
  setActiveTab: (tab: string) => void;
  
  // 任务状态
  tasks: Map<string, TaskState>;
  startTask: (tab: string, params: any) => Promise<string>;
  cancelTask: (taskId: string) => void;
  updateTaskProgress: (taskId: string, progress: number, stage: string) => void;
  appendTaskLog: (taskId: string, message: string) => void;
  setTaskResult: (taskId: string, result: any) => void;
  
  // 文件上传
  uploadedFiles: Map<string, UploadedFile>;
  addUploadedFile: (file: UploadedFile) => void;
  
  // 提示词
  prompts: PromptMap;
  loadPrompt: (type: string, step: string) => string;
  savePrompt: (type: string, step: string, content: string) => void;
}

interface TaskState {
  id: string;
  tab: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage: string;
  logs: string[];
  result: any;
  error?: string;
}
```

---

## 8. 后端架构 (FastAPI)

### 8.1 目录结构

```
backend/
├── main.py              # FastAPI 入口
├── routers/
│   ├── upload.py        # 文件上传
│   ├── filter.py        # 文献筛选
│   ├── reading.py       # 精读（长文本/七步/四步）
│   ├── prompts.py       # 提示词管理
│   └── download.py      # 结果下载
├── services/
│   ├── task_manager.py  # 任务队列管理
│   ├── ws_manager.py    # WebSocket 连接管理
│   ├── file_store.py    # 文件存储
│   └── pipeline/
│       ├── filter_pipeline.py
│       ├── quant_pipeline.py
│       ├── qual_pipeline.py
│       └── long_pipeline.py
├── models/
│   ├── schemas.py       # Pydantic 模型
│   └── database.py      # 数据库（SQLite/PostgreSQL）
└── core/
    ├── config.py        # 配置
    └── exceptions.py    # 异常处理
```

### 8.2 任务队列 (Celery)

```python
# 任务定义
@celery_app.task(bind=True, max_retries=3)
def run_filter_pipeline(self, file_id: str, params: dict):
    """文献筛选异步任务"""
    task_id = self.request.id
    
    # 1. 解析文件
    update_progress(task_id, 10, "解析文献题录...")
    
    # 2. 基础过滤
    update_progress(task_id, 25, "基础过滤...")
    
    # 3. AI 评估
    update_progress(task_id, 40, "AI 评估...")
    
    # 4. 导出结果
    update_progress(task_id, 90, "导出结果...")
    
    return {"output_path": "...", "row_count": 50}
```

### 8.3 WebSocket 管理

```python
class WSManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
    
    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections[task_id] = websocket
    
    async def send_progress(self, task_id: str, progress: int, stage: str):
        if ws := self.connections.get(task_id):
            await ws.send_json({
                "type": "progress",
                "progress": progress,
                "stage": stage
            })
    
    async def send_log(self, task_id: str, message: str):
        if ws := self.connections.get(task_id):
            await ws.send_json({
                "type": "log",
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            })
```

---

## 9. 部署方案

### 9.1 开发环境

```bash
# 前端
npm run dev          # Vite dev server → http://localhost:5173

# 后端
uvicorn main:app --reload --port 8000
```

### 9.2 生产环境

```
┌────────────────────────────────────────┐
│           Nginx (反向代理)              │
│  / → 前端静态文件 (dist/)               │
│  /api → FastAPI (localhost:8000)       │
│  /ws → WebSocket (localhost:8000)      │
└────────────────────────────────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
┌───┴───┐         ┌────┴────┐
│Frontend│         │ Backend │
│(React) │         │(FastAPI)│
└────────┘         └────┬────┘
                        │
              ┌─────────┴─────────┐
              │                   │
         ┌────┴────┐        ┌────┴────┐
         │ Celery  │        │ Redis   │
         │ Workers │        │ Queue   │
         └─────────┘        └─────────┘
```

### 9.3 Docker 部署

```dockerfile
# Dockerfile (前端)
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

```dockerfile
# Dockerfile (后端)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  frontend:
    build: ./frontend
    ports:
      - "80:80"
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
  redis:
    image: redis:7-alpine
  celery:
    build: ./backend
    command: celery -A tasks worker --loglevel=info
    depends_on:
      - redis
```

---

## 10. 迁移计划

### Phase 1: 后端 API (2-3 天)
- [ ] 搭建 FastAPI 框架
- [ ] 实现文件上传接口
- [ ] 实现文献筛选 Pipeline
- [ ] 实现七步精读 Pipeline
- [ ] 实现四步精读 Pipeline
- [ ] 实现长文本精读 Pipeline
- [ ] 集成 Celery + Redis 任务队列
- [ ] WebSocket 实时推送

### Phase 2: 前端基础 (2-3 天)
- [ ] 搭建 React + Vite + Tailwind 项目
- [ ] 实现 Header + Tab 导航
- [ ] 实现文件上传组件（拖拽 + 进度）
- [ ] 实现进度条 + 日志流组件
- [ ] 实现 Markdown 预览组件

### Phase 3: Tab 功能实现 (3-4 天)
- [ ] Tab 0: 文献筛选完整功能
- [ ] Tab 1: 长文本精读完整功能
- [ ] Tab 2: 七步精读完整功能
- [ ] Tab 3: 四步精读完整功能
- [ ] Tab 4: 提示词管理完整功能

### Phase 4: 测试 & 部署 (2 天)
- [ ] 端到端测试所有 Tab
- [ ] 移动端适配测试
- [ ] Docker 部署
- [ ] Nginx + HTTPS 配置
- [ ] Cloudflare 隧道切换

**总计：约 10-12 天**

---

## 11. 风险 & 缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| FastAPI + Celery 学习曲线 | 延期 | 使用简单任务队列，必要时用 threading |
| WebSocket 连接不稳定 | 进度不更新 | 降级为轮询（Polling）作为备选 |
| 大文件上传超时 | 上传失败 | 分片上传 / 增加 Nginx 超时时间 |
| 浏览器兼容性 | 部分功能异常 | 目标浏览器：Chrome 90+, Safari 15+, Firefox 90+ |

---

## 附录：图标映射

| 功能 | Unicode | 说明 |
|---|---|---|
| 上传 | ↗ | U+2197 |
| 目标/筛选 | ★ | U+2605 |
| 聊天/消息 | ✉ | U+2709 |
| 图表 | ■ | U+25A0 |
| 编辑 | ✎ | U+270E |
| 下载 | ↓ | U+2193 |
| 文件夹 | □ | U+25A1 |
| 铅笔 | ✏ | U+270F |
| 水晶/核心 | ◉ | U+25C9 |
| 标尺/步骤 | △ | U+25B3 |
| 齿轮/设置 | ⚙ | U+2699 |
| 箭头/开始 | ➤ | U+27A4 |
| 进度 | ▶ | U+25B6 |
| 完成 | ✓ | U+2713 |
| 警告 | ⚠ | U+26A0 |
| 错误 | ✕ | U+2715 |
