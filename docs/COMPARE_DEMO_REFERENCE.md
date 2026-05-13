# 对比综述 Demo 前后端技术参考

> 本文档供清空上下文后快速恢复开发记忆。包含：文件清单、后端 API、前端页面架构、全局状态、函数索引、数据结构、修改指南。

---

## 1. 文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `backend/compare_demo_server.py` | ~80 | 独立 demo 后端，端口 8001 |
| `frontend/public/compare_index.html` | ~100 | 入口导航页 |
| `frontend/public/compare_long.html` | ~349 | 长文本精读对比页 |
| `frontend/public/compare_4step.html` | ~928 | 四步精读对比页 |
| `frontend/public/compare_7step.html` | ~817 | 七步精读对比页 |
| `docs/compare-design-spec.md` | ~1049 | v2.0 设计规范（色彩/字体/布局/交互） |
| `docs/compare-long-demo-data.json` | — | 长文本 demo 数据（3 篇文献） |
| `docs/compare-qual-demo-data.json` | — | 四步精读 demo 数据（2 篇文献） |
| `docs/compare-quant-demo-data.json` | — | 七步精读 demo 数据（3 篇文献） |

---

## 2. 后端：`backend/compare_demo_server.py`

### 启动

```bash
python backend/compare_demo_server.py    # → http://localhost:8001
```

### 全局变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `DOCS_DIR` | `Path` | 指向 `docs/` 目录 |
| `FRONTEND_PUBLIC` | `Path` | 指向 `frontend/public/` 目录 |
| `DATA_FILES` | `dict` | `{"long": "compare-long-demo-data.json", "qual": ..., "quant": ...}` |
| `_cache` | `dict` | JSON 数据内存缓存 |

### 函数索引

| 函数 | 行号 | 说明 |
|------|------|------|
| `_load(mode)` | L38 | 按模式加载 JSON 文件，带缓存 |
| `get_long()` | L49 | `GET /api/compare-demo/long` |
| `get_qual()` | L54 | `GET /api/compare-demo/qual` |
| `get_quant()` | L59 | `GET /api/compare-demo/quant` |
| `index()` | L66 | `GET /` → 返回 `compare_index.html` |
| `serve_long()` | L74 | `GET /compare_long.html` |
| `serve_4step()` | L79 | `GET /compare_4step.html` |
| `serve_7step()` | L84 | `GET /compare_7step.html` |

### API 端点汇总

| 方法 | 路径 | 返回 |
|------|------|------|
| GET | `/` | `compare_index.html` |
| GET | `/compare_long.html` | 长文本对比页 |
| GET | `/compare_4step.html` | 四步对比页 |
| GET | `/compare_7step.html` | 七步对比页 |
| GET | `/api/compare-demo/long` | 长文本 JSON 数据 |
| GET | `/api/compare-demo/qual` | 四步精读 JSON 数据 |
| GET | `/api/compare-demo/quant` | 七步精读 JSON 数据 |

---

## 3. 数据结构

### 3.1 长文本（long）— 扁平维度式

```json
{
  "mode": "long",
  "label": "长文本精读",
  "papers": [
    {
      "id": "uuid",
      "title": "论文标题",
      "authors": [],
      "year": null,
      "dimensions": [
        { "id": "long.research_question", "label": "Research Question", "content": "## Markdown..." },
        { "id": "long.theory", "label": "Theory", "content": "..." },
        { "id": "long.identification", "label": "Identification", "content": "..." }
      ]
    }
  ]
}
```

**特点**：`papers[].dimensions[]` 是扁平数组，无步骤分组。导航标签 = 所有维度 label 的去重集合。

### 3.2 四步精读（qual）— 步骤分组式

