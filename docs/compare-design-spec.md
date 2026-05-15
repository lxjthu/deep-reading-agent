# 对比综述页面设计方案 v2.0

## 1. 设计目标

打造一个**学术优雅、现代精致**的文献对比工作台，彻底消除"AI 味"。核心体验：
- **纵向维度**：从上到下浏览分析维度，像阅读一份精致的学术简报
- **横向对比**：每个维度展开后，各篇文献的回答并排呈现，一目了然
- **精致交互**：每个操作都有流畅的物理反馈，每个视觉元素都有考究的细节

---

## 2. 页面架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  顶栏（固定）                                                          │
│  标题「对比分析」| 副标题 | [生成 AI 综述]                              │
├──────────────────────────────────────────────────────────────────────┤
│  文献选择栏（固定，横向滚动）                                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ...  ← 可勾选、可删除            │
│  │ 文献A ✓ │ │ 文献B ✓ │ │  文献C  │                                 │
│  └─────────┘ └─────────┘ └─────────┘                                 │
├──────────────────────────────────────────────────────────────────────┤
│  步骤/维度导航（胶囊标签，固定）                                        │
│  [全部] [①核心贡献] [②理论框架] [③方法论] [④实证结果] ...            │
├──────────────────────────────────────────────────────────────────────┤
│  对比操作栏（固定）                                                    │
│  当前步骤 | 已选 N 个问题 | [当前步骤全选] [清空选择]                  │
├──────────────────────────────────────────────────────────────────────┤
│  ↓↓↓ 维度列表区域（纵向滚动）↓↓↓↓                                     │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ ▼ [复选框] 1. 研究的核心问题是什么？                            │  │
│  │    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │  │
│  │    │ 文献A        │ │ 文献B        │ │ 文献C        │ ←横向   │  │
│  │    │              │ │              │ │              │  滚动   │  │
│  │    │ Markdown渲染 │ │ Markdown渲染 │ │ Markdown渲染 │ 卡片   │  │
│  │    │ 内容可右键   │ │ 内容可右键   │ │ 内容可右键   │       │  │
│  │    │ 选中复制     │ │ 选中复制     │ │ 选中复制     │       │  │
│  │    └──────────────┘ └──────────────┘ └──────────────┘         │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ ▶ [复选框] 2. 与已有研究的主要区别？                            │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │ ▶ [复选框] 3. 提出的关键概念或框架？                            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据流设计（保持不变）

### 3.1 数据源
- **从**：解析 Markdown 文件（旧 compare 页面做法）
- **到**：读取 `reading_items` 表结构化数据
  - `GET /api/jobs/{job_id}/structured` 单篇精读
  - `GET /api/compare/structured` 批量多文献
  - 数据包含：mode, section_type, parent_key, item_key, item_label, content

### 3.2 Demo 数据源
在开发和演示阶段，使用以下三个 JSON 文件作为后端数据库：
- `docs/compare-long-demo-data.json` — 长文本精读 demo 数据
- `docs/compare-qual-demo-data.json` — 四步精读 demo 数据
- `docs/compare-quant-demo-data.json` — 七步精读 demo 数据

独立后端服务 `backend/compare_demo_server.py`（端口 8001）提供三个 API 端点：
- `GET /api/compare-demo/long`
- `GET /api/compare-demo/qual`
- `GET /api/compare-demo/quant`

前端通过 `fetch` 调用这些端点获取数据。

### 3.2 数据转换
```
ReadingItem (DB)
├── mode="quant"
├── section_type="step"
├── item_key="quant.step1"
├── item_label="第一步：核心贡献识别"
└── content="步骤概述..."
    └── 子问题 (section_type="subquestion")
        ├── item_key="quant.step1.q1"
        ├── item_label="研究的核心问题是什么？"
        └── content="具体回答内容..."
```

---

## 4. 核心交互逻辑（复用旧 compare）

### 4.1 状态管理（与旧 compare 完全一致）
```javascript
let selectedPapers = [];              // 选中的文献 ID 列表
let selectedSubQuestions = new Set(); // 选中的子问题 key 集合（用于 AI 综述）
let selectedStep = '';                // 当前选中的步骤
```

