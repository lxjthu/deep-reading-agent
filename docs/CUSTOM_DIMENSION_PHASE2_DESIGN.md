# 长文本精读维度用户化 — Phase 2 前端设计规划

> **版本**: v1.0  
> **日期**: 2026-05-08  
> **状态**: 待实施  
> **前置**: [Phase 1 实施文档](./CUSTOM_DIMENSION_PHASE1_IMPL.md)  
> **规划文档**: [CUSTOM_DIMENSION_PLAN.md](./CUSTOM_DIMENSION_PLAN.md)

## 1. 目标

Phase 2 在 Phase 1 已完成的 12 个后端 API 基础上，实现前端维度管理 UI 和 LongTab 动态化改造。完成后用户可以：

1. 在 PromptsTab 中管理多个维度集合（创建/切换/删除/复制）
2. 在集合内增删改维度（名称、描述、提示词、默认问题）
3. 在 LongTab 中使用当前激活集合的维度启动精读
4. 一键恢复系统默认维度

## 2. 前端技术栈与约定

| 项目 | 约定 |
|------|------|
| 框架 | React 19 + TypeScript |
| 样式 | Tailwind CSS 4（纯 utility class，无组件库） |
| 状态管理 | 局部 `useState`（现有模式），**不新增 Zustand store** |
| API 调用 | 原生 `fetch()`（全局拦截器自动注入鉴权） |
| 组件组织 | 内联 function component 或独立文件（参考 `LibraryTab.tsx`、`ReferenceTraceTab.tsx`） |
| 配色 | Emerald 主色 + 灰色辅助 + 红色危险操作 |
| 字体/间距 | 复用现有 App.tsx 风格 |

### 关键约定

- **不引入新依赖**：无组件库（shadcn/MUI 等），无拖拽库
- **所有 Tab 组件条件渲染**：`{activeTab === 'long' && <LongTab />}`，切换 Tab 时组件卸载重建
- **错误处理**：`try/catch` + `message` state，与 PromptsTab 现有模式一致
- **API 鉴权**：`fetch()` 已通过 `installGlobalAuthFetch()` 全局注入 Bearer token

---

## 3. 改动范围

### 3.1 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|----------|
| `frontend/src/DimensionManager.tsx` | 维度管理独立组件 | ~280 行 |

### 3.2 修改文件

| 文件 | 改动 | 影响行数 |
|------|------|----------|
| `frontend/src/App.tsx` | 3 处：import、PromptsTab 加子 Tab、LongTab 动态化 | ~50 行修改 |

### 3.3 不改动的文件

| 文件 | 原因 |
|------|------|
| `frontend/src/store/auth.ts` | 不涉及认证逻辑 |
| `frontend/src/lib/api-fetch.ts` | 全局拦截器已满足需求 |
| `frontend/src/LibraryTab.tsx` | 无关 |
| 后端全部文件 | Phase 1 已完成，Phase 2 纯前端 |

---

## 4. 组件设计：DimensionManager

### 4.1 定位

独立 React 组件，被 PromptsTab 通过子 Tab 切换渲染。负责维度集合 + 维度条目的完整 CRUD 管理。

### 4.2 TypeScript 类型

```typescript
interface DimSet {
  id: number
  name: string
  description: string | null
  is_default: boolean
  is_system: boolean
  item_count: number
  sort_order: number
}

interface DimItem {
  id: number
  dim_key: string
  dim_name: string
  description: string | null
  prompt_content: string
  default_question: string
  sort_order: number
  is_builtin: boolean
}
```

### 4.3 状态设计

```
┌─────────────────────────────────────────────────────────────┐
│ DimensionManager State                                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ 集合层 ─────────────────────────────────────────────┐   │
│  │ sets: DimSet[]             所有维度集合              │   │
│  │ selectedSetId: number|null 当前选中查看的集合 ID      │   │
│  │ showNewSetForm: boolean     新建集合表单可见性        │   │
│  │ newSetName: string          新建集合名称输入          │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 条目层 ─────────────────────────────────────────────┐   │
│  │ items: DimItem[]           selectedSetId 下的条目     │   │
│  │ showNewItemForm: boolean    新建维度表单可见性        │   │
│  │ newItem*: string            新建维度四字段            │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 编辑层 ─────────────────────────────────────────────┐   │
│  │ editingItem: DimItem|null   正在编辑的条目            │   │
│  │ editName, editDesc, editPrompt, editQuestion: string   │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ 通用 ───────────────────────────────────────────────┐   │
│  │ loading: boolean            操作进行中                │   │
│  │ message: string             反馈消息（✓/❌ 前缀）     │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**状态总数**：17 个 useState（集合层 4 + 条目层 5 + 编辑层 5 + 通用 2 + 计算属性 1）

### 4.4 数据流

```
挂载 (useEffect [])
  │
  ├─ GET /api/dimensions/sets → setSets(data)
  │   └─ 自动选中 is_default 的集合 → setSelectedSetId(active.id)
  │
  └─ selectedSetId 变化 (useEffect [selectedSetId])
      └─ GET /api/dimensions/sets/{id}/items → setItems(data)
