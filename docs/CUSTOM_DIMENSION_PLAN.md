# 长文本精读维度用户化改造规划

> **版本**: v1.0  
> **日期**: 2026-05-08  
> **状态**: 规划中，未实施  
> **关联文档**: [DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)、[PROMPT_MANAGEMENT_PLAN.md](./PROMPT_MANAGEMENT_PLAN.md)

## 1. 背景与目标

当前长文本精读的 12 个分析维度硬编码在代码中，用户只能在启动精读时勾选/取消，不能增删改。本改造目标：

1. **维度集合（Dimension Set）**：用户可创建多个命名维度集（如"计量论文专用"、"理论论文专用"）
2. **维度编辑**：在某个集合内增删改维度（名称、描述、提示词）
3. **一键恢复默认**：系统内置的 12 维度作为不可变默认集，可一键恢复
4. **提示词联动**：编辑维度时同步编辑该维度的提示词
5. **数据兼容**：已有 `ReadingItem`、`Artifact` 中按 `long.xxx` item_key 存储的历史数据不受影响
6. **多集合管理**：用户可保存多套维度配置，按研究场景切换

## 2. 现状分析

### 2.1 维度定义的硬编码位置

维度信息分散在 6 个平行位置：

| 位置 | 文件 | 形式 |
|------|------|------|
| 维度定义 | `new_architecture/analysis_dimensions.py` | Python dict `ANALYSIS_DIMENSIONS`，含 name/description/default_questions/system_prompt_addition |
| DB item_key 映射 | `backend/routers/reading.py:40-54` | Python dict `LONG_DIMENSION_KEYS`，中文→`long.xxx` |
| 前端 checkbox | `frontend/src/App.tsx:1048-1052` | JS array `ALL_DIMS`，12 个中文名 |
| 提示词注册表 | `backend/prompt_registry.py:37-57` | Python dict `PROMPT_REGISTRY["long"]`，英文 key→title+file_path |
| 提示词文件 | `prompts/long/*.md` | 13 个 md 文件（12 维度 + 1 自定义） |
| 运行时映射 | `reading.py:757-770` | Chinese → English key `dim_map` |

**关键问题**：维度集固定，用户只能勾选/取消，不能增删改。提示词虽有 `prompt_templates` 表支持用户覆盖，但维度本身不可自定义。

### 2.2 当前端到端数据流

```
前端 LongTab: 用户从 ALL_DIMS 勾选维度
  → POST /api/reading/long/start { analysis_dims: ["研究问题","理论框架",...], custom_question? }
    → reading.py:start_long_context()
      → 加载 prompt_overrides = get_effective_prompt_map(db, user_id, "long")
      → 创建 Job(reading_long) + 入队
      → run_long_context_task() 后台线程:
          → dim_map["研究问题"] = "overview"
          → engine.analyze_dimension("overview")
            → ANALYSIS_DIMENSIONS["overview"] 取元数据
            → _load_prompt_from_file("overview") 取提示词（prompt_overrides > 文件 > builtin）
            → 构建 messages → 调 DeepSeek API
          → results["研究问题"] = answer
      → 写 Markdown 报告（<!--DIMENSION_BOUNDARY--> 分隔）
      → build_long_reading_items(results) → ReadingItem 行
        → item_key = LONG_DIMENSION_KEYS["研究问题"] = "long.research_question"
```

### 2.3 命名不一致问题

系统维护了 3 套并行的命名体系：

| 层 | 示例 | 说明 |
|----|------|------|
| `analysis_dimensions.py` key | `overview` | 英文，引擎内部使用 |
| `LONG_DIMENSION_KEYS` value | `long.research_question` | DB item_key，**与上面不一致** |
| 前端传递 | `研究问题` | 中文，用户可见 |

其中 `overview` → `long.research_question`、`methodology` → `long.identification_strategy`、`results` → `long.statistical_results` 存在刻意的不一致。用户化改造后需统一映射机制。

### 2.4 现有提示词优先级