### 4.2 复选框行为
**每个维度（子问题）左侧放置复选框**，完全复用旧 compare 逻辑：
- 点击复选框：toggle 该子问题的选中状态（用于 AI 综述）
- 复选框状态跨步骤持久化：切换步骤后，之前选中的子问题保持选中
- 当选中文献变化时，自动清理已不存在子问题的选中状态（`pruneSelectedQuestions`）
- **全选/反选**：操作栏提供「当前步骤全选」按钮，一键勾选当前步骤所有可见子问题
- **清空选择**：操作栏提供「清空选择」按钮，一键清空所有已选子问题

### 4.3 AI 综述触发条件
与旧 compare 一致：
- 至少选择 **2 篇文献**
- 至少选择 **1 个子问题**
- 条件满足时，「生成 AI 综述」按钮从禁用态变为可用态

### 4.4 折叠/展开
- 点击维度标题行（除复选框外区域）：展开/折叠该维度下的论文卡片
- 默认状态：**全部折叠**（或记忆用户上次状态）
- 展开动画：高度从 0 到 auto，300ms ease-out

---

## 5. 视觉设计 v2（彻底重构）

### 5.1 设计原则
- **克制**：减少颜色数量，用层级和留白创造呼吸感
- **精致**：圆角、阴影、间距都经过精心计算
- **学术**：参考顶级期刊网站（如 Nature、Science 排版）的克制美学
- **无 AI 味**：避免渐变色、霓虹色、过度动效

### 5.2 色彩系统
```css
/* 背景层 */
--bg-canvas: #faf8f5;           /* 画布底色：温暖米白 */
--bg-surface: #ffffff;          /* 卡片/面板背景：纯白 */
--bg-surface-elevated: #ffffff; /* 悬浮态：纯白 + 阴影 */
--bg-hover: #f5f2ee;            /* 悬停背景：浅暖灰 */
--bg-selected: rgba(22, 101, 52, 0.06);  /* 选中态：半透明墨绿 */
--bg-warm: #f5efe8;             /* 暖色背景：用于提示、标签 */

/* 文字层 */
--text-primary: #2d2a26;        /* 主文字：暖黑 */
--text-secondary: #5c554d;      /* 次要文字：暖灰 */
--text-tertiary: #9a9188;       /* 辅助文字：浅暖灰 */
--text-muted: #b5ada5;          /* 弱化文字：更浅暖灰 */
--text-inverse: #ffffff;        /* 反白文字 */

/* 强调色 */
--accent-primary: #166534;      /* 主色：深墨绿（学术、沉稳） */
--accent-primary-hover: #14532d;/* 主色悬停 */
--accent-gold: #b45309;         /* 点缀：琥珀（用于引用、标签） */
--accent-coral: #9f1239;        /* 警告：深红（用于删除、错误） */

/* 边框 */
--border-light: #ebe7e0;        /* 浅色分隔线 */
--border-medium: #ddd8cf;       /* 中等分隔线 */
--border-focus: #166534;        /* 聚焦态边框 */

/* 阴影 */
--shadow-sm: 0 1px 3px rgba(45, 42, 38, 0.05);
--shadow-md: 0 4px 12px rgba(45, 42, 38, 0.08);
--shadow-lg: 0 12px 32px rgba(45, 42, 38, 0.1);
```

### 5.3 字体系统
```css
/* 标题：衬线体，营造学术感 */
--font-serif: 'Noto Serif SC', 'Songti SC', 'SimSun', serif;

/* 正文：无衬线体，保证可读性 */
--font-sans: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* 代码：等宽体 */
--font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;

/* 字号 */
--text-xs: 13px;    /* 标签、辅助 */
--text-sm: 14px;    /* 正文、卡片内容 */
--text-base: 15px;  /* 导航、按钮 */
--text-lg: 17px;    /* 维度标题 */
--text-xl: 20px;    /* 区域标题 */
--text-2xl: 36px;   /* 页面大标题 */
```

### 5.4 间距系统
```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
```

### 5.5 圆角系统
```css
--radius-sm: 4px;   /* 小元素：标签、徽章 */
--radius-md: 8px;   /* 中等：按钮、输入框 */
--radius-lg: 12px;  /* 大元素：卡片、面板 */
--radius-xl: 16px;  /* 特殊：模态框 */
```

---

## 6. 组件规范

### 6.1 标题区（Header Section）
```
布局: 全宽，padding: 40px 60px
下边距: 28px
下边框: 1px solid var(--border-light)

标题: font-family: var(--font-serif)
      font-size: 36px
      font-weight: 700
      color: var(--text-primary)
      margin-bottom: 12px
      letter-spacing: 1px

副标题: font-size: 16px
        color: var(--text-secondary)
        line-height: 1.7
        max-width: 800px
```

