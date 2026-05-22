# 技术总览文档

> 目的：本文件用于说明当前代码库的**实际实现结构**，帮助后续维护、排错和继续开发。  
> 重点覆盖：
>
> - 当前系统有哪些功能；
> - 前后端代码分别放在哪里；
> - 关键模块、关键函数、关键状态变量分别负责什么；
> - 核心数据如何流转；
> - 最近几轮修改落在什么位置；
> - 后续改某类功能时，应该优先看哪些文件。

## 1. 文档定位

当前 `docs/` 下已经有多种类型的文档：

- 方案类：
  - `MULTI_USER_PLAN.md`
  - `PROMPT_MANAGEMENT_PLAN.md`
  - `PDF_METADATA_MATCH_PLAN.md`
  - `SYNTHESIS_PROMPT_PLAN.md`
  - `REFERENCE_CITATION_TAB_PLAN.md`
- 数据库类：
  - `DATABASE_SCHEMA.md`
- 前端设计类：
  - `frontend-design.md`
- 进度与待办类：
  - `MULTIUSER_PROGRESS.md`
  - `PENDING_PLANS.md`

这些文档主要解决“为什么这么做”和“后面准备做什么”的问题。  
本文件解决的是另一个问题：

- **现在的代码实际上是怎么组织的**
- **我应该去哪里改**
- **哪些函数和变量是关键入口**

## 2. 当前系统功能总览

当前系统已经形成一套多用户学术工作台，核心功能包括：

### 2.1 用户与权限

- 用户注册、登录、刷新登录态、退出登录
- `admin / vip / normal` 三类角色
- 普通用户保留期控制
- 邀请码注册 VIP

### 2.2 文件与上传

- 上传 PDF / Markdown / 题录文件
- 文件按用户隔离存储
- 上传文件去重
- PDF 上传后尝试绑定已有题录

### 2.3 文献筛选

- 上传题录文件后进行规则筛选与 AI 筛选
- 结果导出 Excel
- 题录写入文献库
- 保存筛选评价、分数、筛选任务产物

### 2.4 文献精读

- 长文本精读
- 七步精读
- 四步精读
- **批量文件夹精读**（2026-05-11 新增）
  - 三个精读 Tab 各有「上传文件夹」按钮，通过 `webkitdirectory` 属性选择文件夹
  - 前端过滤 `.pdf/.md/.markdown`，展示文件预览列表，用户确认后逐个上传再调用 `POST /api/reading/batch/start`
  - 后端为每个文件创建独立 Job（共享 `batch_id`），复用单篇精读的完整逻辑
  - 前端通过 `GET /api/reading/batch/{batch_id}/status` 轮询整体进度，内联展示每篇状态
- 结果保存为 Markdown
- 同时拆成结构化结果写入数据库
- **精读完成后自动从前三页提取元数据并写入 `BibEntry`**（2026-05-10 修复）
  - 使用 `pdf_metadata_extract` 提取前三页文本 + `pdf_metadata_llm` 调用 DeepSeek flash 结构化提取
  - 提取字段：标题、作者、年份、期刊、DOI、卷、期、页码、摘要、关键词
  - 只补空字段不覆盖已有值，自动更新 `dedup_key` 和 `metadata_completeness`
  - **MD 文件元数据提取兼容**（2026-05-14）：`extract_front_matter()` 自动判断文件类型，MD 文件读取头部文本填充到与 PDF 相同的 dict 结构；元数据提取失败时仅记录警告不中断精读主流程
- **精读结果多版本并存**（2026-05-16 新增，packaging 分支）
  - 不同模式（七步/四步/长文本）精读结果互不覆盖，可并行存在
  - 同模式重复精读时弹出 `ConflictDialog` 让用户选择：覆盖重跑 / 新增独立记录 / 增量补充（仅长文本）
  - 长文本增量精读：复用已有维度结果，只分析新维度
  - 后端用 `conflict_resolution` 参数（`overwrite`/`new`/`incremental`）替代旧的 `force_overwrite`
  - 新增 `POST /api/reading/check-conflict` 端点，返回冲突详情和增量维度信息
  - 对比综述默认取每个 bib_entry 的最新 job 结果
  - 文献库折叠展示多条精读记录

### 2.5 对比分析与综述

- 长文本对比、七步对比、四步对比
- 支持单问题、多问题、跨步骤综述
- 对比优先读取结构化精读结果
- **v2.0 React 组件已替代 iframe**（2026-05-14）：三个对比 Tab 均使用 `CompareView` React 组件，从生产 API 加载数据，不再通过 iframe 承载旧 HTML
- **AI 文献综述**（2026-05-10 新增）
  - 独立的 `/synthesis`（七步/四步）和 `/synthesis_long`（长文本）端点
  - 按维度串行生成综述，五层写作结构（梳理总结→源流比较→学术对话→缺漏分析→新起点）
  - 利用已提取的参考文献（BibReference）支持二次引用
  - 正文使用中文间注法引用标注，文末生成 GB/T 7714 参考文献目录
  - 使用 `deepseek-v4-flash` 模型（经测试 reasoner 仅慢不优，flash 性价比更高）
  - 产物保存为 `synthesis_md` Artifact

### 2.6 我的文献库

- 查看个人文献列表（显示期刊名称、筛选评分）
- 多维度排序（更新时间、筛选评分、年份、期刊）
- 查看和修改题录元数据
- 查看筛选评价
- 查看任务时间线与产物
- **AI 文献助手**（2026-05-22）
  - 支持 `自动 / 全库 / 当前结果` 多轮自然语言检索
  - DeepSeek 先解析检索意图，再对当前用户文献库召回题录元数据与摘要生成报告
  - 命中文献同步筛选文献列表，并在报告、列表、详情区保持同一 `[n]` 编号
  - 报告编号可点击，按该轮命中集合定位到对应文献
  - AI 可先给出批量标签提议，标签目标由 `tag_target_selector` 在候选结果中结构化选择，用户确认后由批量标签接口写库；标签筛选框支持全标签搜索下拉
  - 每轮报告可单独保存逐篇 AI 点评到 `annotations(library_note)`，文献详情支持编辑或删除已保存点评
- **在线元数据匹配**（2026-05-03 新增）
  - PDF 前 1-3 页文本提取
  - DeepSeek 结构化元数据抽取
  - Crossref / OpenAlex 在线候选检索
  - 多因子评分与置信度分类
  - 高置信度自动补空字段

### 2.7 提示词管理

- 系统默认提示词
- 用户个人提示词覆盖
- 提示词优先级解析
- 前端统一管理 quant / qual / long / filter / library_chat 等固定槽位
- 未被管理员改写的系统默认提示词会随托管 `prompts/` 文件同步更新

### 2.8 维度模板市场

- 系统预设模板（案例研究 12 维度、社会网络分析 12 维度、Ostrom 制度分析 20 维度）
- 用户浏览预设模板并一键导入为自己的维度集
- AI 生成模板：上传种子论文，DeepSeek 自动生成分析维度
- 文档导入：从 TXT/MD/JSON 文件导入维度定义
- 共享功能：用户可将自建维度集分享到模板市场，其他用户看到后一键导入
- 删除功能：删除未使用的自定义维度集（后端检查使用状态）
- 维度分组显示：精读结果按 `group_name` 分组渲染

### 2.9 全文翻译（中文重述）

- **上线日期**：2026-05-21
- 选择已上传的英文 PDF 或 Markdown 文献，调用 DeepSeek 生成术语词典 + 全文中文重述
- **两条线路**：
  - PDF：先提取文本（复用已有 PaddleOCR/pdfplumber），再走翻译流水线
  - Markdown：直接进入翻译流水线
- **PDF 全文翻译**（两步流水线）：
  1. 把 PDF 提取全文交给 DeepSeek → 判断文献类型 + 生成术语库
  2. 把全文一次性交给 DeepSeek → 直接中文重述（max_tokens=65536）
- **Markdown 分片翻译**（旧流程，六步流水线）：
  - 提取前置章节 → 术语词典 → 检测标题层级 → 分块 → 逐块重述 → 补遗英文
- 产物：`translation_md`（中文重述 MD）+ `translation_glossary`（术语词典 MD）
- 翻译结果通过 `JobBibEntry` 关联到文献档案，可在文献库时间线中查看
- 后端路由：`backend/routers/translation.py`（`/api/translation/*`）
- 翻译核心：`translation_pipeline.py`
- 前端组件：`frontend/src/TranslationTab.tsx`
- **表格渲染修复**：`_fix_table_linebreaks()` 自动修复 LLM 输出中多行表格被合并为单行的问题
- **详细日志**：翻译、七步精读、四步精读均输出 `[module:task_id]` 格式的详细日志

### 2.10 数据导入导出

- 一键导出所有用户数据为 `.dra` 格式（JSON + 物理文件打包）
- 一键导入 `.dra` 文件恢复数据
- 导入时自动清空旧数据（避免 UUID 冲突）
- 支持跨设备/跨实例迁移
- 普通用户数据 24h 到期前可导出备份

### 2.10 历史记录与下载

- 历史精读结果
- 历史综述结果
- 鉴权预览
- 鉴权下载

### 2.11 Windows 打包版

- 打包入口：`run_web.py`，打包脚本：`build_web_dist.py`，产物：`dist/DeepReadingAgent-Web.zip`
- 打包版使用单端口架构：FastAPI 在 `localhost:8000` 同时提供 `/api/*` 和 React SPA 静态文件
- 用户可写数据位于 exe 同级 `data/`：`db/app.sqlite`、`_uploads/`、`deep_reading_results/`、`logs/`
- PyInstaller 必须显式包含运行时导入链路：`extractor`、`parsers`、`smart_literature_filter`、`services.*`、`pdfminer.high_level`、`python_multipart`、`httpx`
- PDF 相关子模块通过 `--collect-submodules` 收集：`pdfminer`、`pdfplumber`、`pypdf`、`PyPDF2`、`fitz`
- Excel 读写统一使用 `openpyxl`：筛选导出、参考文献导出、文献库读取筛选产物均显式指定 `engine="openpyxl"`；`xlsxwriter` 是 pandas 可选 warning，不是当前强依赖
- **PyInstaller 打包后路径解析**：`sys.frozen=True` 时 `Path(__file__).resolve().parents[N]` 不再指向项目根目录（指向 exe 所在目录的上级），必须改用 `Path(sys._MEIPASS)` 获取 `_internal` 目录。受影响文件：`prompt_registry.py`、`db/session.py`、`new_architecture/conversation_engine.py`。新增任何通过 `__file__` 计算路径的代码时，必须同步处理 `sys.frozen` 分支
- **打包版隐藏控制台**：PyInstaller 加 `--noconsole`（使用 `runw.exe` bootloader），不再弹出黑色终端窗口。stdout/stderr 重定向到 `data/logs/startup.log`。bat 启动器用 `start ""` 后台运行 exe，窗口闪现即消失。用户通过浏览器内「退出」按钮（`POST /shutdown`）停止服务
- 每次代码改动完成后默认重新运行 `python build_web_dist.py`，并启动打包后的 exe 做 `/health` 冒烟测试

