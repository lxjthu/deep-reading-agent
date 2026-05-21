# 文献库参考文献格式生成 — 设计方案

> 状态：待实施  
> 日期：2026-05-21  
> 关联：AGENTS.md「文献库」模块

## 1. 需求概述

用户在文献库中选择若干条目后，上传或粘贴一篇示例论文（含参考文献区域），系统：

1. **自动定位并提取示例论文的参考文献列表**（复用现有 `deepseek_refs.py` 的定位+提取能力）
2. **调用 DeepSeek 从提取的参考文献中解析出格式规则**（如 GB/T 7714、APA、期刊特有风格）
3. **将用户选中的文献库条目按该格式规则生成参考文献目录**
4. 格式规则可**保存为预设**（如"《经济研究》专用"），下次直接选用

### 输入方式

| 方式 | 说明 |
|------|------|
| 上传 PDF | 完整论文 PDF，系统自动定位参考文献区域 |
| 上传 Markdown | 完整 MD 文件，系统自动定位参考文献区域 |
| 上传 TXT | 纯文本参考文献列表 |
| 直接粘贴 | 在输入框中粘贴参考文献文本 |

### 输出形式

- 页面展示生成结果（可编辑文本区）
- 下载为 `.md` 文件
- 自动存入历史产物（`Artifact`）

## 2. 两阶段架构

```
┌─────────────────────────────────────────────────────────────┐
│  第一阶段：格式规则提取 (analyze)                             │
│                                                             │
│  示例文件 ─→ extract_candidate_text() ─→ 参考文献区域文本     │
│       │                                    │                │
│       └─→ extract_references_deepseek() ──┘                │
│                                            │                │
│                            ┌───────────────▼──────────┐    │
│                            │  DeepSeek 解析格式规则     │    │
│                            │  输出: format_rules JSON   │    │
│                            └───────────────┬──────────┘    │
│                                            │                │
│                              用户可选择保存为预设           │
└────────────────────────────────────────────┼───────────────┘
                                             │
┌────────────────────────────────────────────┼───────────────┐
│  第二阶段：参考文献生成 (generate)           │               │
│                                            ▼               │
│  format_rules (来自预设/刚解析)  +  选中条目的 BibEntry 元数据│
│                            │                                │
│              ┌─────────────▼──────────────┐                │
│              │  DeepSeek 按规则生成         │                │
│              │  输出: 格式化参考文献文本     │                │
│              └─────────────┬──────────────┘                │
│                            │                                │
│              页面展示 + 下载 + 存入 Artifact                 │
└────────────────────────────────────────────────────────────┘
```

## 3. 复用现有代码

本功能复用 `backend/services/deepseek_refs.py` 中的以下函数：

| 函数 | 用途 | 调用位置 |
|------|------|----------|
| `extract_candidate_text(pdf_path)` | PDF 自动定位参考文献区域，返回纯文本 | 第一阶段，上传 PDF 时 |
| `extract_candidate_text_md(md_path)` | Markdown 自动定位参考文献区域 | 第一阶段，上传 MD 时 |
| `extract_references_deepseek(file_path, api_key)` | 完整的定位+结构化提取流程 | 第一阶段，核心提取 |
| `call_deepseek_json(messages, ...)` | 统一的 DeepSeek JSON 调用（含3次重试） | 两个阶段的 LLM 调用 |
| `_is_markdown(file_path)` | 判断文件是否为 Markdown | 文件类型判断 |

**不新增 PDF 提取逻辑**：上传完整论文时，直接调用 `extract_references_deepseek()` 即可获得结构化参考文献列表，再用第一阶段的 LLM 解析其格式规则。

## 4. 数据模型

### 4.1 新表 `ref_format_presets`

迁移文件：`014_ref_format_preset.py`