### 6.2 文献选择区（Paper Selection）
```
容器: 白色卡片背景，圆角 12px，内边距 24px 32px
边框: 1px solid var(--border-light)
阴影: var(--shadow-sm)

区域标题: font-size: 18px, font-weight: 600
          带计数标签（14px，背景 var(--bg-warm)）

文献网格: flex, gap: 14px, flex-wrap: wrap

文献卡片:
  - 最小宽度: 240px, 最大宽度: 320px
  - 内边距: 16px 20px
  - 圆角: 10px
  - 边框: 1.5px solid var(--border-light)
  - 背景: var(--bg-canvas)
  - 悬停: 背景 var(--bg-hover)
  - 选中: 边框 var(--accent-primary), 背景 var(--bg-selected)
  - 标题: font-family: var(--font-serif)
          font-size: 15px, font-weight 600, 单行截断
  - 作者: font-size: 13px, color: var(--text-tertiary)
```

### 6.3 步骤导航（Step Nav）
```
高度: 52px
背景: var(--bg-canvas)
边框: 底部 1px var(--border-light)
内边距: 0 36px
布局: flex, gap: 8px, overflow-x: auto, align-items: center

胶囊标签:
  - 内边距: 7px 16px
  - 圆角: 20px
  - 字号: 13px
  - 未选中: 背景 var(--bg-surface), 边框 1px var(--border-light), 文字 text-secondary
  - 悬停: 背景 var(--bg-hover), 边框 var(--border-medium)
  - 选中: 背景 var(--accent-primary), 文字 white, 边框 transparent, font-weight 600
  - 切换动画: background 200ms ease, color 150ms ease
```

### 6.4 操作栏（Action Bar）
```
高度: 48px
背景: var(--bg-surface)
边框: 底部 1px var(--border-light)
内边距: 0 36px
布局: flex, space-between, align-center

左侧: 「当前步骤：核心贡献识别」（16px，color: var(--accent-green)，font-weight: 600）
      + 「已选 3 个问题」（16px，color: var(--text-secondary)）
右侧: [全部取消] [生成 AI 综述] 
      文字按钮: 14px, padding: 6px 14px
      主按钮: 15px, padding: 10px 28px, 背景 var(--accent-primary)
```

### 6.5 维度折叠面板（Dimension Accordion）
```
面板容器:
  - 背景: var(--bg-canvas)
  - 圆角: 10px
  - 边框: 1px var(--border-light)
  - 阴影: var(--shadow-sm)
  - 下边距: 12px

面板头部（可点击展开）:
  - 高度: 56px
  - 内边距: 16px 24px
  - 布局: flex, space-between, align-center
  - 左侧: 复选框 + 维度标题
  - 复选框: 20px 方形, 圆角 4px, 边框 2px var(--border-medium)
  - 复选框选中: 背景 var(--accent-primary), 边框 var(--accent-primary), 白色 ✓
  - 维度标题: font-family: var(--font-serif)
              font-size: 17px, font-weight 600, text-primary
  - 右侧: ▶ 箭头图标（展开时旋转 90°）
  - 悬停: 背景 var(--bg-hover)

面板内容（展开后）:
  - 内边距: 16px 24px 20px
  - 布局: flex, gap: 14px, overflow-x: auto
  - 背景: var(--bg-canvas)（微妙区分头部和内容区）
  - 上边框: 1px var(--border-light)（分隔头部和内容）
```

### 6.6 论文回答卡片（Answer Card）
```
尺寸:
  - 最小宽度: 340px
  - 最大宽度: 420px
  - 最小高度: 180px
  - 最大高度: 500px（超出滚动）

样式:
  - 背景: var(--bg-surface)
  - 圆角: 10px
  - 边框: 1px var(--border-light)
  - 内边距: 20px

卡片头部:
  - 下边距: 14px
  - 下边距分隔线: 1px var(--border-light)
  - 文献标题: font-family: var(--font-serif)
              font-size: 15px, font-weight 600, 最多 2 行截断
  - 作者: font-size: 13px, color: var(--text-tertiary)

卡片内容（Markdown 渲染区域）:
  - 字号: 14px
  - 行高: 1.8
  - 颜色: text-secondary
  - 最大高度: 380px（超出滚动）
  - overflow-y: auto
  - **user-select: text**（必须允许右键选中复制）
  - **cursor: text**（暗示可编辑/可选中）

卡片悬停:
  - shadow: var(--shadow-md)
  - 边框: var(--border-medium)
```