## 3. 当前架构总览

系统可以简化理解为 4 层：

### 3.1 前端层

目录：

- `frontend/src/`
- `frontend/public/`

职责：

- 登录注册与路由守卫
- 工作台界面
- 文献库、提示词管理、历史记录页面
- 对比页承载
- 调用后端 API

### 3.2 后端 API 层

目录：

- `backend/main.py`
- `backend/routers/`

职责：

- 对外提供认证、上传、筛选、精读、对比、文献库、提示词管理、下载、历史、管理等接口
- 提供 `/api/deploy` webhook 入口
- 提供 `/ws/{task_id}` 实时进度通道

### 3.3 服务与业务层

目录：

- `backend/services/queue_manager.py`
- `backend/prompt_service.py`
- `backend/cleanup.py`
- `new_architecture/`
- 根目录若干分析脚本

职责：

- **任务队列管理**（排队位置、预估等待时间、并发控制）
- 统一提示词解析
- 长文本对话引擎
- 清理过期数据
- 引用追踪、参考文献提取等专项能力

### 3.4 数据层

目录：

- `backend/db/`
- `backend/migrations/`

职责：

- 数据库模型
- 会话管理
- Alembic 迁移
- 多用户、任务、文献、产物、结构化结果、提示词模板持久化

## 4. 核心对象模型

理解当前系统，最重要的是先理解几个核心表。

### 4.1 `users`

作用：

- 用户主表

重点字段：

- `role`：角色
- `token_version`：refresh token 失效版本
- `vip_expires_at`：VIP 到期时间
- `is_active`：是否启用
- `last_login_at`：最近登录时间

补充说明：

- 普通用户的 24 小时保留期不是 `users` 表字段，而是按角色动态计算到各业务表的 `expires_at`
- `warning_msg` 是认证接口返回时动态拼装的响应字段，不是数据库列

### 4.2 `files`

作用：

- 上传文件记录

重点字段：

- `owner_user_id`：归属用户
- `storage_path`：物理存储路径
- `md5`：去重用
- `expires_at`：过期时间

### 4.3 `bib_entries`

作用：

- 文献档案中心

它是当前系统里最重要的业务枢纽。  
筛选、精读、对比、文献库都围绕它组织。

重点字段：

- `title / authors_json / year / journal / doi`
- `owner_user_id`
- `source_file_id`
- `dedup_key`
- `reading_status`

### 4.4 `jobs`

作用：

- 统一记录任务

常见 `job_type`：

- `filter`
- `reading_long`
- `reading_quant`
- `reading_qual`
- `compare`
- `synthesis`

### 4.5 `job_bib_entries`

作用：

- 记录某个任务关联了哪些文献

重点字段：

- `role`

常见取值：

- `target`
- `compare_member`
- `synthesis_member`

### 4.6 `artifacts`

作用：

- 统一管理任务产物

常见 `artifact_type`：

- `filter_excel`
- `reading_final`
- `compare_md`
- `synthesis_md`

### 4.7 `reading_items`

作用：

- 存储结构化精读结果

这是对比页和文献库读取精读内容的重要中间层。  
不要把它理解为“文件表”，它是**结构化内容表**。

### 4.8 `prompt_templates`

作用：

- 存储系统默认提示词和用户覆盖提示词

重点字段：

- `scope`：`system` 或 `user`
- `owner_user_id`
- `prompt_type`
- `prompt_key`
- `content`

## 5. 后端代码结构

## 5.1 入口：`backend/main.py`

文件：

- [main.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/main.py)

职责：

- 创建 FastAPI 应用
- 注册所有 router
- 启动时补齐默认提示词
- 注册清理任务

关键函数：

- `lifespan(app)`
  - 应用启动/关闭生命周期管理
  - 启动时补齐默认提示词并注册清理调度器
- `health_check()`
  - 健康检查接口

何时优先看这个文件：

- 新增 router
- 排查启动问题
- 查看全局初始化做了什么

## 5.2 数据库：`backend/db/session.py`

文件：

- [session.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/db/session.py)

职责：

- 创建数据库引擎
- 创建 `AsyncSession`
- 提供 FastAPI 依赖 `get_db`

关键函数 / 变量：

- `DATABASE_URL`
  - 当前数据库连接串
- `engine`
  - SQLAlchemy 异步引擎
- `AsyncSessionLocal`
  - Session 工厂
- `get_db()`
  - 路由层依赖注入数据库会话

## 5.3 数据模型：`backend/db/models.py`

文件：

- [models.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/db/models.py)

职责：

- 定义所有 ORM 模型

维护建议：

- 新增业务实体时，优先改这里
- 任何字段新增都必须同步 Alembic 迁移和文档

关键模型：

- `User`
- `InviteCode`
- `UserSettings`
- `PromptTemplate`
- `UploadBatch`
- `File`
- `Job`
- `BibEntry`
- `BibFilterLink`
- `JobBibEntry`
- `ReadingItem`
- `Artifact`

## 5.4 认证：`backend/routers/auth.py`

文件：

- [auth.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/auth.py)

职责：

- 注册、登录、刷新、获取当前用户、修改密码、退出登录

关键函数：

- `register(...)`
  - 注册用户
- `login(...)`
  - 用户登录，签发 access/refresh token
- `refresh_token(...)`
  - 刷新 access token
- `me(...)`
  - 获取当前用户信息
- `change_password(...)`
  - 修改密码
- `logout(...)`
  - 通过 `token_version` 使旧 refresh token 失效

相关依赖文件：

- [security.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/auth/security.py)
- [dependencies.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/auth/dependencies.py)
- [schemas.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/auth/schemas.py)

## 5.5 上传：`backend/routers/upload.py`

文件：

- [upload.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/upload.py)

职责：

- 接收上传文件
- 写入用户隔离目录
- 记录到 `files`
- 尝试匹配已有题录

关键函数：

- `upload_file(...)`
  - 上传入口
- `get_file_info(...)`
  - 查询上传文件信息
- `delete_file(...)`
  - 删除上传记录

关键逻辑：

- 上传根目录可由 `UPLOAD_ROOT_DIR` 配置，默认落在 `_uploads/`
- 文件按用户存入 `_uploads/{user_id}/{file_id}.{ext}`
- 仅 PDF / Markdown 会按标题相似度尝试匹配已有 `bib_entries`

## 5.6 筛选：`backend/routers/filter.py`

文件：

- [filter.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/filter.py)

职责：

- 题录筛选主链路

关键函数：

- `start_filter(...)`
  - 启动筛选任务
- `run_filter_task(...)`
  - 后台执行筛选
- `persist_filter_results(...)`
  - 将结果写入数据库，含反向匹配（自动关联已上传 PDF）
- `reverse_match_to_existing_files(...)`
  - 反向匹配：将新创建的 BibEntry 与用户已上传的 PDF/MD 文件关联
- `get_task_status(...)`
  - 查询任务状态

关键数据流：

- 上传题录文件
- 创建 `Job(filter)`
- 解析与筛选
- 写入 `BibEntry`
- 写入 `BibFilterLink`
- 生成 `Artifact(filter_excel)`

## 5.7 精读：`backend/routers/reading.py`

文件：

- [reading.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/reading.py)

职责：

- 长文本 / 七步 / 四步精读
- **批量文件夹精读**（2026-05-11 新增）
- **精读过程中自动提取参考文献**（场景一实现）
- **精读结果多版本并存**（2026-05-16 新增）
  - 不同模式互不覆盖，同模式由用户选择覆盖/新增/增量
  - `conflict_resolution` 参数（`overwrite`/`new`/`incremental`）替代 `force_overwrite`

关键函数：

- `resolve_conflict_mode(force_overwrite, conflict_resolution, default)`
  - 将旧的 `force_overwrite` 和新的 `conflict_resolution` 统一为 `"overwrite"` / `"new"` / `"incremental"` / `"check"`
- `check_conflict(request)` — **新增端点**
  - 查询同 bib_entry + 同 mode 是否有成功 job，返回冲突详情和增量维度信息
- `cleanup_old_reading_data(db, bib_entry, job_type)` — **改签名**
  - 新增 `job_type` 参数，只清理同模式的旧 job，不同模式互不影响
- `start_long_context(...)`
- `start_quant(...)`
- `start_qual(...)`
  - 分别启动三类精读任务，使用 `conflict_resolution` 处理冲突
- `start_batch_reading(...)`
  - 批量精读入口，接收 `file_ids` + `mode`，循环创建 Job 并设 `batch_id`
- `get_batch_status(...)`
  - 按 `batch_id` 聚合查询所有 job 状态，返回整体进度和每篇明细
- `run_long_context_task(...)`
  - 后台线程执行长文本分析
  - 支持 `conflict_resolution="incremental"` 增量模式：通过 `_query_prev_reading_jobs` 和 `_query_prev_reading_items` 获取已有结果，跳过已有维度
- `run_quant_task(...)`
- `run_qual_task(...)`
  - 后台线程执行分析
  - 精读完成后自动调用 `_try_extract_references()` 提取参考文献
  - **精读完成后自动调用 `_try_update_bib_metadata()` 从前三页提取元数据并更新 `BibEntry`**
  - **精读维度收集完成后自动调用 `_check_and_retry_empty_dimensions()` 检查空维度并重试（2026-05-14 新增）**
- `_try_extract_references(...)`
  - 调用 `services/deepseek_refs.py` 提取参考文献
  - 调用 `routers/references.py` 的 `write_trace_outputs()` 生成产物
  - 失败时不阻塞主精读流程
- `_try_update_bib_metadata(...)`
  - 调用 `services/pdf_metadata_extract.py` 提取前三页文本
  - 调用 `services/pdf_metadata_llm.py` 调用 DeepSeek flash 提取结构化元数据
  - 只补空字段，自动更新 `dedup_key` 和 `metadata_completeness`
  - 失败时不阻塞主精读流程
- `persist_reading_items(...)`
  - 将结构化结果写入 `reading_items`

关键数据流：

- 文件 -> `BibEntry`
- 创建 `Job(reading_*)`（批量时共享 `batch_id`）
- 绑定 `JobBibEntry(target)`
- 调用 `ConversationEngine`
- **后检查空维度并自动重试（`_check_and_retry_empty_dimensions`）**
- 保存 Markdown 产物
- 保存 `ReadingItem`
- **自动提取参考文献并生成 Excel/MD/JSON 产物**

参考文献产物类型：

- `references_excel` - 参考文献列表 Excel
- `references_with_citations_excel` - 含正文引用的 Excel
- `citation_trace_md` - 引用追踪 Markdown 报告
- `references_json` - 参考文献结构化 JSON

维护建议：

- 精读结果展示不对，先看这里
- compare 前的数据不对，也先看这里
- 参考文献提取失败不影响精读主流程，查看日志中的警告信息

## 5.8 对比与综述：`backend/routers/compare.py`

文件：

- [compare.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/compare.py)

职责：

- 读取结构化精读结果
- 组织 compare/综述输入
- 调用模型生成综述
- 保存对比产物

关键函数：

- `build_structured_paper_data(...)`
  - 从 `reading_items` 组装结构化对比输入