```json
{
  "mode": "qual",
  "label": "四步精读",
  "papers": [
    {
      "id": "uuid",
      "title": "论文标题",
      "authors": ["作者1"],
      "year": 2022,
      "steps": {
        "第一步：背景与问题": {
          "label": "第一步：背景与问题",
          "subQuestions": [
            { "id": "qual.step1.q1", "label": "1. 论文分类", "content": "Markdown..." },
            { "id": "qual.step1.q2", "label": "2. 核心问题", "content": "..." }
          ]
        },
        "第二步：理论视角": { ... },
        "第三步：逻辑与证据": { ... },
        "第四步：价值与启示": { ... }
      }
    }
  ]
}
```

**特点**：`papers[].steps[stepName].subQuestions[]`，4 步分组。

### 3.3 七步精读（quant）— 步骤分组式

```json
{
  "mode": "quant",
  "label": "七步精读",
  "papers": [
    {
      "id": "uuid",
      "title": "论文标题",
      "steps": {
        "第一步：核心贡献识别": { "label": "...", "subQuestions": [...] },
        "第二步：理论框架评估": { ... },
        "第三步：方法论批判": { ... },
        "第四步：实证结果解读": { ... },
        "第五步：局限性分析": { ... },
        "第六步：实践意义": { ... },
        "第七步：未来方向": { ... }
      }
    }
  ]
}
```

**特点**：同四步，7 步分组。子问题 ID 格式 `quant.step{N}.q{M}`。

---

## 4. 前端页面：`compare_long.html`

### 全局状态（L164-165）

```javascript
var API_URL = 'http://localhost:8001/api/compare-demo/long';
var st = {
  papers: [],           // 全部论文数据
  dims: [],             // 去重后的维度列表 [{id, label}]
  selPapers: new Set(),  // 选中的论文 ID
  activePill: 'all',     // 当前维度标签，'all' 或维度 label
  selDims: new Set(),    // 选中的维度 ID（复选框）
  expanded: new Set()    // 展开的维度 ID
};
```

### 函数索引

| 函数 | 行号 | 参数 | 说明 |
|------|------|------|------|
| `esc(s)` | L167 | `s: string` | HTML 转义 |
| `md2html(raw)` | L168 | `raw: string` | marked.parse + 包裹 `<table>` 为 `.table-wrapper` |
| `mathRender(el)` | L174 | `el: DOM元素` | KaTeX 公式渲染，处理 `$...$` 和 `$$...$$` |
| `uniqueDims(papers)` | L186 | `papers: array` | 从所有论文中提取去重维度列表 |
| `renderPaperCards()` | L195 | — | 渲染文献选择区的卡片 |
| `renderDimPills()` | L210 | — | 渲染维度导航胶囊标签 |
| `renderAccordion()` | L230 | — | 渲染维度折叠面板列表 |
| `updateVisibility()` | L265 | — | 根据 activePill 显示/隐藏维度面板 |
| `togglePaper(id)` | L279 | `id: string` | 切换论文选中状态，重新渲染卡片和折叠面板 |
| `selectPill(label)` | L283 | `label: string` | 切换维度标签，更新 activePill 和可见性 |
| `handleCheckbox(dimId)` | L290 | `dimId: string` | 切换维度复选框选中状态 |
| `toggleAccordion(dimId)` | L295 | `dimId: string` | 展开/折叠维度面板 |
| `init()` | (底部) | — | fetch 数据 → 填充 st → 调用各 render 函数 |

### 关键 DOM 结构

```
#header          → 标题区
#paper-bar       → 文献选择区（内含 .paper-cards）
#dim-nav         → 维度导航胶囊
#action-bar      → 操作栏
#accordion-list  → 维度折叠面板列表
```

---

## 5. 前端页面：`compare_4step.html`

### 全局状态（L558-566）

```javascript
var API_URL = 'http://localhost:8001/api/compare-demo/qual';
var STEP_NAMES = ['第一步：背景与问题', '第二步：理论视角', '第三步：逻辑与证据', '第四步：价值与启示'];
var STEP_KEYS  = ['第一步：背景与问题', '第二步：理论视角', '第三步：逻辑与证据', '第四步：价值与启示'];
var rawData = null;                // 原始 JSON 数据
var selectedPapers = new Set();    // 选中的论文 ID
var selectedSubQs = new Set();     // 选中的子问题 ID（跨步骤持久化）
var currentStep = '全部';           // 当前步骤标签
var openAccordions = new Set();    // 展开的子问题 ID
```