```python
class RefFormatPreset(Base):
    __tablename__ = "ref_format_presets"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_rfp_owner_name"),
    )

    id: Mapped[int]           = Integer PK, autoincrement
    owner_user_id: Mapped[int] = Integer FK→users, ondelete="CASCADE"
    name: Mapped[str]          = String, 非空  # 如"《经济研究》专用"
    description: Mapped[str|None] = Text, nullable  # 用户备注
    source_text: Mapped[str|None] = Text, nullable  # 原始示例参考文献文本
    format_rules: Mapped[str]    = Text, 非空  # DeepSeek 提取的格式规则 JSON
    detected_format_name: Mapped[str|None] = String, nullable  # 如"GB/T 7714-2015"
    entry_count: Mapped[int]     = Integer, default 0  # 示例中解析出的参考文献条目数
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

索引：
- `idx_rfp_owner` on `owner_user_id`

### 4.2 Artifact 类型扩展

`Artifact.artifact_type` 的 CHECK 约束新增 `'ref_format_md'`。

### 4.3 Job 类型扩展

`Job.job_type` 的 CHECK 约束新增 `'ref_format'`。

### 4.4 Prompt Registry 扩展

新增提示词槽位类型 `ref_format`：

| 槽位 key | 标题 | 用途 |
|----------|------|------|
| `analyze_prompt` | 格式规则提取 | 第一阶段：从参考文献列表中提取格式规则 |
| `generate_prompt` | 参考文献生成 | 第二阶段：按规则将条目元数据格式化为参考文献 |

对应 `prompt_registry.py` 的 `PROMPT_TYPE_LABELS` 新增 `"ref_format": "参考文献格式"`。

## 5. 后端 API

新增路由文件 `backend/routers/ref_format.py`，在 `main.py` 注册为 `app.include_router(ref_format.router, prefix="/api/ref-format", tags=["ref-format"])`。

### 5.1 第一阶段：格式规则提取

```
POST /api/ref-format/analyze
```

**请求** (`multipart/form-data` 或 `application/json`)：

| 参数 | 类型 | 说明 |
|------|------|------|
| `source` | `"upload"` / `"paste"` | 来源方式 |
| `file` | File (可选) | 上传的 PDF/MD/TXT 文件 |
| `text` | String (可选) | 粘贴的参考文献文本 |
| `api_key` | String | 用户 DeepSeek Key |

**处理流程**：

1. 根据 `source` 获取参考文献文本：
   - `upload`：保存临时文件 → 调用 `extract_references_deepseek(file_path, api_key)` 获取结构化参考文献列表 → 拼接为 `raw_text` 列表作为格式分析输入
   - `paste`：直接使用 `text` 内容
2. 调用 DeepSeek（`analyze_prompt`），输入参考文献文本，输出格式规则 JSON
3. 返回解析结果

**响应**：

```json
{
  "format_name": "GB/T 7714-2015 著录格式",
  "format_rules": "{
    \"author_style\": \"姓前名后，多个作者用逗号分隔，3人以上加'等'\",
    \"year_position\": \"年份置于作者之后，用逗号分隔\",
    \"title_style\": \"文章标题用书名号《》包裹\",
    \"journal_style\": \"期刊名用书名号《》包裹，后跟逗号\",
    \"volume_issue\": \"卷号(期号):页码范围\",
    \"punctuation\": \"中文文献用句号结尾，各元素间用逗号分隔\",
    \"order\": \"按正文中出现的顺序编号\",
    \"special_rules\": \"英文文献作者姓前名后用逗号，期刊名斜体\"
  }",
  "raw_references_count": 45,
  "raw_references_sample": [
    "[1] 原始参考文献文本示例1",
    "[2] 原始参考文献文本示例2",
    "[3] 原始参考文献文本示例3"
  ],
  "source_text_truncated": "前3000字符的原始文本，用于预设回溯"
}
```

### 5.2 第二阶段：参考文献生成

```
POST /api/ref-format/generate
```

**请求**：

```json
{
  "format_rules": "{ ... }",       // 格式规则 JSON 字符串
  "format_name": "GB/T 7714-2015", // 格式名称
  "entry_ids": ["uuid1", "uuid2"], // 文献库中选中的条目 ID
  "api_key": "sk-xxx",
  "save_preset": false,             // 是否保存为预设
  "preset_name": null               // 预设名称（save_preset=true 时必填）
}
```

**处理流程**：

1. 查询 `entry_ids` 对应的 BibEntry 记录，提取元数据（title, authors, year, journal, volume, issue, pages, doi）
2. 条目数 > 30 时分批，每批 30 条
3. 调用 DeepSeek（`generate_prompt`），输入格式规则 + 条目元数据，生成格式化参考文献列表
4. 多批结果拼接
5. 保存为 `Artifact(ref_format_md)`
6. 如果 `save_preset=true`，保存到 `ref_format_presets` 表
7. 返回生成结果

**响应**：

```json
{
  "result_text": "[1] 张三,李四.某某研究[J].经济研究,2023,58(3):12-25.\n[2] ...",
  "entry_count": 15,
  "artifact_id": 42,
  "preset_id": null
}
```

### 5.3 预设 CRUD

```
GET    /api/ref-format/presets           → 列出用户所有预设
POST   /api/ref-format/presets           → 新建预设
PUT    /api/ref-format/presets/{id}      → 编辑预设（改名/改描述）
DELETE /api/ref-format/presets/{id}      → 删除预设
```

**POST /api/ref-format/presets**：

```json
{
  "name": "《经济研究》专用",
  "description": "经济研究期刊投稿用",
  "format_rules": "{ ... }",
  "format_name": "GB/T 7714-2015",
  "source_text": "原始示例文本（可选）",
  "entry_count": 45
}
```

**GET /api/ref-format/presets** 响应：

```json
{
  "presets": [
    {
      "id": 1,
      "name": "《经济研究》专用",
      "description": "经济研究期刊投稿用",
      "format_name": "GB/T 7714-2015",
      "entry_count": 45,
      "created_at": "2026-05-21T10:00:00",
      "updated_at": "2026-05-21T10:00:00"
    }
  ]
}
```

## 6. DeepSeek 提示词

### 6.1 analyze_prompt（格式规则提取）

```
你是一位学术参考文献格式分析专家。