- `get_structured_reading(...)`
  - 对外提供结构化读取接口
- `analyze_comparison(...)`
  - 七步/四步对比综述（`deepseek-v4-flash`）
- `analyze_long_comparison(...)`
  - 长文本对比综述（`deepseek-v4-flash`）
- `gather_bib_references(...)`
  - 从 BibReference 收集已提取的参考文献（二次引用数据源）
- `build_paper_metadata_block(...)`
  - 构建文献元数据+二次引用信息块（prompt 缓存优化）
- `build_synthesis_dimension_prompt(...)`
  - 单维度综述 prompt 构建（含 `_match_dimension_content` 匹配逻辑）
- `_safe_year(...)`
  - year 值安全转换：None → "年份不详"
- `_collect_flat_secondary_refs(...)`
  - 将 bib_refs 展平为编号列表供 DeepSeek 识别
- `_build_secondary_ref_check_prompt(...)`
  - 构建让 DeepSeek 识别正文中实际引用的二次文献的 prompt
- `_parse_cited_ref_ids(...)`
  - 解析 DeepSeek 返回的引用编号（S1, S3 等）
- `_filter_bib_refs_by_indices(...)`
  - 按编号过滤 bib_refs，只保留正文引用过的二次文献
- `build_gbt7714_references(...)`
  - 生成 GB/T 7714 格式参考文献目录（主要+二次引用，条目间空行）
- `persist_synthesis_result(...)`
  - 保存 synthesis_md 产物（文件名格式 `综述-YYYYMMDD-作者姓.md`）
- `synthesize_dimensions(...)`
  - `POST /synthesis`，七步/四步 AI 综述端点（SSE 流式返回）
- `synthesize_long_dimensions(...)`
  - `POST /synthesis_long`，长文本 AI 综述端点（SSE 流式返回）

当前注意点：

- 旧的 `/analyze` 和 `/analyze_long` 端点保持不变，供对比分析使用
- AI 综述使用独立的 `/synthesis` 和 `/synthesis_long` 端点，SSE `StreamingResponse` 逐维度推送
- 二次引用过滤由 DeepSeek 识别（不用正则），复用 system prompt + metadata_block 缓存命中
- 综述提示词目前仍主要由这里拼装，未来可迁到 prompt_registry
- 维度内容不再截断（DeepSeek 支持百万上下文），OpenAI client timeout 300s

## 5.9 文献库：`backend/routers/library.py`

文件：

- [library.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/library.py)

职责：

- 返回文献列表（含筛选评分，支持多维度排序）
- 返回单篇文献详情
- 更新文献元数据

关键函数：

- `list_entries(...)`
  - 文献库列表，支持 `sort_by`（updated/score/year/journal）、`sort_order`（desc/asc）和标签筛选
  - 通过子查询关联 `bib_filter_links` 获取最高筛选评分 `filter_score`
- `get_entry_detail(...)`
  - 单篇详情，聚合筛选评估、AI 点评和任务时间线
- `list_tags(...)` / `batch_update_tags(...)`
  - 返回当前用户标签候选、批量加删文献标签
- `update_entry(...)`
  - 修改元数据
- `update_ai_comment(...)` / `delete_ai_comment(...)`
  - 只编辑或删除文献库里已保存的 AI 点评
- `match_online(...)`
  - 对单篇文献执行在线元数据匹配（Crossref + OpenAlex）
- `apply_match(...)`
  - 应用候选匹配：重新执行在线搜索，调用 `apply_high_confidence_match` 只补空字段，更新 dedup_key 和 metadata_completeness

列表响应 `LibraryEntrySummary` 包含字段：

- 基础题录（title, authors, year, doi, journal）
- 状态（reading_status, metadata_completeness, is_pinned）
- 来源（source_db, source_file_id, source_file_name）
- 用户标注（tags, note）
- 筛选评分（filter_score，取 bib_filter_links 中的最高分）

详情中额外包含：

- 摘要与关键词
- 筛选评价列表
- 已保存 AI 点评（`annotations.source_type='library_note'` 且 `is_ai_generated=1`）
- 时间线与关联产物

## 5.10 历史记录：`backend/routers/history.py`

文件：

- [history.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/history.py)

职责：

- 历史阅读 / 筛选 / 对比结果
- 历史综述结果
- 保存综述
- 删除历史记录

关键函数：

- `list_history(...)`
- `list_synthesis(...)`
- `preview_file(...)`
- `save_synthesis(...)`
- `delete_file(...)`

## 5.11 下载：`backend/routers/download.py`

文件：

- [download.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/download.py)
- [result_storage.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/result_storage.py)

职责：

- 对受保护文件做鉴权下载
- 统一解析开发版与 PyInstaller 打包版中的结果产物根目录

关键函数：

- `download_file(...)`
- `resolve_result_path(...)`
- `build_result_storage_path(...)`

关键点：

- 不直接暴露物理路径
- 会校验当前用户是否有权访问该 Artifact
- 保存/读取 Artifact 文件时不要在各 router 里自行拼接路径，应复用 `result_storage.py`

## 5.12 参考文献梳理：`backend/routers/references.py` + `backend/services/deepseek_refs.py`

文件：

- [references.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/references.py)
- [deepseek_refs.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/deepseek_refs.py)

职责：

- 参考文献识别与结构化
- 正文引用追踪
- 参考文献入库与匹配
- 生成 Excel/MD/JSON 产物

两种场景：

1. **场景一（精读时自动提取）**：在 `reading.py` 的三种精读任务完成后，自动调用 `_try_extract_references()` 提取参考文献
2. **场景二（已有 PDF 手动提取）**：通过 `references.py` 的 API 端点手动触发参考文献梳理任务

文本提取层：

- 使用 `pdfplumber` 提取 PDF 文本（已从 pypdf 迁移）
- 自动检测双栏布局（`_is_two_column()`），对双栏页面启用 `use_text_flow=True`
- 解决了 pypdf 对 CJK 自定义编码 PDF 的中文乱码问题
- 解决了 pypdf 对双栏排版 PDF 的文本顺序错乱问题

关键函数（`deepseek_refs.py`）：

- `extract_references_deepseek(pdf_path)`
  - 从 PDF 尾部提取参考文献
  - 使用 DeepSeek `deepseek-v4-flash` 模型
  - 文本提取使用 pdfplumber（支持 CJK 编码 + 双栏布局）
  - 返回结构化参考文献列表
- `trace_citations_deepseek(pdf_path, references)`
  - 追踪每条参考文献在正文中的引用位置
  - 返回带 citations 的参考文献列表
  - `quote` 仅作为定位锚点，最终展示优先使用包含完整句子和前后文的 `excerpt`
- `extract_candidate_text(pdf_path)`
  - 从 PDF 提取参考文献候选文本
  - 自动检测双栏布局并启用 `use_text_flow=True`
- `extract_body_text(pdf_path)`
  - 从 PDF 提取正文文本和段落信息
  - 自动检测双栏布局并启用 `use_text_flow=True`
- `_is_two_column(chars)`
  - 通过字符 x0 分布判断是否为双栏布局
- `call_deepseek_json(messages, **kwargs)`
  - 封装 DeepSeek API 调用
  - 支持重试和空内容处理

关键函数（`references.py`）：

- `run_reference_trace_task(...)`
  - 后台执行参考文献梳理任务
- `write_trace_outputs(...)`
  - 生成 Excel/MD/JSON 产物文件
- `persist_trace_success(...)`
  - 将参考文献写入 `bib_references` 表
  - 将引用写入 `bib_reference_citations` 表

产物类型：

- `references_excel` - 参考文献列表
- `references_with_citations_excel` - 含引用信息的参考文献
- `citation_trace_md` - Markdown 格式引用报告
- `references_json` - 结构化 JSON

配置要求：

- `DEEPSEEK_API_KEY` 环境变量必须设置
- 使用 `deepseek-v4-flash` 模型
- `max_tokens` 必须设为 16384（避免 JSON 截断）
- 正文引用详情需要完整句子时，优先检查 `excerpt` 生成链路，不要只看模型返回的短引用标记

## 5.13 提示词管理：`backend/prompt_registry.py` + `backend/prompt_service.py` + `backend/routers/prompts.py`

文件：

- [prompt_registry.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/prompt_registry.py)
- [prompt_service.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/prompt_service.py)
- [prompts.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/prompts.py)

职责分层：

- `prompt_registry.py`
  - 定义有哪些 prompt 槽位
  - 相当于“提示词注册表”
- `prompt_service.py`
  - 负责解析当前应该用哪条提示词
  - 相当于“提示词服务层”
- `prompts.py`
  - 对外提供 API

`prompt_registry.py` 关键内容：

- `PROMPT_SPECS`
  - 所有固定提示词槽位定义

`prompt_service.py` 关键函数：

- `ensure_builtin_prompt_templates(...)`
  - 幂等补齐系统默认提示词
- `get_prompt_payload(...)`
  - 获取单个提示词槽位的完整信息
- `get_effective_prompt_map(...)`
  - 获取某一类提示词的当前生效内容
- `upsert_user_prompt(...)`
  - 保存用户覆盖
- `upsert_system_prompt(...)`
  - 保存系统默认

`prompts.py` 关键接口：

- `/api/prompts/catalog`
- `/api/prompts/item`
- `/api/prompts/my`
- `/api/prompts/system`

## 5.13 任务队列管理：`backend/services/queue_manager.py`

文件：

- [queue_manager.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/queue_manager.py)

职责：

- 任务入队与排队位置计算
- 预估等待时间（基于历史平均耗时的移动平均）
- 并发任务运行状态跟踪
- 队列状态查询

关键类：`TaskQueueManager`

关键方法：

- `enqueue(task_id, user_id, task_type)`
  - 将任务加入队列，返回排队位置和预估等待时间
- `dequeue_next()`
  - FIFO 取出下一个待执行任务
- `mark_running(task_id)`
  - 标记任务为运行中，从队列移除
- `mark_completed(task_id)`
  - 标记任务完成，更新该类型任务的平均耗时（移动平均）
- `get_queue_status()`
  - 返回队列长度、运行中任务数、详细列表
- `get_task_queue_info(task_id)`
  - 查询特定任务的排队/运行状态

默认平均耗时（秒）：

| task_type | 默认耗时 |
|-----------|---------|
| quant | 600（10 分钟） |
| qual | 480（8 分钟） |
| long | 720（12 分钟） |
| reference | 300（5 分钟） |
| filter | 180（3 分钟） |

测试文件：`backend/tests/test_queue_manager.py`（30 个用例，覆盖全部行为）

## 5.14 数据导入导出：`backend/routers/data.py` + `backend/services/data_portability.py`

文件：

- [data.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/data.py)
- [data_portability.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/data_portability.py)

职责：

- 用户数据一键导出为 `.dra` 格式
- `.dra` 文件一键导入恢复数据
- 导出包包含数据库记录（JSON）和物理文件

关键函数：

- `export_user_data(db, user)`
  - 按 FK 正向顺序查询 11 张表，序列化为 JSON
  - 复制物理文件到 files/ 和 artifacts/ 目录
  - 打包为 zip，返回临时文件路径