### 函数索引

| 函数 | 行号 | 参数 | 说明 |
|------|------|------|------|
| `init()` | L570 | — | fetch 数据 → 调用 load() |
| `load(data)` | L581 | `data: object` | 存 rawData → 调用三个 render |
| `renderPaperCards()` | L593 | — | 渲染文献选择卡片 |
| `togglePaper(id)` | L616 | `id: string` | 切换论文选中 → refreshCardStates → renderAccordion |
| `refreshPaperCardStates()` | L623 | — | 刷新所有卡片的 selected 样式 |
| `renderStepNav()` | L631 | — | 渲染步骤导航胶囊（全部 + 4 步） |
| `getStepsToRender()` | L650 | — | 返回当前应显示的步骤列表 |
| `getAllSubQuestionsForStep(step)` | L656 | `step: string` | 从 rawData 中获取某步骤下所有子问题（跨论文） |
| `getSelectedPapers()` | L673 | — | 返回选中的论文对象数组 |
| `renderAccordion()` | L678 | — | 渲染子问题折叠面板列表（核心渲染函数，~130 行） |
| `selectAllVisible()` | L811 | — | 当前可见子问题全选 |
| `clearAllSelections()` | L821 | — | 清空所有选中 |
| `updateActionBar()` | L827 | — | 更新操作栏文案和 AI 综述按钮状态 |
| `handleSynthesis()` | L839 | — | 收集选中子问题内容，弹窗显示 |
| `closeModal()` | L910 | — | 关闭综述弹窗 |
| `wrapTables(html)` | L914 | — | 将 `<table>` 包裹为 `.table-wrapper` |
| `escHtml(s)` | L918 | `s: string` | HTML 转义 |

### 关键 DOM 结构

```
#paper-bar       → 文献选择区
#step-nav        → 步骤导航胶囊
#action-bar      → 操作栏
#accordion-list  → 子问题折叠面板列表
#synthesis-modal → AI 综述弹窗
```

---

## 6. 前端页面：`compare_7step.html`

### 全局状态（L551-575）

```javascript
var API_URL = 'http://localhost:8001/api/compare-demo/quant';
var STEP_KEYS = ['第一步：核心贡献识别', '第二步：理论框架评估', ...共7项];
var STEP_PILLS = ['①核心贡献', '②理论框架', '③方法论', '④实证结果', '⑤局限性', '⑥实践意义', '⑦未来方向'];
var selectedPaperIds = new Set();   // 选中的论文 ID
var currentStep = STEP_KEYS[0];     // 当前步骤（默认第一步）
var selectedSubQIds = new Set();    // 选中的子问题 ID
var openAccordions = new Set();     // 展开的子问题 ID
```

注意：`papers` 是局部变量（在 `loadData` 内赋值），不是全局。

### 函数索引

| 函数 | 行号 | 参数 | 说明 |
|------|------|------|------|
| `loadData()` | L576 | — | fetch 数据 → 存 papers → 调用各 render |
| `showLoading()` | L590 | — | 显示加载中 |
| `showError(msg)` | L594 | `msg: string` | 显示错误信息 |
| `escapeHtml(s)` | L598 | `s: string` | HTML 转义 |
| `renderPaperCards()` | L603 | — | 渲染文献选择卡片 |
| `updatePaperCount()` | L634 | — | 更新选中文献计数 |
| `renderStepNav()` | L637 | — | 渲染步骤导航胶囊（全部 + 7 步缩短标签） |
| `selectStep(key)` | L650 | `key: string` | 切换步骤 → 重新渲染 |
| `getStepsToRender()` | L656 | — | 返回当前应显示的步骤列表 |
| `renderAccordion()` | L660 | — | 渲染子问题折叠面板（核心渲染，~55 行） |
| `getSubQuestionsForStep(step)` | L715 | `step: string` | 获取某步骤下所有子问题（跨论文） |
| `getSubQuestionContent(paperId, subQId)` | L731 | `paperId, subQId` | 获取指定论文指定子问题的 content |
| `renderMarkdown(text)` | L741 | `text: string` | marked.parse + wrapTables |
| `renderMathInContent()` | L749 | — | KaTeX 公式渲染所有已展开的卡片 |
| `updateActionBar()` | L775 | — | 更新操作栏文案和按钮状态 |