```
用户覆盖 (prompt_templates, scope='user')
  > 系统默认 (prompt_templates, scope='system')
    > 文件兜底 (prompts/long/*.md)
      > 代码兜底 (ANALYSIS_DIMENSIONS[key]['system_prompt_addition'])
```

## 3. 数据库改造方案

### 3.1 新增表：`dimension_sets`（维度集合）

```sql
CREATE TABLE dimension_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,              -- 集合名称，如"计量论文专用"
    description     TEXT,                       -- 可选描述
    is_default      INTEGER NOT NULL DEFAULT 0, -- 是否为用户当前激活的默认集合（每用户至多 1 个）
    is_system       INTEGER NOT NULL DEFAULT 0, -- 系统内置集合（不可删除、不可改名）
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (owner_user_id, name)               -- 同一用户集合名不重复
);

CREATE INDEX idx_dim_sets_owner ON dimension_sets (owner_user_id);
CREATE INDEX idx_dim_sets_default ON dimension_sets (owner_user_id, is_default);
```

**字段说明**：

- `is_system=1`：系统内置的默认维度集，不可删除、不可改名，但可以"恢复默认内容"
- `is_default=1`：用户当前激活的集合，启动精读时默认使用此集合的维度。每用户至多一个 `is_default=1`
- `name`：用户自定义集合名，系统集默认名为"默认维度集"

### 3.2 新增表：`dimension_items`（维度条目）

```sql
CREATE TABLE dimension_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id          INTEGER NOT NULL REFERENCES dimension_sets(id) ON DELETE CASCADE,
    dim_key         TEXT NOT NULL,              -- 维度英文标识
    dim_name        TEXT NOT NULL,              -- 中文显示名，如"研究问题"
    description     TEXT,                       -- 维度描述（tooltip 等）
    prompt_content  TEXT NOT NULL DEFAULT '',    -- 该维度的完整提示词
    default_question TEXT NOT NULL DEFAULT '',   -- 默认分析问题
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_builtin      INTEGER NOT NULL DEFAULT 0, -- 1=系统预置的 12 维度之一 0=用户自建
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (set_id, dim_key)                    -- 集合内维度 key 不重复
);

CREATE INDEX idx_dim_items_set ON dimension_items (set_id);
CREATE INDEX idx_dim_items_builtin ON dimension_items (set_id, is_builtin);
```

**dim_key 命名规则**：

- **系统内置维度**：沿用 `ANALYSIS_DIMENSIONS` 的 key（`overview`, `theory`, `methodology` 等）
- **用户自建维度**：使用 `{set_name_prefix}_{uuid_short}` 格式，例如 `计量论文_a3f2`，确保：
  - 不会与系统内置 key 冲突
  - 可追溯属于哪个集合
  - 在 ReadingItem.item_key 中形成 `long.计量论文_a3f2`，与历史数据兼容

### 3.3 对现有表的影响

| 表 | 变更 | 说明 |
|----|------|------|
| `prompt_templates` | **无结构变更** | 系统维度的提示词覆盖继续走此表；用户自建维度的提示词存 `dimension_items.prompt_content` |
| `reading_items` | **无结构变更** | `item_key` 规则兼容：系统维度继续用 `long.research_question`，用户自建用 `long.{dim_key}` |
| `jobs.params_json` | **无结构变更** | `analysis_dims` 字段存中文维度名列表，天然兼容；新增可选字段 `dimension_set_id` |
| `dimension_sets` | **新增** | |
| `dimension_items` | **新增** | |

**级联删除规则补充**：

| 触发 | 行为 |
|------|------|
| 删除 `users` | 级联删除 `dimension_sets` → 级联删除 `dimension_items`（DB ON DELETE CASCADE） |
| 删除 `dimension_sets` | 级联删除 `dimension_items`（DB ON DELETE CASCADE） |

### 3.4 ORM 模型