```

```
用户操作:
  集合 CRUD → POST/PUT/DELETE /api/dimensions/sets[/{id}] → loadSets() 刷新
  激活集合 → POST /api/dimensions/sets/{id}/activate → loadSets() 刷新
  恢复默认 → POST /api/dimensions/sets/{id}/reset → loadItems() 刷新
  维度 CRUD → POST/PUT/DELETE /api/dimensions/sets/{id}/items[/{id}] → loadItems() 刷新
  维度排序 → POST /api/dimensions/sets/{id}/items/reorder → loadItems() 刷新
```

### 4.5 API 调用映射

| 用户操作 | HTTP | API 端点 | 成功后 |
|----------|------|----------|--------|
| 列出集合 | GET | `/api/dimensions/sets` | `setSets()` |
| 新建集合 | POST | `/api/dimensions/sets` body:`{name, clone_from_set_id}` | `loadSets()` + 选中新集 |
| 改名/描述 | PUT | `/api/dimensions/sets/{id}` body:`{name?, description?}` | `loadSets()` |
| 删除集合 | DELETE | `/api/dimensions/sets/{id}` | `loadSets()` + 清空选中 |
| 激活集合 | POST | `/api/dimensions/sets/{id}/activate` | `loadSets()` |
| 恢复默认 | POST | `/api/dimensions/sets/{id}/reset` | `loadItems()` |
| 复制集合 | POST | `/api/dimensions/sets/{id}/clone` | `loadSets()` + 选中新集 |
| 列出条目 | GET | `/api/dimensions/sets/{id}/items` | `setItems()` |
| 新增维度 | POST | `/api/dimensions/sets/{id}/items` body:`{dim_name, description?, prompt_content, default_question}` | `loadItems()` |
| 编辑维度 | PUT | `/api/dimensions/sets/{id}/items/{item_id}` body:`{dim_name?, description?, prompt_content?, default_question?}` | `loadItems()` |
| 删除维度 | DELETE | `/api/dimensions/sets/{id}/items/{item_id}` | `loadItems()` |
| 调整排序 | POST | `/api/dimensions/sets/{id}/items/reorder` body:`{orders: [{id, sort_order}]}` | `loadItems()` |

### 4.6 UI 布局

```
┌─────────────────────────────────────────────────────────┐
│  ┌─ 集合选择区 ────────────────────────────────────────┐  │
│  │                                                       │  │
│  │  维度集合                        [+ 新建集合]         │  │
│  │                                                       │  │
│  │  ┌ 新建集合表单（条件显示）──────────────────────┐   │  │
│  │  │ [集合名称输入] [创建] [取消]                   │   │  │
│  │  └───────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  ┌─ 集合列表 ──────────────────────────────────┐    │  │
│  │  │ ● 默认维度集  [激活] [系统] (13 维度)        │    │  │
│  │  │ ● 计量论文专用  (8 维度)   [激活][复制][删除] │    │  │
│  │  │ ● 理论论文专用  (6 维度)   [激活][复制][删除] │    │  │
│  │  └──────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  [反馈消息: ✓ 已切换为当前激活集合]                            │
│                                                              │
│  ┌─ 维度列表区 ────────────────────────────────────────┐  │
│  │                                                       │  │
│  │  维度列表 — 默认维度集          [恢复默认] [+ 添加]  │  │
│  │                                                       │  │
│  │  ┌ 新增维度表单（条件显示）──────────────────────┐   │  │
│  │  │ [名称] [描述] [默认问题]                       │   │  │
│  │  │ [提示词 textarea]                              │   │  │
│  │  │ [添加] [取消]                                  │   │  │
│  │  └───────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  1. 研究问题      [内置]           [↑][↓][编辑][删除] │  │
│  │  2. 理论框架      [内置]           [↑][↓][编辑][删除] │  │
│  │  3. 识别策略      [内置]           [↑][↓][编辑][删除] │  │
│  │  ...                                                    │  │
│  │  13. 自定义问题                    [↑][↓][编辑][删除] │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 编辑面板（条件显示，选中编辑时展开）───────────────┐  │
│  │                                                       │  │
│  │  编辑：工具变量有效性                          [关闭]  │  │
│  │                                                       │  │
│  │  维度名称  [___________________________]              │  │
│  │  描述      [___________________________]              │  │
│  │  默认问题  [___________________________]              │  │
│  │  提示词                                             │  │
│  │  ┌───────────────────────────────────────────────┐   │  │
│  │  │ (textarea, font-mono, 10 rows)                │   │  │
│  │  └───────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  [保存]  [重置]                                       │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.7 交互规则

