# 卡片笔记引用条目点击跳转参考文献梳理页面 — 设计文档

> 日期：2026-06-01
> 状态：已实施（2026-06-01）

## 背景

卡片笔记阅读页（`MarkdownReader.tsx`）左侧「引用关系」面板中，"引用了"和"被引用"的文献条目目前是纯文本 `<div>`，不可交互。用户希望点击这些条目后跳转到参考文献梳理页面（`ReferenceTraceTab.tsx`）对应的条目。

## 现状分析

| 组件 | 文件 | 现状 |
|------|------|------|
| 卡片笔记阅读页 | `frontend/src/MarkdownReader.tsx` | 左侧引用条目为纯文本 `<div>`，无点击事件 |
| 参考文献梳理页 | `frontend/src/ReferenceTraceTab.tsx` | 无 URL 深链接，不支持跳转到特定条目 |
| 路由 | `frontend/src/App.tsx` | `?tab=references` 已支持 tab 切换 |
| 后端 | `routers/library.py` | outgoing citations 已返回 `matched_bib_entry_id` |

## 方案：URL Query Param 深链接

### 数据流

```
用户点击"引用了"条目
  → navigate('/workspace?tab=references&sourceEntryId={id}&refId={refId}')
  → App.tsx 切换到 references tab
  → ReferenceTraceTab 读取 URL params
    - sourceEntryId → 自动选中左侧来源条目
    - refId → 自动选中中间表格对应行 + scrollIntoView
```

### 前端改动

#### 1. `MarkdownReader.tsx`

- **outgoing 引用类型扩展**：加上 `matched_bib_entry_id` 字段（后端已返回，前端类型定义缺失）
- **"引用了"条目**：`<div>` 加 `onClick`，调用 `navigate('/workspace?tab=references&sourceEntryId={当前entryId}&refId={ref.id}')`
- **"被引用"条目**：同理，用 `ref.source_bib_entry_id` 作为 sourceEntryId
- **点击样式**：加 `cursor-pointer hover:bg-blue-50` 等反馈

#### 2. `ReferenceTraceTab.tsx`

- 用 `useSearchParams()` 读取 `sourceEntryId` 和 `refId`
- **初始化**：URL 有 `sourceEntryId` 时自动选中该来源条目（替代默认选第一个）
- **数据加载后**：URL 有 `refId` 时自动 `setSelectedReferenceId(refId)`，对该行 `scrollIntoView({ behavior: 'smooth', block: 'center' })`
- 表格行加 `id={`ref-row-${item.id}`}` 便于定位滚动

#### 3. `App.tsx`

无需改动。

### 后端改动

无需改动。

### 边界情况

- `refId` 在当前来源条目下不存在 → 忽略 refId，正常显示
- `sourceEntryId` 不存在 → 回退到选第一个来源条目
- 用户手动切换来源/引用后清除 URL params（避免 stale params）

## 涉及文件

| 文件 | 改动类型 |
|------|----------|
| `frontend/src/MarkdownReader.tsx` | 修改：引用条目可点击 + 跳转 |
| `frontend/src/ReferenceTraceTab.tsx` | 修改：读取 URL params + 自动选中 + 滚动 + 表格固定列宽 + 内容换行防溢出 |

## 实施记录

- **commit `5c2db748`**：引用跳转核心功能（MarkdownReader 点击跳转 + ReferenceTraceTab URL 深链接 + scrollIntoView）
- **同日追加**：梳理结果表格改为 `table-layout: fixed` + `<colgroup>` 固定列宽，消除水平滚动条；正文引用详情卡片加 `break-words` + `overflow-hidden` 防止长文本溢出