```python
class DimensionSet(Base):
    __tablename__ = "dimension_sets"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_dim_sets_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class DimensionItem(Base):
    __tablename__ = "dimension_items"
    __table_args__ = (
        UniqueConstraint("set_id", "dim_key", name="uq_dim_items_set_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_sets.id", ondelete="CASCADE"), nullable=False
    )
    dim_key: Mapped[str] = mapped_column(String, nullable=False)
    dim_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_question: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_dim_sets_owner", DimensionSet.owner_user_id)
Index("idx_dim_sets_default", DimensionSet.owner_user_id, DimensionSet.is_default)
Index("idx_dim_items_set", DimensionItem.set_id)
Index("idx_dim_items_builtin", DimensionItem.set_id, DimensionItem.is_builtin)
```

## 4. 数据迁移策略

### 4.1 种子数据填充（应用启动时）

类似现有 `ensure_builtin_prompt_templates()` 模式，在 `main.py` 启动时调用：

```python
async def ensure_default_dimension_sets(db: AsyncSession) -> None:
    """确保每个用户都有系统默认维度集"""
    users = (await db.execute(select(User))).scalars().all()
    
    for user in users:
        existing = (await db.execute(
            select(DimensionSet).where(
                DimensionSet.owner_user_id == user.id,
                DimensionSet.is_system == 1,
            )
        )).scalar_one_or_none()
        
        if existing:
            continue
        
        default_set = DimensionSet(
            owner_user_id=user.id,
            name="默认维度集",
            is_default=1,
            is_system=1,
            sort_order=0,
        )
        db.add(default_set)
        await db.flush()
        
        for idx, (key, dim) in enumerate(ANALYSIS_DIMENSIONS.items()):
            prompt = load_prompt_from_file("long", key) or dim["system_prompt_addition"]
            item = DimensionItem(
                set_id=default_set.id,
                dim_key=key,
                dim_name=dim["name"],
                description=dim["description"],
                prompt_content=prompt,
                default_question=dim["default_questions"][0] if dim["default_questions"] else "",
                sort_order=idx,
                is_builtin=1 if key != "custom" else 0,
            )
            db.add(item)
    
    await db.commit()
```

### 4.2 历史数据兼容

- `ReadingItem.item_key`（如 `long.research_question`）按原样保留，不受影响
- 历史数据中的维度名通过 `LONG_DIMENSION_KEYS` 反查即可
- 新建维度的 `item_key` 生成规则：`long.{dim_key}`，与现有格式一致
- 对比综述 `compare_long.html` 通过 `<!--DIMENSION_BOUNDARY-->` 解析，维度名变化不影响解析

## 5. 运行时架构变更

### 5.1 维度解析流程（改造后）

```
用户打开 LongTab
  → GET /api/dimensions/sets?is_default=1  → 获取当前激活集合
  → GET /api/dimensions/sets/{set_id}/items → 获取维度列表
  → 前端动态渲染 checkbox（从集合读取，非硬编码 ALL_DIMS）

用户启动精读
  → POST /api/reading/long/start
    body: { file_id, dimension_set_id, analysis_dims: [...], ... }
      → 后端从 dimension_items 表加载维度元数据 + 提示词
      → 系统维度(dim_key in ANALYSIS_DIMENSIONS) → 走 engine.analyze_dimension(mapped_key)
      → 用户自建维度(dim_key NOT in ANALYSIS_DIMENSIONS) → 用 prompt_content 作为提示词
      → ReadingItem: item_key = f"long.{dim_key}", item_label = dim_name
```

### 5.2 ConversationEngine 适配

当前 `analyze_dimension()` 硬查 `ANALYSIS_DIMENSIONS` dict。改造方案——扩展参数，不改核心逻辑：

