# 函数索引文档

> 目的：本文件用于做“按文件查函数”的维护索引。  
> 使用方式：
>
> - 想改某个模块时，先看对应文件章节；
> - 先找到关键函数，再回到代码文件里读实现；
> - 重点记录“函数负责什么”，不是逐行解释实现细节。

## 1. 使用说明

本文件不追求列出仓库里每一个函数，而是优先收录：

- 核心入口函数
- 关键业务函数
- 状态协调函数
- 最近几轮修改里变得重要的函数

如果后续新增重要模块，建议同步补到这里。

## 2. 后端函数索引

## 2.1 `backend/main.py`

文件：

- [main.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/main.py)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `lifespan(app)` | 应用启动/关闭生命周期，负责初始化数据库、补齐提示词、注册调度器 | 启动报错、初始化行为异常、想加全局启动逻辑 |
| `health_check()` | 健康检查接口 | 验证后端是否正常存活 |
| `app.include_router(...)` | 注册各业务路由 | 新增或排查某个 API 没挂上 |

## 2.2 `backend/db/session.py`

文件：

- [session.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/db/session.py)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `DATABASE_URL` | 当前数据库连接串 | 想确认当前连的是哪个库 |
| `engine` | SQLAlchemy 异步引擎 | 排查数据库连接或引擎配置问题 |
| `AsyncSessionLocal` | Session 工厂 | 想在后台任务或脚本里手动开会话 |
| `get_db()` | FastAPI 路由依赖，提供数据库会话 | 新增 router 或排查依赖注入问题 |

## 2.3 `backend/db/models.py`

文件：

- [models.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/db/models.py)

| 模型 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `User` | 用户、角色、保留期、token_version | 认证、角色、清理策略 |
| `PromptTemplate` | 系统默认 / 用户覆盖提示词 | 提示词管理与运行时解析 |
| `File` | 上传文件记录 | 上传、物理文件归属、去重 |
| `Job` | 统一任务记录 | 筛选、精读、对比、综述的任务状态 |
| `BibEntry` | 文献档案中心 | 文献库、筛选入库、精读/对比关联 |
| `BibFilterLink` | 筛选评价关系 | 文献库里看筛选得分和解释 |
| `JobBibEntry` | 任务与文献关系 | compare/synthesis/reading 成员关系 |
| `ReadingItem` | 结构化精读结果 | compare 结构化读取、文献库详情 |
| `Artifact` | 任务产物文件索引 | 下载、历史记录、时间线 |

## 2.4 `backend/routers/auth.py`

文件：

