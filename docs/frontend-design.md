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

> 说明：本节以下内容替代旧版“5 Tabs + 固定左栏/右栏比例”的单一布局假设。当前工作台已经扩展为多 Tab、多工作流，且不同页面的布局类型并不相同，必须按“页面族”分别规划，而不是继续使用一套固定骨架硬套全部页面。

```
┌──────────────────────────────────────────────────────────────────────┐
│ Header (品牌 + API 状态 + 用户菜单)                                  │
├──────────────────────────────────────────────────────────────────────┤
│ Top Utility Bar（可选：API Key 输入区 / warning banner）              │
├──────────────────────────────────────────────────────────────────────┤
│ Tabs Navigation（横向滚动，顺序与工作流一一对应）                    │
├──────────────────────────────────────────────────────────────────────┤
│ Workspace Shell                                                     │
│  ├─ Compare Family：独立全屏/全工作区高度链路                        │
│  ├─ Reading / Filter Family：超宽屏双栏，其余宽度单栏                │
│  ├─ Library / Prompts / History：全宽内容页，自适应分块              │
│  └─ Mobile / Tablet：不强制双栏，优先保证单块内容可读性              │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.1.1 工作区总原则

- 所有页面默认占满“Tab 下方的整个工作区宽度”，不再将非对比页统一限制在过窄的中心列中。
- 不同页面按内容形态分为 3 类：
  - **对比页**：iframe / 大内容画布型页面，必须独立维护高度链条，确保铺满可视区。
  - **工作流页**：文献筛选、长文本精读、七步精读、四步精读，属于“控制区 + 状态区/结果区”。
  - **管理页**：文献库、提示词管理、历史记录，属于“列表 / 详情 / 编辑器”型页面。
- “对比页”和“非对比页”禁止共用同一套高度逻辑；任何针对普通页面的布局修改，都不能破坏对比页当前已调通的铺满行为。

### 3.1.2 响应式断点规则

- **手机**：`< 768px`
  - 全部页面单列
  - Tab 导航允许横向滚动
  - 步骤条、按钮组、编辑器工具区允许横向滚动或自动换行
- **平板**：`768px - 1279px`
  - 默认仍优先单列
  - 只有内容天然适合双列的局部区域才允许分栏
  - 不允许出现“单块关键内容被压成窄条”的情况
- **桌面**：`1280px - 1535px`
  - 管理页可进入舒适双列
  - 工作流页仍以单列或宽松双列为主，不能过早固定左窄右宽
- **超宽屏**：`>= 1536px`
  - 工作流页可启用“左控制栏 + 右主内容区”
  - 左栏建议 `320-420px`，右侧使用剩余空间

### 3.1.3 当前必须满足的硬约束

- `长文本对比 / 七步对比 / 四步对比`：
  - 内容必须铺满工作区
  - 不允许出现“上方大片空白、下方内容高度不足、iframe 没拿到剩余空间”的回归
- `提示词管理`：
  - 不能再被压成左侧窄列
  - 必须允许系统默认/我的覆盖两个编辑区在足够宽度时并排，在中等宽度时上下堆叠
- `文献筛选 / 长文本精读 / 七步精读 / 四步精读`：
  - 在平板和普通桌面宽度下应优先单列，避免“进度条和日志被挤成细长卡片”


### 3.2 Tab 定义

| # | ID | 名称 | 图标 | 功能 |
|---|---|---|---|---|
| 0 | `filter` | 文献筛选 | □ | WoS/CNKI 题录上传 → AI 打分 → Excel 导出 |
| 1 | `long` | 长文本精读 | ➤ | PDF 上传 → 多维度分析 → Markdown 报告 |
| 2 | `compare-long` | 长文本对比 | ⇄ | 长文本精读结构化结果对比 |
| 3 | `quant` | 七步精读 | △ | 定量论文 → 7 步深度分析 → 综合报告 |
| 4 | `compare-7step` | 七步对比 | ⇄ | 七步精读结构化结果对比 |
| 5 | `qual` | 四步精读 | ◉ | 定性论文 → 4 步深度分析 → 综合报告 |
| 6 | `compare-4step` | 四步对比 | ⇄ | 四步精读结构化结果对比 |
| 7 | `library` | 我的文献库 | 📚 | 文献总览、编辑、时间线与 artifact 浏览 |
| 8 | `prompts` | 提示词管理 | ⚙ | 系统默认提示词 + 用户个人覆盖管理 |
| 9 | `history` | 历史记录 | 📁 | 预览、下载、删除历史生成结果 |

### 3.2.1 Tab 顺序原则

- 标签顺序必须与用户使用流程一致：
  - 精读页面后面紧跟对应对比页面
- 当前固定顺序为：
  - `文献筛选`
  - `长文本精读`
  - `长文本对比`
  - `七步精读`
  - `七步对比`
  - `四步精读`
  - `四步对比`
  - `我的文献库`
  - `提示词管理`
  - `历史记录`
- 后续除非用户明确要求，否则不再随意调整该顺序

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
- 不换行，优先保证单个 Tab 可点击区域完整
- 不要求所有 Tab 一屏全部显示，允许横向滑动

### 4.1.1 Workspace Shell 设计

#### Compare Family

- 适用 Tab：
  - `compare-long`
  - `compare-7step`
  - `compare-4step`
- 规则：
  - 外层根容器使用固定高度链条
  - `main`、内容容器、iframe 外层、iframe 本身都必须具备 `flex-1 + min-h-0`
  - 不允许复用普通页的 `mx-auto + max-width + auto height` 逻辑
- 目标：
  - 页面内容始终拿到 Tab 下方剩余的整块可视高度
  - 不出现“恢复旧布局后对比页又被缩回去”的回归

#### Workflow Family

- 适用 Tab：
  - `filter`
  - `long`
  - `quant`
  - `qual`
- 规则：
  - 手机 / 平板 / 普通桌面：默认单列
  - 超宽屏：启用双列
  - 左栏仅放上传、设置、操作按钮
  - 右侧放进度、日志、结果，不允许被压缩到影响阅读

#### Management Family

- 适用 Tab：
  - `library`
  - `prompts`
  - `history`
- 规则：
  - 页面整体使用全宽工作区容器
  - 允许内部局部双列，但不能形成“整页偏左、右半边大片空白”的视觉问题
  - 中等宽度优先上下堆叠

### 4.2 Tab 0: 文献筛选

#### 布局规则

- 手机 / 平板 / 普通桌面：单列
- 超宽屏：左栏 `320-420px`，右侧自适应
- 进度卡、日志卡、结果卡在中等宽度下必须占满可用宽度，不允许出现细长卡片

#### 左侧控制区
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

#### 右侧主内容区
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

#### 布局规则

- 与文献筛选一致：
  - 手机 / 平板 / 普通桌面：单列
  - 超宽屏：左控制区 + 右主内容区
- “分析维度”面板在平板及以下宽度下必须自动换列或单列，不得挤压主内容区

#### 左侧控制区
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

#### 右侧主内容区
- 进度条 + 阶段显示
- 实时日志流（自动滚动到底部）
- Markdown 预览区（支持标题折叠）
- 下载按钮（生成后显示）

### 4.4 Tab 2: 七步精读 (QUANT)

#### 布局规则

- 与长文本精读相同
- 7 步进度条在手机和平板上允许横向滚动，不强行压缩到单行可视宽度内

#### 左侧控制区
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

#### 右侧主内容区
- 7 步进度指示器（步骤条）
  ```
  ① → ② → ③ → ④ → ⑤ → ⑥ → ⑦
  ```
- 每步完成时展开显示摘要
- 最终报告预览 + 下载

### 4.5 Tab 3: 四步精读 (QUAL)

#### 布局规则

- 与七步精读一致
- 4 步进度条在中小屏也要保持可读，不得为保持单行而压窄日志和进度卡片

类似 Tab 2，但步骤为 4 个：
```
① 背景与语境 → ② 理论框架 → ③ 论证逻辑 → ④ 价值与启示
```

### 4.6 Tab 4-6: 三个对比页

#### 共用规则

- 三个对比页全部沿用独立的 Compare Family 布局
- 页面标题区高度最小化，不挤占正文
- 主内容区必须完全铺满工作区剩余空间
- iframe 外层与 iframe 自身都必须跟随剩余空间伸展
- 任何普通页的容器宽度/高度优化都不得直接复用到对比页根容器

#### 子页

- `compare-long`：长文本精读对比分析
- `compare-7step`：七步法对比分析
- `compare-4step`：四步法对比分析

### 4.7 Tab 7: 我的文献库

#### 布局规则

- 页面整体使用全宽容器
- 手机 / 平板：先文献列表，再详情区，纵向堆叠
- 超宽屏：列表 + 详情两栏
- 文献列表和详情区各自保持独立滚动，避免整页过长

### 4.8 Tab 8: 提示词管理

```
┌─────────────────────────────────────────────────────────┐
│ 类型: [七步精读 ▼]  步骤: [Step 1 研究概览 ▼]  [刷新]    │
├─────────────────────────────────────────────────────────┤
│ 标题 + 当前来源（系统默认 / 用户覆盖）                 │
├─────────────────────────────────────────────────────────┤
│ ┌──────────────────────┐ ┌───────────────────────────┐ │
│ │ 当前生效内容         │ │ 我的覆盖                  │ │
│ │ (只读)               │ │ [保存我的覆盖] [恢复默认] │ │
│ │                      │ │                           │ │
│ └──────────────────────┘ └───────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│ admin only: 系统默认提示词编辑区 + [保存系统默认]       │
└─────────────────────────────────────────────────────────┘
```

#### 布局规则

- 该页属于 Management Family，不再采用“左侧窄栏 + 右侧大区”的旧模式
- 手机 / 平板 / 普通桌面：
  - 顶部筛选区上下堆叠
  - “当前生效内容”和“我的覆盖”上下排列
  - admin 区块单独放在下方
- 超宽屏：
  - “当前生效内容”和“我的覆盖”可并排
  - admin 区块仍整行独立，避免三栏同时并排导致阅读困难
- 明确禁止：
  - 整个提示词管理页只占左半边，右半边大片留白
  - 在中等宽度下强行并排，导致编辑器宽度不足

### 4.9 Tab 9: 历史记录

#### 布局规则

- 页面整体使用全宽容器
- 子 Tab（文献阅读 / AI 综述）保留顶部切换
- 列表项在手机端改为上下布局，在桌面端保持操作按钮横向排列
- 不引入对比页式高度链条，但应保持舒适的纵向滚动节奏

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
GET /api/prompts/catalog
GET /api/prompts/item?type=quant&key=step_1
PUT /api/prompts/my
DELETE /api/prompts/my?type=quant&key=step_1
PUT /api/prompts/system

兼容旧接口：
GET /api/prompts?type=quant&step=step_1
PUT /api/prompts
```