```python
def analyze_dimension(
    self,
    dimension: str,
    custom_question: str | None = None,
    dim_meta: dict | None = None,  # 新增：外部传入的维度元数据
) -> str:
    if dimension in ANALYSIS_DIMENSIONS:
        # 系统维度：完全走原逻辑，零改动
        dim_info = ANALYSIS_DIMENSIONS[dimension]
        question = custom_question or dim_info["default_questions"][0]
        return self.ask(question, dimension)
    elif dim_meta:
        # 用户自建维度：用外部传入的 prompt_content
        question = custom_question or dim_meta.get("default_question", "请分析这个维度。")
        dim_name = dim_meta.get("dim_name", dimension)
        # 构建增强问题（绕过 _build_messages 中的 ANALYSIS_DIMENSIONS 检查）
        enhanced = f"【分析维度：{dim_name}】\n{dim_meta['prompt_content']}\n\n{question}"
        return self.ask(enhanced, dimension=None)
    else:
        return f"未知维度: {dimension}"
```

### 5.3 reading.py 映射机制改造

```python
# 改造前：硬编码映射
LONG_DIMENSION_KEYS = {"研究问题": "long.research_question", ...}
dim_map = {"研究问题": "overview", ...}

# 改造后：从数据库动态读取
async def get_dimension_map_from_set(
    db: AsyncSession, set_id: int
) -> dict[str, dict]:
    items = (await db.execute(
        select(DimensionItem)
        .where(DimensionItem.set_id == set_id)
        .order_by(DimensionItem.sort_order)
    )).scalars().all()
    
    result = {}
    for item in items:
        result[item.dim_name] = {
            "dim_key": item.dim_key,
            "item_key": f"long.{item.dim_key}",
            "prompt_content": item.prompt_content,
            "default_question": item.default_question,
            "is_builtin": item.is_builtin,
        }
    return result
```

对于系统内置维度，`dim_key` 仍与 `ANALYSIS_DIMENSIONS` 对齐（`overview`, `theory` 等），`conversation_engine.py` 核心逻辑无需修改。

### 5.4 提示词优先级调整

用户自建维度的提示词直接存在 `dimension_items.prompt_content`，不需要走 `prompt_templates` 表。优先级简化为：

**系统内置维度**（保持不变）：
```
用户覆盖 (prompt_templates, scope='user')
  > 系统默认 (prompt_templates, scope='system')
    > dimension_items.prompt_content（种子数据）
      > 文件兜底 (prompts/long/*.md)
        > 代码兜底 (ANALYSIS_DIMENSIONS[key]['system_prompt_addition'])
```

**用户自建维度**（简化）：
```
dimension_items.prompt_content（唯一来源）
```

## 6. API 设计

### 6.1 维度集合管理

| 端点 | 方法 | 功能 | 备注 |
|------|------|------|------|
| `/api/dimensions/sets` | GET | 获取当前用户所有维度集合 | 含 `item_count` 统计 |
| `/api/dimensions/sets` | POST | 创建新维度集合 | 可选 `clone_from_set_id` 参数 |
| `/api/dimensions/sets/{set_id}` | PUT | 更新集合名称/描述 | 系统集不可改名 |
| `/api/dimensions/sets/{set_id}` | DELETE | 删除集合 | 系统集不可删 |
| `/api/dimensions/sets/{set_id}/activate` | POST | 设为当前激活集合 | 清除其他集合 `is_default` |
| `/api/dimensions/sets/{set_id}/reset` | POST | 恢复到系统默认 12 维度 | 仅系统集合可用 |
| `/api/dimensions/sets/{set_id}/clone` | POST | 复制集合为新集合 | 含所有维度条目 |

### 6.2 维度条目管理

| 端点 | 方法 | 功能 | 备注 |
|------|------|------|------|
| `/api/dimensions/sets/{set_id}/items` | GET | 获取集合内所有维度条目 | 按 `sort_order` 排序 |
| `/api/dimensions/sets/{set_id}/items` | POST | 添加维度 | 自动生成 `dim_key` |
| `/api/dimensions/sets/{set_id}/items/{item_id}` | PUT | 编辑维度（名称/描述/提示词/问题） | |
| `/api/dimensions/sets/{set_id}/items/{item_id}` | DELETE | 删除维度 | 系统维度在系统集中不可删（需用 reset） |
| `/api/dimensions/sets/{set_id}/items/reorder` | POST | 批量调整排序 | `{orders: [{id, sort_order}]}` |