- [auth.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/auth.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `register(...)` | 注册用户 | 注册校验、邀请码、默认角色 |
| `login(...)` | 用户登录，签发 access/refresh token | 登录失败、token 返回异常 |
| `refresh_token(...)` | 刷新 access token | 自动登录态续期失败 |
| `me(...)` | 返回当前用户信息 | 前端用户信息、role、warning_msg 异常 |
| `change_password(...)` | 修改密码 | 密码校验、密码更新流程 |
| `logout(...)` | 通过 `token_version` 使旧 refresh token 失效 | 登出后旧 token 仍可续期 |

## 2.5 `backend/auth/security.py`

文件：

- [security.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/auth/security.py)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `verify_password(...)` | 校验明文密码和哈希值 | 登录或改密码校验异常 |
| `get_password_hash(...)` | 生成密码哈希 | 注册或修改密码 |
| `create_access_token(...)` | 生成 access token | JWT 载荷或过期时间调整 |
| `create_refresh_token(...)` | 生成 refresh token | refresh token 结构调整 |
| `decode_token(...)` | 解码 token | 鉴权、token_version 校验 |

## 2.6 `backend/auth/dependencies.py`

文件：

- [dependencies.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/auth/dependencies.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `current_user(...)` | 解析并返回当前登录用户 | 任何需要登录的接口 401/403 |
| `require_admin(...)` | 强制管理员权限 | 后台接口权限问题 |

## 2.7 `backend/routers/upload.py`

文件：

- [upload.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/upload.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `upload_file(...)` | 上传入口，写入文件记录并尝试匹配题录 | 上传失败、文件没入库、PDF 没绑定题录 |
| `get_file_info(...)` | 查询单个上传文件信息 | 前端展示文件状态不对 |
| `delete_file(...)` | 删除上传文件及记录 | 删除失败、权限问题 |

## 2.8 `backend/db/utils.py`

文件：

- [utils.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/db/utils.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `compute_dedup_key(...)` | 生成文献去重 key | 题录重复、compare 解析成员失败 |
| `normalize_title_for_match(...)` | 标题归一化 | PDF 文件名和题录标题匹配不稳定 |
| `title_match_score(...)` | 标题相似度评分 | 自动匹配质量调优 |

## 2.9 `parsers.py`（项目根目录）

文件：

- [parsers.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/parsers.py)

| 函数 / 类 | 作用 | 什么时候优先看 |
|---|---|---|
| `WoSParser.parse()` | 解析 WoS 纯文本格式，支持多行续行 | WoS 导入解析异常 |
| `WoSParser.to_dataframe()` | 将解析结果转为 DataFrame（含 Keywords/Volume/Issue/Pages/ISSN/Language） | WoS 字段映射不对 |
| `CNKIParser.parse()` | 解析 CNKI "Key-中文Key" 格式，支持多行值续行 | CNKI 导入解析异常 |
| `CNKIParser.to_dataframe()` | 将解析结果转为 DataFrame（含 DOI/Keywords/Volume/Issue/Pages/ISSN/URL） | CNKI 字段映射不对、DOI 丢失 |
| `get_parser(file_path)` | 工厂方法：根据文件内容自动检测格式并返回对应 Parser | 新增题录格式或格式检测异常 |

## 2.10 `backend/routers/filter.py`

文件：

- [filter.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/filter.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `start_filter(...)` | 启动筛选任务 | 点击开始筛选没反应、任务没创建 |
| `run_filter_task(...)` | 后台执行筛选、导出、持久化 | 筛选过程出错、日志不对、任务卡住 |
| `persist_filter_results(...)` | 将筛选结果写入 `BibEntry` / `BibFilterLink` / `Artifact`，含反向匹配 | 文献库中缺筛选信息、Excel 产物缺失 |
| `reverse_match_to_existing_files(...)` | 反向匹配：将新 BibEntry 与用户已上传的 PDF/MD 关联（DOI 精确匹配或标题 ≥ 0.72） | 题录导入后 PDF 未自动绑定 |
| `get_task_status(...)` | 返回筛选任务状态 | 前端进度条或轮询异常 |
| `cancel_task(...)` | 取消任务 | 任务无法取消 |

## 2.11 `backend/routers/reading.py`

文件：

- [reading.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/reading.py)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `LONG_DIMENSION_KEYS` | 长文本维度到提示词/结构化 key 的映射 | 长文本维度新增、结构化 key 调整 |
| `QUANT_STEP_KEYS` | 七步步骤 key 映射 | 七步结构化展示不对 |
| `QUAL_STEP_KEYS` | 四步步骤 key 映射 | 四步结构化展示不对 |
| `normalize_reading_prompt(...)` | 规范精读提示词内容，补禁客套要求 | 提示词输出风格异常 |
| `parse_markdown_numbered_sections(...)` | 将 Markdown 步骤内容拆成编号子问题 | 七步/四步子问题拆分不稳定 |
| `build_long_reading_items(...)` | 构造长文本 `ReadingItem` 列表 | 长文本结构化入库问题 |
| `build_step_reading_items(...)` | 构造七步/四步 `ReadingItem` 列表 | compare 结构化读取异常 |
| `get_file_record(...)` | 按用户和 `file_id` 取文件记录 | 精读启动找不到文件 |
| `ensure_readable_file_type(...)` | 限制精读仅支持 PDF/Markdown | 文件类型错误提示 |
| `get_or_create_bib_entry(...)` | 精读前为文件匹配或创建 `BibEntry` | 新 PDF 精读后没进文献库 |
| `persist_reading_items(...)` | 将结构化结果写入数据库 | `reading_items` 丢失或历史回填后显示异常 |
| `run_long_task(...)` | 后台执行长文本精读 | 长文本分析失败 |
| `run_quant_task(...)` | 后台执行七步精读 | 七步分析失败 |
| `run_qual_task(...)` | 后台执行四步精读 | 四步分析失败 |
| `_try_update_bib_metadata(...)` | 从前三页提取元数据并更新 `BibEntry`（只补空字段） | 精读后文献库元数据未更新 |
| `start_long_context(...)` | 启动长文本任务 | 前端开始长文本无响应 |
| `start_quant(...)` | 启动七步任务 | 前端开始七步无响应 |
| `start_qual(...)` | 启动四步任务 | 前端开始四步无响应 |
| `BatchReadingRequest` | 批量精读请求体（`file_ids`, `mode`, `api_key` 等） | 批量精读请求字段问题 |
| `start_batch_reading(...)` | 批量精读入口，循环创建 Job（共享 `batch_id`） | 批量精读全部启动失败 |
| `get_batch_status(...)` | 按 `batch_id` 聚合查询所有 job 状态 | 批量进度 404 / 状态不对 |

## 2.12 `backend/routers/compare.py`

文件：

- [compare.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/compare.py)

| 函数 / 类 | 作用 | 什么时候优先看 |
|---|---|---|
| `CompareRequest` | 七步/四步对比综述请求体 | 前后端请求字段不一致 |
| `LongCompareRequest` | 长文本对比请求体 | 长文本综述请求字段问题 |
| `StructuredStepResponse` | 结构化步骤响应模型 | 四步/七步结构化 API 响应调整 |
| `StructuredReadingResponse` | 单篇结构化精读响应模型 | compare 页结构化读取展示异常 |
| `get_api_key(...)` | 对比分析读取请求或环境变量中的 API Key | compare 生成综述时 key 处理 |
| `parse_paper_authors(...)` | 归一化作者列表 | compare 中作者匹配问题 |
| `bib_entry_to_paper_data(...)` | 从 `BibEntry` 构建 compare 基础数据 | compare 默认数据结构异常 |
| `build_structured_paper_data(...)` | 从 `ReadingItem` 聚合结构化 compare 数据 | compare 页面缺子问题/缺维度 |
| `resolve_compare_members(...)` | 将前端传入的文献解析成 `BibEntry` 成员列表 | compare 权限、成员匹配、至少两篇校验 |
| `create_compare_job(...)` | 创建 compare 任务和成员关系 | compare 任务记录异常 |
| `persist_compare_result(...)` | 保存 compare Markdown 产物 | compare 历史记录或下载异常 |
| `extract_step_id(...)` | 从结构化 key 中反推步骤 | 四步/七步结构化聚合异常 |
| `get_structured_reading(...)` | 返回某个精读任务的结构化结果 | 对比页结构化接口 |
| `analyze_comparison(...)` | 生成七步/四步对比综述 | 七步/四步综述生成问题 |
| `analyze_long_comparison(...)` | 生成长文本对比综述 | 长文本综述生成问题 |
| `SynthesisDimensionRequest` | 七步/四步 AI 综述请求体 | AI 综述请求字段问题 |
| `SynthesisLongRequest` | 长文本 AI 综述请求体 | 长文本 AI 综述请求问题 |
| `gather_bib_references(...)` | 从 BibReference 收集二次引用数据（含 volume/issue/pages/doi） | 二次引用缺失 |
| `format_cite_tag(...)` | 中文间注法引用标注格式化（None 年份兜底为"年份不详"） | 引用标注格式异常 |
| `_safe_year(...)` | year 值安全转换：None → "年份不详" | 年份显示 None |
| `build_paper_metadata_block(...)` | 构建文献元数据+二次引用信息块 | prompt 中元数据异常 |
| `build_synthesis_dimension_prompt(...)` | 单维度综述 prompt 构建（无字符截断） | 综述内容匹配不准 |
| `_match_dimension_content(...)` | 维度内容匹配（精确→去前缀→模糊→兜底） | 维度内容找不到 |
| `_collect_flat_secondary_refs(...)` | 将 bib_refs 展平为 [(member_id, ref)] 列表 | 二次引用过滤 |
| `_build_secondary_ref_check_prompt(...)` | 构建让 DeepSeek 识别正文中实际引用的二次文献的 prompt | 二次引用识别 |
| `_parse_cited_ref_ids(...)` | 解析 DeepSeek 返回的引用编号（S1,S3 等） | 二次引用编号解析 |
| `_filter_bib_refs_by_indices(...)` | 按编号过滤 bib_refs | 二次引用过滤结果 |
| `build_gbt7714_references(...)` | 生成 GB/T 7714 参考文献目录（主要+二次，条目间空行） | 参考文献格式问题 |
| `persist_synthesis_result(...)` | 保存 synthesis_md 产物 | 综述产物保存异常 |
| `synthesize_dimensions(...)` | `POST /synthesis` 七步/四步 AI 综述（SSE 流式返回） | AI 综述生成失败 |
| `synthesize_long_dimensions(...)` | `POST /synthesis_long` 长文本 AI 综述（SSE 流式返回） | 长文本 AI 综述失败 |

## 2.13 `backend/routers/library.py`

文件：

- [library.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/library.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `list_entries(...)` | 返回文献库列表 | 列表筛选、排序、搜索、期刊筛选问题 |
| `get_entry_detail(...)` | 返回单篇文献详情和时间线 | 文献详情、产物列表、筛选评价问题 |
| `update_entry(...)` | 更新文献元数据 | 文献库编辑保存问题 |
| `match_online(...)` | 对单篇文献执行在线元数据匹配 | 在线匹配失败、候选结果异常 |
| `apply_match(...)` | 应用候选元数据到文献（重新搜索 → 只补空字段 → 更新 dedup_key 和 metadata_completeness） | 应用匹配结果失败 |

## 2.13.1 `backend/services/pdf_metadata_extract.py`

文件：

- [pdf_metadata_extract.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/pdf_metadata_extract.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `extract_front_matter(pdf_path)` | 从 PDF 前 1-3 页提取文本和 DOI/ISBN | 元数据提取失败 |
| `extract_dois(text)` | 从文本中正则提取 DOI | DOI 提取不全或误提取 |
| `extract_isbns(text)` | 从文本中正则提取 ISBN | ISBN 提取问题 |
| `extract_page_header(page)` | 提取页面页眉区域 | 页眉提取不准确 |

## 2.13.2 `backend/services/pdf_metadata_llm.py`

文件：

- [pdf_metadata_llm.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/pdf_metadata_llm.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `extract_metadata_with_llm(front_matter, filename)` | 调用 DeepSeek 从 PDF 前三页抽取结构化元数据（含摘要、关键词） | LLM 抽取结果异常 |
| `_clean_metadata(data)` | 清洗和验证 LLM 返回的元数据（含 abstract/keywords） | 元数据字段格式问题 |
| `_empty_metadata()` | 返回空元数据字典（含 abstract/keywords 字段） | 新增字段默认值 |

## 2.13.3 `backend/services/metadata_sources.py`

文件：

- [metadata_sources.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/metadata_sources.py)

| 类 / 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `CandidateMetadata` | 候选元数据数据类 | 候选数据结构问题 |
| `MetadataSource` | 元数据源抽象基类 | 新增数据源时参考 |

## 2.13.4 `backend/services/crossref_source.py`

文件：

- [crossref_source.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/crossref_source.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `CrossrefSource.search_by_doi(doi)` | 通过 Crossref API 查询 DOI | Crossref 查询失败 |
| `CrossrefSource.search_by_metadata(title, authors, year)` | 通过标题/作者/年份搜索 | Crossref 搜索无结果 |

## 2.13.5 `backend/services/openalex_source.py`

文件：

- [openalex_source.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/openalex_source.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `OpenAlexSource.search_by_doi(doi)` | 通过 OpenAlex API 查询 DOI | OpenAlex 查询失败 |
| `OpenAlexSource.search_by_metadata(title, authors, year)` | 通过标题/作者/年份搜索 | OpenAlex 搜索无结果 |

## 2.13.6 `backend/services/metadata_match_service.py`

文件：

- [metadata_match_service.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/metadata_match_service.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `score_candidates(extracted, candidates)` | 对候选列表评分排序 | 评分逻辑问题 |
| `classify_confidence(score)` | 将分数分为 high/medium/low | 置信度阈值问题 |
| `apply_high_confidence_match(bib_entry, candidate)` | 高置信度自动补空字段 | 自动补全逻辑问题 |

## 2.13.7 `backend/db/utils.py` (新增函数)

文件：

- [utils.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/db/utils.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `compute_metadata_match_score(extracted, existing)` | 综合评分：DOI、标题、作者、年份、期刊 | 匹配分数计算问题 |
| `normalize_doi(value)` | DOI 标准化 | DOI 比对问题 |
| `_extract_surname(author_name)` | 提取作者姓氏 | 作者匹配问题 |

## 2.14 `backend/routers/history.py`

文件：

- [history.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/history.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `list_history(...)` | 列出阅读 / 筛选 / 对比历史 | 历史记录缺项 |
| `list_synthesis(...)` | 列出综述历史 | 综述记录缺项 |
| `preview_file(...)` | 鉴权预览历史文件 | 历史预览失败或未认证 |
| `save_synthesis(...)` | 将前端生成的综述保存为任务与产物 | 点击“保存到历史记录”无效 |
| `delete_file(...)` | 删除历史记录 | 删除失败或权限问题 |

## 2.15 `backend/routers/download.py`

文件：

- [download.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/download.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `download_file(...)` | 鉴权下载产物文件 | 下载返回 401/404/Not authenticated |

## 2.16 `backend/prompt_registry.py`

文件：

- [prompt_registry.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/prompt_registry.py)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `PromptSpec` | 单个提示词槽位定义 | 新增提示词类型或 key |
| `PROMPT_SPECS` | 所有固定槽位注册表 | 提示词管理页下拉选项、后端槽位映射 |
| `group_specs_by_type()` | 按类型整理槽位 | catalog 构建逻辑 |
| `get_prompt_spec(...)` | 获取某个提示词槽位定义 | 取单个槽位 |

## 2.16 `backend/prompt_service.py`

文件：

- [prompt_service.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/prompt_service.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `ensure_builtin_prompt_templates(...)` | 幂等导入系统默认提示词 | 启动后提示词全空 |
| `get_prompt_payload(...)` | 返回单个槽位的“生效内容 + 默认 + 覆盖 + 来源” | 提示词管理详情页异常 |
| `get_effective_prompt_map(...)` | 获取某类 prompt 的当前生效内容映射 | filter/reading 运行时取 prompt 问题 |
| `upsert_user_prompt(...)` | 保存用户覆盖提示词 | 普通用户保存失败 |
| `delete_user_prompt(...)` | 删除用户覆盖并恢复默认 | 点击恢复默认无效 |
| `upsert_system_prompt(...)` | 保存系统默认提示词 | admin 改系统默认无效 |

## 2.17 `backend/routers/prompts.py`

文件：

- [prompts.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/prompts.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `prompt_catalog(...)` | 返回提示词目录 | 提示词管理页类型/步骤下拉为空 |
| `get_prompt_item(...)` | 返回某个槽位详情 | 提示词详情显示 `Not Found` |
| `save_my_prompt(...)` | 保存个人覆盖 | 普通用户保存失败 |
| `reset_my_prompt(...)` | 删除个人覆盖 | 恢复默认失败 |
| `save_system_prompt(...)` | 保存系统默认 | 管理员保存失败 |
| `legacy_get_prompt(...)` | 兼容旧接口读取 | 旧链路兼容问题 |
| `legacy_set_prompt(...)` | 兼容旧接口写入 | 老页面或脚本兼容问题 |

## 2.18 `backend/cleanup.py`

文件：

- [cleanup.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/cleanup.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `reapply_user_retention(...)` | 重算用户保留期和过期时间 | 调整角色后过期策略不对 |
| `cleanup_expired(...)` | 清理过期文件、任务和产物 | normal 用户数据未按 24h 清理 |

## 2.19 `new_architecture/conversation_engine.py`

文件：

- [conversation_engine.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/new_architecture/conversation_engine.py)

| 函数 / 方法 | 作用 | 什么时候优先看 |
|---|---|---|
| `ConversationEngine.__init__(...)` | 初始化长上下文分析引擎 | 引擎配置问题 |
| `build_messages(...)` | 构造发给 DeepSeek 的消息列表 | 提示词拼接、缓存命中逻辑 |
| `ask(...)` | 执行单轮问答 | 七步/四步 prompt 问题 |
| `analyze_dimension(...)` | 执行长文本某维度分析 | 长文本输出异常 |

## 2.20 `backend/services/deepseek_refs.py`

文件：

- [deepseek_refs.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/deepseek_refs.py)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `extract_references_deepseek(pdf_path, api_key)` | 从 PDF 尾部提取参考文献（主入口） | 参考文献提取结果异常 |
| `trace_citations_deepseek(pdf_path, references, api_key)` | 追踪每条参考文献在正文中的引用位置 | 引用追踪结果异常 |
| `extract_candidate_text(pdf_path)` | 从 PDF 提取参考文献候选文本（双栏自动检测） | 候选文本为空或乱码 |
| `extract_body_text(pdf_path)` | 从 PDF 提取正文文本和段落信息（双栏自动检测） | 正文提取顺序异常 |
| `_is_two_column(chars)` | 通过字符 x0 分布判断是否为双栏布局 | 双栏检测不准确 |
| `_extract_page_text(page, force_text_flow)` | 统一页面文本提取（支持 use_text_flow） | 页面文本提取问题 |
| `call_deepseek_json(messages, **kwargs)` | 封装 DeepSeek API 调用（重试 + JSON 修复） | DeepSeek 返回异常 |

## 2.21 `backend/routers/references.py`

文件：

- [references.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/references.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `run_reference_trace_task(...)` | 后台执行参考文献梳理任务 | 参考文献任务异常 |
| `write_trace_outputs(...)` | 生成 Excel/MD/JSON 产物文件 | 产物生成异常 |
| `persist_trace_success(...)` | 将参考文献和引用写入数据库 | 数据库写入异常 |

## 2.22 `backend/services/data_portability.py`

文件：

- [data_portability.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/data_portability.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `export_user_data(db, user)` | 将用户全部数据打包为 `.dra` 文件 | 导出功能异常 |
| `import_user_data(db, user, dra_path)` | 从 `.dra` 文件恢复用户数据 | 导入功能异常 |
| `_clear_user_data(db, user_id)` | 按 FK 逆序删除用户关联数据 | 导入时清理不完整 |
| `_pre_delete_conflicts(db, model, records, ...)` | 三层冲突预删除（PK / UniqueConstraint / FK） | 导入 PK/unique 冲突 |
| `_deserialize_table(db, model, records, ...)` | 反序列化 JSON 并 INSERT 到数据库 | 导入数据格式问题 |
| `_serialize_table(db, model, user_id)` | 将表数据序列化为 JSON | 导出数据不全 |

## 2.23 `backend/routers/data.py`

文件：

- [data.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/data.py)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `export_data(user, db)` | GET /api/data/export 导出接口 | 导出 API 问题 |
| `import_data(file, user, db)` | POST /api/data/import 导入接口 | 导入 API 问题 |

## 2.24 `backend/routers/dimensions.py` (22 endpoints)

文件：

- [dimensions.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/routers/dimensions.py)

Key functions/endpoints:
| Function/Endpoint | Purpose | When to look |
|---|---|---|
| `list_sets` GET /sets | List user's dimension sets with item count | Set list display issues |
| `toggle_share` PATCH /sets/{id}/share | Toggle is_shared on a set | Share/unshare not working |
| `delete_set` DELETE /sets/{id} | Delete unused set (checks Job usage) | Delete fails or allows used set |
| `clone_set` POST /sets/{id}/clone | Clone a user set with all items | Clone issues |
| `list_shared` GET /shared | List other users' shared sets (with owner joined) | Shared list not showing |
| `import_shared` POST /shared/{id}/import | Import shared set (copies items with group_name) | Import shared fails |
| `import_template` POST /templates/{id}/import | Import preset template | Template import fails |
| `generate_template` POST /generate | AI generate dimensions from paper via DeepSeek | AI generation errors |
| `save_generated` POST /generate/save | Save AI-generated template as user set | Save fails |
| `preview_document_import` POST /import/preview | Parse TXT/MD/JSON dimension doc | Import preview issues |
| `confirm_document_import` POST /import/confirm | Save imported document dimensions | Import confirm fails |

## 2.25 `backend/services/ai_template_generator.py`

文件：

- [ai_template_generator.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/ai_template_generator.py)

| Function | Purpose | When to look |
|---|---|---|
| `generate_dimension_template(text, dim_count, api_key)` | Call DeepSeek to generate dimensions from paper text | AI generation returns bad results, meta-prompt tuning |

## 2.26 `backend/services/document_parser.py`

文件：

- [document_parser.py](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/backend/services/document_parser.py)

| Function | Purpose | When to look |
|---|---|---|
| `parse_dimension_document(content, filename)` | Parse TXT/MD/JSON files into dimension list | Document import parsing errors |
| `ParseError` | Custom exception for parse failures | Error handling |

## 3. 前端函数索引

## 3.1 `frontend/src/RootApp.tsx`

文件：

- [RootApp.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/RootApp.tsx)

| 组件 / 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `PASSWORD_RULE_TEXT` | 注册密码规则文案 | 想改密码规则提示 |
| `isStrongPassword(...)` | 前端密码强度校验 | 注册时前端校验问题 |
| `AuthLayout` | 登录/注册通用表单壳 | 登录注册 UI、错误提示、提交流程 |
| `buildWorkspaceRedirect(...)` | 依据登录态决定跳转 | 跳转逻辑不对 |
| `HomeRedirect` | 根路径跳转 | 首页重定向异常 |
| `ProtectedRoute` | 工作台登录保护 | 未登录仍可访问工作台 |
| `AdminRoute` | 后台权限保护 | 非 admin 进入后台 |
| `LoginPage` | 登录页逻辑 | 登录表单行为异常 |
| `RegisterPage` | 注册页逻辑 | 注册后自动登录/跳转异常 |
| `AppRoutes` | 全应用路由 | 路由映射问题 |

## 3.2 `frontend/src/store/auth.ts`

文件：

- [auth.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/store/auth.ts)

| 函数 / 状态 | 作用 | 什么时候优先看 |
|---|---|---|
| `parseJson(...)` | 统一解析接口返回和错误消息 | 前端报错文案异常 |
| `hydrate()` | 从本地恢复登录态 | 刷新后掉登录 |
| `setAccessToken(...)` | 单独更新 access token | refresh 后 token 不更新 |
| `setSession(...)` | 保存完整会话 | 登录后前端状态不对 |
| `clearSession()` | 清空会话 | 退出登录后仍残留状态 |
| `fetchMe()` | 获取当前用户信息 | 用户信息或 role 不刷新 |
| `login(...)` | 登录流程 | 登录异常 |
| `register(...)` | 注册流程 | 注册成功但自动登录失败 |
| `logout()` | 登出流程 | 切换账号或退出登录问题 |

## 3.3 `frontend/src/lib/api-fetch.ts`

文件：

- [api-fetch.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/lib/api-fetch.ts)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `refreshAccessToken()` | 调 refresh 接口换新 access token | 401 自动续期失败 |
| `redirectToLogin(...)` | 续期失败后回登录页 | 自动跳登录不对 |
| `apiFetch(...)` | 包装全局 fetch，自动加 token 和重试 | 所有鉴权接口统一入口 |
| `installGlobalAuthFetch()` | 安装全局 fetch 包装 | 应用启动后未走鉴权 fetch |

## 3.4 `frontend/src/App.tsx`

文件：

- [App.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/App.tsx)

### 3.4.1 壳层函数

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `TABS` | 工作台标签定义 | 调整标签顺序、名称、图标 |
| `getApiKeyStorageKey(...)` | 根据用户名生成本地 key 存储 key | API Key 隔离逻辑 |
| `getInitialTab(...)` | 根据路径和查询参数决定初始 tab | 路由/tab 同步问题 |
| `handleTabChange(...)` | 切换 tab 并同步 URL | 某个 tab 打不开 |
| `handleSaveKey()` | 保存当前账号的 API Key | API Key 保存问题 |
| `handleDeleteKey()` | 删除当前账号的 API Key | API Key 删除问题 |
| `handleLogout()` | 登出并跳登录页 | 顶部菜单退出逻辑 |

### 3.4.2 通用任务状态函数

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `getReadingTaskStorageKey(...)` | 生成本地持久化任务 key | 精读切 tab 后进度恢复 |
| `persistReadingTaskId(...)` | 保存任务 id 到本地 | 精读任务恢复 |
| `restoreReadingTaskId(...)` | 读取本地任务 id | 精读任务恢复 |
| `useReadingTaskTracker(...)` | 统一管理长文本/七步/四步任务轮询状态 | 精读进度条、日志、恢复逻辑 |
| `useBatchReadingTracker(...)` | 管理批量精读轮询状态（`batchId`, `total`, `completed`, `failed`, `tasks`） | 批量精读进度面板、轮询逻辑 |

### 3.4.3 业务组件函数

| 组件 / 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `FilterTab` | 文献筛选页面 | 筛选 UI、参数提交、结果下载 |
| `LongTab` | 长文本精读页面 | 长文本上传、启动、日志、结果预览 |
| `QuantTab` | 七步精读页面 | 七步上传、启动、日志、结果预览 |
| `QualTab` | 四步精读页面 | 四步上传、启动、日志、结果预览 |
| `PromptsTab` | 提示词管理页面 | 系统默认 / 用户覆盖编辑 |
| `HistoryTab` | 历史记录页面 | 历史预览、下载、删除 |
| `CompareView` | React 对比综述主组件 | 替代 iframe，文献选择+维度导航+折叠面板+AI综述 |

## 3.5 `frontend/src/LibraryTab.tsx`

文件：

- [LibraryTab.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/LibraryTab.tsx)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `buildDraft(...)` | 将详情对象转成可编辑草稿 | 文献编辑表单显示异常 |
| `splitCsv(...)` | 文本转数组 | 作者/关键词/标签保存问题 |
| `formatTime(...)` | 时间显示格式化 | 时间线显示问题 |
| `loadEntries()` | 拉取文献列表 | 列表刷新问题 |
| `loadDetail(id)` | 拉取文献详情 | 选中后右侧详情空白 |
| `handleSave()` | 保存元数据编辑 | 保存失败或回写不对 |

## 3.6 `frontend/src/lib/download.ts`

文件：

- [download.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/lib/download.ts)

| 函数 | 作用 | 什么时候优先看 |
|---|---|---|
| `parseFilename(...)` | 从响应头解析下载文件名 | 下载文件名异常 |
| `downloadWithAuth(...)` | 鉴权下载 | 下载失败、返回 401 |
| `openPreviewWithAuth(...)` | 鉴权预览 | 预览报 `Not authenticated` |

## 3.7 `frontend/public/compare_7step.html`

文件：

- [compare_7step.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_7step.html)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `allReports` | 全部可对比七步报告 | 数据源问题 |
| `selectedStep` | 当前查看步骤 | 步骤切换问题 |
| `selectedPapers` | 当前已选文献 | 文献勾选问题 |
| `selectedSubQuestions` | 当前累计已选问题集合 | 跨步骤累计选择问题 |
| `getCurrentApiKey()` | 按当前用户读取 API Key | compare 综述串号 |
| `parseFrontmatter(...)` | 解析 Markdown frontmatter | 标题/作者/年份显示问题 |
| `parseStepContent(...)` | 从报告中拆某一步的子问题内容 | 七步表格内容缺失 |
| `loadReports()` | 拉取可对比报告 | 页面“加载失败” |
| `parseQuestionKey(...)` | 解析“步骤 + 子问题”复合 key | 跨步骤累计选择定位错误 |
| `buildPaperMeta(...)` | 统一渲染文献标题、作者、年份 | 表头信息显示异常 |
| `renderEmptyState(...)` | 渲染空状态占位 | 初始页或无选择时展示异常 |
| `pruneSelectedQuestions()` | 清理当前已失效的选题 key | 历史选择残留 |
| `updateSelectAllCheckbox()` | 同步当前步骤“全选”勾选状态 | 全选框状态不对 |
| `togglePaper(...)` | 勾选/取消文献 | 文献选择状态异常 |
| `selectStep(...)` | 切换步骤 | 步骤切换不刷新 |
| `updateUI()` | 刷新按钮和表格状态 | AI 综述按钮不亮 |
| `renderComparisonTable()` | 渲染对比表格 | 表格显示问题 |
| `toggleAllSubQuestions(...)` | 当前步骤全选 | 全选逻辑问题 |
| `toggleSubQuestion(...)` | 勾选/取消单个问题 | 单项选择问题 |
| `clearAllSelectedQuestions()` | 清空所有累计选择 | “全部取消”无效 |

## 3.8 `frontend/public/compare_4step.html`

文件：

- [compare_4step.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_4step.html)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `getCurrentApiKey()` | 按用户读取 API Key | 四步综述串号 |
| `parseFrontmatter(...)` | 解析 Markdown frontmatter | 标题/作者/年份显示问题 |
| `loadReports()` | 拉取可对比四步报告，并在内部读取后端结构化结果 | 页面无数据或结构化内容未注入 |
| `parseQuestionKey(...)` | 解析“步骤 + 子问题”复合 key | 跨步骤累计选择定位错误 |
| `getPaperSubQuestions(...)` | 优先用结构化结果，否则回退 Markdown 解析 | 子问题丢失 |
| `buildPaperMeta(...)` | 统一渲染文献标题、作者、年份 | 表头信息显示异常 |
| `renderEmptyState(...)` | 渲染空状态占位 | 初始页或无选择时展示异常 |
| `pruneSelectedQuestions()` | 清理当前已失效的选题 key | 历史选择残留 |
| `updateSelectionSummary()` | 刷新已选文献数和问题数 | 顶部摘要不更新 |
| `updateSelectAllCheckbox()` | 同步当前步骤“全选”勾选状态 | 全选框状态不对 |
| `selectStep(...)` | 切换步骤 | 步骤切换不刷新 |
| `updateUI()` | 刷新按钮和表格状态 | AI 综述按钮不亮 |
| `renderComparisonTable()` | 渲染四步对比表格 | 表格显示问题 |
| `togglePaper(...)` | 文献选择 | 文献勾选状态异常 |
| `toggleAllSubQuestions(...)` | 当前步骤全选 | 全选逻辑问题 |
| `toggleSubQuestion(...)` | 单个问题选择 | 单项选择问题 |
| `clearAllSelectedQuestions()` | 清空所有累计选择 | “全部取消”无效 |

## 3.9 `frontend/public/compare_long.html`

文件：

- [compare_long.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_long.html)

| 函数 / 变量 | 作用 | 什么时候优先看 |
|---|---|---|
| `selectedDims` | 当前已选维度集合 | 长文本多维对比问题 |
| `allDimensions` | 当前所有可选维度 | 维度列表缺失 |
| `getCurrentApiKey()` | 按用户读取 API Key | 长文本综述串号 |
| `parseFrontmatter(...)` | 解析 Markdown frontmatter | 标题/作者/年份显示问题 |
| `extractDimensions(...)` | 解析报告中的维度边界 | 某些报告维度读不出来 |
| `getDimensionContent(...)` | 获取某个维度内容 | 表格内容缺失 |
| `loadReports()` | 拉取可对比长文本报告 | 页面无数据 |
| `deleteReport(...)` | 删除单篇长文本报告 | 删除失败 |
| `togglePaper(...)` | 勾选/取消文献 | 文献选择状态异常 |
| `toggleDim(...)` | 勾选/取消维度 | 维度选择状态异常 |
| `updateUI()` | 刷新按钮和对比区域 | 选择后页面不更新 |
| `renderComparisonTable()` | 渲染长文本对比表 | 长文本表格问题 |

## 3.10 `frontend/src/TemplateMarket.tsx`

文件：

- [TemplateMarket.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/TemplateMarket.tsx)

Key functions:
| Function | Purpose | When to look |
|---|---|---|
| `loadTemplates` | Fetch preset templates | Template list not loading |
| `loadUserSets` | Fetch user's own sets | User sets not showing |
| `loadSharedSets` | Fetch other users' shared sets | Shared section not showing |
| `importTemplate` | Import preset template | Import button not working |
| `cloneUserSet` | Clone user's own set | Clone fails |
| `toggleShare` | Toggle share/unshare | Share toggle not working |
| `deleteSet` | Delete unused custom set | Delete not working |
| `importSharedSet` | Import shared set from other user | Shared import fails |
| `startAiGeneration` | Start AI dimension generation | AI wizard errors |
| `saveAiResult` | Save AI-generated dimensions | AI save fails |
| `previewDocumentImport` | Preview uploaded dimension doc | Document preview errors |
| `confirmDocumentImport` | Confirm document import | Document import fails |

## 4. 常见修改场景速查

| 需求 / 问题 | 优先看哪些函数 |
|---|---|
| 注册页提示或校验不对 | `RootApp.tsx` 中的 `AuthLayout`、`isStrongPassword(...)`、`auth.py.register(...)` |
| 新用户串用了旧账号 API Key | `App.tsx` 中的 `getApiKeyStorageKey(...)`、`handleSaveKey()`、`handleDeleteKey()` |
| 上传 PDF 没匹配上题录 | `upload.py.upload_file(...)`、`db/utils.py.normalize_title_for_match(...)`、`reading.py.get_or_create_bib_entry(...)` |
| 筛选结果没进文献库 | `filter.py.run_filter_task(...)`、`persist_filter_results(...)` |
| 精读结果有 Markdown 但 compare 页读不出来 | `reading.py.persist_reading_items(...)`、`compare.py.build_structured_paper_data(...)`、`compare_4step.html.loadReports()`、`compare_4step.html.getPaperSubQuestions(...)` |
| 对比页 AI 综述按钮不亮 | `compare_7step.html.updateUI()`、`compare_4step.html.updateUI()` |
| 历史记录预览报未认证 | `download.ts.openPreviewWithAuth(...)`、`history.py.preview_file(...)` |
| 精读后文献库元数据未更新 | `reading.py._try_update_bib_metadata(...)`、`pdf_metadata_extract.py.extract_front_matter(...)`、`pdf_metadata_llm.py.extract_metadata_with_llm(...)` |
| 提示词管理显示空或保存失败 | `prompt_service.py.ensure_builtin_prompt_templates(...)`、`get_prompt_payload(...)`、`prompts.py.get_prompt_item(...)` |

## 5. 维护建议

- 新增一个重要函数后，如果它成为某个模块的主入口，建议同步补到本文件。
- 如果某个模块重构后入口函数发生变化，也建议同步更新本文件。
- 如果某个问题总是重复出现，优先把对应“需求/问题 -> 函数入口”补到第 4 节的速查表中。