---

## 7. Markdown 渲染规范

### 7.1 渲染库
- **主渲染器**：`marked.js` (v9.x)
- **公式渲染**：`KaTeX` (v0.16.x)
- **代码高亮**：`highlight.js`（如需要，否则用简单样式）

### 7.2 卡片内 Markdown 样式
```css
/* 段落 */
.markdown-body p {
  margin: 10px 0;
  line-height: 1.8;
}

/* 标题 */
.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 16px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-light);
}
.markdown-body h4, .markdown-body h5, .markdown-body h6 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 10px 0 6px;
}

/* 粗体 */
.markdown-body strong {
  font-weight: 600;
  color: var(--text-primary);
}

/* 斜体 */
.markdown-body em {
  font-style: italic;
  color: var(--text-secondary);
}

/* 引用块 */
.markdown-body blockquote {
  margin: 12px 0;
  padding: 12px 16px;
  border-left: 3px solid var(--accent-gold);
  background: rgba(180, 83, 9, 0.04);
  border-radius: 0 6px 6px 0;
  color: var(--text-secondary);
}

/* 列表 */
.markdown-body ul, .markdown-body ol {
  margin: 10px 0;
  padding-left: 24px;
}
.markdown-body li {
  margin: 6px 0;
}
.markdown-body li::marker {
  color: var(--accent-primary);
}

/* 表格 */
.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin: 12px 0;
  border: 1px solid var(--border-medium);
  border-radius: 6px;
  overflow: hidden;
}
.markdown-body th {
  background: var(--bg-hover);
  font-weight: 600;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 2px solid var(--border-medium);
}
.markdown-body td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
}
.markdown-body tr:nth-child(even) {
  background: rgba(0,0,0,0.015);
}

/* 代码 */
.markdown-body code {
  background: var(--bg-hover);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--accent-coral);
}
.markdown-body pre {
  background: #1c1917;
  color: #e7e5e4;
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.7;
  margin: 12px 0;
}
.markdown-body pre code {
  background: transparent;
  color: inherit;
  padding: 0;
}

/* 分割线 */
.markdown-body hr {
  border: none;
  height: 1px;
  background: var(--border-light);
  margin: 18px 0;
}

/* 链接 */
.markdown-body a {
  color: var(--accent-primary);
  text-decoration: none;
}
.markdown-body a:hover {
  text-decoration: underline;
}
```

### 7.3 公式渲染
```javascript
// 在卡片内容渲染完成后调用
function renderMathInCards() {
  const cards = document.querySelectorAll('.answer-card-content');
  cards.forEach(card => {
    renderMathInElement(card, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '$', right: '$', display: false},
        {left: '\\[', right: '\\]', display: true},
        {left: '\\(', right: '\\)', display: false}
      ],
      throwOnError: false,
      trust: true,
      strict: false
    });
  });
}
```

**重要**：公式渲染必须在 Markdown 渲染**之后**执行，且只对**已展开**的卡片进行（性能优化）。

### 7.4 表格渲染方案（优雅学术风格）

表格是学术论文中极为重要的内容元素，必须给予专门的优雅渲染方案。表格在卡片内横向空间有限，需要精心设计。

#### 7.4.1 基础表格样式
```css
/* 卡片内表格容器 */
.answer-card-content .table-wrapper {
  overflow-x: auto;
  margin: 12px 0;
  border-radius: 8px;
  border: 1px solid var(--border-light);
  /* 微妙的内阴影暗示可滚动 */
  box-shadow: inset -8px 0 8px -8px rgba(0,0,0,0.04);
}

/* 表格基础 */
.markdown-body table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
  line-height: 1.5;
  background: var(--bg-surface);
}

/* 表头 */
.markdown-body thead {
  background: var(--bg-hover);
}
.markdown-body thead tr:first-child th:first-child {
  border-top-left-radius: 8px;
}
.markdown-body thead tr:first-child th:last-child {
  border-top-right-radius: 8px;
}
.markdown-body th {
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 2px solid var(--border-medium);
  white-space: nowrap;
  position: sticky;
  top: 0;
  background: var(--bg-hover);
  z-index: 1;
}

/* 表体 */
.markdown-body td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
  color: var(--text-secondary);
  vertical-align: top;
}

/* 斑马纹 */
.markdown-body tbody tr:nth-child(even) {
  background: rgba(0, 0, 0, 0.015);
}

/* 悬停行 */
.markdown-body tbody tr:hover {
  background: rgba(22, 101, 52, 0.03);
}

/* 最后一行底部圆角 */
.markdown-body tbody tr:last-child td:first-child {
  border-bottom-left-radius: 8px;
}
.markdown-body tbody tr:last-child td:last-child {
  border-bottom-right-radius: 8px;
}
```

