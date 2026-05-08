# 长文本精读维度用户化 — Phase 1 后端实施文档

> **版本**: v1.0  
> **日期**: 2026-05-08  
> **状态**: 已实施  
> **规划文档**: [CUSTOM_DIMENSION_PLAN.md](./CUSTOM_DIMENSION_PLAN.md)

## 1. 概述

Phase 1 完成了维度用户化改造的全部后端工作，包括数据库表、ORM 模型、种子数据、CRUD API、以及精读管线的运行时适配。**所有改动均为纯增量**——新增两个表，不修改任何现有表结构；新增可选参数，不破坏已有调用方式。

### 已实施内容清单

| # | 内容 | 文件 | 状态 |
|---|------|------|------|
| 1 | Alembic 迁移 | `backend/migrations/versions/007_add_dimension_tables.py` | ✅ |
| 2 | ORM 模型 | `backend/db/models.py` (lines 556-609) | ✅ |
| 3 | 种子数据 | `backend/dimension_seed.py` | ✅ |
| 4 | 启动集成 | `backend/main.py` (lines 24, 26, 66-70, 123) | ✅ |
| 5 | 维度集合/条目 CRUD API | `backend/routers/dimensions.py` (477 行, 12 端点) | ✅ |
| 6 | 精读管线适配 | `backend/routers/reading.py` (lines 211, 694, 752-823, 1217) | ✅ |
| 7 | 引擎接口扩展 | `new_architecture/conversation_engine.py` (lines 221-240) | ✅ |

---

## 2. 数据库层

### 2.1 新增表：`dimension_sets`

**迁移文件**: `backend/migrations/versions/007_add_dimension_tables.py`  
**ORM 文件**: `backend/db/models.py` (lines 556-580)  
**迁移链**: `006_add_bib_entry_volume_issue_pages` → `007_add_dimension_tables`

```sql
CREATE TABLE dimension_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    is_default      INTEGER NOT NULL DEFAULT 0,
    is_system       INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (owner_user_id, name)
);

CREATE INDEX idx_dim_sets_owner ON dimension_sets (owner_user_id);
CREATE INDEX idx_dim_sets_default ON dimension_sets (owner_user_id, is_default);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `owner_user_id` | Integer FK→users.id | 所属用户，CASCADE 删除 |
| `name` | String | 集合名称，同一用户内唯一 |
| `description` | Text (nullable) | 可选描述 |
| `is_default` | Integer (0/1) | 是否为用户当前激活集合（每用户至多 1 个） |
| `is_system` | Integer (0/1) | 系统内置集合（不可删除、不可改名） |
| `sort_order` | Integer | 显示排序 |

**约束**：`UniqueConstraint("owner_user_id", "name")` → `uq_dim_sets_owner_name`

### 2.2 新增表：`dimension_items`

**ORM 文件**: `backend/db/models.py` (lines 583-609)

```sql
CREATE TABLE dimension_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id          INTEGER NOT NULL REFERENCES dimension_sets(id) ON DELETE CASCADE,
    dim_key         TEXT NOT NULL,
    dim_name        TEXT NOT NULL,
    description     TEXT,
    prompt_content  TEXT NOT NULL DEFAULT '',
    default_question TEXT NOT NULL DEFAULT '',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_builtin      INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (set_id, dim_key)
);

CREATE INDEX idx_dim_items_set ON dimension_items (set_id);
CREATE INDEX idx_dim_items_builtin ON dimension_items (set_id, is_builtin);
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `set_id` | Integer FK→dimension_sets.id | 所属集合，CASCADE 删除 |
| `dim_key` | String | 英文标识。内置维度沿用 `ANALYSIS_DIMENSIONS` 的 key；自建维度用 `{prefix}_{uuid4[:4]}` |
| `dim_name` | String | 中文显示名，如"研究问题" |
| `description` | Text (nullable) | 维度描述（tooltip 等） |
| `prompt_content` | Text | 该维度的完整提示词 |
| `default_question` | Text | 默认分析问题 |
| `is_builtin` | Integer (0/1) | 1=系统预置维度（不可在系统集中删除），0=用户自建 |

**约束**：`UniqueConstraint("set_id", "dim_key")` → `uq_dim_items_set_key`

### 2.3 级联删除

```
删除 users       → CASCADE 删除 dimension_sets → CASCADE 删除 dimension_items
删除 dimension_sets → CASCADE 删除 dimension_items
```

### 2.4 对现有表的影响

**无结构变更**。`reading_items`、`jobs`、`prompt_templates` 等现有表完全不动。

---

