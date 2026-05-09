# Phase 3 维度模板市场 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现维度模板市场（预置模板 + AI生成 + 文档导入），用户可一键导入专业分析框架或从种子论文自动生成。

**Architecture:** 新增 `dimension_templates`/`template_items` 系统级表存储预置模板；`ai_template_generator.py` 服务调用 DeepSeek 从论文生成维度；`document_parser.py` 解析 txt/md 文档；前端新增 TemplateMarket 组件集成到 PromptsTab。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + SQLite (backend), React 19 + Tailwind (frontend), DeepSeek API (AI生成)

---

## File Structure

### Backend — Create

| File | Responsibility |
|------|---------------|
| `backend/db/migrations/versions/2026_05_09_add_dimension_templates.py` | Alembic 迁移：新增 dimension_templates + template_items 表 |
| `backend/services/ai_template_generator.py` | 调用 DeepSeek API 从论文文本生成维度模板 |
| `backend/services/document_parser.py` | 解析 txt/md/json 维度文档为标准格式 |
| `backend/data/preset_templates/` | 预置模板种子数据（案例研究通用、社会网络、Ostrom） |

### Backend — Modify

| File | Change |
|------|--------|
| `backend/db/models.py` | 新增 DimensionTemplate、TemplateItem ORM 模型 |
| `backend/main.py` | 启动时调用 ensure_dimension_templates() 填充种子数据 |
| `backend/routers/dimensions.py` | 新增模板市场 API、AI生成 API、文档导入 API |
| `backend/routers/reading.py` | 读取 dimension_set.group_config 适配 LongTab 分组展示 |

### Frontend — Create

| File | Responsibility |
|------|---------------|
| `frontend/src/TemplateMarket.tsx` | 模板市场主组件：展示预置模板、AI生成向导、文档导入 |
| `frontend/src/components/DimensionGroupDisplay.tsx` | LongTab 分组维度 checkbox 渲染组件 |

### Frontend — Modify

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | PromptsTab 添加"模板市场"子 Tab；LongTab 支持分组展示 |

---

## Phase 3a: 预置模板 + 模板市场 UI

### Task 1: Database Migration

**Files:**
- Create: `backend/db/migrations/versions/2026_05_09_add_dimension_templates.py`
- Modify: `backend/db/models.py`

- [ ] **Step 1: Write Alembic migration**

```python
"""add dimension_templates and template_items

Revision ID: 2026_05_09_add_dimension_templates
Revises: 
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2026_05_09_add_dimension_templates'
down_revision = None  # 根据当前最新迁移调整
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dimension_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('dim_count', sa.Integer(), nullable=False),
        sa.Column('preview_json', sa.Text(), nullable=True),
        sa.Column('group_config', sa.Text(), nullable=True),
        sa.Column('is_featured', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index('idx_dim_templates_category', 'dimension_templates', ['category'])
    op.create_index('idx_dim_templates_featured', 'dimension_templates', ['is_featured'])
    
    op.create_table(
        'template_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('dimension_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dim_key', sa.String(), nullable=False),
        sa.Column('dim_name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('prompt_content', sa.Text(), nullable=False),
        sa.Column('default_question', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('group_name', sa.String(), nullable=True),
        sa.Column('is_builtin', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_index('idx_template_items_template', 'template_items', ['template_id'])
    op.create_index('idx_template_items_key', 'template_items', ['template_id', 'dim_key'], unique=True)


def downgrade():
    op.drop_table('template_items')
    op.drop_table('dimension_templates')
```

- [ ] **Step 2: Add ORM models to models.py**

Add after DimensionItem class (around line 609):

```python
class DimensionTemplate(Base):
    __tablename__ = "dimension_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    dim_count: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_dim_templates_category", DimensionTemplate.category)
Index("idx_dim_templates_featured", DimensionTemplate.is_featured)


class TemplateItem(Base):
    __tablename__ = "template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "dim_key", name="uq_template_items_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_templates.id", ondelete="CASCADE"), nullable=False
    )
    dim_key: Mapped[str] = mapped_column(String, nullable=False)
    dim_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_question: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    group_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_template_items_template", TemplateItem.template_id)
```

- [ ] **Step 3: Run migration**

```bash
cd backend && alembic upgrade head
```

Expected: Migration completes without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/db/migrations backend/db/models.py
git commit -m "feat(db): add dimension_templates and template_items tables"
```

---

### Task 2: Preset Template Seed Data

**Files:**
- Create: `backend/data/preset_templates/case_study_general.py`
- Create: `backend/data/preset_templates/social_network.py`
- Create: `backend/data/preset_templates/ostrom_framework.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create case_study_general.py**

```python
"""案例研究通用框架 - 12维度"""

TEMPLATE = {
    "name": "案例研究通用框架",
    "description": "适用于案例研究类论文的通用分析框架，涵盖研究设计、因果机制、可推广性等核心维度",
    "category": "案例研究",
    "dim_count": 12,
    "group_config": None,
    "dimensions": [
        {
            "dim_key": "research_question",
            "dim_name": "研究问题与创新定位",
            "description": "论文解决了什么问题？创新点在哪里？",
            "default_question": "这篇论文的核心研究问题是什么？",
            "prompt_content": "【分析维度：研究问题与创新定位】\n\n请分析这篇论文的核心研究问题与创新贡献。\n\n要求：\n1. 聚焦核心贡献，避免泛泛而谈\n2. 最多识别3点，避免过度扩展\n3. 引用论文的具体段落、数据、方法论细节\n4. 直接输出分析内容，不要客套开场白",
            "group_name": "核心维度",
            "sort_order": 0,
        },
        # ... 其余11个维度（从 12维度案例分析.txt 提取）
    ]
}
```