#### 7.4.2 特殊表格类型增强
```css
/* 数据表格（包含数字的表格） */
.markdown-body table.data-table td:not(:first-child) {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
}

/* 对比表格（两列对比） */
.markdown-body table.compare-table {
  border-left: 3px solid var(--accent-primary);
}
.markdown-body table.compare-table td:first-child {
  font-weight: 500;
  color: var(--text-primary);
  width: 30%;
  background: rgba(22, 101, 52, 0.02);
}

/* 引用表格（带来源标注） */
.markdown-body table caption {
  caption-side: bottom;
  text-align: left;
  padding: 8px 12px;
  font-size: 11px;
  color: var(--text-tertiary);
  font-style: italic;
  border-top: 1px solid var(--border-light);
}
```

#### 7.4.3 卡片内表格适配
由于卡片宽度有限（360px），表格可能需要横向滚动：
```css
/* 表格横向滚动提示 */
.answer-card-content .table-wrapper::after {
  content: "";
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 24px;
  background: linear-gradient(to right, transparent, var(--bg-surface));
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s;
}
.answer-card-content .table-wrapper:hover::after {
  opacity: 1;
}

/* 最小列宽防止挤压 */
.markdown-body th,
.markdown-body td {
  min-width: 80px;
}

/* 第一列通常较宽（标签/名称） */
.markdown-body td:first-child,
.markdown-body th:first-child {
  min-width: 120px;
}
```

#### 7.4.4 表格与 Markdown 其他元素的关系
```css
/* 表格前的段落 */
.markdown-body p + table {
  margin-top: 8px;
}

/* 表格后的段落 */
.markdown-body table + p {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
  font-style: italic;
}

/* 嵌套在列表中的表格 */
.markdown-body li > table {
  margin: 8px 0;
  font-size: 11px;
}
```

#### 7.4.5 渲染时机
表格渲染与 Markdown 同步进行，无需额外处理。但为确保复杂表格正确渲染：
```javascript
// 在渲染卡片内容时，为表格添加 wrapper
function renderCardContent(content) {
  const html = marked.parse(content);
  // 为每个 table 添加 wrapper（便于横向滚动）
  return html.replace(
    /<table/g,
    '<div class="table-wrapper"><table'
  ).replace(
    /<\/table>/g,
    '</table></div>'
  );
}
```

---

## 8. 动画与微交互

### 8.1 页面加载
```css
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.dimension-item {
  animation: fadeInUp 0.4s ease-out both;
}
/* stagger: 每个维度延迟 50ms */
.dimension-item:nth-child(1) { animation-delay: 0ms; }
.dimension-item:nth-child(2) { animation-delay: 50ms; }
.dimension-item:nth-child(3) { animation-delay: 100ms; }
/* ... */
```

### 8.2 折叠展开
```css
.dimension-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.dimension-item.expanded .dimension-body {
  max-height: 800px; /* 足够大的值 */
}
.dimension-arrow {
  transition: transform 0.25s ease;
}
.dimension-item.expanded .dimension-arrow {
  transform: rotate(90deg);
}
```

### 8.3 卡片悬停
```css
.answer-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.answer-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--border-medium);
}
```

### 8.4 复选框动画
```css
.dimension-checkbox {
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.dimension-checkbox.checked {
  animation: checkPop 0.2s ease;
}
@keyframes checkPop {
  0% { transform: scale(1); }
  50% { transform: scale(1.1); }
  100% { transform: scale(1); }
}
```

### 8.5 文献卡片选中
```css
.paper-card {
  transition: all 0.2s ease;
}
.paper-card.selected {
  animation: selectPulse 0.3s ease;
}
@keyframes selectPulse {
  0% { box-shadow: 0 0 0 0 rgba(22, 101, 52, 0.2); }
  70% { box-shadow: 0 0 0 6px rgba(22, 101, 52, 0); }
  100% { box-shadow: 0 0 0 0 rgba(22, 101, 52, 0); }
}
```