## 3. 种子数据

**文件**: `backend/dimension_seed.py` (46 行)

### 3.1 触发时机

在 `backend/main.py` 的 `lifespan()` 上下文管理器中，应用启动时自动执行（line 66-70）：

```python
# main.py:66-70
try:
    async with AsyncSessionLocal() as db:
        await ensure_default_dimension_sets(db)
except Exception as exc:
    print(f"[dimension-seed] skipped: {exc}")
```

执行顺序：在 `ensure_builtin_prompt_templates()` 之后（line 62）、挂起任务恢复之前（line 73）。

### 3.2 填充逻辑

```python
async def ensure_default_dimension_sets(db: AsyncSession) -> None:
```

1. 查询所有用户
2. 对每个用户：检查是否已有 `is_system=1` 的集合
3. 如果没有，创建系统集合（name="默认维度集", is_default=1, is_system=1）
4. 遍历 `ANALYSIS_DIMENSIONS` 的 13 个条目，逐个创建 `DimensionItem`：
   - `dim_key` = ANALYSIS_DIMENSIONS 的 key（overview, theory, ...）
   - `dim_name` = dim["name"]（中文显示名）
   - `prompt_content` = `load_prompt_from_file("long", key)` 或兜底 `dim["system_prompt_addition"]`
   - `default_question` = dim["default_questions"][0] 或 ""
   - `is_builtin` = 1（custom 维度为 0）

### 3.3 ANALYSIS_DIMENSIONS 内置的 13 个维度

| dim_key | dim_name | is_builtin |
|---------|----------|------------|
| `overview` | 研究问题 | 1 |
| `theory` | 理论框架 | 1 |
| `methodology` | 识别策略 | 1 |
| `data_source` | 数据来源 | 1 |
| `variable_measurement` | 变量度量 | 1 |
| `identification_assumptions` | 识别假设 | 1 |
| `results` | 统计结果 | 1 |
| `mechanism` | 机制分析 | 1 |
| `robustness` | 稳健性检验 | 1 |
| `external_validity` | 外部有效性 | 1 |
| `contributions_limitations` | 贡献与局限 | 1 |
| `writing_quality` | 写作质量 | 1 |
| `custom` | 自定义问题 | 0 |

---

## 4. API 层

**文件**: `backend/routers/dimensions.py` (477 行)  
**路由挂载**: `main.py:123` → `app.include_router(dimensions.router, prefix="/api/dimensions", tags=["Dimensions"])`  
**鉴权**: 所有端点通过 `Depends(current_user)` 获取当前用户，按 `user.id` 隔离数据。

### 4.1 维度集合端点（7 个）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/sets` | `list_sets` | 列出当前用户所有集合，含 `item_count` |
| POST | `/sets` | `create_set` | 创建集合，可选 `clone_from_set_id` 从已有集合复制 |
| PUT | `/sets/{set_id}` | `update_set` | 修改名称/描述（系统集不可改名） |
| DELETE | `/sets/{set_id}` | `delete_set` | 删除集合（系统集不可删） |
| POST | `/sets/{set_id}/activate` | `activate_set` | 设为激活集合（清除其他 is_default） |
| POST | `/sets/{set_id}/reset` | `reset_set` | 恢复系统集为默认 13 维度 |
| POST | `/sets/{set_id}/clone` | `clone_set` | 深度复制集合（自动追加" (副本)"后缀） |

### 4.2 维度条目端点（5 个）

| 方法 | 路径 | 函数 | 说明 |
|------|------|------|------|
| GET | `/sets/{set_id}/items` | `list_items` | 按 sort_order 列出集合内所有维度 |
| POST | `/sets/{set_id}/items` | `create_item` | 新增维度，自动生成 `dim_key = {prefix}_{uuid4[:4]}` |
| PUT | `/sets/{set_id}/items/{item_id}` | `update_item` | 修改维度名称/描述/提示词/问题 |
| DELETE | `/sets/{set_id}/items/{item_id}` | `delete_item` | 删除维度（系统集内置维度受保护） |
| POST | `/sets/{set_id}/items/reorder` | `reorder_items` | 批量调整排序 |

### 4.3 请求/响应 Schema

```python
class SetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    clone_from_set_id: Optional[int] = None

class SetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class ItemCreate(BaseModel):
    dim_name: str
    description: Optional[str] = None
    prompt_content: str = ""
    default_question: str = ""

class ItemUpdate(BaseModel):
    dim_name: Optional[str] = None
    description: Optional[str] = None
    prompt_content: Optional[str] = None
    default_question: Optional[str] = None

class ItemsReorder(BaseModel):
    orders: list[dict]  # [{id: int, sort_order: int}]
```

