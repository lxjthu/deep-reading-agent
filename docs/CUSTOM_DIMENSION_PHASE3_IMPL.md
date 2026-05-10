# 长文本精读维度用户化 — Phase 3 模板市场实施记录

> **版本**: v1.0  
> **日期**: 2026-05-10  
> **状态**: 已实施  
> **前置**: [Phase 1 后端实施](./CUSTOM_DIMENSION_PHASE1_IMPL.md) | [Phase 2 前端实施](./CUSTOM_DIMENSION_PHASE2_IMPL.md)  
> **设计文档**: [模板市场设计](./superpowers/specs/2026-05-09-dimension-template-market-design.md) | [实施计划](./superpowers/plans/2026-05-09-dimension-template-market.md)

## 1. 概述

Phase 3 在 Phase 1（后端 CRUD）和 Phase 2（前端内联维度管理）基础上，实现了维度模板市场，包括预置模板浏览/导入、AI 自动生成维度模板、文档导入三大功能。

### 实施完成清单

| # | 内容 | 文件 | 状态 |
|---|------|------|------|
| 1 | 预置模板种子数据 | `backend/template_seed.py` | ✅ Phase 3a 已完成 |
| 2 | dimension_templates / template_items 表 | `backend/db/models.py` + 迁移 008 | ✅ Phase 3a 已完成 |
| 3 | 模板市场基础 API（list/detail/import） | `backend/routers/dimensions.py` | ✅ Phase 3a 已完成 |
| 4 | dimension_items 加 group_name 字段 | 迁移 009 | ✅ |
| 5 | 前端 TemplateMarket 组件 | `frontend/src/TemplateMarket.tsx` | ✅ |
| 6 | PromptsTab 子Tab（提示词管理 / 模板市场） | `frontend/src/App.tsx` | ✅ |
| 7 | LongTab 分组维度展示 | `frontend/src/App.tsx` | ✅ |
| 8 | AI 模板生成服务 | `backend/services/ai_template_generator.py` | ✅ |
| 9 | AI 生成 API（/generate, /generate/save） | `backend/routers/dimensions.py` | ✅ |
| 10 | 文档解析服务 | `backend/services/document_parser.py` | ✅ |
| 11 | 文档导入 API（/import/preview, /import/confirm） | `backend/routers/dimensions.py` | ✅ |
| 12 | 前端 AI 生成向导 + 文档导入 UI | `frontend/src/TemplateMarket.tsx` | ✅ |

---

## 2. 数据库层

### 2.1 新增表：dimension_templates（迁移 008）

```sql
CREATE TABLE dimension_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL,
    dim_count       INTEGER NOT NULL,
    preview_json    TEXT,
    group_config    TEXT,
    is_featured     INTEGER NOT NULL DEFAULT 1,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);
```

### 2.2 新增表：template_items（迁移 008）

```sql
CREATE TABLE template_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     INTEGER NOT NULL REFERENCES dimension_templates(id) ON DELETE CASCADE,
    dim_key         TEXT NOT NULL,
    dim_name        TEXT NOT NULL,
    description     TEXT,
    prompt_content  TEXT NOT NULL DEFAULT '',
    default_question TEXT NOT NULL DEFAULT '',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    group_name      TEXT,
    is_builtin      INTEGER NOT NULL DEFAULT 1
);
```

### 2.3 dimension_items 加 group_name（迁移 009）

```sql
ALTER TABLE dimension_items ADD COLUMN group_name TEXT;
```

使 dimension_items 也能存储分组信息，与 template_items 的 group_name 对应。导入模板时自动复制 group_name。

---

## 3. 预置模板

### 3.1 三套预置模板

| 模板名称 | 维度数 | category | group_config |
|----------|--------|----------|-------------|
| 案例研究通用框架 | 12 | 案例研究 | 无 |
| 社会网络分析框架 | 12 | 理论分析 | 无 |
| Ostrom制度分析框架 | 20 | 制度分析 | 4组分组 |

### 3.2 种子数据

`backend/template_seed.py` 的 `ensure_dimension_templates()` 在应用启动时调用（`main.py`），检查每个模板是否已存在，不存在则创建。

### 3.3 Ostrom 分组

```json
{"groups": [
  {"name": "核心行动情境", "order": 0},
  {"name": "规则与制度", "order": 1},
  {"name": "资源与治理", "order": 2},
  {"name": "评估与对话", "order": 3}
]}
```

前端 LongTab 检测到维度有 `group_name` 字段时自动按分组展示（双列布局）。

---

## 4. API 层

### 4.1 新增端点（共 7 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/templates` | 列出预置模板 |
| GET | `/templates/{id}` | 模板详情（含维度列表） |
| POST | `/templates/{id}/import` | 导入预置模板到用户集合 |
| POST | `/generate` | AI 生成维度模板（multipart/form-data，含 file_upload） |
| POST | `/generate/save` | 保存 AI 生成结果为用户集合（JSON body） |
| POST | `/import/preview` | 上传文档预览解析结果 |
| POST | `/import/confirm` | 确认导入文档为用户集合 |

### 4.2 AI 生成端点细节

- 请求格式：`multipart/form-data`（`file_upload` + `dim_count` + `api_key` + `file_id`）
- PDF 文本提取：复用 `routers.reading.extract_paper_text`（pdfminer + PyPDF2 回退）
- 直接上传的 PDF 先写临时文件再提取
- LLM 调用：`deepseek-chat`，温度 0.7，max_tokens 4000
- 结果按 `md5(text[:1000])` 缓存在内存中

### 4.3 修改的已有端点