---

## 9. 布局核心：非表格的行列结构

### 9.1 核心原则
**坚决不使用 `<table>` 元素**，而是用现代 CSS Grid + Flexbox 实现：
- **行（纵向）**：每个分析维度是一个独立的面板（accordion item）
- **列（横向）**：每个面板内，各篇文献的回答卡片横向排列

### 9.2 CSS 实现
```css
/* 页面容器 */
.container {
  width: 100%;
  padding: 40px 60px;
}

/* 维度列表容器 */
.dimension-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px 24px;
}

/* 单个维度面板 */
.dimension-item {
  background: var(--bg-canvas);
  border-radius: 10px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

/* 面板头部 */
.dimension-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  height: 56px;
  cursor: pointer;
  user-select: none;
}

/* 面板内容区：论文卡片横向排列 */
.dimension-body {
  background: var(--bg-canvas);
  border-top: 1px solid var(--border-light);
}

.paper-cards-container {
  display: flex;
  gap: 14px;
  padding: 16px 24px 20px;
  overflow-x: auto;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
}

/* 单张论文卡片 */
.answer-card {
  flex: 0 0 auto;      /* 不伸缩 */
  width: 380px;        /* 固定宽度 */
  min-height: 200px;
  max-height: 500px;
  background: var(--bg-surface);
  border-radius: 10px;
  border: 1px solid var(--border-light);
  padding: 20px;
  overflow-y: auto;
  user-select: text;   /* 允许选中文本 */
  cursor: text;
}
```

### 9.3 横向滚动优化
```css
.paper-cards-container::-webkit-scrollbar {
  height: 6px;
}
.paper-cards-container::-webkit-scrollbar-track {
  background: transparent;
  margin: 0 4px;
}
.paper-cards-container::-webkit-scrollbar-thumb {
  background: var(--border-medium);
  border-radius: 3px;
}
.paper-cards-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* 鼠标拖拽滚动 */
.paper-cards-container {
  cursor: grab;
}
.paper-cards-container:active {
  cursor: grabbing;
}
```

---

## 10. 固定栏层级管理

页面有多个固定定位区域，需要精确的 z-index 管理：
```css
:root {
  --z-header: 100;        /* 顶栏 */
  --z-paper-bar: 99;      /* 文献选择栏 */
  --z-step-nav: 98;       /* 步骤导航 */
  --z-action-bar: 97;     /* 操作栏 */
  --z-modal: 200;         /* 模态框/弹窗 */
}
```

**阴影策略**：固定栏底部添加微妙的阴影，暗示内容在其下方滚动：
```css
.header, .paper-bar, .step-nav, .action-bar {
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
```

---

## 11. 文字选中与复制

### 11.1 全局策略
```css
/* 全局允许选中文本 */
body {
  user-select: text;
  -webkit-user-select: text;
}

/* 仅以下元素禁止选中：
   - 按钮
   - 导航标签
   - 面板头部（但复选框除外）
*/
button, .step-pill, .dimension-header {
  user-select: none;
  -webkit-user-select: none;
}
```

### 11.2 卡片内容区
```css
.answer-card-content {
  user-select: text;
  -webkit-user-select: text;
  cursor: text;
}

/* 确保公式也能被选中 */
.answer-card-content .katex {
  user-select: text;
  -webkit-user-select: text;
}
```

### 11.3 复制提示
当用户选中文本时，显示一个浮动的「复制」按钮（可选增强）：
```
用户选中文字 → 鼠标释放 → 显示小型浮动工具栏 [复制] [引用]
```

---

## 12. 响应式适配

### 12.1 桌面端（≥1024px）
- 完整布局，所有固定栏显示
- 卡片宽度 360px，一行可显示 3-4 张

### 12.2 平板端（768px - 1023px）
- 文献选择栏改为 2 行网格
- 卡片宽度 320px
- 固定栏保持，但间距缩小

### 12.3 移动端（<768px）
- 操作栏简化，仅保留核心信息
- 卡片宽度 85vw（几乎全屏）
- 横向滚动改为触摸滑动为主
- 固定栏高度适当减小

---

## 13. 技术依赖