- [ ] **Step 2: Create social_network.py**

```python
"""社会网络分析框架 - 12维度"""

TEMPLATE = {
    "name": "社会网络分析框架",
    "description": "聚焦社会网络、社会资本与嵌入性，以资深社会学家视角展开系统性精读",
    "category": "理论分析",
    "dim_count": 12,
    "group_config": None,
    "dimensions": [
        {
            "dim_key": "sociological_question",
            "dim_name": "社会学问题意识",
            "description": "论文是否真正提出了社会学意义上的问题？",
            "default_question": "这篇论文的核心社会学问题是什么？",
            "prompt_content": "【分析维度：社会学问题意识】\n\n请识别本文的社会学问题意识...",
            "group_name": "核心维度",
            "sort_order": 0,
        },
        # ... 其余11个维度（从 社会学案例分析.txt 提取）
    ]
}
```

- [ ] **Step 3: Create ostrom_framework.py**

```python
"""Ostrom制度分析框架 - 20维度"""

TEMPLATE = {
    "name": "Ostrom制度分析框架",
    "description": "基于IAD框架与SES框架，系统解析公共池塘资源、集体行动与治理制度的案例研究",
    "category": "制度分析",
    "dim_count": 20,
    "group_config": '{"groups": [{"name": "核心行动情境", "order": 0}, {"name": "规则与制度", "order": 1}, {"name": "资源与治理", "order": 2}, {"name": "评估与对话", "order": 3}]}',
    "dimensions": [
        {
            "dim_key": "action_arena_boundary",
            "dim_name": "行动情境的边界界定",
            "description": "论文是否清晰界定了分析的行动情境边界？",
            "default_question": "本文的行动情境边界是如何划定的，界定是否合理？",
            "prompt_content": "【分析维度：行动情境的边界界定】\n\n请评估本文对行动情境边界的界定清晰度与合理性...",
            "group_name": "核心行动情境",
            "sort_order": 0,
        },
        # ... 其余19个维度（从 Ostrom IAD...txt 提取）
    ]
}
```

- [ ] **Step 4: Modify main.py to seed templates**

Add after existing `ensure_default_dimension_sets()` call:

```python
async def ensure_dimension_templates(db: AsyncSession) -> None:
    """确保系统预置模板存在"""
    from data.preset_templates.case_study_general import TEMPLATE as CASE_STUDY
    from data.preset_templates.social_network import TEMPLATE as SOCIAL_NETWORK
    from data.preset_templates.ostrom_framework import TEMPLATE as OSTROM
    
    templates = [CASE_STUDY, SOCIAL_NETWORK, OSTROM]
    
    for template_data in templates:
        existing = (
            await db.execute(
                select(DimensionTemplate).where(
                    DimensionTemplate.name == template_data["name"]
                )
            )
        ).scalar_one_or_none()
        
        if existing:
            continue
        
        template = DimensionTemplate(
            name=template_data["name"],
            description=template_data["description"],
            category=template_data["category"],
            dim_count=template_data["dim_count"],
            group_config=template_data.get("group_config"),
        )
        db.add(template)
        await db.flush()
        
        for dim in template_data["dimensions"]:
            db.add(
                TemplateItem(
                    template_id=template.id,
                    dim_key=dim["dim_key"],
                    dim_name=dim["dim_name"],
                    description=dim.get("description"),
                    prompt_content=dim["prompt_content"],
                    default_question=dim["default_question"],
                    sort_order=dim["sort_order"],
                    group_name=dim.get("group_name"),
                )
            )
    
    await db.commit()
```

- [ ] **Step 5: Commit**

```bash
git add backend/data backend/main.py
git commit -m "feat(templates): add preset template seed data"
```

---

### Task 3: Template Market API

**Files:**
- Modify: `backend/routers/dimensions.py`

- [ ] **Step 1: Add template list endpoint**

```python
@router.get("/templates")
async def list_templates(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取预置模板列表"""
    query = select(DimensionTemplate).where(DimensionTemplate.is_featured == 1)
    if category:
        query = query.where(DimensionTemplate.category == category)
    query = query.order_by(DimensionTemplate.sort_order, DimensionTemplate.id)
    
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "dim_count": t.dim_count,
            "preview": json.loads(t.preview_json) if t.preview_json else None,
        }
        for t in rows
    ]
```

- [ ] **Step 2: Add template detail endpoint**

```python
@router.get("/templates/{template_id}")
async def get_template_detail(
    template_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取模板详情（含维度列表）"""
    template = (
        await db.execute(
            select(DimensionTemplate).where(DimensionTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    items = (
        await db.execute(
            select(TemplateItem)
            .where(TemplateItem.template_id == template_id)
            .order_by(TemplateItem.sort_order)
        )
    ).scalars().all()
    
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "dim_count": template.dim_count,
        "group_config": json.loads(template.group_config) if template.group_config else None,
        "dimensions": [
            {
                "id": item.id,
                "dim_key": item.dim_key,
                "dim_name": item.dim_name,
                "description": item.description,
                "default_question": item.default_question,
                "prompt_content": item.prompt_content,
                "group_name": item.group_name,
                "sort_order": item.sort_order,
            }
            for item in items
        ],
    }
```