Request（保存我的覆盖）:
```json
{
  "type": "quant",
  "key": "step_1",
  "content": "..."
}
```

Request（保存系统默认）:
```json
{
  "type": "quant",
  "key": "step_1",
  "content": "..."
}
```

Response（获取单个提示词）:
```json
{
  "type": "quant",
  "key": "step_1",
  "title": "Step 1: 研究概览",
  "effective_content": "...",
  "system_content": "...",
  "user_content": "...",
  "source": "system_default",
  "has_system_default": true,
  "has_user_override": false,
  "can_edit_system": true
}
```

### 5.2 前端布局实施约束

- 先更新本设计文档，再实施布局改动
- 对比页与非对比页的布局改造必须拆成两步，不允许一次性改全局壳子
- 每次修改后至少验证：
  - 长文本对比是否仍铺满
  - 提示词管理是否仍然居左变窄
  - 筛选/精读页在平板宽度下是否仍出现细长卡片

### 5.3 验收清单

- [ ] Tab 顺序与本文件定义一致
- [ ] 对比页在桌面端铺满工作区，不出现大块空白
- [ ] 提示词管理在桌面端不过度偏左，在平板端不挤压编辑器宽度
- [ ] 文献筛选 / 长文本精读 / 七步精读 / 四步精读在平板宽度下默认单列
- [ ] 手机端 Tab 导航可横向滚动
- [ ] 手机端步骤条、按钮组、编辑区不溢出不可操作
- [ ] 文献库与历史记录在中小屏下保持可点击、可滚动、可阅读
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