## 任务
分析下面提供的参考文献列表，提取出该列表所遵循的参考文献著录格式规则。

## 分析维度
请从以下维度逐一分析：

1. **格式名称**：识别这是哪种标准格式（GB/T 7714、APA、MLA、Chicago、Harvard、期刊特有格式等）
2. **作者格式**：
   - 中英文作者的排列方式（姓前名后？名前姓后？）
   - 多作者的分隔符
   - 超过 N 个作者的省略规则（如"等"/"et al."）
3. **年份位置**：年份出现在哪个位置
4. **标题格式**：
   - 文章标题的标记方式（书名号、引号、斜体、无标记等）
   - 标题大小写规则
5. **期刊格式**：
   - 期刊名的标记方式
   - 卷号、期号、页码的表达方式
6. **标点规则**：
   - 各元素之间的分隔符
   - 条目结尾标点
7. **编号方式**：顺序编码制 / 著者-出版年制 / 无编号
8. **特殊规则**：中英文混排时的差异处理、其他特殊要求

## 输出格式
严格 JSON：
```json
{
  "format_name": "识别出的格式名称",
  "rules": "用自然语言完整描述格式规则，使另一位编辑能仅凭此描述完全复现该格式",
  "special_notes": "需要注意的特殊情况"
}
```

## 约束
- 规则描述必须精确到标点符号级别
- 如果示例中同时包含中英文文献，分别描述两种格式
- 不确定的地方标注"视情况而定"而非猜测
```

### 6.2 generate_prompt（参考文献生成）

```
你是一位学术参考文献著录专家。请严格按照给定的格式规则，将提供的文献信息格式化为参考文献条目。

## 格式规则
{format_rules}

## 格式名称
{format_name}

## 文献信息
以下是 {count} 条文献的结构化信息（JSON 格式）：

{entries_json}

## 输出要求
1. 每条文献生成一行参考文献文本
2. 严格遵循上述格式规则中的每一个细节（标点、空格、顺序）
3. 如果某些字段缺失（如缺少卷号或期号），按该格式的惯例处理
4. 按提供的顺序编号（如果格式要求编号）
5. 不添加任何解释性文字，只输出参考文献列表

