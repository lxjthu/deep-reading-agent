# 直接导入 & 批量翻译摘要 — 设计文档

日期：2026-05-22

## 概述

两个独立但共享 `abstract_cn` 字段的功能：

1. **直接导入**：在筛选页面新增按钮，上传 .txt 题录文件后可跳过 AI 筛选，直接将解析出的全部题录入库。
2. **批量翻译摘要**：在文献库页面对勾选条目批量调用 DeepSeek flash 翻译英文摘要，结果存入 BibEntry 的新 `abstract_cn` 字段。

## 一、数据库变更

### 1.1 新增字段

`bib_entries` 表新增：

| 列 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `abstract_cn` | Text | NULL | 摘要中文翻译（AI 筛选或批量翻译产生） |

### 1.2 Alembic 迁移

- 新建迁移脚本，`ALTER TABLE bib_entries ADD COLUMN abstract_cn TEXT`
- 旧行 `abstract_cn` 为 NULL

### 1.3 数据回填

一次性脚本，遍历现有 BibEntry：
1. 通过 BibFilterLink → Job → Artifact 找到 filter_excel 产物
2. 用 `_load_abstract_translation_from_artifact()` 读取 `abstract_cn`
3. 写入 BibEntry.abstract_cn

### 1.4 ORM 模型更新

`backend/db/models.py` BibEntry 类新增：
```python
abstract_cn = Column(Text, nullable=True, default=None)
```

### 1.5 导入导出同步

`backend/services/data_portability.py`：
- `CURRENT_SCHEMA_VERSION` 更新为最新 migration 编号
- `.dra` 导出/导入加入 `abstract_cn` 字段

## 二、功能一：直接导入

### 2.1 前端变更（FilterTab）

在 App.tsx FilterTab 区域，"开始筛选"按钮旁新增"直接导入"按钮：

- 按钮仅在已选择文件时启用（与"开始筛选"一致）
- 点击后调用 `POST /api/filter/direct-import`
- 请求体：`{ file_id: string }`
- 返回 `{ task_id, row_count }` 或同步返回结果（见下方方案选择）
- 按钮文案："直接导入（跳过AI筛选）"
- 完成后显示 toast 提示导入数量，并在日志区显示简要信息

**交互流程**：
1. 用户上传 .txt 文件（复用现有上传逻辑）
2. 点击"直接导入"按钮
3. 前端调用 direct-import 接口
4. 后端解析文件 → 入库 → 返回结果
5. 前端提示"N 条题录已导入文献库"

### 2.2 后端变更

#### 新增端点 `POST /api/filter/direct-import`

```
请求：DirectImportRequest { file_id: str, api_key: Optional[str] }
响应：DirectImportResponse { count: int, entries: [{title, authors, year, doi, journal}] }
```

- 不需要 api_key（不走 AI），但保留字段以备后用
- 不创建 Job 记录（同步操作，解析+入库通常 < 5 秒）
- 不创建 BibFilterLink（没有 filter job）
- 不创建 Artifact（没有 Excel 产物）

#### 处理逻辑

1. 验证 file_id 对应文件存在且属于当前用户
2. `get_parser(file_path)` 解析题录文件，获得 DataFrame
3. 遍历 DataFrame 每行：
   - 复用 `persist_filter_results()` 的核心逻辑：compute_dedup_key → 查找已有 BibEntry → 创建或更新
   - `source_db` 从 DataFrame 的 SourceType 列推导（wos/cnki）
   - `abstract_cn` 初始为 NULL
   - 不设置 score、reason
4. 返回导入数量和简要条目列表

#### 代码组织

在 `backend/routers/filter.py` 中新增 `direct_import` 端点。提取 `persist_filter_results()` 中 BibEntry 创建/更新的核心逻辑为独立函数 `_upsert_bib_entry()`，供筛选和直接导入共用。

## 三、功能二：批量翻译摘要

### 3.1 前端变更（LibraryTab）

在已有批量操作栏（"添加标签"、"删除"按钮旁）新增"翻译摘要"按钮：

- 仅在勾选了条目时显示（复用现有选择逻辑）
- 点击后弹出确认框："确认翻译 N 条英文摘要？将调用 DeepSeek API。"
- 确认后调用 `POST /api/library/entries/batch-translate-abstracts`
- 请求体：`{ entry_ids: string[], api_key: string }`
- 进入轮询状态，显示进度（已翻译 N/M 条）
- 完成后刷新列表，已翻译条目在详情中显示 `abstract_cn`

