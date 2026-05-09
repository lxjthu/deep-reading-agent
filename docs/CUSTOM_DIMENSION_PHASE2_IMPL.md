# 长文本精读维度用户化 — Phase 2 前端实施记录

> **版本**: v1.0  
> **日期**: 2026-05-09  
> **状态**: 已实施  
> **前置**: [Phase 1 后端实施](./CUSTOM_DIMENSION_PHASE1_IMPL.md) | [Phase 2 原始设计](./CUSTOM_DIMENSION_PHASE2_DESIGN.md)  
> **关联**: [导入导出修复](./CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md)

## 1. 概述

Phase 2 在 Phase 1 已完成的 12 个后端 API 基础上，实现了前端维度管理 UI 和 LongTab 动态化改造。最终方案与原始 Phase 2 设计文档有显著差异：将维度管理直接嵌入 LongTab 内联操作，而非作为 PromptsTab 的子 Tab。

### 实施完成清单

| # | 内容 | 文件 | 状态 |
|---|------|------|------|
| 1 | DimensionManager.tsx 独立组件 | `frontend/src/DimensionManager.tsx` | ✅ 创建（备用，未引用） |
| 2 | LongTab 内联维度编辑 | `frontend/src/App.tsx` (LongTab 函数) | ✅ |
| 3 | LongTab API 调用加 dimension_set_id | `frontend/src/App.tsx` (LongTab) | ✅ |
| 4 | 导入导出适配维度表 | `backend/services/data_portability.py` | ✅ |

### 与原始设计文档的差异

| 原始设计 | 实际实施 | 原因 |
|----------|----------|------|
| PromptsTab 增加"维度管理"子 Tab | 维度管理直接嵌入 LongTab | 用户反馈：在长文本精读里直接编辑更直观 |
| DimensionManager 作为主组件 | DimensionManager 已创建但未引用 | 保留备用，LongTab 内联实现替代 |
| 无拖拽排序 | 原生 HTML5 Drag & Drop 排序 | 用户请求，无新依赖 |
| 未涉及导入导出 | data_portability.py 已适配 | 分析发现维度表被遗漏，一并修复 |

---

## 2. LongTab 内联维度管理

### 2.1 新增状态（~17 个 useState）

```
LongTab State（维度相关）
├─ dimensionSetId: number|null         当前激活的维度集合 ID
├─ dimensionItems: any[]               当前集合的维度条目（完整对象）
├─ dimSets: any[]                      用户所有维度集合（用于下拉选择）
├─ editingDim: any|null                正在内联编辑的维度
├─ editName / editDesc / editPrompt / editQuestion: string
├─ showAddDim: boolean                 添加维度表单可见性
├─ addName / addDesc / addPrompt / addQuestion: string
├─ dimMessage: string                  操作反馈消息
├─ showSaveAsSet: boolean              "另存为"表单可见性
├─ saveAsName: string                  新集合名称
├─ dragIdx / overIdx: number|null      拖拽排序状态
```

### 2.2 数据加载流程

```
组件挂载 (useEffect [])
  │
  ├─ GET /api/dimensions/sets → setDimSets(data)
  │   └─ 找到 is_default 的集合 → setDimensionSetId(active.id)
  │
  └─ GET /api/dimensions/sets/{id}/items → setDimensionItems(data)
      └─ 默认选中前 3 个维度 → setDims([前3个].dim_name)
```

**静默回退**：API 失败时使用硬编码 `ALL_DIMS`，LongTab 仍可正常使用。

### 2.3 UI 交互

#### 维度列表区

```
┌─ ★ 分析维度 ──────────────────────── [另存为] [+ 新集合] ─┐
│                                                            │
│  [默认维度集 ▾]              （多集合时显示下拉）            │
│                                                            │
│  ⠿ ☑ 研究问题                     [✏] [✕]               │
│  ⠿ ☑ 理论框架                     [✏] [✕]               │
│  ⠿ ☐ 识别策略                     [✏] [✕]               │
│  ⠿ ☐ 数据来源                     [✏] [✕]               │
│  ...                                                       │
│                                                            │
│  [+ 添加维度]                                              │
│                                                            │
│  (编辑面板 / 添加表单 按需展开)                             │
└────────────────────────────────────────────────────────────┘
```

