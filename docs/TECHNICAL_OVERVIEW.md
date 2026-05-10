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
- 结果保存为 Markdown
- 同时拆成结构化结果写入数据库

### 2.5 对比分析与综述

- 长文本对比
- 七步对比
- 四步对比
- 支持单问题、多问题、跨步骤综述
- 对比优先读取结构化精读结果

### 2.6 我的文献库

- 查看个人文献列表（显示期刊名称、筛选评分）
- 多维度排序（更新时间、筛选评分、年份、期刊）
- 查看和修改题录元数据
- 查看筛选评价
- 查看任务时间线与产物
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
- 前端统一管理 quant / qual / long / filter

### 2.8 维度模板市场

- 系统预设模板（案例研究 12 维度、社会网络分析 12 维度、Ostrom 制度分析 20 维度）
- 用户浏览预设模板并一键导入为自己的维度集
- AI 生成模板：上传种子论文，DeepSeek 自动生成分析维度
- 文档导入：从 TXT/MD/JSON 文件导入维度定义
- 共享功能：用户可将自建维度集分享到模板市场，其他用户看到后一键导入
- 删除功能：删除未使用的自定义维度集（后端检查使用状态）
- 维度分组显示：精读结果按 `group_name` 分组渲染

### 2.9 数据导入导出

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
- **精读过程中自动提取参考文献**（场景一实现）

关键函数：

- `start_long_context(...)`
- `start_quant(...)`
- `start_qual(...)`
  - 分别启动三类精读任务
- `run_long_task(...)`
- `run_quant_task(...)`
- `run_qual_task(...)`
  - 后台线程执行分析
  - 精读完成后自动调用 `_try_extract_references()` 提取参考文献
- `_try_extract_references(...)`
  - 调用 `services/deepseek_refs.py` 提取参考文献
  - 调用 `routers/references.py` 的 `write_trace_outputs()` 生成产物
  - 失败时不阻塞主精读流程
- `persist_reading_items(...)`
  - 将结构化结果写入 `reading_items`

关键数据流：

- 文件 -> `BibEntry`
- 创建 `Job(reading_*)`
- 绑定 `JobBibEntry(target)`
- 调用 `ConversationEngine`
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
  - 七步/四步对比综述
- `analyze_long_comparison(...)`
  - 长文本对比综述

当前注意点：

- 综述提示词目前仍主要由这里拼装
- 未来计划迁到 `synthesis` 提示词类型

## 5.9 文献库：`backend/routers/library.py`

文件：

- [library.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/library.py)

职责：

- 返回文献列表（含筛选评分，支持多维度排序）
- 返回单篇文献详情
- 更新文献元数据

关键函数：

- `list_entries(...)`
  - 文献库列表，支持 `sort_by`（updated/score/year/journal）和 `sort_order`（desc/asc）
  - 通过子查询关联 `bib_filter_links` 获取最高筛选评分 `filter_score`
- `get_entry_detail(...)`
  - 单篇详情
- `update_entry(...)`
  - 修改元数据
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

职责：

- 对受保护文件做鉴权下载

关键函数：

- `download_file(...)`

关键点：

- 不直接暴露物理路径
- 会校验当前用户是否有权访问该 Artifact

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

## 6.7 对比页承载

工作台内的对比页是通过 `iframe` 承载旧页面：

- [compare_long.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_long.html)
- [compare_7step.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_7step.html)
- [compare_4step.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_4step.html)

在 `App.tsx` 中的职责：

- 负责给这三个页面提供全屏容器
- 保证对比页不被普通页布局挤压

### 6.7.1 `compare_7step.html`

职责：

- 七步对比
- 支持跨步骤累计选题
- 生成 AI 综述

关键状态变量：

- `allReports`
  - 全部七步报告
- `selectedStep`
  - 当前查看的步骤
- `selectedPapers`
  - 当前勾选的文献
- `selectedSubQuestions`
  - 所有已选问题集合

关键函数：

- `loadReports()`
  - 加载可对比报告
- `renderComparisonTable()`
  - 渲染当前步骤表格
- `togglePaper(...)`
  - 勾选/取消文献
- `toggleSubQuestion(...)`
  - 勾选/取消单个问题
- `toggleAllSubQuestions(...)`
  - 当前步骤全选
- `clearAllSelectedQuestions()`
  - 全部取消
- `updateUI()`
  - 刷新表格、按钮和选择摘要
- `getCurrentApiKey()`
  - 按当前用户读取对应的 API Key

最近修改：

- 删除了旧的“跨步骤模式”按钮
- 改成真实的跨步骤累计选择
- `AI 综述` 按钮启用条件改为：
  - 至少 2 篇文献
  - 至少 1 个问题

### 6.7.2 `compare_4step.html`

职责：

- 四步对比
- 优先读取后端结构化结果
- 支持跨步骤累计选择与综述

关键状态变量与函数：

- 与 `compare_7step.html` 基本同构
- 额外重点在：
  - `getPaperSubQuestions(...)`
    - 优先从结构化接口返回的数据中取子问题

最近修改：

- 修复了旧四步法报告子问题读取不出来的问题
- 综述选择交互与七步法统一

### 6.7.3 `compare_long.html`

职责：

- 长文本多维度对比

关键状态变量：

- `allReports`
- `selectedDims`
- `selectedPapers`
- `allDimensions`

关键函数：

- `extractDimensions(...)`
  - 解析长文本维度
- `loadReports()`
  - 加载可对比报告
- `togglePaper(...)`
  - 勾选/取消文献
- `toggleDim(...)`
  - 勾选/取消维度
- `updateUI()`
  - 刷新按钮和对比区域
- `renderComparisonTable()`
  - 渲染维度对比表
- `getCurrentApiKey()`
  - 读取当前账号对应的 API Key

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
- `frontend/public/compare_4step.html`

当前结果：

- 四步法历史结果能按步骤/子问题更稳定展示

### 8.3 七步/四步综述交互修复

改动目标：

- 修复 `AI 综述` 按钮不点亮
- 删除旧的跨层模式按钮
- 改成跨步骤累计选择

落点文件：

- `frontend/public/compare_7step.html`
- `frontend/public/compare_4step.html`

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
- `frontend/public/compare_long.html`
- `frontend/public/compare_7step.html`
- `frontend/public/compare_4step.html`

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

- `backend/routers/compare.py`
- `frontend/public/compare_long.html`
- `frontend/public/compare_7step.html`
- `frontend/public/compare_4step.html`

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
12. `frontend/public/compare_*.html`

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

- 是放在 React 主工作台内
- 还是像 compare 一样暂时挂旧页面

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