**UI 展示**：
- LibraryTab 详情面板的 Filter evaluation 区域，已显示 `abstract_translation`，改为优先显示 `entry.abstract_cn`
- 如果 `abstract_cn` 不为空，直接显示；否则 fallback 到从 Excel 产物读取

### 3.2 后端变更

#### 新增端点 `POST /api/library/entries/batch-translate-abstracts`

```
请求：BatchTranslateRequest { entry_ids: list[str], api_key: str }
响应：{ job_id: str }
```

- 验证 api_key
- 创建 Job(job_type="translate_abstracts", status="pending")
- 启动后台线程执行翻译
- 返回 job_id 供轮询

#### 翻译任务逻辑

后台线程函数 `run_batch_translate()`：

1. 查询所有 entry_ids 对应的 BibEntry，过滤出 `abstract IS NOT NULL AND abstract != '' AND (abstract_cn IS NULL OR abstract_cn = '')` 的条目
2. 可选：进一步过滤 `language = 'en'`（如果已有语言标记）
3. 使用 OpenAI client 调用 DeepSeek flash：

```python
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

system_prompt = """你是一位学术翻译专家。将英文学术摘要翻译为中文。
要求：
1. 保持学术术语的准确性
2. 保留关键数据和方法信息
3. 语言流畅自然
4. 直接输出翻译结果，不要添加前缀或说明"""

user_prompt = f"请翻译以下学术摘要：\n\n{abstract}"

resp = client.chat.completions.create(
    model="deepseek-v4-flash",
    extra_body={"thinking": {"type": "disabled"}},
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    max_tokens=2000,
    timeout=120,
)
```

4. 并发控制：`ThreadPoolExecutor(max_workers=5)`
5. 每完成一条，更新 Job.progress 并写入 BibEntry.abstract_cn
6. 失败重试：每条最多重试 2 次，间隔 3 秒
7. 全部完成后 Job.status = "success"

#### 状态轮询端点 `GET /api/library/translate-job/{job_id}/status`

复用现有 Job 表结构：
```json
{
  "job_id": "...",
  "status": "running",  // pending / running / success / failed
  "progress": 15,       // 百分比
  "current_stage": "正在翻译第 3/20 条摘要...",
  "error": null,
  "result": {
    "total": 20,
    "translated": 15,
    "skipped": 3,
    "failed": 2
  }
}
```

### 3.3 代码组织

- 后端：在 `backend/routers/library.py` 新增两个端点
- 翻译函数可以放在 `backend/services/abstract_translator.py`（新文件），复用 translation_pipeline 的 client 创建模式和重试模式
- 提示词注册到 `prompt_registry.py`，支持用户自定义

## 四、现有代码改动汇总

| 文件 | 改动 |
|------|------|
| `backend/db/models.py` | BibEntry 新增 abstract_cn 字段 |
| `backend/routers/filter.py` | 新增 direct-import 端点；提取 _upsert_bib_entry 共用函数；persist_filter_results 写入 abstract_cn |
| `backend/routers/library.py` | 新增 batch-translate-abstracts 和 translate-job/status 端点；修改 _load_abstract_translation 优先读字段 |
| `backend/prompt_registry.py` | 注册 abstract_translate 提示词槽位 |
| `backend/services/abstract_translator.py` | 新文件，批量翻译逻辑 |
| `backend/services/data_portability.py` | 同步 abstract_cn 到导入导出 |
| `migrations/versions/xxx_add_abstract_cn.py` | Alembic 迁移 |
| `frontend/src/App.tsx` | FilterTab 新增"直接导入"按钮 |
| `frontend/src/LibraryTab.tsx` | 批量操作栏新增"翻译摘要"按钮 + 轮询逻辑 |

## 五、边界情况与错误处理

- **直接导入重复题录**：dedup_key 去重，已有则更新元数据、不覆盖已有 abstract_cn
- **批量翻译中部分失败**：记录失败条目 ID，其余继续，最终汇总报告
- **翻译中取消**：支持 cancel_check，检查 Job.status 是否被标记为 cancelled
- **API Key 缺失**：直接导入不需要 key；翻译必须提供
- **摘要为空**：翻译时跳过 abstract 为空的条目
- **abstract_cn 已存在**：翻译时覆盖（用户明确要求）