## 输出格式
```json
{
  "references": [
    {"order": 1, "formatted": "格式化后的完整参考文献文本"},
    {"order": 2, "formatted": "..."}
  ]
}
```
```

## 7. 前端交互设计

### 7.1 文献库批量操作栏

在现有"删除选中 (N)"按钮旁新增「生成参考文献目录」按钮：
- 选中 ≥ 1 条时可用（灰色禁用状态 → 蓝色可用）
- 点击后弹出 Modal

### 7.2 生成弹窗 (RefFormatModal)

分三个步骤，可前进后退：

**Step 1 — 选择格式来源**

```
┌──────────────────────────────────────────────────┐
│  生成参考文献目录                              ✕  │
├──────────────────────────────────────────────────┤
│                                                  │
│  已选择 15 篇文献                                │
│                                                  │
│  格式来源：                                      │
│  ┌────────────────────────────────────────────┐  │
│  │ 📋 使用已存预设                              │  │
│  │   ○ 《经济研究》专用 (GB/T 7714, 45条示例)  │  │
│  │   ○ APA 7th (32条示例)                      │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │ 📄 上传新示例                                │  │
│  │   支持 PDF / Markdown / TXT，或直接粘贴      │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│                              [取消]  [下一步 →]  │
└──────────────────────────────────────────────────┘
```

- 选择预设 → 跳过 Step 2，直接到 Step 3
- 选择上传新示例 → 进入 Step 2

**Step 2 — 上传示例**

```
┌──────────────────────────────────────────────────┐
│  生成参考文献目录 (2/3)                       ✕  │
├──────────────────────────────────────────────────┤
│                                                  │
│  上传方式：[上传文件] [粘贴文本]                   │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  拖拽文件到此处，或点击选择文件               │  │
│  │  支持 PDF / Markdown / TXT                  │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ── 或 ──                                        │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ 直接粘贴参考文献文本...                      │  │
│  │                                            │  │
│  │                                            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│                              [← 上一步]  [解析 →]│
└──────────────────────────────────────────────────┘
```

- 点击"解析"后调用 `POST /analyze`，显示 loading
- 解析完成后展示结果预览，进入 Step 3

**Step 3 — 确认生成**

```
┌──────────────────────────────────────────────────┐
│  生成参考文献目录 (3/3)                       ✕  │
├──────────────────────────────────────────────────┤
│                                                  │
│  解析结果：                                      │
│  ┌────────────────────────────────────────────┐  │
│  │ 格式：GB/T 7714-2015 著录格式               │  │
│  │ 示例条目数：45 条                            │  │
│  │ 规则摘要：作者姓前名后...                    │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ☑ 保存为预设  名称：[《经济研究》专用     ]     │
│                                                  │
│  将格式化 15 篇文献                              │
│                                                  │
│                     [← 上一步]  [生成参考文献 →] │
└──────────────────────────────────────────────────┘
```

- 点击"生成"后调用 `POST /generate`
- 生成完成后切换到结果展示视图

**结果展示视图**

```
┌──────────────────────────────────────────────────┐
│  参考文献目录已生成                            ✕  │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ [1] 张三,李四.某某研究[J].经济研究,         │  │
│  │     2023,58(3):12-25.                       │  │
│  │ [2] Wang, Y., & Li, Z. (2022). Title...    │  │
│  │ ...                                         │  │
│  │ (可编辑文本区)                               │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  [复制到剪贴板]  [下载 .md]  [关闭]              │
└──────────────────────────────────────────────────┘
```

### 7.3 预设管理页

在文献库页面内通过 URL 参数 `?tab=presets` 切换到预设管理视图（或独立子页面），展示卡片列表：

```
┌────────────────────────────────────────────┐
│ ← 返回文献库                               │
│                                            │
│ 参考文献格式预设              [+ 新建预设]  │
│                                            │
│ ┌──────────────────────────────────────┐   │
│ │ 《经济研究》专用                      │   │
│ │ GB/T 7714-2015 · 45条示例            │   │
│ │ 经济研究期刊投稿用                    │   │
│ │ 创建于 2026-05-21                    │   │
│ │                    [预览] [重命名] [删除]│  │
│ └──────────────────────────────────────┘   │
│                                            │
│ ┌──────────────────────────────────────┐   │
│ │ APA 7th                               │   │
│ │ APA 7th Edition · 32条示例            │   │
│ │                                    │   │
│ │ 创建于 2026-05-20                    │   │
│ │                    [预览] [重命名] [删除]│  │
│ └──────────────────────────────────────┘   │
└────────────────────────────────────────────┘
```

功能：
- 预览：展开显示格式规则原文和原始示例文本
- 重命名：内联编辑名称和描述
- 删除：确认后删除

## 8. 需要修改的现有文件

| 文件 | 改动 |
|------|------|
| `backend/db/models.py` | 新增 `RefFormatPreset` 模型 |
| `backend/migrations/versions/014_ref_format_preset.py` | 新建迁移：建表 + 扩展 Artifact/JOB CHECK 约束 |
| `backend/main.py` | 注册 `ref_format` 路由 |
| `backend/prompt_registry.py` | 新增 `ref_format` 类型 + `analyze_prompt`/`generate_prompt` 槽位 |
| `backend/services/data_portability.py` | `EXPORT_TABLE_ORDER` 新增 `RefFormatPreset`；`CURRENT_SCHEMA_VERSION` 更新为 `"014"` |
| `frontend/src/LibraryTab.tsx` | 批量操作栏新增"生成参考文献目录"按钮 + RefFormatModal 弹窗 |
| `frontend/src/App.tsx` | 预设管理页入口（或在 LibraryTab 内通过状态切换） |
| `frontend/src/lib/api-fetch.ts` | 无需改动（已有鉴权 fetch） |

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/routers/ref_format.py` | 参考文献格式生成 API（analyze + generate + presets CRUD） |
| `backend/services/ref_format_service.py` | 核心业务逻辑（调用 deepseek_refs 提取 + 两阶段 LLM） |
| `backend/prompts/ref_format/analyze_prompt.md` | 格式规则提取提示词 |
| `backend/prompts/ref_format/generate_prompt.md` | 参考文献生成提示词 |
| `frontend/src/components/RefFormatModal.tsx` | 三步弹窗组件 |
| `frontend/src/components/RefFormatPresetManager.tsx` | 预设管理组件 |

