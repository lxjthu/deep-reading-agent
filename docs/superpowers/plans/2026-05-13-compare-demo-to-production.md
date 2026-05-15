# 对比综述 Demo 接入生产数据库 实施规划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将三个独立 demo HTML 页面（长文本/四步/七步对比）改造为接入真实数据库的 React 组件模块，替代现有 iframe 方案，成为工作台的正式 Tab。

**Architecture:** 新增后端 API 端点，根据用户已完成的精读任务（ReadingItem）自动聚合出对比数据（与 demo JSON 同构）。前端新建 `CompareView` React 组件替代 iframe，复用 demo 的 CSS/交互但改为 React 状态管理 + 真实 API 调用。AI 综述功能对接已有 SSE 流式端点。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async（后端）；React 19 + Zustand + Tailwind（前端）；SSE 流式响应（AI 综述）

---

## 现状分析

### 当前架构（Demo 模式）

```
App.tsx CompareTab → <iframe src="/compare_long.html">
                           ↓
                     静态 HTML (vanilla JS)
                           ↓
               fetch http://localhost:8001/api/compare-demo/long
                           ↓
               compare_demo_server.py → docs/compare-*-demo-data.json
```

- 三个对比 Tab 均通过 `<iframe>` 加载 `frontend/public/compare_*.html`
- 静态 HTML 从独立 demo 服务（端口 8001）获取硬编码 JSON 数据
- 无 JWT 鉴权、无用户隔离、AI 综述按钮不可用

### 目标架构（生产模式）

```
App.tsx CompareTab → <CompareView mode="long|quant|qual" />
                           ↓
                     React 组件 (Zustand state)
                           ↓
               fetch /api/compare/reading-data (自动带 JWT)
                           ↓
               compare.py → build_structured_paper_data()
                           ↓
               ReadingItem (DB) → 聚合为 papers[] JSON
```

### 数据映射关系

Demo JSON 结构 ←→ 数据库模型：

| Demo JSON 字段 | DB 来源 |
|---|---|
| `papers[].id` | `BibEntry.id` |
| `papers[].title` | `BibEntry.title` |
| `papers[].authors` | `BibEntry.authors_json` |
| `papers[].year` | `BibEntry.year` |
| `papers[].dimensions[]` (long) | `ReadingItem` where `mode='long'`, `section_type='dimension'` |
| `papers[].dimensions[].id` | `ReadingItem.item_key` (如 `long.research_question`) |
| `papers[].dimensions[].label` | `ReadingItem.item_label` (如 `Research Question`) |
| `papers[].dimensions[].content` | `ReadingItem.content` |
| `papers[].steps[name].subQuestions[]` (4/7步) | `ReadingItem` where `section_type='subquestion'`, grouped by `parent_key` |
| `papers[].steps[name].subQuestions[].id` | `ReadingItem.item_key` (如 `quant.step1.q1`) |
| `papers[].steps[name].subQuestions[].label` | `ReadingItem.item_label` |
| `papers[].steps[name].subQuestions[].content` | `ReadingItem.content` |

---

## 文件结构

