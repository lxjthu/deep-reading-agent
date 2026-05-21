# 全文翻译（中文重述）功能集成规划

> 状态：规划中，待确认  
> 日期：2026-05-21  
> 目标：将离线脚本 `translation_pipeline.py` 的核心能力集成到在线 Web 系统，支持 PDF 和 Markdown 两条上传线路

---

## 1. 现状分析

### 1.1 遗留代码

`translation_pipeline.py`（831 行，项目根目录）包含完整的"经济学论文中文重述"六步流水线：

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `extract_front_sections()` | 从 Markdown 提取标题/摘要/引言 |
| 2 | `generate_glossary()` | 调 DeepSeek 生成术语词典 |
| 3 | `detect_section_level()` | LLM 判断章节标题层级（# / ## / ###） |
| 4 | `chunk_md_by_headers()` | 按标题切块，每块 ≤ max_chars |
| 5 | `restate_chunk()` × N | 并发调 DeepSeek 逐块重述为中文 |
| 6 | `fix_untranslated_blocks()` | 补遗残留英文段落 |

入口函数：
- `translate_md_file(md_path)` — 接受一个 Markdown 文件路径
- `translate_pdf_file(pdf_path)` — PDF → PaddleOCR 提取 MD → 再走 `translate_md_file`

### 1.2 问题

1. **不兼容在线架构**：直接用 `os.getenv("DEEPSEEK_API_KEY")` 读取 .env，而非用户传入 Key
2. **同步阻塞**：全程同步代码，无进度上报，无法融入 Job 异步任务体系
3. **文件 I/O 硬编码**：输入输出都走本地路径，不兼容 `upload_storage` / `result_storage`
4. **无数据库记录**：无 Job / Artifact / BibEntry 集成
5. **PDF 提取耦合**：`translate_pdf_file` 直接 import `paddleocr_pipeline`，与在线系统已有的 PDF 提取逻辑重复

### 1.3 在线系统现有模式（需遵循）

- **API Key**：前端传入 → `validate_deepseek_key()` 验证 → `OpenAI(api_key=user_key)`
- **任务模型**：`Job(job_type, status, input_file_id, params_json, progress, current_stage)`
- **产物存储**：`Artifact(artifact_type, filename, storage_path)` + `result_storage` 目录
- **异步执行**：`threading.Thread` 后台运行，通过 Job 表轮询进度
- **路由注册**：`backend/routers/` 下独立 router → `main.py` 中 `app.include_router()`
- **队列控制**：`task_queue.enqueue()` / `mark_running()` / `mark_completed()`

---

## 2. 功能设计

### 2.1 两条线路

```
线路 A（Markdown 直传）：
  用户上传 .md/.markdown → File(markdown) → translate_md_file()
  → 输出 _cn.md + _glossary.md

线路 B（PDF 提取后翻译）：
  用户上传 .pdf → File(pdf)
  → 先走已有 PDF 提取（PaddleOCR/pdfplumber）得到 MD
  → 再走 translate_md_file()
  → 输出 _cn.md + _glossary.md
```

**关键变更**：线路 B 不再让翻译模块自己做 PDF 提取，而是复用在线系统已有的提取流程（与精读、筛选共享同一套提取逻辑）。翻译模块只接受 Markdown 输入。

### 2.2 与现有功能的关系

翻译与精读是**并列关系**，不是替代关系：
- 精读 = 分析论文各维度（研究问题、方法、结果等）
- 翻译 = 全文中文重述（保留所有原文信息，转换为中文经济学学术表达）

翻译可以看作一种特殊的"精读模式"，但产物形态完全不同（输出整篇中文 MD，而非结构化的 ReadingItem）。

---

## 3. 数据模型变更

### 3.1 Job 类型扩展

`jobs.job_type` 的 CHECK 约束需增加 `'translation'`：

```sql
-- 当前约束
"job_type IN ('filter','reading_long','reading_quant','reading_qual',
              'compare','synthesis','reference_trace')"

-- 新约束
"job_type IN ('filter','reading_long','reading_quant','reading_qual',
              'compare','synthesis','reference_trace','translation')"
```

### 3.2 Artifact 类型扩展