### 4.4 业务规则

- **系统集保护**：`is_system=1` 的集合不可删除（`delete_set`）、不可改名（`update_set`）
- **内置维度保护**：系统集中 `is_builtin=1` 的条目不可删除（`delete_item`），需通过 `reset` 整体重置
- **dim_key 自动生成**：用户自建维度的 `dim_key` 格式为 `{集合名前6字去空格}_{uuid4[:4]}`，如 `计量论文_a3f2`
- **clone_from_set_id**：创建集合时可传入源集合 ID，自动复制所有维度条目（`is_builtin` 强制为 0）
- **activate 唯一性**：激活一个集合时，先将该用户所有集合 `is_default` 置 0，再设置目标集合为 1

### 4.5 辅助函数

```python
async def _get_user_set(db, set_id, user_id) -> DimensionSet
# 查询 set_id + owner_user_id = user_id，不存在抛 404

async def _get_user_item(db, set_id, item_id, user_id) -> tuple[DimensionSet, DimensionItem]
# 先验证集合归属，再查 item，不存在抛 404
```

---

## 5. 精读管线集成

### 5.1 数据流全景

```
前端 POST /api/reading/long/start
  body: { file_id, analysis_dims: ["研究问题","工具变量有效性"], dimension_set_id: 2, api_key }
    │
    ├─ LongContextRequest.dimension_set_id (reading.py:211)
    │
    ├─ 创建 Job(reading_long) + 入队
    │
    └─ threading.Thread(args=[..., request.dimension_set_id])  (reading.py:1217)
        │
        └─ run_long_context_task(dimension_set_id=2)  (reading.py:694)
            │
            ├─ if dimension_set_id is not None:  (reading.py:753)
            │   └─ _load_custom_dims()
            │       └─ SELECT * FROM dimension_items WHERE set_id=2 ORDER BY sort_order
            │       └─ custom_dim_map = {
            │             "研究问题": {dim_key, prompt_content, default_question, is_builtin},
            │             "工具变量有效性": {dim_key, prompt_content, default_question, is_builtin},
            │             ...
            │           }
            │
            └─ for dim_key in analysis_dims:  (reading.py:788)
                │
                ├─ if dim_key in dim_map (硬编码映射):  (line 812)
                │   └─ engine.analyze_dimension("overview")  # 原有路径
                │
                ├─ elif dim_key in custom_dim_map:  (line 814)
                │   └─ engine.analyze_dimension("工具变量有效性", dim_meta={...})  # 新路径
                │
                └─ else (fallback):  (line 817)
                    └─ engine.analyze_dimension("overview")
```

### 5.2 请求模型变更

**文件**: `backend/routers/reading.py:204-211`

```python
class LongContextRequest(BaseModel):
    file_id: str
    analysis_dims: list[str]
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    api_key: Optional[str] = None
    force_overwrite: bool = False
    dimension_set_id: Optional[int] = None   # ← 新增，可选
```

不传 `dimension_set_id` 时，`custom_dim_map` 为空字典，走原有的 `dim_map` 硬编码路径。**完全向后兼容**。

### 5.3 自定义维度加载

**文件**: `backend/routers/reading.py:752-784`

关键实现细节：

1. 在后台线程中调用，需要独立的 DB session（`AsyncSessionLocal()`）
2. 使用 `asyncio.run(_inner())` 在同步线程中运行异步查询
3. `custom_dim_map` 以 **中文显示名** (`dim_name`) 为 key，与前端传来的 `analysis_dims` 列表匹配
4. 异常时 `custom_dim_map` 退化为空字典，不影响原有流程

### 5.4 分析分发三路逻辑

**文件**: `backend/routers/reading.py:811-818`

```python
if mapped_key:                                    # 路径 A：系统维度
    answer = engine.analyze_dimension(mapped_key)
elif custom_dim_map and dim_key in custom_dim_map: # 路径 B：用户自建维度
    answer = engine.analyze_dimension(dim_key, dim_meta=dim_meta)
else:                                              # 路径 C：兜底
    answer = engine.analyze_dimension("overview")
```

| 路径 | 条件 | 说明 |
|------|------|------|
| A | `dim_key` 在硬编码 `dim_map` 中 | 走 `ANALYSIS_DIMENSIONS` 原逻辑，零改动 |
| B | `dim_key` 在 `custom_dim_map` 中 | 新路径，传入 `dim_meta` |
| C | 兜底 | 按 overview 处理 |

### 5.5 ConversationEngine 接口扩展