| 操作 | 条件/约束 | 确认对话框 |
|------|-----------|------------|
| 删除集合 | `is_system=true` 时禁用 | 是（"确定删除此集合？"） |
| 激活集合 | 切换前不清空维度选中状态 | 否 |
| 恢复默认 | 仅 `is_system=true` 的集合可见此按钮 | 是（"将删除所有自定义维度并恢复默认"） |
| 删除维度 | 系统集中 `is_builtin=true` 时禁用 | 是（"确定删除此维度？"） |
| 新建集合 | 自动从当前选中集合 clone | 否 |
| 复制集合 | 自动追加" (副本)"后缀 | 否 |
| 维度排序 | ↑↓ 按钮，交换相邻 sort_order | 否 |
| 编辑维度 | 点击"编辑"展开编辑面板，替换正在编辑的条目 | 否 |

### 4.8 样式约定

| 元素 | 样式 |
|------|------|
| 卡片容器 | `rounded-xl border border-gray-200 bg-white p-5` |
| 集合选中 | `bg-emerald-50 border border-emerald-200` |
| 集合悬浮 | `hover:bg-gray-50 border border-transparent` |
| 标签（激活） | `rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700` |
| 标签（系统） | `rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700` |
| 标签（内置） | `rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500` |
| 编辑面板 | `rounded-xl border border-amber-200 bg-amber-50/30 p-5` |
| 新建表单 | `rounded-lg border border-emerald-200 bg-emerald-50/50 p-3` |
| 主按钮 | `bg-gradient-to-r from-emerald-600 to-emerald-500 text-white` |
| 次按钮 | `bg-gray-100 text-gray-700` |
| 输入框 | `rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none` |

---

## 5. 组件设计：PromptsTab 改造

### 5.1 改动说明

在 PromptsTab 顶部增加**子 Tab 切换器**，在"提示词管理"和"维度管理"之间切换。

### 5.2 新增状态

```typescript
const [subTab, setSubTab] = useState<'prompts' | 'dimensions'>('prompts')
```

### 5.3 UI 结构

```tsx
<div className="w-full space-y-4">
  {/* 子 Tab 切换器 — 新增 */}
  <div className="flex gap-1 rounded-xl border border-gray-200 bg-white p-1">
    <button onClick={() => setSubTab('prompts')}
      className={subTab === 'prompts' ? 'bg-emerald-50 text-emerald-700 ...' : 'text-gray-500 ...'}>
      提示词管理
    </button>
    <button onClick={() => setSubTab('dimensions')}
      className={subTab === 'dimensions' ? 'bg-emerald-50 text-emerald-700 ...' : 'text-gray-500 ...'}>
      维度管理
    </button>
  </div>

  {/* 维度管理 — 新增 */}
  {subTab === 'dimensions' && <DimensionManager />}

  {/* 原有提示词管理 — 包在条件渲染中 */}
  {subTab === 'prompts' && <>
    {/* ... 原有 PromptsTab 内容不变 ... */}
  </>}
</div>
```

### 5.4 具体改动位置（App.tsx）

| 改动 | 位置 | 说明 |
|------|------|------|
| import | line 5 附近 | 新增 `import DimensionManager from './DimensionManager'` |
| subTab state | line 1588 附近 | 新增一个 useState |
| 子 Tab UI | line 1787-1789 之间 | 插入切换按钮 + 条件渲染 DimensionManager |
| 条件包裹 | 原有 PromptsTab 内容 | 用 `{subTab === 'prompts' && <> ... </>}` 包裹 |
| 关闭 Fragment | 原有 PromptsTab 结尾 | 在外层 `</div>` 前加 `</>` |

---

## 6. 组件设计：LongTab 改造

### 6.1 改动说明

将 LongTab 中硬编码的 `ALL_DIMS` 替换为从后端 API 动态获取的维度列表，并在启动精读时发送 `dimension_set_id`。

### 6.2 新增状态

```typescript
const [dimensionSetId, setDimensionSetId] = useState<number | null>(null)
const [dimensionItems, setDimensionItems] = useState<{ dim_key: string; dim_name: string }[]>([])
```

### 6.3 数据加载