### 后端修改

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/routers/compare.py` | 修改 | 新增 `GET /api/compare/reading-data` 端点 + 辅助函数 |
| `backend/routers/compare.py` | 修改 | 新增 `POST /api/compare/synthesis-stream` 统一 AI 综述端点 |

### 前端新建

| 文件 | 操作 | 职责 |
|------|------|------|
| `frontend/src/components/CompareView.tsx` | 新建 | 对比综述主组件（替代 iframe），含文献选择、维度导航、折叠面板 |
| `frontend/src/components/compare/PaperSelector.tsx` | 新建 | 文献选择区：列出已精读的论文卡片 |
| `frontend/src/components/compare/DimNavigation.tsx` | 新建 | 维度/步骤胶囊导航 |
| `frontend/src/components/compare/AccordionPanel.tsx` | 新建 | 三级折叠面板（collapsed/preview/full） |
| `frontend/src/components/compare/AnswerCard.tsx` | 新建 | 单篇论文的答案卡片（预览版 + 完整版） |
| `frontend/src/components/compare/SynthesisModal.tsx` | 新建 | AI 综述弹窗 + SSE 流式显示 |
| `frontend/src/hooks/useCompareData.ts` | 新建 | 对比数据获取 hook |
| `frontend/src/hooks/useSynthesisStream.ts` | 新建 | AI 综述 SSE 流式 hook |

### 前端修改

| 文件 | 操作 | 职责 |
|------|------|------|
| `frontend/src/App.tsx` | 修改 | 替换 CompareTab iframe 为 CompareView 组件 |

### 不修改的文件

| 文件 | 原因 |
|------|------|
| `backend/compare_demo_server.py` | 保留 demo 服务不动，供开发调试 |
| `frontend/public/compare_*.html` | 保留 demo 页面不动，作为交互参考 |
| `docs/compare-*-demo-data.json` | 保留 demo 数据不动 |
| `backend/db/models.py` | 无需新增模型，复用 ReadingItem/BibEntry |

---

## Task 1: 后端 — 新增对比数据聚合 API

**Files:**
- Modify: `backend/routers/compare.py`

### 目标端点

```
GET /api/compare/reading-data?mode=long|quant|qual
```

返回当前用户所有已完成精读的文献数据，结构与 demo JSON 一致。

### 实现要点

后端已有 `build_structured_paper_data()` 函数（L156-189）可以从 BibEntry 列表聚合 ReadingItem 数据。但该函数输出的格式（`dimensions` 是 `{label: content}` dict）与 demo JSON 格式（`dimensions` 是 `[{id, label, content}]` 数组）不完全一致。需要新建一个格式转换层。

- [ ] **Step 1: 在 compare.py 中新增 `reading_data` 端点**

在 `compare.py` 中新增端点，查询当前用户所有有 ReadingItem 的 BibEntry，按 mode 聚合数据。

```python
@router.get("/reading-data")
async def get_reading_data(
    mode: str = Query(..., pattern="^(long|quant|qual)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """获取当前用户所有已精读文献的对比数据，结构与 demo JSON 一致。"""
    # 1. 查询该用户所有有 ReadingItem 的 BibEntry（按 mode 过滤）
    # 2. 对每个 BibEntry 调用 build_structured_paper_data 的变体
    # 3. 转换为前端期望的 papers[] 格式
    # 4. 返回 { mode, label, papers }
```

查询逻辑：
1. 先查所有 ReadingItem where `owner_user_id == user.id` and `mode == mode`
2. 提取去重的 `bib_entry_id` 列表
3. 对每个 bib_entry_id，获取 BibEntry 基本信息 + 该 BibEntry 下所有 ReadingItem
4. 按 demo JSON 结构组装

- [ ] **Step 2: 新增 `build_compare_response` 辅助函数**

```python
def build_compare_response(mode: str, bib_entries_items: dict[str, list[ReadingItem]], bib_entries: dict[str, BibEntry]) -> dict:
    """
    将 ReadingItem 数据转换为前端期望的 papers[] 格式。
    bib_entries_items: { bib_entry_id: [ReadingItem, ...] }
    bib_entries: { bib_entry_id: BibEntry }
    """
    mode_labels = {"long": "长文本精读", "quant": "七步精读", "qual": "四步精读"}
    papers = []

    for bib_id, items in bib_entries_items.items():
        bib = bib_entries[bib_id]
        paper = {
            "id": bib.id,
            "title": bib.title,
            "authors": json.loads(bib.authors_json or "[]"),
            "year": bib.year,
            "journal": bib.journal or "",
            "doi": bib.doi or "",
        }

        if mode == "long":
            dimensions = []
            seen = set()
            for item in items:
                if item.item_key in seen:
                    continue
                seen.add(item.item_key)
                dimensions.append({
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                })
            paper["dimensions"] = dimensions
        else:
            steps = {}
            for item in items:
                step_name = item.parent_key or item.item_label
                if step_name not in steps:
                    steps[step_name] = {"label": step_name, "subQuestions": []}
                steps[step_name]["subQuestions"].append({
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                })
            paper["steps"] = steps

        papers.append(paper)

    return {"mode": mode, "label": mode_labels.get(mode, ""), "papers": papers}
```

- [ ] **Step 3: 验证端点**

启动后端，用 curl 测试：
```bash
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/compare/reading-data?mode=long"
```

预期返回与 demo JSON 同构的数据。

- [ ] **Step 4: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat: 新增 GET /api/compare/reading-data 端点，聚合 ReadingItem 为对比数据"
```

---

## Task 2: 后端 — 新增 AI 综述 SSE 端点

**Files:**
- Modify: `backend/routers/compare.py`

### 目标端点

```
POST /api/compare/synthesis-stream
```

统一入口，根据 mode 调用已有的 `synthesize_dimensions` 或 `synthesize_long_dimensions` 逻辑，以 SSE 流式返回。

### 实现要点

后端已有 `/synthesis`（L1197）和 `/synthesis_long`（L1341）两个 SSE 端点。新端点做统一封装，前端只需调一个 URL。

```python
class CompareSynthesisRequest(BaseModel):
    mode: str  # "long" | "quant" | "qual"
    bib_entry_ids: list[str]
    api_key: str
    selected_dimensions: list[str] = []  # 选中的维度/子问题 ID

@router.post("/synthesis-stream")
async def synthesis_stream(
    req: CompareSynthesisRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """统一 AI 综述 SSE 流式端点"""
    # 根据 mode 走已有逻辑
```

- [ ] **Step 1: 新增请求模型和端点**

在 `compare.py` 中新增 `CompareSynthesisRequest` 模型和 `synthesis_stream` 端点。内部复用已有的 `build_synthesis_dimension_prompt`、`build_paper_metadata_block`、`gather_bib_references` 等函数。

- [ ] **Step 2: 验证 SSE 端点**

用 curl 测试流式响应：
```bash
curl -N -H "Authorization: Bearer <token>" -X POST \
  "http://localhost:8000/api/compare/synthesis-stream" \
  -H "Content-Type: application/json" \
  -d '{"mode":"long","bib_entry_ids":["id1","id2"],"api_key":"sk-xxx","selected_dimensions":["long.research_question"]}'
```

预期：SSE 事件流，逐块返回综述内容。

- [ ] **Step 3: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat: 新增 POST /api/compare/synthesis-stream 统一 AI 综述端点"
```

---

## Task 3: 前端 — 新建 useCompareData Hook

**Files:**
- Create: `frontend/src/hooks/useCompareData.ts`

### 功能

封装对比数据获取逻辑：请求 `GET /api/compare/reading-data?mode=...`，返回 `{ papers, dims, loading, error, refetch }`。

```typescript
import { useState, useEffect, useCallback } from 'react'

interface DimItem {
  id: string
  label: string
  content: string
}

interface StepData {
  label: string
  subQuestions: DimItem[]
}

interface Paper {
  id: string
  title: string
  authors: string[]
  year: number | null
  journal?: string
  doi?: string
  dimensions?: DimItem[]
  steps?: Record<string, StepData>
}

interface CompareData {
  mode: string
  label: string
  papers: Paper[]
}

export function useCompareData(mode: 'long' | 'quant' | 'qual') {
  const [data, setData] = useState<CompareData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/compare/reading-data?mode=${mode}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [mode])

  useEffect(() => { fetchData() }, [fetchData])

  return { data, papers: data?.papers ?? [], loading, error, refetch: fetchData }
}
```

- [ ] **Step 1: 创建 `frontend/src/hooks/useCompareData.ts`**

写入上述代码。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useCompareData.ts
git commit -m "feat: 新增 useCompareData hook，封装对比数据获取逻辑"
```

---

## Task 4: 前端 — 新建 useSynthesisStream Hook

**Files:**
- Create: `frontend/src/hooks/useSynthesisStream.ts`

### 功能

封装 SSE 流式 AI 综述：POST `/api/compare/synthesis-stream`，通过 `EventSource` 或 `fetch + ReadableStream` 逐块读取，返回 `{ content, isStreaming, error, start }`。

```typescript
import { useState, useCallback, useRef } from 'react'

interface SynthesisParams {
  mode: string
  bib_entry_ids: string[]
  api_key: string
  selected_dimensions: string[]
}

export function useSynthesisStream() {
  const [content, setContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const start = useCallback(async (params: SynthesisParams) => {
    setIsStreaming(true)
    setContent('')
    setError(null)
    abortRef.current = new AbortController()

    try {
      const res = await fetch('/api/compare/synthesis-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: abortRef.current.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No response body')

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6)
            if (payload === '[DONE]') break
            try {
              const parsed = JSON.parse(payload)
              if (parsed.content) {
                setContent(prev => prev + parsed.content)
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setIsStreaming(false)
    }
  }, [])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const reset = useCallback(() => {
    setContent('')
    setError(null)
    setIsStreaming(false)
  }, [])

  return { content, isStreaming, error, start, abort, reset }
}
```

- [ ] **Step 1: 创建 `frontend/src/hooks/useSynthesisStream.ts`**

写入上述代码。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useSynthesisStream.ts
git commit -m "feat: 新增 useSynthesisStream hook，封装 AI 综述 SSE 流式调用"
```

---

## Task 5: 前端 — 新建 AnswerCard 和 AccordionPanel 组件

**Files:**
- Create: `frontend/src/components/compare/AnswerCard.tsx`
- Create: `frontend/src/components/compare/AccordionPanel.tsx`

### AnswerCard

从 demo HTML 的 `answerCard()` / `answerCardPreview()` 函数翻译为 React 组件。两种模式：`preview`（500px 高+渐变遮罩）和 `full`（无高度限制）。

### AccordionPanel

从 demo HTML 的三级折叠逻辑翻译为 React 组件。状态用 React state 管理（`collapsed` / `preview` / `full`）。

- [ ] **Step 1: 创建 `AnswerCard.tsx`**

```tsx
interface AnswerCardProps {
  paper: { id: string; title: string; authors: string[]; year: number | null }
  content: string | null
  variant: 'preview' | 'full'
}

export function AnswerCard({ paper, content, variant }: AnswerCardProps) {
  const auth = paper.authors?.slice(0, 3).join(', ') ?? ''
  const yr = paper.year ? ` (${paper.year})` : ''
  const isPreview = variant === 'preview'

  return (
    <div className={isPreview ? 'preview-card' : 'answer-card'}>
      <div className={isPreview ? 'preview-card-header' : 'answer-card-header'}>
        <div className={isPreview ? 'preview-card-title' : 'answer-card-title'}>
          {paper.title || '未命名文献'}
        </div>
        <div className={isPreview ? 'preview-card-meta' : 'answer-card-meta'}>
          {auth}{yr}
        </div>
      </div>
      {content ? (
        <div
          className={isPreview ? 'preview-card-content md-content' : 'answer-card-content md-content'}
          dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
        />
      ) : (
        <div className="answer-card-empty">（未包含此维度）</div>
      )}
    </div>
  )
}
```

其中 `renderMarkdown` 使用 `marked.parse` + KaTeX 渲染（从 demo 逻辑翻译，或在组件内 import marked）。

- [ ] **Step 2: 创建 `AccordionPanel.tsx`**

实现三级折叠面板，Props 包含维度标签、论文列表、内容映射、选中状态、展开/收起回调。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/compare/
git commit -m "feat: 新建 AnswerCard 和 AccordionPanel 对比组件"
```

---

## Task 6: 前端 — 新建 PaperSelector 和 DimNavigation 组件

**Files:**
- Create: `frontend/src/components/compare/PaperSelector.tsx`
- Create: `frontend/src/components/compare/DimNavigation.tsx`

### PaperSelector

从 demo HTML 的 `renderPaperCards()` 翻译。显示用户已精读的论文卡片列表，支持多选。Props: `papers[]`, `selectedIds: Set`, `onToggle(id)`。

### DimNavigation

从 demo HTML 的 `renderDimPills()` 翻译。动态显示选中论文包含的维度胶囊。Props: `dims[]`, `activeId`, `onSelect(id)`。

- [ ] **Step 1: 创建两个组件**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/compare/
git commit -m "feat: 新建 PaperSelector 和 DimNavigation 对比组件"
```

---

## Task 7: 前端 — 新建 SynthesisModal 组件

**Files:**
- Create: `frontend/src/components/compare/SynthesisModal.tsx`

### 功能

AI 综述结果弹窗，调用 `useSynthesisStream` hook，实时显示流式内容。

- 弹窗触发条件：≥2 篇文献 + ≥1 个选中维度 + 有 API Key
- 内容区使用 `md-content` 样式渲染 Markdown
- 底部显示"正在生成..."或完成状态
- 支持复制/关闭

- [ ] **Step 1: 创建 SynthesisModal 组件**

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/compare/SynthesisModal.tsx
git commit -m "feat: 新建 SynthesisModal AI 综述弹窗组件"
```

---

## Task 8: 前端 — 新建 CompareView 主组件

**Files:**
- Create: `frontend/src/components/CompareView.tsx`

### 功能

对比综述主容器组件，整合所有子组件。对应 demo HTML 的全局状态和渲染逻辑。

### Props

```tsx
interface CompareViewProps {
  mode: 'long' | 'quant' | 'qual'
  apiKey: string | null
}
```

### 内部状态（Zustand 风格，用 useState）

```typescript
const [selectedPaperIds, setSelectedPaperIds] = useState<Set<string>>(new Set())
const [activePill, setActivePill] = useState<string>('all')
const [selectedDimIds, setSelectedDimIds] = useState<Set<string>>(new Set())
const [dimStates, setDimStates] = useState<Record<string, 'collapsed' | 'preview' | 'full'>>({})
const [showSynthesis, setShowSynthesis] = useState(false)
```

### 核心逻辑

1. `useCompareData(mode)` 获取数据
2. 根据 `selectedPaperIds` 动态计算可用维度列表（`selectedDims` 函数逻辑）
3. 渲染 `PaperSelector` → `DimNavigation` → `AccordionPanel` → `SynthesisModal`
4. CSS：从 demo HTML 的 `<style>` 提取，转为 Tailwind 类或保留为 CSS module

- [ ] **Step 1: 创建 CompareView.tsx**

将 demo HTML 的全部 CSS 变量和关键样式复制为内联 style 或独立 CSS 文件。组件内部实现 demo HTML 中 `st` 对象的所有状态管理逻辑。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/CompareView.tsx
git commit -m "feat: 新建 CompareView 对比综述主组件"
```

---

## Task 9: 前端 — 替换 App.tsx 中的 iframe Tab 为 CompareView

**Files:**
- Modify: `frontend/src/App.tsx`

### 修改点

1. 删除 `CompareTab` 函数组件（L2986-3003）
2. 在三个 compare tab 的渲染中，替换为 `<CompareView mode="..." apiKey={apiKey} />`
3. 保留 Tab ID 和标签不变（`compare-long`, `compare-7step`, `compare-4step`）
4. 确保全屏布局（去掉 iframe 的 flex 容器，改用 CompareView 自身处理高度）

```tsx
// 修改前
case 'compare-long':
  return <CompareTab title="长文本精读对比分析" src="/compare_long.html" />

// 修改后
case 'compare-long':
  return <CompareView mode="long" apiKey={apiKey} />
```

对 `compare-7step`（mode="quant"）和 `compare-4step`（mode="qual"）同理。

- [ ] **Step 1: 修改 App.tsx**

导入 CompareView，替换三个 case 分支，删除 CompareTab 组件定义。

- [ ] **Step 2: 验证**

```bash
cd frontend && npm run build
```

确保无 TypeScript 错误，无 import 缺失。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: 替换对比 Tab iframe 为 CompareView React 组件"
```

---

## Task 10: 前端 — CSS 样式迁移

**Files:**
- Create: `frontend/src/components/compare/compare.css`

### 功能

从 demo HTML 的 `<style>` 块提取所有 CSS，作为独立 CSS 文件在 CompareView 中 import。

### 要点

- 保留所有 CSS 变量（`:root` 块）
- 保留所有组件样式（`.paper-card`, `.dim-pill`, `.accordion-*`, `.answer-card`, `.preview-card` 等）
- 保留所有 Markdown 渲染样式（`.md-content *`）
- 保留响应式媒体查询
- 在 CompareView 中 `import './compare/compare.css'`

- [ ] **Step 1: 提取 CSS 到独立文件**

- [ ] **Step 2: 在 CompareView 中导入**

- [ ] **Step 3: 验证样式正确**

启动前端 `npm run dev`，切换到对比 Tab，检查卡片、胶囊、折叠面板样式与 demo 一致。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/compare/compare.css
git commit -m "feat: 迁移对比综述 CSS 样式到独立文件"
```

---

## Task 11: 端到端验证

**Files:**
- 无新文件

### 验证流程

1. 启动后端 `uvicorn backend.main:app --reload --port 8000`
2. 启动前端 `cd frontend && npm run dev`
3. 注册/登录 → 设置 API Key
4. 上传 PDF → 完成一篇长文本精读
5. 再上传一篇 → 完成精读
6. 切换到"长文本对比" Tab
7. 验证：
   - [ ] 两篇论文出现在文献选择区
   - [ ] 点击选中后，维度胶囊动态显示
   - [ ] 折叠面板三级交互正常（collapsed → preview → full）
   - [ ] 预览卡片显示 Markdown 渲染内容 + 渐变遮罩
   - [ ] 完整展开显示所有内容
   - [ ] 全选/清空按钮正常
   - [ ] AI 综述按钮可用，点击后弹窗流式显示
8. 同理验证四步对比和七步对比 Tab

### 四步/七步特有验证

- [ ] 步骤胶囊导航正确（4 步 / 7 步）
- [ ] 子问题折叠面板按步骤分组
- [ ] 跨步骤选中持久化正常

---

## Task 12: 清理和文档更新

**Files:**
- Modify: `docs/COMPARE_DEMO_REFERENCE.md`
- Modify: `docs/TECHNICAL_OVERVIEW.md`

### 清理内容

1. 更新 `COMPARE_DEMO_REFERENCE.md`：记录从 demo 到生产的改造
2. 更新 `TECHNICAL_OVERVIEW.md`：记录新的对比 Tab 架构
3. 保留 demo 文件不动（供开发调试），但在文档中标注"仅用于开发调试"
4. `AGENTS.md` 更新：对比 Tab 相关的修改指引指向新文件

- [ ] **Step 1: 更新文档**

- [ ] **Step 2: 最终 Commit**

```bash
git add docs/ frontend/src/
git commit -m "docs: 更新技术文档，记录对比综述从 demo 到生产的改造"
```

---

## 风险和注意事项

| 风险 | 缓解措施 |
|------|---------|
| ReadingItem 数据格式可能与 demo JSON 有差异 | 后端 `build_compare_response` 做格式转换，确保与 demo JSON 完全同构 |
| KaTeX 渲染在 React 中需要特殊处理 | 参考 demo HTML 的 `mathRender` 逻辑，用 `useEffect` + `ref` 在渲染后触发 |
| SSE 流式响应格式需与后端对齐 | Task 2 中验证实际 SSE 格式，Task 4 中按实际格式解析 |
| 四步/七步的步骤名（parent_key）可能不一致 | 后端查询时从 ReadingItem 的实际 parent_key 提取，不硬编码 |
| 用户未精读过任何文献时 Tab 应显示空状态 | CompareView 中处理空 papers 数组，显示引导文案 |
| AI 综述需要 API Key | CompareView 接收 `apiKey` prop，未设置时提示用户 |

---

## 执行顺序依赖图

```
Task 1 (后端 API) ──────┐
Task 2 (SSE 端点) ──────┤
                         ├── Task 8 (CompareView 主组件) ── Task 9 (替换 App.tsx) ── Task 11 (验证)
Task 3 (useCompareData) ─┤
Task 4 (useSynthesis)  ──┤
Task 5 (AnswerCard)    ──┤
Task 6 (PaperSelector) ──┤
Task 7 (SynthesisModal)──┘
Task 10 (CSS) ──────────── Task 8 依赖

最终: Task 12 (文档)
```

Task 1-7 可并行开发，Task 8 整合所有子组件，Task 9 接入 App.tsx，Task 11 端到端验证。