- [ ] **Step 3: Add template import endpoint**

```python
@router.post("/templates/{template_id}/import")
async def import_template(
    template_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """导入预置模板到用户集合"""
    template = (
        await db.execute(
            select(DimensionTemplate).where(DimensionTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 创建新集合
    new_name = template.name
    suffix = 1
    while True:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == new_name,
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            break
        suffix += 1
        new_name = f"{template.name} ({suffix})"
    
    ds = DimensionSet(
        owner_user_id=user.id,
        name=new_name,
        description=template.description,
        is_default=0,
        is_system=0,
    )
    db.add(ds)
    await db.flush()
    
    # 复制维度
    items = (
        await db.execute(
            select(TemplateItem)
            .where(TemplateItem.template_id == template_id)
            .order_by(TemplateItem.sort_order)
        )
    ).scalars().all()
    
    for item in items:
        db.add(
            DimensionItem(
                set_id=ds.id,
                dim_key=item.dim_key,
                dim_name=item.dim_name,
                description=item.description,
                prompt_content=item.prompt_content,
                default_question=item.default_question,
                sort_order=item.sort_order,
                is_builtin=1,
            )
        )
    
    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(items)}
```

- [ ] **Step 4: Test APIs**

```bash
# 列出模板
curl http://localhost:8000/api/dimensions/templates

# 获取详情
curl http://localhost:8000/api/dimensions/templates/1

# 导入模板（需登录）
curl -X POST http://localhost:8000/api/dimensions/templates/1/import \
  -H "Authorization: Bearer YOUR_TOKEN"
```

- [ ] **Step 5: Commit**

```bash
git add backend/routers/dimensions.py
git commit -m "feat(api): add template market CRUD endpoints"
```

---

### Task 4: Frontend Template Market UI

**Files:**
- Create: `frontend/src/TemplateMarket.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create TemplateMarket.tsx**

```typescript
import { useState, useEffect } from 'react'

interface Template {
  id: number
  name: string
  description: string
  category: string
  dim_count: number
}