- `import_user_data(db, user, dra_path)`
  - 解压 `.dra` 文件，读取 manifest.json
  - 验证 format_version
  - 清空导入用户自己的关联数据（junction tables 等）
  - 按 FK 正向顺序导入 JSON 数据，每张表先 `_pre_delete_conflicts` 再 INSERT
  - 每张表 flush 一次，捕获早期错误
  - 统一提交事务
  - 恢复物理文件（best-effort）

**关键实现要点**：

1. **事务管理**：所有数据库操作在一个事务中完成，不要在 `_clear_user_data()` 内部调用 `db.commit()`
2. **冲突覆盖策略**：`_pre_delete_conflicts` 在每张表 INSERT 前按三层策略清理旧数据：
   - UUID PK 表（File/BibEntry/Job 等）：`DELETE WHERE pk IN (导出数据PKs)`，不区分 owner_user_id
   - 有 UniqueConstraint 的表（BibFilterLink/JobBibEntry/ReadingItem）：按唯一键组合精确删除
   - Auto-PK 无唯一约束的子表（Artifact）：按 FK 列值删除（如 `job_id IN (...)`），因为 SQLite 不强制 FK CASCADE
3. **文件恢复时机**：必须在 `db.commit()` 之后进行，但恢复所需信息（storage_path）在 commit 前收集
4. **错误处理**：导入失败时抛出异常，由路由层捕获并返回 500 错误
5. **用户 ID 替换**：导入时 `owner_user_id` 统一替换为当前用户，`expires_at` 按当前角色重算
6. **安全注意事项**：导入前保存 `user.id`/`user.role` 到局部变量，避免 flush 后访问过期 ORM 对象触发 MissingGreenlet

导出包格式：

```
export_20260506_username.dra
├── manifest.json              # 格式版本、统计信息、错误记录
├── data/                      # 数据库记录（每表一个 JSON）
│   ├── bib_entries.json
│   ├── files.json
│   └── ...
├── files/                     # 上传的物理文件
│   └── {file_id}.{ext}
└── artifacts/                 # 产物物理文件
    └── {job_id}/
        └── {filename}
```

## 5.15 清理与管理员：`backend/cleanup.py` + `backend/routers/admin.py`

文件：

- [cleanup.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/cleanup.py)
- [admin.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/admin.py)

职责：

- 管理员管理用户与邀请码
- 定时清理过期文件与记录

关键函数：

- `cleanup_expired(...)`
  - 清理过期数据
- `reapply_user_retention(...)`
  - 重算用户保留期

## 6. 前端代码结构

## 6.1 入口与路由：`frontend/src/RootApp.tsx`

文件：

- [RootApp.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/RootApp.tsx)

职责：

- 应用根路由
- 登录页
- 注册页
- 工作台路由守卫
- 管理后台路由守卫

关键组件 / 函数：

- `AuthLayout`
  - 登录/注册通用表单壳
- `buildWorkspaceRedirect(...)`
  - 根据登录状态决定跳转到哪里
- `ProtectedRoute`
  - 未登录不能进工作台
- `AdminRoute`
  - 非管理员不能进后台
- `LoginPage`
- `RegisterPage`
- `AppRoutes`

最近修改：

- 注册页新增前端密码规则校验
- 明确提示“密码至少 8 位且包含字母和数字”

关键状态变量：

- `username / email / password / confirmPassword / inviteCode`
- `error / loading`

## 6.2 认证状态：`frontend/src/store/auth.ts`

文件：

- [auth.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/store/auth.ts)

职责：

- 统一管理登录态

关键状态变量：

- `accessToken`
- `refreshToken`
- `user`
- `initialized`

关键函数：

- `hydrate()`
  - 从本地恢复登录态
- `setSession(...)`
  - 保存完整会话
- `clearSession()`
  - 清空会话
- `fetchMe()`
  - 重新获取当前用户
- `login(...)`
- `register(...)`
- `logout()`

## 6.3 全局鉴权请求：`frontend/src/lib/api-fetch.ts`

文件：

- [api-fetch.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/lib/api-fetch.ts)

职责：

- 覆盖全局 `fetch`
- 自动附加 token
- 401 时自动刷新 access token 并**重试原请求**

关键函数：

- `installGlobalAuthFetch()`
  - 安装全局包装后的 fetch
- `apiFetch(...)`
  - 实际请求逻辑
  - **重要**：retry 时必须重新 `new Request(input, initSnapshot)`，禁止复用已消费的 Request 对象（body 只能消费一次）
- `refreshAccessToken()`
  - 调 refresh 接口
- `redirectToLogin(...)`
  - 刷新失败后跳登录页

**踩坑记录**：

- 曾出现 `Cannot construct a Request with a Request object that has already been used` 错误
- 原因：token refresh 后 retry 复用了同一个 Request 对象，其 body 已被第一次 fetch 消费
- 修复：保存 `init` 快照，retry 时用 `new Request(input, initSnapshot)` 重新创建
- 详见 [TROUBLESHOOTING_SERVER_ERRORS.md](TROUBLESHOOTING_SERVER_ERRORS.md) 问题 5

## 6.4 工作台主壳：`frontend/src/App.tsx`

文件：

- [App.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/App.tsx)

职责：

- 工作台 Tab 导航
- 用户菜单
- API Key 管理
- 挂载筛选、精读、对比、文献库、提示词、历史记录页面

关键状态变量：

- `activeTab`
  - 当前标签页
- `apiKey`
  - 当前登录用户的 DeepSeek API Key
- `showKeyInput`
  - 是否展开 Key 编辑区
- `tempKey`
  - 输入框中的临时 key
- `showUserMenu`
  - 是否展开右上角用户菜单

关键函数：

- `getInitialTab(...)`
  - 根据 URL 决定初始 Tab
- `handleTabChange(...)`
  - 切换 Tab 并同步 URL
- `handleSaveKey()`
  - 保存当前账号的 API Key
- `handleDeleteKey()`
  - 删除当前账号的 API Key
- `handleLogout()`
  - 登出并跳登录页

最近修改：

- API Key 改成按当前用户名隔离存储
- 新用户不会再继承别的账号在本地浏览器里保存的 key

## 6.5 文献库页：`frontend/src/LibraryTab.tsx`

文件：

- [LibraryTab.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/LibraryTab.tsx)

职责：

- 文献列表（卡片式，显示标题、作者、年份、期刊、阅读状态、筛选评分）
- 文献详情
- 元数据编辑
- 时间线与产物下载
- 多维度排序（更新时间、筛选评分、年份、期刊，升降序）

关键状态变量：

- `search`
- `journalFilter`
- `readingStatus`
- `pinnedOnly`
- `sortBy`（updated / score / year / journal）
- `sortOrder`（desc / asc）
- `entries`
- `selectedId`
- `detail`
- `draft`
- `listLoading / detailLoading / saving`
- `listError / detailError / saveMessage`

关键函数：

- `loadEntries()`
  - 加载列表，传递 sort_by / sort_order 参数
- `loadDetail(id)`
  - 加载详情
- `handleSave()`
  - 保存元数据
- `saveChatTurnComments()`
  - 只保存当前 turn 中值得写入条目的逐篇 AI 点评
- `buildDraft(...)`
  - 将详情转换成表单草稿

## 6.6 下载与预览：`frontend/src/lib/download.ts`

文件：

- [download.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/lib/download.ts)

职责：

- 鉴权下载
- 鉴权预览

关键函数：

- `downloadWithAuth(...)`
- `openPreviewWithAuth(...)`

## 6.7 对比页承载（v2.0 React 组件）

三个对比 Tab 已从旧 iframe/demo HTML 迁移为 React 组件。当前生产入口只保留 React 组件与后端真实数据接口，`frontend/public/compare_*.html` 和 `backend/compare_demo_server.py` 已从代码树移除，避免进入打包产物。

- `frontend/src/components/CompareView.tsx` — 对比综述主组件（替代 iframe）
- `frontend/src/components/compare/AnswerCard.tsx` — 答案卡片（预览/完整两种模式）
- `frontend/src/components/compare/AccordionPanel.tsx` — 维度折叠面板（三级展开 + 维度级模式按钮）
- `frontend/src/components/compare/PaperSelector.tsx` — 文献选择卡片
- `frontend/src/components/compare/DimNavigation.tsx` — 维度/步骤导航胶囊
- `frontend/src/components/compare/SynthesisModal.tsx` — AI 综述弹窗
- `frontend/src/components/compare/compare.css` — 对比页独立样式
- `frontend/src/hooks/useCompareData.ts` — 对比数据加载 Hook
- `frontend/src/hooks/useSynthesisStream.ts` — AI 综述 SSE 流式 Hook

后端生产端点：

- `GET /api/compare/reading-data` — 聚合用户精读数据（返回与 demo JSON 同构的数据）
- `POST /api/compare/synthesis-stream` — AI 综述 SSE 流式端点

在 `App.tsx` 中的集成：

- 三个对比 Tab 直接渲染 `<CompareView mode="long|quant|qual" apiKey={...} />`
- 对比页全屏布局，不受普通 Tab 布局挤压

## 6.8 提示词管理页

当前提示词管理页直接写在：

- [App.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/App.tsx)

主要状态变量：

- `promptType`
  - 当前提示词类型
- `currentKey`
  - 当前槽位 key
- `catalog`
  - 后端返回的目录
- `effectiveContent`
  - 当前生效内容
- `userContent`
  - 当前用户的个人覆盖
- `systemContent`
  - 系统默认内容
- `source`
  - 当前来源：system / user / fallback
- `hasUserOverride`
  - 当前用户是否已有覆盖
- `message`
  - 操作成功/失败提示

关键函数：

- `loadCatalog()`
- `loadItem()`
- `refreshAll()`
- `saveMyPrompt()`
- `resetMyPrompt()`
- `saveSystemPrompt()`

## 7. 核心业务数据流

## 7.1 登录/注册

- 前端注册/登录页
- `auth.ts`
- 后端 `/api/auth/*`
- 保存到本地存储
- 跳转到工作台

## 7.2 上传 -> 题录绑定

- 用户上传文件
- 后端写入 `files`
- 根据标题尝试匹配 `bib_entries`
- 若后续精读启动时仍未绑定，会再次兜底匹配

## 7.3 题录筛选 -> 文献库

- 题录文件进入筛选
- 创建 `Job(filter)`
- 结果写入 `BibEntry`
- 筛选评价写入 `BibFilterLink`
- Excel 写入 `Artifact`

## 7.4 精读 -> 结构化结果

- PDF 文件进入精读
- 创建 `Job(reading_*)`
- 产出 Markdown
- 结构化结果写入 `ReadingItem`

## 7.5 对比 -> 综述

- 前端选择多篇文献
- 后端优先从 `ReadingItem` 组装数据
- `/api/compare/analyze*` 生成 `Job(compare)` 和 `Artifact(compare_md)`
- 用户保存到历史时，再由 `/api/history/synthesis/` 额外生成 `Job(synthesis)` 和 `Artifact(synthesis_md)`

### 7.5.1 AI 文献综述（新，2026-05-10）