```html
<!-- 字体 -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&family=Noto+Serif+SC:wght@500;600;700&display=swap" rel="stylesheet">

<!-- Markdown 渲染 -->
<script src="https://cdn.jsdelivr.net/npm/marked@9.x/marked.min.js"></script>

<!-- 公式渲染 -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.x/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.x/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.x/dist/contrib/auto-render.min.js"></script>

<!-- 代码高亮（可选） -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.x/styles/github.min.css">
<script src="https://cdn.jsdelivr.net/npm/highlight.js@11.x/lib/highlight.min.js"></script>
```

---

## 14. 编码规范（⚠️ 极其重要）

### 14.1 统一使用 UTF-8
**本项目所有文件必须使用 UTF-8 编码**，包括：
- HTML 文件：`charset="UTF-8"`
- JavaScript 文件：UTF-8 无 BOM
- CSS 文件：UTF-8 无 BOM
- JSON 数据文件：UTF-8
- Python 后端文件：`# -*- coding: utf-8 -*-`

### 14.2 中文乱码预防
- 所有 HTML 文件必须在 `<head>` 中明确声明：`<meta charset="UTF-8">`
- 所有 JSON 文件必须使用 UTF-8 编码保存，不得使用 GBK/GB2312/GB18030
- 在 Windows 环境下编辑时，**特别注意**某些编辑器可能默认使用 GBK 保存，务必手动指定 UTF-8
- 后端读取 JSON 文件时，**必须**显式指定 `encoding="utf-8"`：
  ```python
  with open(filepath, "r", encoding="utf-8") as f:
      return json.load(f)
  ```

### 14.3 后续修改注意事项
**⚠️ 警告**：在后续修改、查找替换、批量编辑时，**千万要注意保持编码一致**：
- 使用支持编码选择的编辑器（VS Code、WebStorm、Notepad++）
- 修改前确认文件当前编码为 UTF-8
- 修改后保存时再次确认编码为 UTF-8
- **绝对禁止**在 UTF-8 文件中混入 GBK 编码的中文内容
- 如果发现中文显示为乱码（如 `�` 或 `æ¼å±`），立即检查文件编码
- 建议提交前使用 `git diff` 检查中文内容是否正常显示

## 15. 文件清单

| 文件 | 说明 |
|------|------|
| `frontend/public/compare_7step.html` | 七步精读对比（基于本方案重构） |
| `frontend/public/compare_4step.html` | 四步精读对比（基于本方案重构） |
| `frontend/public/compare_long.html` | 长文本精读对比（基于本方案重构） |
| `backend/routers/compare.py` | 后端接口（已存在，无需改动） |
| `backend/compare_demo_server.py` | 独立 Demo 后端服务（端口 8001） |
| `docs/compare-long-demo-data.json` | 长文本精读 demo 数据 |
| `docs/compare-qual-demo-data.json` | 四步精读 demo 数据 |
| `docs/compare-quant-demo-data.json` | 七步精读 demo 数据 |

---

## 16. 验收标准

- [ ] **视觉**：整体效果优雅精致，无"AI 味"，配色克制高级
- [ ] **布局**：维度纵向排列，论文横向对比，**坚决不使用 table 标签**
- [ ] **交互**：复选框逻辑与旧 compare 完全一致（选中状态持久化、全选/清空、AI 综述触发条件）
- [ ] **公式**：`$...$` 和 `$$...$$` 正确渲染，排版美观
- [ ] **复制**：卡片内所有文字均可右键选中和复制，包括公式
- [ ] **动画**：展开/折叠、悬停、选中都有流畅的微交互动画
- [ ] **性能**：5-10 篇文献流畅显示，展开/折叠不卡顿
- [ ] **响应式**：桌面端体验完美，移动端可用

---

## 17. 与 v1.0 的关键差异

| 维度 | v1.0 | v2.0 |
|------|------|------|
| **布局结构** | 步骤切换后重载整个问题列表 | 固定步骤导航 + 维度纵向列表 |
| **复选框** | 未明确说明 | **完全复用旧 compare 逻辑** |
| **配色** | 暖纸白+墨绿+琥珀金 | **更克制的温暖中性色+深墨绿** |
| **卡片设计** | 基础卡片 | **精致卡片：头像、悬停动效、阴影层次** |
| **文字选中** | 未提及 | **明确支持右键选中和复制** |
| **公式渲染** | 简单提及 | **详细的 KaTeX 配置和时机说明** |
| **动画** | 简单列表 | **每个元素都有精心设计的微交互** |
| **字体** | 未明确 | **衬线标题+无衬线正文，提升学术感** |