**文件**: `new_architecture/conversation_engine.py:221-240`

```python
def analyze_dimension(
    self,
    dimension: str,
    custom_question: Optional[str] = None,
    dim_meta: Optional[Dict] = None,   # ← 新增可选参数
) -> str:
    if dimension in ANALYSIS_DIMENSIONS:
        # 原有逻辑不变
        ...
    elif dim_meta:
        # 新路径：用外部传入的元数据构建增强问题
        question = custom_question or dim_meta.get("default_question", "请分析这个维度。")
        dim_name = dim_meta.get("dim_name", dimension)
        prompt_content = dim_meta.get("prompt_content", "")
        enhanced = f"【分析维度：{dim_name}】\n{prompt_content}\n\n{question}"
        return self.ask(enhanced, dimension=None)
    else:
        return f"未知维度: {dimension}"
```

**关键设计决策**：
- 系统维度（`dimension` 在 `ANALYSIS_DIMENSIONS` 中）→ 完全走原逻辑，**零改动**
- 用户自建维度（`dim_meta` 非 None）→ 将 `prompt_content` + `default_question` 组装为增强问题，调用 `self.ask(enhanced, dimension=None)` 绕过 `_load_prompt_from_file` 的硬编码路径
- `dimension=None` 确保 `_build_messages` 不查 `ANALYSIS_DIMENSIONS`

---

## 6. 命名映射体系

系统维护 3 套并行的维度命名，Phase 1 **保留全部**，通过 `dim_map` + `custom_dim_map` 双层映射：

| 层 | 示例 | 来源 | 用途 |
|----|------|------|------|
| `ANALYSIS_DIMENSIONS` key | `overview` | `analysis_dimensions.py` | 引擎内部，系统维度查找 |
| `LONG_DIMENSION_KEYS` value | `long.research_question` | `reading.py:40-54` | DB `reading_items.item_key`，历史数据兼容 |
| 前端传递 | `研究问题` | 前端 `analysis_dims` | 用户可见，API 请求参数 |
| `dimension_items.dim_key` | `overview` / `计量论文_a3f2` | 数据库 | 新维度标识，用于 `item_key` 生成 |

**运行时映射过程**：

```
前端 "研究问题"
  → dim_map["研究问题"] = "overview"  → engine.analyze_dimension("overview")
                                          → ANALYSIS_DIMENSIONS["overview"]

前端 "工具变量有效性"
  → dim_map: 不命中
  → custom_dim_map["工具变量有效性"] = {dim_key: "计量论文_a3f2", ...}
  → engine.analyze_dimension("工具变量有效性", dim_meta=...)
```

---

## 7. 向后兼容性

| 场景 | 行为 |
|------|------|
| 前端不传 `dimension_set_id` | `custom_dim_map` 为空，走原 `dim_map` 硬编码路径，与改造前完全一致 |
| 已有 `ReadingItem.item_key`（如 `long.research_question`） | 不受影响，`LONG_DIMENSION_KEYS` 保留不变 |
| 已有 `jobs.params_json` | 不受影响，`dimension_set_id` 是新增可选字段 |
| `ANALYSIS_DIMENSIONS` / `prompt_registry.py` / `prompt_service.py` | **未修改**，继续作为系统维度的元数据源和提示词来源 |
| `compare_long.html` | **未修改**，按 `<!--DIMENSION_BOUNDARY-->` 分割，维度名变化不影响 |
| `dimension_seed.py` 对已存在的用户 | 跳过（检测 `is_system=1` 集合已存在则 continue） |

---

## 8. 文件变更清单

| 文件 | 变更类型 | 行数 | 说明 |
|------|----------|------|------|
| `backend/db/models.py` | 新增 | +54 行 | DimensionSet + DimensionItem 类及索引 |
| `backend/dimension_seed.py` | 新增 | 46 行 | 种子数据填充函数 |
| `backend/routers/dimensions.py` | 新增 | 477 行 | 12 个 CRUD 端点 |
| `backend/migrations/versions/007_add_dimension_tables.py` | 新增 | 67 行 | Alembic 迁移脚本 |
| `backend/main.py` | 修改 | +5 行 | import + router 挂载 + 种子调用 |
| `backend/routers/reading.py` | 修改 | +40 行 | schema 加字段 + 线程参数传递 + custom_dim_map 加载 + 三路分发 |
| `new_architecture/conversation_engine.py` | 修改 | +8 行 | `analyze_dimension` 新增 `dim_meta` 参数 |
| **总计** | | **~697 行** | 4 个新文件 + 3 个修改 |