- 前端「AI 综述」按钮改为调用独立端点
  - 七步/四步：`POST /api/compare/synthesis`（dimensions 为 `[{label, step}]`）
  - 长文本：`POST /api/compare/synthesis_long`（dimensions 为 `["维度1", "维度2"]`）
- 数据流：
  1. `resolve_compare_members()` — 复用现有函数解析文献
  2. `ensure_paper_data()` — 复用，优先读结构化精读结果
  3. `gather_bib_references()` — 新增，从 BibReference 收集二次引用
  4. 串行逐维度调用 `deepseek-v4-flash`，每维度独立 prompt
  5. `build_gbt7714_references()` — 新增，生成 GB/T 7714 参考文献目录
  6. `persist_synthesis_result()` — 新增，保存为 `synthesis_md` Artifact
- 前端 `CompareView` / `SynthesisModal` 调用新端点
- 旧的 `/analyze` 和 `/analyze_long` 端点不受影响，仍供「对比分析」按钮使用

## 7.6 文献库与历史

- 文献库围绕 `BibEntry` 聚合展示
- 列表查询通过子查询关联 `bib_filter_links` 获取筛选评分
- 支持按更新时间、筛选评分、年份、期刊排序
- 历史记录围绕 `Artifact` 和 `Job` 聚合展示
- 下载与预览统一走鉴权接口

## 8. 最近几轮重要修改记录

本节用于记录“近期已落地的重要代码调整”，方便后续定位。

### 8.1 提示词中心

改动目标：

- 将默认提示词和用户自定义提示词统一纳入数据库管理

落点文件：

- `backend/prompt_registry.py`
- `backend/prompt_service.py`
- `backend/routers/prompts.py`
- `frontend/src/App.tsx`

当前结果：

- 支持系统默认 + 用户覆盖
- 前端可查看当前生效来源

### 8.2 compare 结构化读取

改动目标：

- 让四步/七步对比优先读取结构化精读结果，而不是完全依赖前端拆 Markdown

落点文件：

- `backend/routers/compare.py`
- `backend/scripts/backfill_reading_items.py`
- `frontend/src/hooks/useCompareData.ts`
- `frontend/src/components/CompareView.tsx`

当前结果：

- 四步法历史结果能按步骤/子问题更稳定展示

### 8.3 七步/四步综述交互修复

改动目标：

- 修复 `AI 综述` 按钮不点亮
- 删除旧的跨层模式按钮
- 改成跨步骤累计选择

落点文件：

- `frontend/src/components/CompareView.tsx`
- `frontend/src/components/compare/SynthesisModal.tsx`

当前结果：

- 顶部显示已选问题数
- 支持“全部取消”
- 综述启用条件更合理

### 8.4 注册页密码规则前置

改动目标：

- 前端直接提示并校验密码强度

落点文件：

- `frontend/src/RootApp.tsx`

当前结果：

- 注册页会明确提示：
  - 至少 8 位
  - 同时包含字母和数字

### 8.5 API Key 按账号隔离

改动目标：

- 避免新用户复用 `admin` 在本地浏览器中保存的 key

落点文件：

- `frontend/src/App.tsx`
- `frontend/src/components/CompareView.tsx`
- `frontend/src/components/compare/SynthesisModal.tsx`

当前结果：

- API Key 现在按 `用户名` 存储
- 不同账号互不继承本地 key

### 8.6 任务队列管理器

改动目标：

- 当系统繁忙时，让用户看到排队位置和预估等待时间，而不是直接拒绝

落点文件：

- `backend/services/queue_manager.py`（新建）
- `backend/tests/test_queue_manager.py`（新建，30 个用例）

当前结果：

- `TaskQueueManager` 支持入队/出队、运行状态跟踪、排队位置查询
- 预估等待时间基于历史平均耗时的移动平均
- 支持 quant/qual/long/reference/filter 五种任务类型
- 全部 30 个单元测试通过（`.\venv\Scripts\python.exe -m unittest backend.tests.test_queue_manager`）

### 8.7 文献库增强：期刊显示、评分排序、MD 精读

改动目标：

- 文献库列表卡片显示期刊名称和筛选评分
- 支持按筛选评分、年份、期刊、更新时间排序
- 精读入口支持直接上传 Markdown 文件

落点文件：

- `backend/routers/library.py`（列表接口增加 filter_score 字段和排序参数）
- `backend/routers/reading.py`（新增 `extract_paper_text` 函数，MD 文件直接读取文本）
- `frontend/src/LibraryTab.tsx`（卡片增加期刊/评分显示，增加排序控件）
- `frontend/src/App.tsx`（精读入口 accept 改为 .pdf,.md,.markdown）

当前结果：

- 文献库列表卡片显示 `作者 · 年份 · 期刊` 和评分徽章
- 排序支持 updated/score/year/journal + 升降序
- 精读三种模式均支持上传 PDF 和 Markdown

### 8.8 Markdown 参考文献梳理支持

改动目标：

- 让参考文献梳理功能不仅支持 PDF，也支持 Markdown 文件

落点文件：

- `backend/services/deepseek_refs.py`（新增 `extract_candidate_text_md`、`extract_body_text_md`，`extract_references_deepseek` / `trace_citations_deepseek` 自动根据后缀选择提取逻辑）
- `backend/routers/references.py`（`get_owned_entry_with_pdf` → `get_owned_entry_with_file`，所有查询条件放宽为 `file_type.in_(["pdf", "markdown"])`）

当前结果：

- 上传 `.md`/`.markdown` 文件并绑定 BibEntry 后，参考文献梳理页面可正常识别和梳理
- 修复了残留的旧函数名引用导致的 500 错误

### 8.9 题录解析增强与反向匹配

改动目标：

- CNKI Parser 补全 DOI、Keywords、Volume、Issue、Pages、ISSN、URL 等被丢弃的字段
- CNKI Parser 支持多行值续行（超长摘要场景）
- WoS Parser 新增 Keywords（DE+ID 合并）、Volume(VL)、Issue(IS)、Pages(BP-EP)、ISSN(SN)、Language(LA) 字段
- BibEntry 模型新增 `volume`、`issue`、`pages` 三个字段
- 筛选入库时执行反向匹配：将 CNKI/WoS 题录自动关联用户已上传的 PDF/MD 文件
- 修复 `apply_match` 空壳端点：实际执行在线匹配并补空字段

落点文件：

- `parsers.py`（CNKIParser 重写 + WoSParser to_dataframe 增强）
- `backend/db/models.py`（BibEntry 新增 volume/issue/pages）
- `backend/routers/filter.py`（新增 `reverse_match_to_existing_files()`、persist_filter_results 写入新字段）
- `backend/routers/library.py`（`apply_match` 从空壳改为实际匹配+补全逻辑）
- `backend/migrations/versions/006_add_bib_entry_volume_issue_pages.py`（新增 Alembic 迁移）

当前结果：

- CNKI 导出的 DOI 不再丢失（约 40% 条目恢复 DOI）
- Keywords、Volume、Issue、Pages 等元数据完整保留，可用于 AI 筛选和文献库展示
- 用户先上传 PDF 再导入题录时，系统自动合并为同一文献条目（DOI 精确匹配或标题相似度 ≥ 0.72）
- 文献库"匹配 → 应用匹配"端点可用，先本地库搜索再在线搜索，只补空字段不覆盖已有值，并自动更新 dedup_key 和 metadata_completeness

踩坑记录：

- **Edit 替换路由函数时连带删掉相邻路由**：用编辑工具替换 `apply_match` 函数体时，`oldString` 匹配范围包含了紧邻的 `match_online` 路由定义（从 `class ApplyMatchRequest` 到文件末尾），导致 `match_online` 被 `apply_match` 的新实现完全覆盖，运行时 404。**教训：编辑 FastAPI router 文件时，替换完务必验证所有路由注册是否完整**，例如：`python -c "from routers.xxx import router; [print(r.path) for r in router.routes]"`
- **apply_match 不应重新搜索**：最初 `apply_match` 重新执行在线搜索重建候选列表，但前端展示的列表包含本地匹配结果（source=local），两份列表不一致导致索引越界（400 候选索引无效）。**教训：`apply_match` 应直接接收前端传来的完整候选数据，而非重新搜索**

### 8.10 用户数据导入导出

改动目标：

- 支持用户一键导出和导入全部数据（文献库、精读结果、源文件、提示词等）
- 解决普通用户 24h 数据过期无法恢复的问题
- 支持跨设备/跨实例迁移

落点文件：

- `backend/services/data_portability.py`（新建，核心导出/导入逻辑）
- `backend/routers/data.py`（新建，API 路由）
- `frontend/src/App.tsx`（添加导出/导入 UI 和事件处理）

关键实现细节：

- 导出格式：`.dra`（zip 包），内含 `manifest.json` + `data/*.json` + `files/` + `artifacts/`
- 导入策略：**清空所有数据后导入**（避免 UUID 主键冲突）
- 事务管理：所有数据库操作在一个事务内完成，文件恢复在事务提交后进行
- 序列化：datetime → ISO8601，owner_user_id → 替换为当前用户 ID，expires_at → 根据当前角色重算
- 错误处理：添加详细日志记录（`logger.info/error`），前端捕获非 JSON 响应

踩坑记录：

- **事务关闭错误**：最初使用 `async with db.begin_nested()` 嵌套事务，但 `_clear_user_data()` 内部调用了 `db.commit()`，导致事务提前关闭。解决方案：去掉嵌套事务，由调用方统一控制 `db.commit()`
- **跨用户 UUID 冲突**：导入时 `_clear_user_data()` 仅删除当前用户的数据，但导出文件可能来自其他用户（如 admin 导出后用普通用户导入），UUID PK 全局冲突。实测 100% overlap（files 17/17、bib_entries 367/367）。解决方案：`_pre_delete_conflicts()` 按 PK 直接删除，不区分 owner_user_id
- **UniqueConstraint 冲突**：`bib_filter_links` 有 auto PK 但 `UNIQUE(bib_entry_id, filter_job_id)`，auto PK 跳过 PK 删除后 unique 约束仍然冲突。解决方案：`_pre_delete_conflicts()` 第二层按 UniqueConstraint 列组合批量 `DELETE WHERE OR`
- **Auto-PK 子表残留**：Artifact 无 UniqueConstraint，父表（jobs）被 PK 删除后子表行残留（SQLite 不强制 FK CASCADE），导致文件恢复查询 `scalar_one_or_none()` 报 `MultipleResultsFound`。解决方案：`_pre_delete_conflicts()` 第三层按 FK 列值批量删除
- **MissingGreenlet**：`db.flush()` 后访问 `user.id` 触发 lazy load，在 async session 中报 greenlet 错误。解决方案：flush 前保存 `uid = user.id; urole = user.role` 到局部变量
- **文件恢复时机**：最初在事务内查询 storage_path，但 commit 后 session 已关闭。解决方案：先收集所有恢复信息，再执行文件复制

### 8.11 维度模板市场（Phase 3）

改动目标：

- 在自定义维度（Phase 1/2）基础上，新增模板市场，让用户可以浏览预设模板、AI 生成模板、从文档导入维度、共享和删除维度集
- 修复 33 维度 bug：LLM meta-prompt 强制包含 13 个系统默认维度，导致用户自定义维度集无法独立生效