`artifacts.artifact_type` 的 CHECK 约束需增加 `'translation_md'` 和 `'translation_glossary'`：

```sql
-- 新增两个值
"artifact_type IN (..., 'translation_md', 'translation_glossary')"
```

### 3.3 PromptTemplate 类型扩展

`prompt_templates.prompt_type` 的 CHECK 约束需增加 `'translation'`：

```sql
"prompt_type IN (..., 'translation')"
```

### 3.4 无需新增表

翻译的输入是 `File`（PDF 或 Markdown），输出是 `Artifact`，关联通过 `Job` 完成。不需要新建数据表。

### 3.5 data_portability 影响

- `CURRENT_SCHEMA_VERSION` 需同步更新（新的 migration 编号）
- 翻译产生的 `Artifact` 类型 `translation_md` / `translation_glossary` 已被现有导出逻辑覆盖（`Artifact` 按表导出，不含 artifact_type 过滤）
- 无需修改导出/导入顺序

---

## 4. 后端实施规划

### 4.1 `translation_pipeline.py` 改造

将原有同步脚本改为可被后端调用的服务模块。核心改动：

| 改动 | 说明 |
|------|------|
| **API Key 参数化** | `translate_md_file()` 新增 `api_key` 参数，不再读 `.env` |
| **base_url 参数化** | 支持自定义 `base_url`（目前系统也支持用户自定义） |
| **进度回调** | 新增 `progress_cb(stage, current, total)` 回调，用于更新 Job |
| **取消检查** | 已有 `cancel_check` 参数，保持不变 |
| **去掉 PDF 入口** | 删除 `translate_pdf_file()`，PDF 提取由后端 router 层在调用翻译前完成 |
| **输出到 result_storage** | 新增 `out_dir` 参数，路由层传入 `result_storage` 路径 |

改造后的函数签名：

```python
def translate_md_file(
    md_path: str,
    out_dir: str,
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-flash",
    max_chars: int = 5000,
    max_workers: int = 5,
    log_cb: Callable[[str], None] | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Tuple[str, str]:
    """
    Returns (cn_md_path, glossary_path).
    """
```

### 4.2 新增路由 `backend/routers/translation.py`

#### 端点设计

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/translation/start` | 发起翻译任务 |
| `GET` | `/api/translation/{job_id}/status` | 查询任务进度 |
| `GET` | `/api/translation/{job_id}/result` | 获取翻译结果（下载链接） |
| `POST` | `/api/translation/cancel/{job_id}` | 取消翻译任务 |

#### `POST /api/translation/start` 请求体

```python
class TranslationStartRequest(BaseModel):
    file_id: str                           # 已上传文件的 ID（PDF 或 Markdown）
    api_key: str | None = None             # 用户 DeepSeek Key
    max_workers: int = 5                   # 并发重述线程数
```

#### 核心流程（路由层）

```
1. 验证用户身份 + API Key
2. 查询 File 记录，确认 file_type ∈ {'pdf', 'markdown'}
3. 创建 Job(job_type='translation', status='pending')
4. 入队 task_queue
5. 启动后台线程：
   a. 若 file_type == 'pdf'：
      - 调用已有 PDF 提取逻辑（PaddleOCR / pdfplumber）得到 MD 文件路径
      - 更新 Job.current_stage = 'extracting'
   b. 若 file_type == 'markdown'：
      - 直接用 File.storage_path 解析得到的 MD 文件路径
   c. 更新 Job.current_stage = 'generating_glossary'
   d. 调用 translate_md_file(md_path, api_key=user_key, ...)
   e. 保存产物到 result_storage：
      - Artifact(artifact_type='translation_md', filename='{stem}_cn.md')
      - Artifact(artifact_type='translation_glossary', filename='{stem}_glossary.md')
   f. 更新 Job → status='success'
