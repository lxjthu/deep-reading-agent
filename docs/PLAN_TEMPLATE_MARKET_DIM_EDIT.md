# 实施规划：模板市场维度编辑

> 日期：2026-05-20
> 状态：待实施

## 背景

`TemplateMarket.tsx` 的详情页（`panel === 'detail'` 且 `detailTarget._source === 'user'`）当前为纯只读展示维度列表。后端 CRUD API 完整，前端精读 Tab（`App.tsx:1183-1381`）已有成熟的编辑交互可复用。

详见 `PACKAGING_DOWNLOAD_FILTER_REPORT_BUG.md` 第 12 节分析。

## 改动范围

**仅改 `frontend/src/TemplateMarket.tsx`**，后端无需改动。

## 现有 API

| 方法 | 路由 | 用途 |
|------|------|------|
| GET | `/api/dimensions/sets/{set_id}/items` | 获取维度列表 |
| POST | `/api/dimensions/sets/{set_id}/items` | 添加维度 |
| PUT | `/api/dimensions/sets/{set_id}/items/{item_id}` | 编辑维度 |
| DELETE | `/api/dimensions/sets/{set_id}/items/{item_id}` | 删除维度 |

## 具体步骤

### Step 1：新增编辑状态变量（约第 103 行后）

```ts
const [editingDimId, setEditingDimId] = useState<number | null>(null)
const [editName, setEditName] = useState('')
const [editDesc, setEditDesc] = useState('')
const [editPrompt, setEditPrompt] = useState('')
const [editQuestion, setEditQuestion] = useState('')
const [showAddDim, setShowAddDim] = useState(false)
const [addName, setAddName] = useState('')
const [addDesc, setAddDesc] = useState('')
const [addPrompt, setAddPrompt] = useState('')
const [addQuestion, setAddQuestion] = useState('')
```

### Step 2：新增处理函数

| 函数 | 功能 | 调用 API |
|------|------|----------|
| `startEditDim(dim)` | 填充编辑表单 | — |
| `saveEditDim()` | PUT 保存 | `PUT /api/dimensions/sets/{setId}/items/{itemId}` |
| `cancelEdit()` | 关闭编辑态 | — |
| `deleteDim(dim)` | 删除维度 | `DELETE /api/dimensions/sets/{setId}/items/{itemId}` |
| `addDimension()` | 添加维度 | `POST /api/dimensions/sets/{setId}/items` |

函数逻辑直接复用 `App.tsx:1313-1381` 的模式，将 `dimensionSetId` 替换为 `detailTarget.id`。

### Step 3：改造详情页维度列表渲染（lines 476-515）

对 `detailTarget._source === 'user'` 的场景，每个维度卡片增加：

1. **操作按钮行**：编辑（铅笔）+ 删除（×）图标按钮，靠右排列
2. **编辑态展开区域**：点击编辑后，卡片下方展开四个字段（dim_name input、description input、default_question input、prompt_content textarea）+ 保存/取消按钮
3. **添加维度入口**：列表底部追加「+ 添加维度」按钮，展开添加表单
4. 预设模板（`_source !== 'user'`）保持只读不变

### Step 4：保存后刷新

`saveEditDim` / `deleteDim` / `addDimension` 成功后调用 `showUserSetDetail(detailTarget.id)` 重新加载维度列表。

## 不做的事情

- 不做拖拽排序（YAGNI，精读 Tab 已有）
- 不改后端
- 不改预设模板详情页（只读）

## 验证

```powershell
cd frontend && npm run build
```