| 端点 | 变更 |
|------|------|
| `GET /sets/{set_id}/items` | 返回值新增 `group_name` 字段 |
| `POST /templates/{id}/import` | 导入时复制 `group_name` 到 dimension_items |

---

## 5. 前端

### 5.1 TemplateMarket 组件（~550 行）

路径：`frontend/src/TemplateMarket.tsx`

**四种面板视图**：

| panel | 说明 |
|-------|------|
| `list` | 默认。分类过滤 + 预置模板卡片 + AI生成/文档导入入口 + 用户集合列表 |
| `detail` | 模板详情（分组维度列表 + 一键导入） |
| `ai` | AI 生成向导（上传→配置→生成→预览→保存） |
| `import` | 文档导入（上传→解析预览→确认） |

### 5.2 PromptsTab 子Tab

`App.tsx` 中 `PromptsTab` 改为双子 Tab 容器：

```
┌─ 提示词管理 ─┬─ 模板市场 ─┐
└──────────────┴────────────┘
```

- `PromptsEditor`：原提示词管理内容（重命名）
- `TemplateMarket`：新增模板市场组件
- `apiKey` 通过 props 传入

### 5.3 LongTab 分组展示

`App.tsx` LongTab 的维度 checkbox 区域支持两种渲染：

| 条件 | 渲染方式 |
|------|---------|
| 维度有 `group_name` 字段 | 按分组渲染，每组双列 grid，带组标题 |
| 无 `group_name`（默认维度集） | 保持原有平铺列表 + 拖拽排序 |

---

## 6. 服务层

### 6.1 ai_template_generator.py

- 元提示词模板：要求 LLM 先分析论文特征（学科/类型/理论/变量），再从维度池选择维度
- 输出格式：严格 JSON（paper_analysis + template + dimensions）
- JSON 解析：处理 `\`\`\`json` 包裹、纯 JSON 两种情况

### 6.2 document_parser.py

- 支持 `.txt` / `.md` / `.json` 格式
- txt/md 解析规则：`# 标题` → 模板名，`> 描述` → 模板描述，`## 维度 N：名称` → 维度，`**描述：**` / `**默认问题：**` / `` ``` `` 代码块 → 字段提取
- 自定义异常 `ParseError`，API 层映射为 400

---

## 7. 数据流

### 7.1 AI 生成流程

```
前端 TemplateMarket (ai panel)
  → FormData: file_upload + dim_count + api_key
  → POST /api/dimensions/generate
    → 写临时文件 → extract_paper_text (pdfminer/PyPDF2)
    → generate_template_from_paper (deepseek-chat)
    → 返回 JSON (paper_analysis + template + dimensions)
  → 前端预览
  → POST /api/dimensions/generate/save (JSON body)
    → 创建 DimensionSet + DimensionItem[]
    → 返回 {id, name, dim_count}
```

### 7.2 文档导入流程

```
前端 TemplateMarket (import panel)
  → FormData: file
  → POST /api/dimensions/import/preview
    → parse_document (txt/md/json)
    → 返回 {template_name, description, dimension_count, dimensions[]}
  → 前端预览
  → POST /api/dimensions/import/confirm (JSON body)
    → 创建 DimensionSet + DimensionItem[]
```

### 7.3 预置模板导入流程

```
前端 TemplateMarket (detail panel)
  → POST /api/dimensions/templates/{id}/import
    → 查询 DimensionTemplate + TemplateItem[]
    → 创建 DimensionSet (复制 name/description)
    → 创建 DimensionItem[] (复制 dim_key/dim_name/prompt_content/default_question/group_name)
```

---

## 8. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/services/ai_template_generator.py` | 新增 | AI 维度模板生成服务 |
| `backend/services/document_parser.py` | 新增 | 文档解析服务 |
| `backend/migrations/versions/008_add_dimension_templates.py` | 新增 | dimension_templates + template_items 表迁移 |
| `backend/migrations/versions/009_add_dim_item_group_name.py` | 新增 | dimension_items 加 group_name |
| `backend/db/models.py` | 修改 | DimensionTemplate/TemplateItem ORM + DimensionItem.group_name |
| `backend/routers/dimensions.py` | 修改 | 新增 7 个端点 + group_name 返回/复制 |
| `backend/template_seed.py` | 已有 | 预置模板种子数据（Phase 3a 已创建） |
| `frontend/src/TemplateMarket.tsx` | 新增 | 模板市场组件 |
| `frontend/src/App.tsx` | 修改 | PromptsTab 子Tab + LongTab 分组展示 + apiKey 传递 |

---

## 9. 向后兼容性

| 场景 | 行为 |
|------|------|
| 未执行迁移 009 | dimension_items 无 group_name 列，写入手动置 NULL |
| dimension_set_id 为 null（旧前端） | 精读走原 dim_map 硬编码路径 |
| 旧 .dra 导出文件无维度 JSON | 文件不存在则 skip |
| AI 生成 API key 为空 | validate_deepseek_key 抛 ValueError → 400 |
| 文档格式不符合标准 | ParseError → 400 + 错误提示 |

---

## 10. 待优化

| 项目 | 说明 |
|------|------|
| AI 生成缓存 | 当前内存缓存，重启丢失。可改为 SQLite/Redis |
| 流式输出 | AI 生成目前非流式，大论文可能等 60s+ |
| 模板分享 | 用户间分享维度集合 |
| 预置模板更新 | 目前种子数据只检查 name 存在则跳过，无法更新维度内容 |
| 文档导入 PDF | 目前仅支持 txt/md/json，PDF 需先转 Markdown |