### 6.3 请求/响应示例

**GET /api/dimensions/sets**
```json
[
  {
    "id": 1,
    "name": "默认维度集",
    "description": null,
    "is_default": true,
    "is_system": true,
    "item_count": 13,
    "sort_order": 0
  },
  {
    "id": 2,
    "name": "计量论文专用",
    "description": "适用于因果推断和实证分析的论文",
    "is_default": false,
    "is_system": false,
    "item_count": 8,
    "sort_order": 1
  }
]
```

**GET /api/dimensions/sets/2/items**
```json
[
  {
    "id": 14,
    "dim_key": "overview",
    "dim_name": "研究问题",
    "description": "论文解决了什么问题？创新点在哪里？",
    "prompt_content": "请聚焦核心研究问题...",
    "default_question": "这篇论文的核心研究问题是什么？",
    "sort_order": 0,
    "is_builtin": true
  },
  {
    "id": 22,
    "dim_key": "计量论文_a3f2",
    "dim_name": "工具变量有效性",
    "description": "评估工具变量的外生性和相关性",
    "prompt_content": "请详细评估论文中使用的工具变量...",
    "default_question": "工具变量是否满足排他性约束？",
    "sort_order": 6,
    "is_builtin": false
  }
]
```

**POST /api/reading/long/start**（改造后）
```json
{
  "file_id": "abc-123",
  "dimension_set_id": 2,
  "analysis_dims": ["研究问题", "工具变量有效性"],
  "custom_question": "这篇论文的政策含义是什么？",
  "api_key": "sk-..."
}
```

## 7. 前端 UI 规划

### 7.1 入口位置

在 `PromptsTab` 中增加"维度管理"子模块，或新建独立 Tab。建议放在 `PromptsTab` 内，因为提示词管理与维度管理天然关联。

### 7.2 界面布局

```
┌─────────────────────────────────────────────────┐
│  维度管理                                        │
├─────────────────────────────────────────────────┤
│                                                  │
│  当前集合: [▼ 默认维度集          ] [+ 新建] [复制] │
│                                                  │
│  ┌──维度列表──────────────────────────────────┐  │
│  │ ☑ 研究问题         [编辑] [↑] [↓] [删除]   │  │
│  │ ☑ 理论框架         [编辑] [↑] [↓] [删除]   │  │
│  │ ☐ 识别策略         [编辑] [↑] [↓] [删除]   │  │
│  │ ...                                        │  │
│  │ ☐ 工具变量有效性   [编辑] [↑] [↓] [删除]   │  │
│  │                                            │  │
│  │          [+ 添加自定义维度]                  │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  [恢复默认维度]     [另存为新集合]                  │
│                                                  │
│  ┌──编辑面板: 工具变量有效性────────────────────┐ │
│  │  维度名称: [工具变量有效性________________]   │ │
│  │  描述:     [评估工具变量的外生性和相关性___]   │ │
│  │  默认问题: [工具变量是否满足排他性约束？___]   │ │
│  │                                             │ │
│  │  提示词:                                    │ │
│  │  ┌─────────────────────────────────────────┐│ │
│  │  │ 请详细评估论文中使用的工具变量...         ││ │
│  │  │                                         ││ │
│  │  │ 1. 工具变量是否满足相关性条件？           ││ │
│  │  │ 2. 排他性约束是否合理？                  ││ │
│  │  │ 3. 是否存在弱工具变量问题？               ││ │
│  │  └─────────────────────────────────────────┘│ │
│  │                          [保存] [重置]       │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 7.3 LongTab 改造

`LongTab` 的 checkbox 区域从硬编码 `ALL_DIMS` 改为从当前激活的维度集合动态生成：

```javascript
// 改造前
const ALL_DIMS = ["研究问题", "理论框架", ...]