```typescript
useEffect(() => {
  const fetchActiveSet = async () => {
    try {
      const res = await fetch('/api/dimensions/sets')
      if (!res.ok) return                    // API 失败 → 静默回退到 ALL_DIMS
      const sets = await res.json()
      const active = sets.find((s: any) => s.is_default)
      if (!active) return                    // 无激活集合 → 静默回退
      setDimensionSetId(active.id)
      const itemsRes = await fetch(`/api/dimensions/sets/${active.id}/items`)
      if (!itemsRes.ok) return
      const items = await itemsRes.json()
      setDimensionItems(items)
      // 默认选中前 3 个维度
      if (items.length > 0) {
        setDims(items.slice(0, Math.min(3, items.length)).map((i: any) => i.dim_name))
      }
    } catch {
      // 网络错误 → 静默回退到 ALL_DIMS
    }
  }
  fetchActiveSet()
}, [])
```

**关键设计决策**：

- **静默回退**：API 失败时不弹错误，直接使用硬编码 `ALL_DIMS`。这确保了离线/后端未升级等场景下 LongTab 仍可用
- **默认选中**：首次加载时自动选中前 3 个维度，保持与改造前一致的用户体验
- **组件重建**：切换到其他 Tab 再回来时组件卸载重建，useEffect 重新执行，自动获取最新数据

### 6.4 ALL_DIMS 处理

```typescript
// 保留硬编码作为回退
const ALL_DIMS = [
  "研究问题", "理论框架", "识别策略", "数据来源", "变量度量",
  "识别假设", "统计结果", "机制分析", "稳健性检验", "外部有效性",
  "贡献与局限", "写作质量"
]

// 渲染时动态选择
const availableDims = dimensionItems.length > 0
  ? dimensionItems.map(i => i.dim_name)
  : ALL_DIMS
```

checkbox 区域改为：

```tsx
{availableDims.map(dim => (
  <label key={dim} className="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm">
    <input type="checkbox" checked={dims.includes(dim)} onChange={() => toggleDim(dim)} />
    <span className="text-gray-700">{dim}</span>
  </label>
))}
```

### 6.5 API 调用改造

**初始调用**（原 line 1095）：

```typescript
// 改造前
body: JSON.stringify({ file_id, analysis_dims: dims, custom_question, extraction_method, api_key })

// 改造后
body: JSON.stringify({
  file_id,
  analysis_dims: dims,
  dimension_set_id: dimensionSetId || undefined,   // ← 新增
  custom_question: customQ || undefined,
  extraction_method: extraction,
  api_key: effectiveKey,
})
```

**覆盖重试调用**（原 line 1105）：

```typescript
// 同样加入 dimension_set_id
body: JSON.stringify({
  file_id,
  analysis_dims: dims,
  dimension_set_id: dimensionSetId || undefined,   // ← 新增
  custom_question: customQ || undefined,
  extraction_method: extraction,
  api_key: effectiveKey,
  force_overwrite: true,
})
```

**`dimensionSetId || undefined`**：当 `null` 时属性不会被序列化，后端走原有 fallback 路径。

### 6.6 改动位置汇总（App.tsx LongTab）

| 改动 | 原位置 | 说明 |
|------|--------|------|
| 新增 2 个 state | line 1030 后 | `dimensionSetId`, `dimensionItems` |
| 新增 useEffect | line 1056 后（toggleDim 之后） | 拉取激活集合 |
| 替换 checkbox 渲染 | lines 1144-1151 | 用 `availableDims` 替代 `ALL_DIMS` |
| 初始 API 调用加字段 | line 1095 | 加 `dimension_set_id` |
| 覆盖重试加字段 | line 1105 | 加 `dimension_set_id` |

---

## 7. 用户体验流程

### 7.1 首次使用（新用户）

```
1. 注册 → 登录
2. 后端启动时 ensure_default_dimension_sets() 自动创建系统集
3. 打开 LongTab → 前端 GET /api/dimensions/sets → 拿到默认维度集
4. 看到 12 个维度 checkbox（与改造前完全一致）
5. 正常使用，无感知变化
```

### 7.2 创建自定义维度集

```
1. 切换到"提示词管理" Tab → 点"维度管理"子 Tab
2. 看到系统默认集合 + 其 12 个维度
3. 点"+ 新建集合" → 输入名称"计量论文专用" → 创建
   （自动从当前集合复制所有维度到新集合）
4. 删除不需要的维度（如"写作质量"、"外部有效性"等）
5. 点"+ 添加维度" → 输入"工具变量有效性" → 填写提示词 → 保存
6. 点集合旁"激活"按钮 → 切换为当前激活集合
```