### 关键 DOM 结构

```
#loading         → 加载提示
#error           → 错误提示
#paper-bar       → 文献选择区
#step-nav        → 步骤导航胶囊
#action-bar      → 操作栏
#accordion-list  → 子问题折叠面板列表
```

---

## 7. 共享设计规范摘要

### CSS 变量（三个页面一致）

```css
--bg-canvas: #faf8f5;        --text-primary: #2d2a26;
--bg-surface: #ffffff;       --text-secondary: #5c554d;
--bg-hover: #f5f2ee;         --text-tertiary: #9a9188;
--bg-selected: rgba(22,101,52,0.06); --accent-primary: #166534;
--border-light: #ebe7e0;     --accent-gold: #b45309;
--border-medium: #ddd8cf;    --shadow-sm/md/lg
```

### CDN 依赖

```
Google Fonts: Noto Sans SC, Noto Serif SC
marked.js v9: Markdown 渲染
KaTeX v0.16: 公式渲染（katex.min.js + auto-render.min.js）
```

### 交互规则

- 文献选择：≥2 篇才能触发 AI 综述
- 复选框：子问题级别，跨步骤/维度持久化
- 折叠：默认全部折叠，350ms max-height 动画
- 全选：仅作用于当前可见的子问题
- 清空：清空所有已选子问题

---

## 8. 常见修改场景

### 8.1 改配色/字体/间距

改 CSS 变量即可。三个文件各自内联 `<style>`，改对应文件内的 `:root` 块。

### 8.2 改长文本页面的维度展示

文件：`compare_long.html`
核心函数：`renderAccordion()` (L230) — 每个维度面板的 HTML 结构

### 8.3 改四步/七步的子问题卡片样式

文件：`compare_4step.html` 或 `compare_7step.html`
核心函数：`renderAccordion()` — 答案卡片的 HTML 结构

### 8.4 改 AI 综述按钮行为

- `compare_4step.html`: `handleSynthesis()` (L839)
- `compare_long.html` / `compare_7step.html`: 无独立函数，按钮在 `updateActionBar()` 或 `renderAccordion()` 内创建

### 8.5 换 demo 数据

替换对应的 JSON 文件：
- `docs/compare-long-demo-data.json`
- `docs/compare-qual-demo-data.json`
- `docs/compare-quant-demo-data.json`

重启服务即可（有内存缓存）。

### 8.6 改后端端口

改 `compare_demo_server.py` 末尾 `uvicorn.run(app, port=8001)` 和三个 HTML 文件的 `API_URL`。

### 8.7 添加新的文献到 demo

在对应 JSON 的 `papers` 数组中添加新对象，保持相同结构。注意四步/七步的 `steps` key 必须与已有步骤名一致。

---

## 9. 三个页面的架构差异速查

| | compare_long | compare_4step | compare_7step |
|---|---|---|---|
| API | `/api/compare-demo/long` | `/api/compare-demo/qual` | `/api/compare-demo/quant` |
| 数据结构 | `papers[].dimensions[]` | `papers[].steps[name].subQuestions[]` | `papers[].steps[name].subQuestions[]` |
| 导航粒度 | 维度（动态提取） | 4 步（硬编码） | 7 步（硬编码） |
| 折叠单位 | 维度 | 子问题 | 子问题 |
| 全局状态 | `st` 对象 | 6 个独立变量 | 4 个独立变量 |
| papers 存储 | `st.papers` | `rawData.papers` | 局部变量（loadData 内） |
| 综述弹窗 | 无 | `#synthesis-modal` | 无 |
| 代码量 | ~349 行 | ~928 行 | ~817 行 |