| 操作 | 交互 | API |
|------|------|-----|
| 勾选/取消维度 | checkbox toggle | 无（前端状态） |
| 编辑维度 | hover → 点 ✏ → 展开内联面板 | `PUT /api/dimensions/sets/{id}/items/{item_id}` |
| 删除维度 | hover → 点 ✕ → 确认对话框 | `DELETE /api/dimensions/sets/{id}/items/{item_id}` |
| 添加维度 | 点 [+ 添加维度] → 展开表单 | `POST /api/dimensions/sets/{id}/items` |
| 拖拽排序 | 拖 ⠿ 手柄 → 放下目标位置 | `POST /api/dimensions/sets/{id}/items/reorder` |
| 切换集合 | 下拉选择 | `POST /api/dimensions/sets/{id}/activate` + reload |
| 另存为集合 | 点 [另存为] → 输入名称 | `POST /api/dimensions/sets` (clone_from) |
| 新建集合 | 点 [+ 新集合] → prompt 输入名 | `POST /api/dimensions/sets` (clone_from) |

### 2.4 拖拽排序实现

使用原生 HTML5 Drag & Drop API，无第三方依赖：

```typescript
// 状态
const [dragIdx, setDragIdx] = useState<number | null>(null)
const [overIdx, setOverIdx] = useState<number | null>(null)

// 每个维度行
<div draggable onDragStart={() => setDragIdx(idx)}
     onDragOver={e => { e.preventDefault(); setOverIdx(idx) }}
     onDragLeave={() => setOverIdx(null)}
     onDrop={onDragEnd}>

// 放下时：本地重排 + API 持久化
const onDragEnd = async () => {
  const reordered = [...dimensionItems]
  const [moved] = reordered.splice(dragIdx, 1)
  reordered.splice(overIdx, 0, moved)
  setDimensionItems(reordered)
  await fetch(`/api/dimensions/sets/${id}/items/reorder`, {
    body: JSON.stringify({ orders: reordered.map((it, i) => ({ id: it.id, sort_order: i })) })
  })
}
```

视觉效果：拖起行 `opacity-40`，目标行顶部 `border-t-2 border-emerald-400`。

### 2.5 精读 API 调用改造

```typescript
// 初始调用和覆盖重试均加入 dimension_set_id
body: JSON.stringify({
  file_id, analysis_dims: dims,
  dimension_set_id: dimensionSetId || undefined,  // null 时不序列化
  custom_question, extraction_method, api_key,
})
```

`dimensionSetId || undefined`：当 `null` 时属性不会被 JSON.stringify 序列化，后端走原有 fallback 路径。

---

## 3. 导入导出适配

详见 [CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md](./CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md)。

关键改动：
- `EXPORT_TABLE_ORDER` 加入 `DimensionSet`, `DimensionItem`
- `IMPORT_CLEAR_ORDER` 加入 `DimensionItem`, `DimensionSet`（反向）
- `_deserialize_table` 增加 ID 重映射（`id_map`），解决 auto-PK 导入后 `set_id` 指向旧 ID 的问题
- `CURRENT_SCHEMA_VERSION` 从 `"006"` 升至 `"007"`

---

## 4. 文件变更清单

| 文件 | 变更类型 | 行数 | 说明 |
|------|----------|------|------|
| `frontend/src/App.tsx` | 修改 | +293 行 | LongTab 内联维度管理 + 拖拽 + API 适配 |
| `frontend/src/DimensionManager.tsx` | 新增 | ~395 行 | 独立维度管理组件（备用，未引用） |
| `backend/services/data_portability.py` | 修改 | +51 行 | 导入导出适配维度表 + ID 重映射 |
| `docs/CUSTOM_DIMENSION_PHASE2_IMPL.md` | 新增 | 本文件 | 实施记录 |
| `docs/CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md` | 新增 | — | 导入导出修复文档 |

---

## 5. 边界情况

| 场景 | 处理 |
|------|------|
| API 不可达 | LongTab 静默回退到硬编码 ALL_DIMS，仍可正常精读 |
| 新用户首次使用 | 后端启动种子自动创建系统集，体验与改造前一致 |
| 编辑中切换集合 | editingDim 清空，编辑面板自动关闭 |
| 精读进行中切换集合 | 不影响（dimension_set_id 已提交后台线程） |
| 导入旧版 .dra（无维度 JSON） | 文件不存在则 skip，不报错 |
| DimensionManager.tsx 未被引用 | 保留备用，tree-shaking 不会打包 |