### 7.3 使用自定义集合精读

```
1. 切换到"长文本精读" Tab
2. 上传 PDF
3. 看到维度 checkbox 已变为新集合的维度列表（如 8 个）
4. 勾选需要的维度 → 开始精读
5. 后端收到 dimension_set_id=2 + analysis_dims=["研究问题","工具变量有效性",...]
6. 分析完成后结果正常展示
```

### 7.4 恢复默认

```
1. 维度管理 → 选中系统默认集合 → 点"恢复默认"
2. 确认对话框 → 确定
3. 所有自定义维度被清除，恢复 13 个系统维度
4. 点"激活" → LongTab 恢复显示 12 个默认维度
```

---

## 8. 边界情况与错误处理

| 场景 | 处理 |
|------|------|
| API 不可达（网络故障/后端未启动） | LongTab 静默回退到 `ALL_DIMS`；DimensionManager 显示错误消息 |
| 新注册用户尚无系统集 | 后端启动时种子已填充；如种子失败，LongTab 回退到 `ALL_DIMS` |
| 用户删除了所有非系统集 | LongTab 使用系统集的维度，无影响 |
| 系统集中删除了所有维度 | LongTab 显示空的 checkbox 区域（用户可输入自定义问题） |
| 同一维度名出现在不同集合 | 无冲突——`dim_key` 集合内唯一，不同集合独立 |
| 编辑中切换集合 | 编辑面板自动关闭（`editingItem` 被清空） |
| 精读进行中切换维度集合 | 不影响正在执行的任务（`dimension_set_id` 已提交给后台线程） |

---

## 9. 测试计划

### 9.1 手动测试场景

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 新用户首次打开 LongTab | checkbox 显示 12 个默认维度，默认勾选前 3 个 |
| 2 | 启动精读不传 dimension_set_id | 后端走 fallback 路径，结果正常 |
| 3 | 启动精读传 dimension_set_id | 后端走 custom_dim_map 路径，结果正常 |
| 4 | 维度管理 → 新建集合 | 成功创建，自动 clone 当前集合维度 |
| 5 | 维度管理 → 添加自定义维度 | 新维度出现在列表，编辑面板可编辑 |
| 6 | 维度管理 → 编辑维度提示词 | 保存后重新加载显示更新后的内容 |
| 7 | 维度管理 → 删除非系统集合 | 成功删除，集合列表刷新 |
| 8 | 维度管理 → 尝试删除系统集合 | 删除按钮不可见/禁用 |
| 9 | 维度管理 → 恢复默认 | 系统集维度重置为 13 个 |
| 10 | 维度管理 → 激活集合 A → LongTab | checkbox 显示集合 A 的维度 |
| 11 | 维度管理 → 排序维度 → LongTab | checkbox 按新顺序显示 |
| 12 | 维度管理 → 复制集合 | 新集合名称含" (副本)"，维度内容一致 |
| 13 | 系统集中尝试删除内置维度 | 删除按钮禁用，tooltip 提示 |
| 14 | API 不可达时打开 LongTab | 静默回退到硬编码 12 维度 |

### 9.2 构建验证

```powershell
cd frontend && npm run lint && npm run build
```

确保 lint 无错误、build 成功。

---

## 10. 实施步骤

按以下顺序逐步实施，每步完成后可独立验证：

### Step 1：创建 `DimensionManager.tsx`

独立组件，不依赖 App.tsx。可先单独编写，通过临时在 PromptsTab 中引用来验证。

### Step 2：集成到 PromptsTab

修改 App.tsx：
1. 添加 `import DimensionManager`
2. 添加 `subTab` state
3. 插入子 Tab 切换器
4. 包裹原有内容 + 渲染 DimensionManager

验证：PromptsTab 显示子 Tab，切换到"维度管理"可看到集合和维度列表。

### Step 3：改造 LongTab

修改 App.tsx：
1. 添加 `dimensionSetId` + `dimensionItems` state
2. 添加 `useEffect` 拉取激活集合
3. 替换 checkbox 数据源
4. API 调用加 `dimension_set_id`

验证：LongTab checkbox 动态显示，启动精读发送 dimension_set_id。

### Step 4：构建验证

```powershell
cd frontend && npm run lint && npm run build
```

### 预估工时

| 步骤 | 预估 |
|------|------|
| Step 1: DimensionManager.tsx | ~280 行新代码 |
| Step 2: PromptsTab 集成 | ~15 行修改 |
| Step 3: LongTab 改造 | ~30 行修改 |
| Step 4: 构建验证 | 排错 |
| **总计** | ~325 行改动 |