6. 异常时：Job → status='failed', error_msg=str(e)
```

#### 进度映射

翻译六步流水线映射到 `Job.progress`（0-100）：

| 阶段 | current_stage | progress |
|------|---------------|----------|
| PDF 提取（仅线路 B） | `extracting` | 5 |
| 提取前置章节 | `front_sections` | 10 |
| 生成术语词典 | `glossary` | 20 |
| 检测标题层级 | `detect_level` | 25 |
| 切块 | `chunking` | 30 |
| 逐块重述 | `restating` | 30 + 50 × (completed / total) |
| 补遗英文 | `fixing_untranslated` | 85 |
| 保存产物 | `saving` | 95 |
| 完成 | — | 100 |

### 4.3 路由注册

`backend/main.py` 中新增：

```python
from routers import translation
app.include_router(translation.router, prefix="/api/translation", tags=["Translation"])
```

### 4.4 队列集成

`queue_manager.py` 中 `_avg_duration` 增加：

```python
"translation": 480,  # 约 8 分钟，与长文本精读相当
```

### 4.5 提示词注册

`prompt_registry.py` 中新增 `translation` 类型的提示词槽位：

```python
"translation": {
    "glossary": {
        "title": "术语词典生成",
        "file_path": "prompts/translation/glossary.md",
    },
    "restate": {
        "title": "逐块重述",
        "file_path": "prompts/translation/restate.md",
    },
},
```

默认提示词内容直接从 `translation_pipeline.py` 中的 `GLOSSARY_SYSTEM/USER_TMPL` 和 `RESTATE_SYSTEM/USER_TMPL` 提取到文件。这样用户可以通过提示词管理界面自定义翻译风格。

### 4.6 PDF 提取复用

线路 B 的 PDF 提取需复用已有逻辑。查看现有精读流程中 PDF 提取的调用方式，在 router 层完成提取，将 MD 文件路径传给翻译模块。具体复用 `reading.py` 中已有的提取逻辑（需抽取为公共函数）。

---

## 5. 前端实施规划

### 5.1 新增 Tab

在 `App.tsx` 的 `TABS` 数组中新增：

```typescript
{ id: 'translation', label: '全文翻译', icon: '文' },
```

### 5.2 TranslationTab 组件

新建 `frontend/src/TranslationTab.tsx`，UI 参考 FilterTab 的模式：

```
┌─────────────────────────────────────────────┐
│  全文翻译 — DeepSeek 中文重述                │
├─────────────────────────────────────────────┤
│                                             │
│  [选择文件] 已上传的 PDF 或 Markdown 文件    │
│     下拉列表，列出当前用户的所有             │
│     file_type ∈ {pdf, markdown} 的文件      │
│                                             │
│  并发数：[5 ▼]  (1-10)                      │
│                                             │
│  [开始翻译]                                  │
│                                             │
├─────────────────────────────────────────────┤
│  翻译进度                                    │
│  ████████████░░░░░ 75%  正在逐块重述 (12/16) │
│  当前阶段：逐块重述                           │
│  [取消]                                      │
├─────────────────────────────────────────────┤
│  翻译结果                                    │
│  📄 paper_cn.md  [下载] [预览]               │
│  📄 paper_glossary.md  [下载] [预览]         │
└─────────────────────────────────────────────┘
```

### 5.3 文件选择

两种来源：
1. **从已有文件选择**：下拉列出用户已上传的 PDF / Markdown 文件（调 `/api/upload/` 或已有文件列表接口）
2. **上传新文件**：触发文件上传，上传完成后自动选中

这与 FilterTab 中选择 PDF 的模式一致，可直接复用。

### 5.4 进度轮询

使用 `setInterval` 轮询 `GET /api/translation/{job_id}/status`，复用 App.tsx 中已有的轮询模式（参考 `useReadingTracker`）。

### 5.5 结果展示

- **预览**：在新窗口/Modal 中渲染 Markdown（复用 `marked` + `KaTeX` 的现有渲染逻辑）
- **下载**：通过 `/api/download/artifact/{artifact_id}` 下载（已有通用下载端点）

---

## 6. 数据库迁移

### 6.1 Migration 脚本

新增 Alembic migration，内容：

1. 修改 `jobs` 表的 `ck_jobs_job_type` 约束，增加 `'translation'`
2. 修改 `artifacts` 表的 `ck_artifacts_artifact_type` 约束，增加 `'translation_md'`、`'translation_glossary'`
3. 修改 `prompt_templates` 表的 `ck_prompt_templates_type` 约束，增加 `'translation'`

### 6.2 部署注意

SQLite 不支持 `ALTER TABLE ... ALTER CONSTRAINT`，需要：
- 删除旧约束 → 重建新约束
- 或通过 `CREATE TABLE new ... INSERT INTO new SELECT ... DROP TABLE old ALTER TABLE new RENAME TO old` 模式

这在线上已有成熟做法（查看已有 migration 中的处理方式）。

---

## 7. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `translation_pipeline.py` | **改造** | 参数化 API Key/base_url，去掉 PDF 入口，增加进度回调 |
| `backend/routers/translation.py` | **新建** | 翻译任务路由（start / status / result / cancel） |
| `backend/main.py` | **修改** | 注册 translation router |
| `backend/db/models.py` | **修改** | 扩展 Job/Artifact/PromptTemplate 的 CHECK 约束 |
| `backend/services/queue_manager.py` | **修改** | `_avg_duration` 增加 `translation` |
| `backend/prompt_registry.py` | **修改** | 增加 `translation` 类型槽位 |
| `backend/services/data_portability.py` | **修改** | `CURRENT_SCHEMA_VERSION` 更新 |
| `migrations/versions/xxx_add_translation.py` | **新建** | Alembic 迁移脚本 |
| `prompts/translation/glossary.md` | **新建** | 术语词典生成提示词 |
| `prompts/translation/restate.md` | **新建** | 逐块重述提示词 |
| `frontend/src/TranslationTab.tsx` | **新建** | 翻译 Tab 组件 |
| `frontend/src/App.tsx` | **修改** | TABS 数组增加 translation |

---

## 8. 风险与注意事项

### 8.1 并发资源

翻译的逐块重述默认 `max_workers=5`，意味着一个翻译任务同时占 5 个 DeepSeek API 连接。在多用户场景下需要考虑：
- 限制同一用户同时只能有一个翻译任务
- 或降低默认并发数到 3

### 8.2 文本长度

150k 字符上限对全文翻译也适用。长论文可能需要先截断再翻译，或分段处理。需在 UI 上明确提示用户。

### 8.3 PDF 提取质量

线路 B 的翻译质量直接取决于 PDF 提取质量。已有系统中 PaddleOCR 提取的 MD 可能包含格式问题（表格错乱、公式丢失），这些会影响翻译质量。需要在 UI 中建议用户：如已有较好的 Markdown 版本，优先走线路 A。

### 8.4 提示词领域

现有提示词专注于"经济学论文"。如果用户翻译其他领域的论文，术语词典和重述风格可能不理想。可在 Phase 2 考虑支持用户选择领域或自定义提示词。

### 8.5 产物与文献库关联

翻译产物应关联到 BibEntry，这样在文献库中可以看到"该文献有中文重述版本"。Phase 1 可先通过 Job → File → BibEntry 的链路实现简单关联，Phase 2 在 LibraryTab 中展示翻译结果。

---

## 9. 实施分阶段建议

### Phase 1（最小可用）

- 改造 `translation_pipeline.py`（参数化）
- 新建 translation router
- 前端 TranslationTab（基本功能）
- 数据库 migration

### Phase 2（体验优化）

- 文献库集成（LibraryTab 展示翻译结果）
- 提示词可自定义（复用提示词管理体系）
- 支持批量翻译（多文件排队）
- 翻译结果在线预览优化

### Phase 3（高级功能）

- 翻译结果编辑（类似 ReadingItemEdit）
- 对比查看（原文 vs 译文并排）
- 领域选择（经济学/管理学/计算机科学等）
- 导出为 Word/PDF 格式

---

## 10. 依赖关系图

```
上传文件（已有）
    │
    ├── PDF ──→ PDF 提取（已有 PaddleOCR/pdfplumber）──→ Markdown
    │                                                      │
    └── Markdown ──────────────────────────────────────────┘
                                                           │
                                                    translation_pipeline
                                                    （参数化改造后）
                                                           │
                                                    ┌──────┴──────┐
                                                    │             │
                                              _cn.md        _glossary.md
                                              Artifact       Artifact
                                                    │             │
                                                    └──────┬──────┘
                                                           │
                                                    下载 / 预览
```