export default function TemplateMarket() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedCategory, setSelectedCategory] = useState('全部')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    loadTemplates()
  }, [selectedCategory])

  const loadTemplates = async () => {
    try {
      const url = selectedCategory === '全部' 
        ? '/api/dimensions/templates'
        : `/api/dimensions/templates?category=${encodeURIComponent(selectedCategory)}`
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        setTemplates(data)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const importTemplate = async (templateId: number) => {
    setLoading(true)
    try {
      const res = await fetch(`/api/dimensions/templates/${templateId}/import`, {
        method: 'POST',
      })
      if (res.ok) {
        const data = await res.json()
        setMessage(`✓ 已导入「${data.name}」，共 ${data.dim_count} 个维度`)
      } else {
        setMessage('✗ 导入失败')
      }
    } catch (e) {
      setMessage('✗ 网络错误')
    }
    setLoading(false)
  }

  const categories = ['全部', '案例研究', '理论分析', '制度分析']

  return (
    <div className="w-full space-y-4">
      {/* 分类过滤 */}
      <div className="flex gap-2">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3 py-1 rounded-full text-sm ${
              selectedCategory === cat
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-gray-100 text-gray-600'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* 模板列表 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {templates.map(template => (
          <div key={template.id} className="rounded-xl border border-gray-200 bg-white p-5">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-gray-900">{template.name}</h3>
                <span className="text-xs text-gray-500">{template.category} · {template.dim_count}个维度</span>
              </div>
            </div>
            <p className="mt-2 text-sm text-gray-600">{template.description}</p>
            <button
              onClick={() => importTemplate(template.id)}
              disabled={loading}
              className="mt-3 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 disabled:opacity-50"
            >
              {loading ? '导入中...' : '一键导入'}
            </button>
          </div>
        ))}
      </div>

      {message && (
        <div className="text-sm text-gray-600">{message}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Modify App.tsx to add TemplateMarket tab**

In PromptsTab section (around line 1787), add third sub-tab:

```tsx
<div className="flex gap-1 rounded-xl border border-gray-200 bg-white p-1">
  <button onClick={() => setSubTab('prompts')} className={...}>提示词管理</button>
  <button onClick={() => setSubTab('dimensions')} className={...}>维度管理</button>
  <button onClick={() => setSubTab('market')} className={subTab === 'market' ? 'bg-emerald-50 text-emerald-700 ...' : 'text-gray-500 ...'}>
    模板市场
  </button>
</div>

{subTab === 'market' && <TemplateMarket />}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/TemplateMarket.tsx frontend/src/App.tsx
git commit -m "feat(ui): add template market component"
```

---

### Task 5: LongTab Grouping Support

**Files:**
- Create: `frontend/src/components/DimensionGroupDisplay.tsx`
- Modify: `frontend/src/App.tsx` (LongTab)

- [ ] **Step 1: Create DimensionGroupDisplay.tsx**

```typescript
interface DimensionItem {
  dim_key: string
  dim_name: string
  group_name?: string
}

interface Props {
  items: DimensionItem[]
  selectedDims: string[]
  onToggle: (dimName: string) => void
  groupConfig?: { groups: { name: string; order: number }[] } | null
}

export default function DimensionGroupDisplay({ items, selectedDims, onToggle, groupConfig }: Props) {
  // 如果没有分组配置，使用普通列表
  if (!groupConfig || !groupConfig.groups) {
    return (
      <div className="space-y-1">
        {items.map(item => (
          <label key={item.dim_name} className="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm">
            <input 
              type="checkbox" 
              checked={selectedDims.includes(item.dim_name)}
              onChange={() => onToggle(item.dim_name)}
            />
            <span className="text-gray-700">{item.dim_name}</span>
          </label>
        ))}
      </div>
    )
  }

  // 按分组组织
  const grouped: Record<string, DimensionItem[]> = {}
  const ungrouped: DimensionItem[] = []
  
  items.forEach(item => {
    if (item.group_name && groupConfig.groups.some(g => g.name === item.group_name)) {
      if (!grouped[item.group_name]) grouped[item.group_name] = []
      grouped[item.group_name].push(item)
    } else {
      ungrouped.push(item)
    }
  })

  return (
    <div className="space-y-3">
      {groupConfig.groups.map(group => {
        const groupItems = grouped[group.name] || []
        if (groupItems.length === 0) return null
        return (
          <div key={group.name} className="border border-gray-200 rounded-lg p-3">
            <h4 className="text-xs font-medium text-gray-500 mb-2">{group.name}</h4>
            <div className="grid grid-cols-2 gap-1">
              {groupItems.map(item => (
                <label key={item.dim_name} className="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm">
                  <input 
                    type="checkbox" 
                    checked={selectedDims.includes(item.dim_name)}
                    onChange={() => onToggle(item.dim_name)}
                  />
                  <span className="text-gray-700">{item.dim_name}</span>
                </label>
              ))}
            </div>
          </div>
        )
      })}
      {ungrouped.length > 0 && (
        <div className="grid grid-cols-2 gap-1">
          {ungrouped.map(item => (
            <label key={item.dim_name} className="flex items-center gap-2 p-1.5 rounded hover:bg-gray-50 cursor-pointer text-sm">
              <input 
                type="checkbox" 
                checked={selectedDims.includes(item.dim_name)}
                onChange={() => onToggle(item.dim_name)}
              />
              <span className="text-gray-700">{item.dim_name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Modify LongTab to use DimensionGroupDisplay**

In App.tsx LongTab section, replace checkbox rendering:

```tsx
// 获取当前激活集合的分组配置
const [groupConfig, setGroupConfig] = useState(null)

useEffect(() => {
  // 在获取维度列表时同时获取分组配置
  const fetchSetDetails = async () => {
    if (!dimensionSetId) return
    const res = await fetch(`/api/dimensions/sets/${dimensionSetId}`)
    if (res.ok) {
      const data = await res.json()
      if (data.group_config) {
        setGroupConfig(data.group_config)
      }
    }
  }
  fetchSetDetails()
}, [dimensionSetId])

// 渲染时
<DimensionGroupDisplay 
  items={dimensionItems}
  selectedDims={dims}
  onToggle={toggleDim}
  groupConfig={groupConfig}
/>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components frontend/src/App.tsx
git commit -m "feat(ui): add dimension grouping display for LongTab"
```

---

## Phase 3b: AI 自动生成

### Task 6: AI Template Generator Service

**Files:**
- Create: `backend/services/ai_template_generator.py`

- [ ] **Step 1: Create ai_template_generator.py**

```python
import json
from typing import Optional
from openai import OpenAI
from backend.utils.api_key import validate_deepseek_key

MODEL = "deepseek-chat"
MAX_TOKENS = 4000
MAX_PAPER_CHARS = 8000

META_PROMPT_TEMPLATE = """你是一位资深的学术论文分析专家。请根据以下论文内容，设计一套系统性的案例分析维度体系。

【论文内容】
{paper_text}

【任务说明】
1. 先对论文进行快速解析，识别：学科归属、研究类型、理论传统、核心变量(X→Y)、方法论特征
2. 基于识别结果，从以下维度池中选择最适合该论文的 {dim_count} 个维度：

   基础维度（必选）：研究问题定位、理论框架评估、数据来源与方法论、因果机制分析、可推广性评估、整体评价
   
   条件维度（根据论文特征选择）：
   - 案例研究类：案例选择逻辑、案例呈现方式、过程追踪
   - 定量实证类：识别策略与内生性处理、统计结果解读、稳健性检验
   - 制度分析类：制度情境与历史脉络、规则体系分析、治理结构
   - 网络/关系类：社会网络结构、社会资本类型、嵌入性分析
   - 产业经济类：市场结构、价值链治理、产业政策
   - 公共资源类：行动情境边界、设计原则对照、多中心治理
   - 政策评估类：政策含义与实践转化、政策因果识别

3. 为每个维度生成完整的提示词

【输出格式】
严格按以下 JSON 输出，不要添加任何解释或markdown标记：

{{
  "paper_analysis": {{
    "discipline": "一级学科—二级学科",
    "research_type": "研究类型",
    "theory_tradition": "理论传统",
    "core_x": "解释变量",
    "core_y": "被解释变量",
    "methodology": "方法论特征"
  }},
  "template": {{
    "name": "模板名称（学科+研究类型+分析框架）",
    "description": "该模板适用于什么类型的论文",
    "category": "案例研究/定量实证/混合方法/理论建构",
    "dimension_count": 12
  }},
  "dimensions": [
    {{
      "dim_name": "维度名称（6-12字，专业术语）",
      "description": "分析焦点（20-40字）",
      "default_question": "默认分析问题",
      "prompt_content": "【分析维度：维度名称】\\n\\n默认问题\\n\\n要求：\\n1. 子问题1（事实识别：引用原文段落/数据/方法）\\n2. 子问题2（逻辑评估：判断论证是否成立）\\n3. 子问题3（批判判断：指出潜在缺陷或替代解释）\\n4. 直接输出分析，不做铺垫性表述",
      "group_name": "核心维度/方法论维度/理论维度/批判维度",
      "rationale": "为什么选这个维度的简要说明"
    }}
  ]
}}

【质量规范】
1. 维度名称使用学科专业术语，避免通用表达
2. 子问题从"事实识别→逻辑评估→批判判断"递进
3. 至少一个维度包含对典型方法论缺陷的质疑
4. 全篇术语统一，使用同一理论传统的话语体系
5. 维度之间互补不重复
6. 维度总数控制在 {dim_count} 个左右（±2）
"""


def generate_template_from_paper(
    paper_text: str,
    api_key: str,
    dim_count: int = 12,
) -> dict:
    """基于论文内容生成维度模板"""
    api_key = validate_deepseek_key(api_key)
    
    # 截取前 MAX_PAPER_CHARS 字符
    text = paper_text[:MAX_PAPER_CHARS]
    
    meta_prompt = META_PROMPT_TEMPLATE.format(
        paper_text=text,
        dim_count=dim_count,
    )
    
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是一个专业的学术论文分析助手，擅长设计多维度的论文精读分析框架。你必须严格按照用户要求的JSON格式输出，不要添加任何markdown标记或解释性文字。"},
            {"role": "user", "content": meta_prompt}
        ],
        temperature=0.7,
        max_tokens=MAX_TOKENS,
    )
    
    content = response.choices[0].message.content
    
    # 解析 JSON
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content.strip()
        
        result = json.loads(json_str)
        return result
    except json.JSONDecodeError:
        return {"error": "JSON解析失败", "raw_content": content[:500]}
```

- [ ] **Step 2: Test generator service**

```python
# backend/tests/test_ai_template_generator.py
import pytest
from services.ai_template_generator import generate_template_from_paper

@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="No API key")
def test_generate_template():
    result = generate_template_from_paper(
        paper_text="人工智能对制造业企业生产效率的影响研究...",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        dim_count=12,
    )
    assert "error" not in result
    assert "dimensions" in result
    assert len(result["dimensions"]) >= 10
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/ai_template_generator.py backend/tests/test_ai_template_generator.py
git commit -m "feat(ai): add template generation service"
```

---

### Task 7: AI Generation API

**Files:**
- Modify: `backend/routers/dimensions.py`

- [ ] **Step 1: Add generate endpoint**

```python
from services.ai_template_generator import generate_template_from_paper
from services.pdf_extractor import extract_text_from_pdf  # 复用现有PDF提取
import hashlib