落点文件：

- `frontend/src/TemplateMarket.tsx`（新建，~750 行）— 模板市场组件，含列表/详情/AI 生成/文档导入 4 个面板，共享集展示、分享/删除按钮
- `frontend/src/App.tsx` — PromptsTab 增加子标签页（"提示词管理" / "模板市场"），LongTab 增加分组维度渲染
- `backend/routers/dimensions.py` — 从 12 个端点扩展到 22 个，Phase 3 新增 10 个：
  - `PATCH /sets/{set_id}/share` — 切换维度集共享状态
  - `GET /shared` — 列出其他用户的共享维度集
  - `POST /shared/{set_id}/import` — 导入他人共享的维度集
  - `POST /generate` — AI 从种子论文生成维度模板（预览）
  - `POST /generate/save` — 保存 AI 生成的模板
  - `POST /import/preview` — 预览文档导入的维度解析结果
  - `POST /import/confirm` — 确认文档导入
  - `POST /templates/{id}/import` — 导入系统预设模板
  - `GET /templates/{id}` — 获取预设模板详情
  - `GET /templates` — 列出所有预设模板
- `backend/services/ai_template_generator.py`（新建）— 调用 DeepSeek API 从种子论文生成分析维度
- `backend/services/document_parser.py`（新建）— 解析 TXT/MD/JSON 格式的维度定义文档
- `backend/db/models.py` — `DimensionSet` 新增 `is_shared` 字段和 `owner` relationship；`DimensionItem` 新增 `group_name` 字段
- `backend/template_seed.py` — 3 套预设模板定义（案例研究 12 维度、社会网络分析 12 维度、Ostrom 制度分析 20 维度）
- `backend/migrations/versions/009_add_dim_item_group_name.py` — dimension_items 表新增 group_name 列
- `backend/migrations/versions/010_add_dim_set_is_shared.py` — dimension_sets 表新增 is_shared 列

数据模型变更：

- `dimension_sets` 表：新增 `is_shared` INTEGER 列（默认 0）
- `dimension_items` 表：新增 `group_name` TEXT 列（nullable）
- `dimension_templates` 表：系统预设模板（Phase 2 migration 008 已创建）
- `template_items` 表：预设模板的维度条目（Phase 2 migration 008 已创建）

Bug 修复：

- **33 维度 bug**：精读 LLM meta-prompt 在用户选择自定义维度集时，仍强制追加 13 个系统默认维度，导致实际分析维度远超预期。修复后 meta-prompt 仅包含用户选定的维度集内容

当前结果：

- PromptsTab 内含"提示词管理"和"模板市场"两个子标签页
- 用户可浏览 3 套预设模板并一键导入
- 用户可上传种子论文让 AI 生成分析维度
- 用户可从 TXT/MD/JSON 文件导入维度定义
- 用户可将自建维度集共享到模板市场，其他用户可一键导入
- LongTab 精读结果按 group_name 分组渲染维度
- 自定义维度集不再被强制追加系统默认维度

### 8.12 对比综述页面 v2.0 Redesign Demo（历史记录）

改动目标：

- 对三个对比页面（长文本/四步/七步）进行视觉和交互的彻底重构，打造学术优雅、现代精致的文献对比工作台
- 曾设计独立于主应用的 demo 后端服务，使用静态 JSON 数据驱动，不依赖生产数据库
- 建立完整的设计规范文档（色彩/字体/布局/组件/动画/Markdown 渲染），供后续正式实现参考

设计规范文档：

- `docs/compare-design-spec.md` — v2.0 完整设计方案，包含：
  - 色彩系统（温暖米白底色 + 深墨绿强调色）
  - 字体系统（衬线标题 + 无衬线正文 + 等宽代码）
  - 间距/圆角/阴影系统
  - 组件规范（标题区、文献选择区、步骤导航、操作栏、维度折叠面板、论文回答卡片）
  - Markdown + KaTeX 渲染规范（含表格样式）
  - 动画微交互规范
  - 编码规范（UTF-8 强制要求）

Demo 数据文件（仅作设计样例/回归参考，不进入前端打包）：

- `docs/compare-long-demo-data.json` — 长文本精读，3 篇文献（土地整治、AI企业生产率、电子支付），每篇含 10 个分析维度
- `docs/compare-qual-demo-data.json` — 四步精读，2 篇文献（土地整治、生态颜值），4 个步骤共 20+ 子问题
- `docs/compare-quant-demo-data.json` — 七步精读，3 篇文献（土地整治、生态产品、灌溉公地），7 个步骤共 27+ 子问题

历史落点文件：

- `backend/compare_demo_server.py` — 已移除
- `frontend/public/compare_long.html` — 已移除
- `frontend/public/compare_4step.html` — 已移除
- `frontend/public/compare_7step.html` — 已移除
- `frontend/public/compare_index.html` — 已移除
- `docs/compare-design-spec.md` — v2.0 设计规范
- `docs/compare-long-demo-data.json` / `compare-qual-demo-data.json` / `compare-quant-demo-data.json`

v2 页面核心架构（与 v1 对比）：

| 维度 | v1（旧 compare） | v2（redesign demo） |
|------|-------------------|---------------------|
| 数据来源 | 生产 API（需登录+API Key） | 静态 JSON 文件（独立服务） |
| 配色 | 基础白色/蓝色 | 温暖米白 + 深墨绿学术配色 |
| 字体 | 系统默认 | Noto Serif SC 标题 + Noto Sans SC 正文 |
| 布局 | 步骤切换重载整个列表 | 固定导航 + 纵向维度列表 + 横向卡片滚动 |
| 折叠 | 无 | 手风琴折叠面板（350ms 动画） |
| 文献选择 | 简单列表 | 卡片式选择（绿色边框+脉冲动画） |
| 步骤导航 | 下拉菜单 | 胶囊标签横向滚动 |
| 卡片设计 | 基础表格 | 精致卡片（悬停抬升、阴影层次） |
| 公式 | 无 | KaTeX 完整支持 |
| 表格 | 基础 | 学术优雅风格（横向滚动包装） |
| 动画 | 无 | fadeInUp 进场 + 选中脉冲 + 展开过渡 |

三种数据结构的页面适配：

1. **长文本（long）**：`papers[].dimensions[]` — 扁平维度列表，无步骤分组。导航标签 = 所有维度的 label 集合
2. **四步（qual）**：`papers[].steps[stepName].subQuestions[]` — 4 步分组，每步含多个子问题。导航标签 = 4 个步骤名
3. **七步（quant）**：`papers[].steps[stepName].subQuestions[]` — 7 步分组，每步含多个子问题。导航标签 = 7 个步骤名（缩短显示）

交互逻辑：

- 文献选择：卡片点击 toggle，≥2 篇才能触发 AI 综述
- 步骤/维度导航：胶囊标签切换，"全部"显示所有
- 折叠面板：点击展开/收起，默认全部折叠
- 复选框：子问题级别的选择，跨步骤持久化
- 全选/清空：作用于当前可见的子问题集合
- AI 综述按钮：≥2 文献 + ≥1 子问题选中时可用

当前状态：

- **v2.0 React 组件已正式集成到主应用**（2026-05-14），替换了 iframe 承载方案
- 三个对比 Tab 均使用 `CompareView` 组件，从生产 API 加载真实精读数据
- AI 综述通过 `SynthesisModal` 组件调用 SSE 流式端点
- 旧 demo HTML 与 8001 demo 后端已从代码树移除，避免混入 `frontend/dist` 和 PyInstaller 包

### 8.13 AI 文献综述模块

改动目标：

- 新增独立的 AI 文献综述端点，使用 deepseek-v4-flash 按维度串行生成高质量综述
- 支持二次引用（利用已提取的 BibReference 数据）和 GB/T 7714 参考文献目录
- 前端通过 `SynthesisModal` 调用新端点，不破坏旧对比功能
- SSE 流式返回，每维度生成后立即推送，避免多维度长耗时超时
- 二次引用过滤改用 DeepSeek 识别正文实际引用的文献，避免参考文献目录膨胀

落点文件：

- `backend/routers/compare.py`（新增约 500 行：请求模型、辅助函数、SSE 端点、二次引用过滤）
- `frontend/src/components/compare/SynthesisModal.tsx`（选择维度/步骤并展示 SSE 输出）
- `frontend/src/hooks/useSynthesisStream.ts`（SSE 流式读取）
- `frontend/vite.config.ts`（Vite proxy timeout 从 60s 调至 600s）

新增/修改函数：

- `SynthesisDimensionRequest` / `SynthesisLongRequest` — 请求体模型
- `gather_bib_references()` — 从 BibReference 收集二次引用数据（含 volume/issue/pages/doi）
- `format_cite_tag()` — 引用标注格式化（中文间注法，None 年份兜底"年份不详"）
- `_safe_year()` — year 值安全转换：None → "年份不详"
- `build_paper_metadata_block()` — 文献元数据+二次引用信息块
- `build_synthesis_dimension_prompt()` — 单维度综述 prompt（无字符截断）
- `_match_dimension_content()` — 维度内容匹配（精确→去前缀→模糊→兜底）
- `_collect_flat_secondary_refs()` — 将 bib_refs 展平为编号列表
- `_build_secondary_ref_check_prompt()` — 构建让 DeepSeek 识别二次引用的 prompt
- `_parse_cited_ref_ids()` — 解析 DeepSeek 返回的引用编号
- `_filter_bib_refs_by_indices()` — 按编号过滤 bib_refs
- `build_gbt7714_references()` — GB/T 7714 参考文献目录（主要+二次，条目间空行）
- `persist_synthesis_result()` — 保存 synthesis_md 产物（文件名 `综述-YYYYMMDD-作者姓.md`）
- `POST /synthesis` — 七步/四步 AI 综述端点（SSE StreamingResponse）
- `POST /synthesis_long` — 长文本 AI 综述端点（SSE StreamingResponse）

设计文档：

- `docs/superpowers/specs/2026-05-10-ai-synthesis-design.md`
- `docs/superpowers/plans/2026-05-10-ai-synthesis.md`
- `docs/superpowers/plans/2026-05-11-synthesis-secondary-ref-filter.md`

踩坑记录：