// 改造后
const { data: activeSet } = useActiveDimensionSet()
const dims = activeSet?.items || []
// dims.map(item => ({ label: item.dim_name, key: item.dim_key }))
```

### 7.4 交互细节

- **拖拽排序**：维度列表支持拖拽调整顺序，拖动后自动保存 `sort_order`
- **一键恢复默认**：点击"恢复默认维度"→ 确认对话框 → 删除系统集合中所有自定义维度，重新从 `ANALYSIS_DIMENSIONS` 填充
- **另存为新集合**：将当前集合的所有维度复制一份到新集合，用户可自定义名称
- **集合切换**：下拉切换集合后，LongTab 的 checkbox 自动刷新
- **编辑联动**：在维度编辑面板中修改提示词后，自动同步到 `dimension_items.prompt_content`；如果是系统内置维度，同时更新 `prompt_templates` 中的用户覆盖

## 8. 实施步骤（建议顺序）

### Phase 1：数据库与后端（不破坏现有功能）

1. **Alembic 迁移**：新建 `dimension_sets` + `dimension_items` 表
2. **ORM 模型**：`models.py` 新增 `DimensionSet` + `DimensionItem`
3. **种子数据**：`ensure_default_dimension_sets()` 启动时填充
4. **维度集合 CRUD API**：新 router `backend/routers/dimensions.py`
5. **维度条目 CRUD API**：同上
6. **运行时适配**：`reading.py` 新增 `dimension_set_id` 参数读取逻辑，**保持原有 `analysis_dims` 传中文方式作为 fallback**

### Phase 2：前端维度管理 UI

7. **维度管理组件**：在 `PromptsTab` 中增加维度管理区域
8. **集合切换器**：下拉选择 + 激活
9. **维度编辑面板**：名称/描述/提示词/默认问题 四栏编辑
10. **LongTab 改造**：checkbox 从动态集合读取

### Phase 3：高级功能

11. **集合克隆**：复制现有集合
12. **一键恢复默认**：清空系统集自定义维度并重置
13. **维度预设模板**：提供"计量论文"、"理论论文"、"系统论文"等预设集合供一键导入

## 9. 风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| ReadingItem UNIQUE(job_id, item_key) 冲突 | 用户自建维度 `dim_key` 用 `{set_prefix}_{uuid_short}` 格式，保证唯一性 |
| 对比综述兼容性 | `compare_long.html` 按 `<!--DIMENSION_BOUNDARY-->` 分割，维度名作为标题，不受 key 变化影响 |
| 历史数据追溯 | 历史数据中 `item_key` 如 `long.research_question` 仍可通过 `LONG_DIMENSION_KEYS` 反查，不需依赖新表 |
| 迁移脚本是纯增量 | 只加表（`dimension_sets` + `dimension_items`），不改现有表结构 |
| 提示词体系混乱 | 系统维度提示词继续走 `prompt_templates` 表；自建维度提示词走 `dimension_items.prompt_content`，互不干扰 |
| `dim_key` 命名冲突 | 系统维度 key 固定为 ANALYSIS_DIMENSIONS 的 13 个 key；自建维度强制 `{prefix}_{uuid}` 格式，前端/后端校验 |
| `jobs.params_json` 兼容 | 新增可选 `dimension_set_id` 字段；不传时 fallback 到原有 `analysis_dims` 中文列表 + `dim_map` |

## 10. 与现有系统的关系

| 组件 | 改造后行为 | 兼容性 |
|------|-----------|--------|
| `analysis_dimensions.py` | 继续作为系统维度的元数据源和代码兜底 | **不删除**，种子数据从此读取 |
| `prompt_registry.py` | 系统维度继续注册；自建维度不在注册表中 | **不修改** |
| `prompt_service.py` | 系统维度提示词优先级不变 | **不修改** |
| `conversation_engine.py` | 新增 `dim_meta` 可选参数，原逻辑零改动 | **向后兼容** |
| `reading.py` `LONG_DIMENSION_KEYS` / `dim_map` | 保留作为 fallback，新增数据库查询路径 | **向后兼容** |
| `compare_long.html` | 不改动解析逻辑 | **无影响** |
| `PromptsTab` | 继续管理系统维度提示词覆盖 | **无影响** |