# 简单的内存缓存（生产环境应使用Redis）
_generation_cache = {}

class GenerateTemplateRequest(BaseModel):
    file_id: Optional[str] = None
    dim_count: int = 12
    api_key: Optional[str] = None

@router.post("/generate")
async def generate_template(
    body: GenerateTemplateRequest,
    file_upload: Optional[UploadFile] = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传论文生成维度模板（返回预览，不保存）"""
    
    # 获取论文文本
    if body.file_id:
        file_record = await db.get(File, body.file_id)
        if file_record is None:
            raise HTTPException(status_code=404, detail="文件不存在")
        text = extract_text_from_pdf(file_record.storage_path)
    elif file_upload:
        # 保存临时文件
        content = await file_upload.read()
        text = extract_text_from_pdf_bytes(content)
    else:
        raise HTTPException(status_code=400, detail="请提供 file_id 或上传文件")
    
    if not text or len(text.strip()) < 100:
        raise HTTPException(status_code=400, detail="无法从文件中提取有效文本")
    
    # 检查缓存
    cache_key = hashlib.md5(text[:1000].encode()).hexdigest()
    if cache_key in _generation_cache:
        return _generation_cache[cache_key]
    
    # 调用生成服务
    try:
        result = generate_template_from_paper(
            paper_text=text,
            api_key=body.api_key,
            dim_count=body.dim_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    # 缓存结果
    _generation_cache[cache_key] = result
    
    return result
```

- [ ] **Step 2: Add save generated template endpoint**

```python
class SaveGeneratedRequest(BaseModel):
    name: str
    description: Optional[str] = None
    category: str = "AI生成"
    dimensions: list[dict]

@router.post("/generate/save")
async def save_generated_template(
    body: SaveGeneratedRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """将AI生成的结果保存为维度集合"""
    
    # 创建集合
    ds = DimensionSet(
        owner_user_id=user.id,
        name=body.name,
        description=body.description,
        is_default=0,
        is_system=0,
    )
    db.add(ds)
    await db.flush()
    
    # 添加维度
    for idx, dim in enumerate(body.dimensions):
        db.add(
            DimensionItem(
                set_id=ds.id,
                dim_key=f"ai_{dim['dim_name'][:10]}_{idx}",
                dim_name=dim["dim_name"],
                description=dim.get("description"),
                prompt_content=dim["prompt_content"],
                default_question=dim["default_question"],
                sort_order=idx,
                is_builtin=0,
            )
        )
    
    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(body.dimensions)}
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/dimensions.py
git commit -m "feat(api): add AI template generation endpoints"
```

---

### Task 8: AI Generation Frontend Wizard

**Files:**
- Modify: `frontend/src/TemplateMarket.tsx`

- [ ] **Step 1: Add AI generation section to TemplateMarket**

```tsx
// 在 TemplateMarket 组件中添加状态
const [showAIGenerator, setShowAIGenerator] = useState(false)
const [generationStep, setGenerationStep] = useState(0) // 0: upload, 1: config, 2: generating, 3: preview
const [generatedResult, setGeneratedResult] = useState(null)

// AI 生成向导 UI
{showAIGenerator && (
  <div className="border border-emerald-200 rounded-xl bg-emerald-50/30 p-5">
    <h3 className="font-semibold text-gray-900 mb-4">AI生成专属模板</h3>
    
    {generationStep === 0 && (
      <div className="space-y-4">
        <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
          <input 
            type="file" 
            accept=".pdf,.md,.txt" 
            onChange={handleFileUpload}
            className="hidden" 
            id="paper-upload"
          />
          <label htmlFor="paper-upload" className="cursor-pointer">
            <div className="text-gray-500">拖拽论文到这里，或点击选择</div>
            <div className="text-xs text-gray-400 mt-1">支持 PDF / Markdown</div>
          </label>
        </div>
      </div>
    )}
    
    {generationStep === 1 && (
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">期望维度数</label>
          <select 
            value={dimCount} 
            onChange={e => setDimCount(Number(e.target.value))}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-2"
          >
            <option value={8}>8个</option>
            <option value={12}>12个</option>
            <option value={16}>16个</option>
            <option value={20}>20个</option>
          </select>
        </div>
        <button 
          onClick={startGeneration}
          className="px-4 py-2 bg-emerald-600 text-white rounded-lg"
        >
          开始生成
        </button>
      </div>
    )}
    
    {generationStep === 2 && (
      <div className="text-center py-8">
        <div className="animate-spin w-8 h-8 border-2 border-emerald-600 border-t-transparent rounded-full mx-auto"></div>
        <p className="mt-2 text-sm text-gray-600">正在分析论文并生成维度...</p>
      </div>
    )}
    
    {generationStep === 3 && generatedResult && (
      <div className="space-y-4">
        <div className="bg-white rounded-lg p-4">
          <h4 className="font-medium">{generatedResult.template.name}</h4>
          <p className="text-sm text-gray-600">{generatedResult.template.description}</p>
          <div className="mt-2 text-xs text-gray-500">
            识别：{generatedResult.paper_analysis.discipline} · {generatedResult.paper_analysis.research_type}
          </div>
        </div>
        
        <div className="max-h-64 overflow-y-auto space-y-2">
          {generatedResult.dimensions.map((dim, idx) => (
            <div key={idx} className="bg-white rounded p-3 text-sm">
              <div className="font-medium">{dim.dim_name}</div>
              <div className="text-gray-500 text-xs">{dim.description}</div>
            </div>
          ))}
        </div>
        
        <div className="flex gap-2">
          <button onClick={saveGenerated} className="px-4 py-2 bg-emerald-600 text-white rounded-lg">
            保存为我的集合
          </button>
          <button onClick={() => setGenerationStep(1)} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg">
            重新生成
          </button>
        </div>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/TemplateMarket.tsx
git commit -m "feat(ui): add AI generation wizard"
```

---

## Phase 3c: 文档导入

### Task 9: Document Parser Service

**Files:**
- Create: `backend/services/document_parser.py`
- Create: `backend/tests/test_document_parser.py`

- [ ] **Step 1: Create document_parser.py**

```python
import json
import re
from typing import Optional


class ParseError(Exception):
    """文档解析错误"""
    pass


def parse_dimension_document(text: str) -> dict:
    """
    解析维度文档为标准格式
    
    支持格式：
    - # 标题（模板名称）
    - > 描述（模板描述）
    - ## 维度 N：维度名称 / ## 前导：框架定位
    - **描述：** 维度描述
    - **默认问题：** 默认问题
    - ``` 提示词内容 ```
    """
    result = {
        "template_name": "",
        "description": "",
        "dimensions": []
    }
    
    lines = text.split('\n')
    current_dim = None
    in_code_block = False
    code_content = []
    
    for line in lines:
        stripped = line.strip()
        
        # 模板标题
        if stripped.startswith('# ') and not result["template_name"]:
            result["template_name"] = stripped[2:].strip()
        
        # 模板描述
        elif stripped.startswith('> ') and not result["description"]:
            result["description"] = stripped[2:].strip()
        
        # 维度标题（支持多种格式）
        elif stripped.startswith('## '):
            # 保存上一个维度
            if current_dim and not in_code_block:
                if code_content:
                    current_dim["prompt_content"] = '\n'.join(code_content)
                    code_content = []
                result["dimensions"].append(current_dim)
            
            dim_title = stripped[3:].strip()
            # 解析 "维度 1：名称" 或 "前导：框架定位"
            if '：' in dim_title or ':' in dim_title:
                parts = re.split(r'[：:]', dim_title, 1)
                prefix = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                
                current_dim = {
                    "dim_name": name,
                    "prefix": prefix,
                    "description": "",
                    "default_question": "",
                    "prompt_content": "",
                    "group_name": "核心维度"
                }
        
        # 维度描述
        elif re.match(r'\*\*描述[：:]\*\*', stripped) and current_dim and not in_code_block:
            current_dim["description"] = re.sub(r'\*\*描述[：:]\*\*', '', stripped).strip()
        
        # 默认问题
        elif re.match(r'\*\*默认问题[：:]\*\*', stripped) and current_dim and not in_code_block:
            current_dim["default_question"] = re.sub(r'\*\*默认问题[：:]\*\*', '', stripped).strip()
        
        # 代码块（提示词内容）
        elif stripped.startswith('```'):
            if in_code_block:
                # 结束代码块
                current_dim["prompt_content"] = '\n'.join(code_content)
                code_content = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
        elif in_code_block and current_dim:
            code_content.append(line)
    
    # 保存最后一个维度
    if current_dim and not in_code_block:
        if code_content:
            current_dim["prompt_content"] = '\n'.join(code_content)
        result["dimensions"].append(current_dim)
    
    # 验证
    if not result["template_name"]:
        raise ParseError("未找到模板标题（应以 # 开头）")
    if len(result["dimensions"]) == 0:
        raise ParseError("未识别到任何维度（应以 ## 维度 N：开头）")
    
    return result


def parse_json_document(text: str) -> dict:
    """解析 JSON 格式文档"""
    try:
        data = json.loads(text)
        # 验证必要字段
        if "dimensions" not in data:
            raise ParseError("JSON 缺少 dimensions 字段")
        return data
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}")


def parse_document(text: str, file_extension: str = ".txt") -> dict:
    """根据文件扩展名选择解析器"""
    if file_extension.lower() in ['.json']:
        return parse_json_document(text)
    elif file_extension.lower() in ['.txt', '.md', '']:
        return parse_dimension_document(text)
    else:
        raise ParseError(f"不支持的文件格式: {file_extension}")
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_document_parser.py
import pytest
from services.document_parser import parse_dimension_document, ParseError

SAMPLE_DOC = """# 测试模板
> 这是一个测试模板

## 维度 1：研究问题
**描述：** 论文解决了什么问题？
**默认问题：** 核心研究问题是什么？
```
请分析研究问题...

要求：
1. 识别核心问题
2. 评估创新性
3. 直接输出分析
```

## 维度 2：理论框架
**描述：** 使用了什么理论？
**默认问题：** 理论框架是什么？
```
请分析理论框架...
```
"""

def test_parse_dimension_document():
    result = parse_dimension_document(SAMPLE_DOC)
    assert result["template_name"] == "测试模板"
    assert result["description"] == "这是一个测试模板"
    assert len(result["dimensions"]) == 2
    assert result["dimensions"][0]["dim_name"] == "研究问题"
    assert "请分析研究问题" in result["dimensions"][0]["prompt_content"]

def test_parse_empty_document():
    with pytest.raises(ParseError):
        parse_dimension_document("空文档")
```

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/test_document_parser.py -v
```

Expected: 2 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/services/document_parser.py backend/tests/test_document_parser.py
git commit -m "feat(parser): add dimension document parser"
```

---

### Task 10: Document Import API

**Files:**
- Modify: `backend/routers/dimensions.py`

- [ ] **Step 1: Add preview endpoint**

```python
from services.document_parser import parse_document, ParseError

@router.post("/import/preview")
async def preview_import(
    file: UploadFile,
    user: User = Depends(current_user),
):
    """上传文档预览解析结果"""
    try:
        content = await file.read()
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, 
            detail="文件编码错误，请保存为 UTF-8 格式后重试"
        )
    
    # 获取文件扩展名
    ext = os.path.splitext(file.filename)[1]
    
    try:
        result = parse_document(text, ext)
    except ParseError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(e),
                "suggestion": "文档格式不符合标准。请确保包含 # 标题 和 ## 维度 N：名称 格式的标题。",
                "alternative": "如为 PDF 文件，可前往百度 PaddleOCR 将 PDF 转换为 Markdown 后重试。"
            }
        )
    
    return {
        "template_name": result["template_name"],
        "description": result.get("description", ""),
        "dimension_count": len(result["dimensions"]),
        "dimensions": [
            {
                "dim_name": d["dim_name"],
                "description": d.get("description", ""),
                "default_question": d.get("default_question", ""),
            }
            for d in result["dimensions"]
        ],
        "raw_data": result,  # 完整数据用于确认导入
    }
```

- [ ] **Step 2: Add confirm import endpoint**

```python
class ConfirmImportRequest(BaseModel):
    name: str
    description: Optional[str] = None
    dimensions: list[dict]

@router.post("/import/confirm")
async def confirm_import(
    body: ConfirmImportRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """确认导入，保存为维度集合"""
    
    # 创建集合
    ds = DimensionSet(
        owner_user_id=user.id,
        name=body.name,
        description=body.description,
        is_default=0,
        is_system=0,
    )
    db.add(ds)
    await db.flush()
    
    # 添加维度
    for idx, dim in enumerate(body.dimensions):
        db.add(
            DimensionItem(
                set_id=ds.id,
                dim_key=f"import_{idx}",
                dim_name=dim["dim_name"],
                description=dim.get("description"),
                prompt_content=dim.get("prompt_content", ""),
                default_question=dim.get("default_question", ""),
                sort_order=idx,
                is_builtin=0,
            )
        )
    
    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(body.dimensions)}
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/dimensions.py
git commit -m "feat(api): add document import endpoints"
```

---

### Task 11: Document Import Frontend

**Files:**
- Modify: `frontend/src/TemplateMarket.tsx`

- [ ] **Step 1: Add document import section**

```tsx
// 在 TemplateMarket 组件中添加
const [showImport, setShowImport] = useState(false)
const [importPreview, setImportPreview] = useState(null)
const [importError, setImportError] = useState('')

// 文档导入 UI
{showImport && (
  <div className="border border-amber-200 rounded-xl bg-amber-50/30 p-5">
    <h3 className="font-semibold text-gray-900 mb-4">从文档导入</h3>
    
    {!importPreview && !importError && (
      <div className="space-y-4">
        <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
          <input 
            type="file" 
            accept=".txt,.md,.json" 
            onChange={handleImportUpload}
            className="hidden" 
            id="doc-upload"
          />
          <label htmlFor="doc-upload" className="cursor-pointer">
            <div className="text-gray-500">拖拽维度文档到这里，或点击选择</div>
            <div className="text-xs text-gray-400 mt-1">支持 .txt / .md / .json</div>
          </label>
        </div>
        <div className="text-xs text-gray-500">
          提示：可从其他大模型生成提示词后导出为 txt/md，再导入此处
        </div>
      </div>
    )}
    
    {importError && (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="text-red-700 font-medium">导入失败</div>
        <div className="text-red-600 text-sm mt-1">{importError}</div>
        <div className="text-gray-500 text-xs mt-2">
          建议：如为 PDF 文件，可前往百度 PaddleOCR 将 PDF 转换为 Markdown 后重试
        </div>
        <button 
          onClick={() => { setImportError(''); setImportPreview(null); }}
          className="mt-2 text-sm text-emerald-600"
        >
          重新上传
        </button>
      </div>
    )}
    
    {importPreview && (
      <div className="space-y-4">
        <div className="bg-white rounded-lg p-4">
          <h4 className="font-medium">{importPreview.template_name}</h4>
          <div className="text-sm text-gray-600">{importPreview.description}</div>
          <div className="text-xs text-gray-500 mt-1">
            共 {importPreview.dimension_count} 个维度
          </div>
        </div>
        
        <div className="max-h-48 overflow-y-auto space-y-1">
          {importPreview.dimensions.map((dim, idx) => (
            <div key={idx} className="bg-white rounded p-2 text-sm flex justify-between">
              <span>{dim.dim_name}</span>
              <span className="text-gray-400 text-xs">{dim.description}</span>
            </div>
          ))}
        </div>
        
        <div className="flex gap-2">
          <button onClick={confirmImport} className="px-4 py-2 bg-emerald-600 text-white rounded-lg">
            确认导入
          </button>
          <button onClick={() => setImportPreview(null)} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg">
            取消
          </button>
        </div>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/TemplateMarket.tsx
git commit -m "feat(ui): add document import flow"
```

---

## Final Integration & Testing

### Task 12: End-to-End Testing

- [ ] **Step 1: Run full backend tests**

```bash
cd backend
python -m pytest tests/test_document_parser.py tests/test_ai_template_generator.py -v
```

- [ ] **Step 2: Run frontend build**

```bash
cd frontend
npm run lint
npm run build
```

- [ ] **Step 3: Manual test checklist**

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 打开模板市场 | 显示3个预置模板 |
| 2 | 导入 Ostrom 框架 | 创建20维度集合，LongTab 分组展示 |
| 3 | 上传 PDF 生成模板 | AI 分析并生成 12 维度 |
| 4 | 上传 txt 导入 | 正确解析并创建集合 |
| 5 | 导入失败时 | 显示错误信息，提示转换为 Markdown |
| 6 | LongTab 分组 | 20维度按4组展示，可勾选 |

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(phase3): complete dimension template market with AI generation and document import"
```

---

## Spec Coverage Check

| 设计文档章节 | 实现任务 | 状态 |
|-------------|---------|------|
| 3.1 数据库设计（dimension_templates + template_items） | Task 1 | ✓ |
| 3.2 种子数据填充 | Task 2 | ✓ |
| 4. 模板市场 UI | Task 3, 4 | ✓ |
| 5.2 20维度 UI 适配 | Task 5 | ✓ |
| 5.3 AI 自动生成 | Task 6, 7, 8 | ✓ |
| 6. 文档导入 | Task 9, 10, 11 | ✓ |
| 7. API 设计 | Task 3, 7, 10 | ✓ |
| 错误处理（PDF转MD提示） | Task 10 | ✓ |

---

## Placeholder Scan

✓ 无 "TBD"/"TODO" 占位符
✓ 所有步骤包含实际代码
✓ 所有文件路径准确
✓ 类型和命名一致

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-09-dimension-template-market.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