- **模型选择**：最初计划用 `deepseek-reasoner`（thinking 模式），但实测与 `deepseek-v4-flash` 相比耗时接近（25s vs 28s）、质量差异不大，而 reasoner 额外消耗 thinking tokens 且多维度串行时易超时。最终改用 `deepseek-v4-flash`
- **"Failed to fetch"**：Vite proxy timeout 默认 60s，reasoner 多维度串行调用容易超时。改用 flash 后单维度 ~25s，但仍可能 10+ 维度超时，最终改为 SSE 流式返回 + proxy timeout 600s
- **None 年份穿透**：`dict.get('year', 'n.d.')` 当值为 None 时返回 None 而非默认值，输出 `佚名 (None). 标题`。用 `_safe_year()` 统一处理
- **二次引用膨胀**：`build_gbt7714_references()` 将所有 BibReference 都列入二次引用目录。改用 DeepSeek 识别正文实际引用的文献（temperature=0.1, max_tokens=500），复用 system prompt + metadata_block 前缀保持缓存命中
- **维度内容截断**：原 `CONTENT_CHAR_LIMIT = 3000` 截断维度文本，DeepSeek 支持百万上下文无此必要，已移除
- **OpenAI client 超时**：`compare.py`（5处）和 `conversation_engine.py`（1处）统一设 `timeout=300s`；其余服务（`deepseek_refs.py`、`pdf_metadata_llm.py`、`ai_template_generator.py`、`metadata_extractor.py`）设 `connect=30s, read=120s, write=30s, pool=30s`，`deepseek_refs.py` 的重试循环额外捕获 `APITimeoutError`/`ConnectTimeout` 以触发重试而非直接失败

当前结果：

- 三个 compare 页面的「AI 综述」按钮调用新端点，SSE 逐维度流式显示
- 综述输出按维度分节，含 GB/T 7714 参考文献目录和二次引用（仅正文引用过的）
- 二次引用过滤由 DeepSeek 识别，非正则匹配
- None 年份统一显示为"年份不详"
- 产物文件名格式 `综述-YYYYMMDD-作者姓.md`
- 旧的「对比分析」按钮和 `/analyze`、`/analyze_long` 端点完全不受影响

### 8.14 精读后检查与自动重试

改动目标：

- 三种精读模式（长文本/七步/四步）完成后，在生成报告和元数据提取之前，自动检查每个维度/步骤的结果是否为空
- 空结果判定：空字符串、`[分析出错...]` 错误占位、少于 50 字符且无中文标点的疑似无意义内容
- 对空维度最多重试 2 次，复用已有的 `ConversationEngine` 实例重新调用 DeepSeek
- 重试失败不阻塞主流程，通过任务日志告知用户哪些维度重试失败

落点文件：

- `backend/routers/reading.py`（新增 `_is_empty_result`、`_check_and_retry_empty_dimensions` 辅助函数，三个 `run_*_task` 函数各插入后检查调用）

新增函数：

- `_is_empty_result(content, min_chars=50)` — 检测结果是否为空或错误占位
- `_check_and_retry_empty_dimensions(results, task_id, retry_fn, max_retries=2)` — 通用后检查+重试函数

插入位置：

- `run_long_context_task`：自定义问题处理之后、生成报告之前；支持内置维度、自定义维度集、自定义问题三种重试路径
- `run_quant_task`：七步循环之后、生成报告之前；通过 `QUANT_PROMPT_KEYS` 找回 prompt_key
- `run_qual_task`：四步循环之后、生成报告之前；通过 `QUAL_PROMPT_KEYS` 找回 prompt_key

当前结果：

- 精读完成后自动检测空维度并重试，最多 2 次
- 重试过程通过 `tasks[task_id]` 日志实时推送，用户可在前端看到「后检查」和「重试」日志
- 所有维度检查通过时日志显示「✓ [后检查] 所有维度检查通过」
- 重试失败不阻塞，任务仍正常完成

### 8.15 对比综述 Demo → 生产集成（React 组件替换 iframe）

改动目标：

- 将三个对比 Tab 从 iframe 承载 `compare_*.html` 迁移为 React 组件 `CompareView`
- 从生产 API 加载真实精读数据，不再依赖 demo JSON
- AI 综述通过 `SynthesisModal` 调用 SSE 流式端点

落点文件：

- `frontend/src/components/CompareView.tsx` — 对比综述主组件（新建）
- `frontend/src/components/compare/AnswerCard.tsx` — 答案卡片（预览/完整两种模式）
- `frontend/src/components/compare/AccordionPanel.tsx` — 维度折叠面板（三级展开 + 维度级模式按钮）
- `frontend/src/components/compare/PaperSelector.tsx` — 文献选择卡片
- `frontend/src/components/compare/DimNavigation.tsx` — 维度/步骤导航胶囊
- `frontend/src/components/compare/SynthesisModal.tsx` — AI 综述弹窗
- `frontend/src/components/compare/compare.css` — 对比页独立样式（限定 `.compare-root` 作用域）
- `frontend/src/hooks/useCompareData.ts` — 对比数据加载 Hook
- `frontend/src/hooks/useSynthesisStream.ts` — AI 综述 SSE 流式 Hook
- `frontend/src/App.tsx` — 替换 CompareTab iframe 为 CompareView 组件
- `backend/routers/compare.py` — 新增 `GET /reading-data` 和 `POST /synthesis-stream`

踩坑记录：

- **CSS 全局选择器污染**（2026-05-14）：`compare.css` 中的 `*, *::before, *::after { margin: 0; padding: 0; }` 全局 reset 和 `:root` CSS 变量声明在 Vite 打包后对整个应用生效，清零了 Tailwind 的排版样式（标题、段落、按钮间距全部消失），导致所有页面排版崩溃。修复方案：所有样式用 `.compare-root` 顶层 class 包裹限定作用域，keyframes 加 `compare-` 前缀避免冲突。**以后新增独立 CSS 文件必须遵守此规则**（已写入 AGENTS.md）。
- **iframe 全屏布局遗留**（2026-05-14）：原 `CompareTab` 使用 iframe 时，App.tsx 对比 Tab 用 `h-screen overflow-hidden` 锁定视口（iframe 内部自行滚动）。迁移为 React 组件后未移除此约束，导致对比页内容超出一屏无法下拉。修复：移除 `isCompareTab` 的特殊布局分支，统一使用 `min-h-screen` 正常滚动。**教训：从 iframe 迁移为 React 组件时，必须同步清理父容器的溢出控制**。
- **React Hooks 位置违规导致白屏**（2026-05-14）：`TemplateMarket.tsx` 中 `useState(exampleTab)` 和 `useState(copied)` 放在了两个 early return（detail 面板、AI 面板）之后。当用户点击「AI 生成专属模板」时 `panel === 'ai'` 触发第 482 行提前返回，后面的 hooks 不会被调用，违反 React「所有 hooks 必须在 early return 之前」的规则，导致 React 崩溃渲染白屏。修复：将这两个 `useState` 移到组件顶部与其他 hooks 并列。**教训：React hooks 声明顺序必须与渲染路径无关，新增 hooks 时务必放在所有 early return 之前**。
- **长文本对比维度集合名称匹配**（2026-05-14）：对比页胶囊需按维度集合名称分组显示（如「Ostrom制度分析框架」「地理学综述类论文理论建构与批判分析框架」），但 `ReadingItem.item_key`（`long.行动情境的边界界定`）和 `DimensionItem.dim_key`（`action_arena_boundary`）是两套完全不同的 key 体系，通过 key 无法直接 join。**正确匹配方式**：用 `ReadingItem.item_label`（中文维度名，如「行动情境的边界界定」）与 `DimensionItem.dim_name` 匹配，再通过 `set_id` 关联 `DimensionSet.name` 获取集合名称。注意同一个 `dim_name` 可能出现在多个维度集中，取首次出现即可（同一用户不会在不同集合中重复定义同名维度）。**教训**：系统中存在三套维度标识体系（`item_key`/`dim_key`/中文名），跨表关联时务必先确认实际数据格式，不能假设 key 可直接对应。

### 8.16 DeepSeek API 全局超时治理

改动目标：

- 修复长文本精读后自动提取参考文献时，`OpenAI()` 客户端默认 connect 超时 5s，走代理 SSL 握手超时直接失败的问题
- 统一所有调用 DeepSeek API 的入口的超时配置

落点文件：

- `backend/services/deepseek_refs.py` — 添加 `httpx.Timeout(connect=30, read=120, write=30, pool=30)`，重试循环捕获 `APITimeoutError`/`ConnectTimeout`
- `backend/services/pdf_metadata_llm.py` — 添加同等超时配置
- `backend/services/ai_template_generator.py` — 添加同等超时配置
- `backend/routers/metadata_extractor.py` — 添加同等超时配置

已验证无需改动的文件：

- `backend/routers/compare.py`（5 处）— 已有 `timeout=300`
- `new_architecture/conversation_engine.py`（1 处）— 已有 `timeout=300`

踩坑记录：

- **默认超时过短**（2026-05-14）：`OpenAI()` 不传 `timeout` 时 httpx 默认 connect 5s，走 HTTP 代理做 TLS 握手时容易超时。`deepseek_refs.py` 的重试循环只处理空响应，不捕获超时异常，导致超时直接穿透到 `_try_extract_references` 被外层 `except Exception` 吞掉并静默失败。**教训：所有 OpenAI 客户端必须显式设置超时，重试循环必须捕获超时异常**。

### 8.17 对比综述维度级模式按钮

改动目标：

- 在对比综述的每个维度 accordion header 右侧新增三按钮（编辑/点评/AI总结），点击后该维度所有卡片同时切换到对应显示模式
- 移除原有的 `activeModeCard` 单卡活跃限制，允许同一维度内多张卡片同时处于非 normal 模式
- 每张卡片的实际操作（保存编辑、创建点评、触发AI总结）仍为独立单卡行为

落点文件：

- `frontend/src/components/compare/AccordionPanel.tsx` — 移除 `activeModeCard`，新增 `handleDimModeChange` + `dimMode` 计算，header 增加维度级按钮
- `frontend/src/components/compare/compare.css` — 新增 `.compare-dim-mode-buttons` / `.compare-dim-mode-btn` 样式

设计文档：`docs/2026-05-17-dimension-mode-buttons-design.md`

### 8.18 PyInstaller 打包后提示词路径修复

改动目标：

- 修复打包版所有提示词回退到 `get_builtin_fallback()` 简短兜底文本的问题（如"请直接输出分析内容，不要客套开场白"），导致打包版精读质量与 dev 版差距巨大

根因：

- PyInstaller 打包后 `Path(__file__).resolve().parents[N]` 不再指向项目根目录，而是指向 exe 所在目录的上级。`prompt_registry.py` 用 `PROJECT_ROOT / "prompts/..."` 查找提示词文件时找不到，全部回退到代码内硬编码的简短兜底文本
- `build_web_dist.py` 通过 `--add-data=prompts;prompts` 将提示词 md 文件打包到了 `_internal/prompts/`，而 `sys._MEIPASS` 正好指向 `_internal/`

落点文件：

- `backend/prompt_registry.py` — `PROJECT_ROOT` 在 `sys.frozen` 时改用 `Path(sys._MEIPASS)`
- `backend/db/session.py` — 同上，`PROJECT_ROOT` 在 `sys.frozen` 时改用 `Path(sys._MEIPASS)`
- `new_architecture/conversation_engine.py` — `_load_dimension_prompt()` 中 `base_dir` 在 `sys.frozen` 时改用 `Path(sys._MEIPASS)`

踩坑记录：

- **`__file__` 路径在 frozen 环境不可靠**（2026-05-18）：PyInstaller onedir 模式下，`_internal/backend/prompt_registry.py` 的 `parents[1]` 会解析到 `_internal` 的父级（exe 所在目录），而 `prompts/` 在 `_internal/prompts/` 中。正确做法是用 `sys._MEIPASS` 获取 PyInstaller 解压的临时目录。**教训：任何通过 `__file__` 计算 `PROJECT_ROOT` 的代码，打包后都必须用 `sys._MEIPASS` 替代，并加 `getattr(sys, "frozen", False)` 分支判断**