## 9. 不涉及的改动

- 不修改 BibEntry 模型
- 不修改现有参考文献梳理（references）功能
- 不修改任务队列（本功能是轻量实时调用，不走 Job 队列，后台线程执行即可）
- 不修改 `deepseek_refs.py` 本身（仅引用其函数）

## 10. 错误处理

| 场景 | 处理 |
|------|------|
| 上传文件无法提取参考文献（如纯图片 PDF） | 返回 422，提示"未能从文件中定位参考文献区域，请尝试直接粘贴文本" |
| DeepSeek 调用失败（3次重试后） | 返回 502，提示"AI 服务暂时不可用，请稍后重试" |
| 条目元数据严重缺失（无标题无作者） | 在生成结果中标注"[信息不完整]"，不跳过 |
| 预设名称重复 | 返回 409，前端提示改名 |
| 选中条目数 = 0 | 前端禁用按钮，不发请求 |
| 粘贴文本过短（< 80 字符） | 前端提示"文本过短，请粘贴完整的参考文献列表" |

## 11. 分批策略

第二阶段当条目数 > 30 时分批处理：

```
total = len(entries)
batch_size = 30
batches = [entries[i:i+batch_size] for i in range(0, total, batch_size)]

results = []
for batch in batches:
    partial = call_deepseek(generate_prompt, batch, format_rules)
    results.extend(partial)

final_text = "\n".join(r["formatted"] for r in results)
# 重新编号
```

每批独立调用 DeepSeek，拼接后重新编号（1, 2, 3, ...）。

## 12. 实施顺序

1. 数据库迁移（`014_ref_format_preset.py` + 模型 + data_portability）
2. 提示词文件（`prompts/ref_format/` + `prompt_registry.py` 注册）
3. 后端服务（`ref_format_service.py`）
4. 后端路由（`ref_format.py` + `main.py` 注册）
5. 前端组件（`RefFormatModal.tsx` + `RefFormatPresetManager.tsx`）
6. 文献库页面集成（`LibraryTab.tsx` 按钮入口）
7. 端到端测试