### 8.19 打包版产物路径、引用详情与模板生成修复

改动目标：

- 修复 Windows 打包版中筛选报告、精读结果、对比综述、参考文献梳理等产物无法查看/下载的问题
- 修复参考文献梳理页“正文引用详情”只显示短引用标记，缺少完整句子和前后文的问题
- 修复模板市场 AI 生成专属模板时重新生成命中旧缓存、20 维度生成 JSON 被截断报错的问题

根因：

- 打包版运行时的结果文件根目录与开发环境不同，历史代码在多个 router 中直接按 `Artifact.file_path` 或当前工作目录拼路径，导致 frozen 环境下找不到真实产物
- 引用追踪中 DeepSeek 返回的 `quote` 容易只是“作者（年份）”短标记；后端此前直接展示或精确查找该短标记，无法稳定还原完整引用句
- 模板生成缓存 key 只取论文前 1000 字，未包含用户和维度数；同一论文从 8/12/16 改到 20 维度仍可能返回旧结果
- 模板生成固定 `max_tokens=4000`，20 维度时模型输出常在 JSON 中途被截断，引发 `JSON解析失败`

落点文件：

- `backend/result_storage.py`（新建）— 统一 `RESULTS_ROOT_DIR` / `RESULTS_DIR` / 默认结果目录解析，提供 `build_result_storage_path()` 与 `resolve_result_path()`
- `backend/routers/download.py`、`filter.py`、`reading.py`、`compare.py`、`references.py`、`history.py`、`library.py` — 产物写入与读取改用统一路径解析
- `frontend/src/App.tsx` — 批量精读下载入口改为鉴权下载，避免直接 `<a href="/api/download/...">` 丢 token
- `backend/services/deepseek_refs.py` — 引用 `quote` 改作定位锚点，新增归一化匹配、作者年份模糊匹配、完整句+前后句上下文抽取、文末参考文献条目误命中过滤
- `frontend/src/ReferenceTraceTab.tsx` — 正文引用详情优先展示 `excerpt`，短 `quote_text` 仅作为命中标记
- `backend/services/ai_template_generator.py` — 根据维度数动态提高 token 预算，20 维度最高使用 12000，并在截断时重试；解析失败时尝试 `json_repair`
- `backend/routers/dimensions.py` — 模板生成缓存 key 纳入用户、维度数和论文文本，新增 `force_regenerate` 表单参数覆盖缓存
- `frontend/src/TemplateMarket.tsx` — “重新生成”清空旧结果并传 `force_regenerate=true`

验证：

- `python -m py_compile` 覆盖相关后端模块
- `frontend npm run build` 通过
- `python build_web_dist.py` 已重新生成 `dist/DeepReadingAgent-Web.zip`
- 使用用户提供的 Markdown 论文和 DeepSeek key 直跑 20 维度，返回完整 JSON，`dimensions=20`
- 使用同一论文抽样验证参考文献引用详情，能从短引用标记定位到正文完整句及前后文

踩坑记录：

- **打包版产物路径不能散落在各 router 中自行拼接**（2026-05-19）：开发环境的相对路径在 PyInstaller onedir 下很容易指向错误目录。后续凡是保存或读取 Artifact 文件，都应通过 `result_storage.py` 统一处理，并优先保存相对结果根目录的路径，保留旧绝对路径兼容
- **LLM 返回的引用标记不是展示文本**（2026-05-19）：`quote` 只能当定位锚点，用户真正需要的是命中句及上下文。引用追踪类功能应将“模型识别锚点”和“用户展示摘录”分开存放
- **高维模板生成要按输出规模配置 token**（2026-05-19）：维度数越多，JSON 输出越长；固定 4000 token 对 20 维度不够。缓存也必须包含影响输出的参数，否则“重新生成”会被旧结果吞掉

## 9. 改代码时的推荐查找路径

## 9.1 要改注册/登录/权限

先看：

- `frontend/src/RootApp.tsx`
- `frontend/src/store/auth.ts`
- `frontend/src/lib/api-fetch.ts`
- `backend/routers/auth.py`
- `backend/auth/`

## 9.2 要改上传、文件绑定、PDF 匹配

先看：

- `backend/routers/upload.py`
- `backend/db/utils.py`
- `backend/routers/reading.py`

## 9.3 要改题录筛选

先看：

- `backend/routers/filter.py`
- `frontend/src/App.tsx` 中的 `FilterTab`

## 9.4 要改长文本/七步/四步精读

先看：

- `backend/routers/reading.py`
- `new_architecture/conversation_engine.py`
- `frontend/src/App.tsx` 中的 `LongTab / QuantTab / QualTab`

## 9.5 要改对比分析

先看：

- `frontend/src/components/CompareView.tsx` — 对比综述主组件
- `frontend/src/components/compare/*.tsx` — 子组件（AnswerCard, AccordionPanel, PaperSelector, DimNavigation, SynthesisModal）
- `frontend/src/components/compare/compare.css` — 对比页样式
- `frontend/src/hooks/useCompareData.ts` — 数据加载 Hook
- `frontend/src/hooks/useSynthesisStream.ts` — AI 综述 SSE Hook
- `backend/routers/compare.py` — 生产 API（含 `/reading-data` 和 `/synthesis-stream`）
- `docs/compare-design-spec.md` — v2 设计规范
- `docs/COMPARE_DEMO_REFERENCE.md` — Demo 前后端技术参考

## 9.6 要改文献库

先看：

- `backend/routers/library.py`
- `frontend/src/LibraryTab.tsx`

## 9.7 要改提示词管理

先看：

- `backend/prompt_registry.py`
- `backend/prompt_service.py`
- `backend/routers/prompts.py`
- `frontend/src/App.tsx`

## 9.8 要改下载、预览、历史记录

先看：

- `backend/routers/download.py`
- `backend/routers/history.py`
- `frontend/src/lib/download.ts`
- `frontend/src/App.tsx` 中的 `HistoryTab`

## 9.9 要改数据导入导出

先看：

- `backend/routers/data.py`
- `backend/services/data_portability.py`
- `frontend/src/App.tsx` 中的导出/导入处理函数
- `docs/superpowers/specs/2026-05-06-user-data-export-import-design.md`

常见修改点：

- 新增表到导出范围 → 修改 `EXPORT_TABLE_ORDER` 和 `IMPORT_CLEAR_ORDER`
- 修改导入策略（如从"清空所有"改为"仅清空当前用户"）→ 修改 `_clear_user_data()`
- 修改事务行为 → 注意 `db.commit()` 的调用位置
- 新增字段序列化/反序列化逻辑 → 修改 `_serialize_value()` / `_deserialize_value()`

## 9.10 要改任务队列、并发控制、排队提醒

先看：

- `backend/services/queue_manager.py`
- `backend/tests/test_queue_manager.py`
- `docs/MIGRATION_PLAN_10PLUS_USERS.md` 第 1.3 节

## 9.11 要改维度模板市场

先看：

- `backend/routers/dimensions.py`（22 个端点，共享/导入/AI 生成/模板管理）
- `backend/services/ai_template_generator.py`（AI 生成模板逻辑）
- `backend/services/document_parser.py`（文档导入解析）
- `backend/template_seed.py`（预设模板定义）
- `backend/db/models.py`（DimensionSet / DimensionItem / DimensionTemplate 模型）
- `frontend/src/TemplateMarket.tsx`（模板市场组件）
- `frontend/src/App.tsx`（PromptsTab 子标签页、LongTab 分组渲染）

## 10. 当前仍在规划、未实施的能力

请结合以下文档继续看：

- [PENDING_PLANS.md](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/docs/PENDING_PLANS.md)
- [PDF_METADATA_MATCH_PLAN.md](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/docs/PDF_METADATA_MATCH_PLAN.md)
- [SYNTHESIS_PROMPT_PLAN.md](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/docs/SYNTHESIS_PROMPT_PLAN.md)
- [REFERENCE_CITATION_TAB_PLAN.md](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/docs/REFERENCE_CITATION_TAB_PLAN.md)

当前重点未实施项包括：

- PDF 元数据在线匹配增强
- 参考文献梳理标签页与引用关系入库
- ~~双栏 PDF 参考文献提取修复~~（已完成：pdfplumber + use_text_flow）
- 参考文献目录兜底修复
- 文献综述提示词纳入提示词管理
- 综述引用锚点强化

## 11. 阅读代码的推荐顺序

如果第一次系统性读当前项目，建议按下面顺序：

1. `docs/TECHNICAL_OVERVIEW.md`
2. `docs/DATABASE_SCHEMA.md`
3. `backend/db/models.py`
4. `backend/main.py`
5. `backend/routers/reading.py`
6. `backend/routers/compare.py`
7. `backend/prompt_service.py`
8. `backend/routers/library.py`
9. `frontend/src/RootApp.tsx`
10. `frontend/src/App.tsx`
11. `frontend/src/LibraryTab.tsx`
12. `frontend/src/components/CompareView.tsx` + `compare/` 子组件

## 12. 维护建议

### 12.1 新增功能时

优先判断它属于哪一层：

- 前端展示层
- 后端路由层
- 业务服务层
- 数据模型层

不要一上来把所有逻辑堆进单个 router。

### 12.2 新增数据库字段时

必须同步：

- `models.py`
- Alembic migration
- `DATABASE_SCHEMA.md`
- 必要时更新 `MULTIUSER_PROGRESS.md`

### 12.3 新增前端页面时

优先决定：

- 是放在 React 主工作台内（如 CompareView）
- 还是独立 HTML 页面（如 demo 页面）

同时同步更新：

- `frontend-design.md`
- `TECHNICAL_OVERVIEW.md`

### 12.4 修 bug 时

先确认问题属于哪一层：

- 数据不对
- API 不对
- 前端状态不对
- 页面展示不对

不要只看页面现象就直接改前端。

### 12.5 编辑 FastAPI router 文件时

**替换函数体后务必验证路由注册完整**。

FastAPI 的路由是按 `@router.get/post(...)` 装饰器的声明顺序注册的。用编辑工具替换某个函数时，如果 `oldString` 匹配范围过大，很容易把紧邻的另一个路由函数连带删掉——运行时不报错但该端点直接 404。

验证命令：

```bash
python -c "from backend.routers.xxx import router; [print(r.path) for r in router.routes]"
```

历史事故：

- 替换 `library.py` 中的 `apply_match` 函数时，`oldString` 从 `class ApplyMatchRequest` 匹配到了文件末尾，把 `match_online` 路由定义一起覆盖了，导致 `/entries/{id}/match-online` 返回 404

## 13. 本文档维护原则

后续每次出现以下情况时，建议同步更新本文件：

- 新增一个重要功能模块
- 数据模型发生明显变化
- 核心业务流改变
- 关键入口文件调整
- 某个近期修改需要长期记忆

如果只是小样式、小文案或临时实验，不必更新本文件。
