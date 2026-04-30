# 状态、API 与数据库映射文档

> 目的：本文件用于把**前端状态变量、后端 API、数据库对象、任务产物**放到一张图景里理解。  
> 适合在以下场景使用：
>
> - 想知道某个页面按钮点下去到底会打哪个接口；
> - 想知道一个接口会改哪些表；
> - 想知道某个页面显示的数据来自哪里；
> - 想判断一个功能改动会影响前端、后端还是数据库。

## 1. 阅读方式

本文件按业务流组织：

1. 认证
2. API Key
3. 上传与题录绑定
4. 文献筛选
5. 文献精读
6. 对比分析与综述
7. 文献库
8. 提示词管理
9. 历史记录与下载

每一节都尽量回答 4 个问题：

- 前端主要状态变量是什么？
- 调用了哪些后端 API？
- 后端主要会读写哪些数据库对象？
- 页面上最终显示的内容来自哪里？

## 2. 总体映射

| 业务域 | 前端主入口 | 后端主入口 | 核心表 | 产物 |
|---|---|---|---|---|
| 认证 | `RootApp.tsx`、`auth.ts` | `routers/auth.py` | `users`、`invite_codes` | 无 |
| API Key | `App.tsx`、`compare_*.html` | 大多数接口通过请求体传 `api_key`；仅 compare 支持环境变量兜底 | 浏览器本地存储，不入库 | 无 |
| 上传 | `App.tsx` 中各上传页 | `routers/upload.py` | `files`、`bib_entries` | 用户文件 |
| 筛选 | `FilterTab` | `routers/filter.py` | `jobs`、`bib_entries`、`bib_filter_links`、`artifacts` | `filter_excel` |
| 精读 | `LongTab / QuantTab / QualTab` | `routers/reading.py` | `jobs`、`job_bib_entries`、`bib_entries`、`reading_items`、`artifacts` | `reading_final` |
| 对比综述 | `compare_*.html` | `routers/compare.py`、`routers/history.py` | `jobs`、`job_bib_entries`、`bib_entries`、`reading_items`、`artifacts` | `compare_md`、`synthesis_md` |
| 文献库 | `LibraryTab.tsx` | `routers/library.py` | `bib_entries`、`bib_filter_links`、`job_bib_entries`、`artifacts` | 时间线产物 |
| 提示词管理 | `PromptsTab` | `routers/prompts.py`、`prompt_service.py` | `prompt_templates` | 无 |
| 历史记录 / 下载 | `HistoryTab`、`download.ts` | `routers/history.py`、`routers/download.py` | `jobs`、`artifacts` | 各类产物文件 |

## 3. 认证链路

## 3.1 前端状态

文件：

- [RootApp.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/RootApp.tsx)
- [auth.ts](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/store/auth.ts)

关键状态：

- `accessToken`
- `refreshToken`
- `user`
- `initialized`
- 注册页局部状态：
  - `username`
  - `email`
  - `password`
  - `confirmPassword`
  - `inviteCode`
  - `error`
  - `loading`

这些状态分别表示：

- `accessToken / refreshToken`
  - 当前会话凭证
- `user`
  - 当前登录用户信息
- `initialized`
  - 本地登录态是否已经恢复完成

## 3.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 注册 | `POST /api/auth/register` | `auth.py.register(...)` |
| 登录 | `POST /api/auth/login` | `auth.py.login(...)` |
| 拉当前用户 | `GET /api/auth/me` | `auth.py.me(...)` |
| 刷新 token | `POST /api/auth/refresh` | `auth.py.refresh_token(...)` |
| 改密码 | `POST /api/auth/change_password` | `auth.py.change_password(...)` |
| 退出登录 | `POST /api/auth/logout` | `auth.py.logout(...)` |

## 3.3 数据库映射

主要涉及：

- `users`
- `invite_codes`

其中：

- 注册会写 `users`
- 用邀请码注册 VIP 时会读写 `invite_codes`
- logout 会更新 `users.token_version`

## 3.4 页面显示来源

- 顶部用户名、邮箱、角色徽标来自 `user`
- 管理员后台是否显示来自 `user.role`
- 普通用户提醒条来自 `user.warning_msg`

## 4. API Key 链路

## 4.1 前端状态

文件：

- [App.tsx](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/src/App.tsx)
- [compare_long.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_long.html)
- [compare_7step.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_7step.html)
- [compare_4step.html](file:///d:/code/deepagent/deep-reading-agent-online/deep-reading-agent/frontend/public/compare_4step.html)

关键状态：

- `apiKey`
- `tempKey`
- `showKeyInput`

当前策略：

- API Key 不入库
- 只保存在浏览器 `localStorage`
- 按用户名隔离：
  - `deepseek_api_key:{username}`

## 4.2 API 映射

API Key 本身没有单独的后端管理接口。  
当前实现里：

- `filter` / `reading` 需要显式在请求体里传 `api_key`
- `compare` 优先用请求体 `api_key`，未传时可回退到环境变量

它主要进入这些分析接口：

| 功能 | API | 请求字段 |
|---|---|---|
| 文献筛选 | `POST /api/filter/start` | `api_key` |
| 长文本精读 | `POST /api/reading/long/start` | `api_key` |
| 七步精读 | `POST /api/reading/quant/start` | `api_key` |
| 四步精读 | `POST /api/reading/qual/start` | `api_key` |
| 七步/四步综述 | `POST /api/compare/analyze` | `api_key` |
| 长文本综述 | `POST /api/compare/analyze_long` | `api_key` |

## 4.3 数据库映射

- 无数据库表
- 只在请求运行时使用

## 5. 上传与题录绑定链路

## 5.1 前端状态

上传主要分散在以下页面内部：

- `FilterTab`
- `LongTab`
- `QuantTab`
- `QualTab`

当前上传相关页面里，稳定存在的局部状态主要是：

- `file`

上传成功后的接口返回值通常作为 `handleStart()` 内部局部变量 `uploadData` 使用，而不是统一保存在组件状态中。  
`uploadData` 通常包含：

- `file_id`
- `filename`
- `storage_path`
- `matched_bib_entry_id`（如果后端已匹配）

## 5.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 上传文件 | `POST /api/upload/` | `upload.py.upload_file(...)` |
| 查文件信息 | `GET /api/upload/{file_id}/info` | `upload.py.get_file_info(...)` |
| 删除文件 | `DELETE /api/upload/{file_id}` | `upload.py.delete_file(...)` |

## 5.3 数据库映射

主要涉及：

- `files`
- 可选更新 `bib_entries.source_file_id`

处理逻辑：

1. 上传文件写入 `files`
2. 记录归属用户
3. 仅对 PDF / Markdown 按标题相似度尝试匹配已有 `bib_entries`
4. 若命中，则将文件与文献档案关联

## 5.4 页面显示来源

- 上传成功提示来自 `/api/upload/` 返回值
- 文献库中的“是否有源文件”来自 `bib_entries.source_file_id`

## 6. 文献筛选链路

## 6.1 前端状态

入口组件：

- `FilterTab`

常见状态：

- `file`
- `mode`
- `topic`
- `minYear`
- `keywords`
- `isRunning`
- `progress`
- `stage`
- `logs`
- `results`
- `downloadUrl`

这些状态分别对应：

- 上传文件与筛选参数
- 后台任务状态
- 日志轮询
- 筛选结果预览与下载

## 6.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 启动筛选 | `POST /api/filter/start` | `filter.py.start_filter(...)` |
| 查状态 | `GET /api/filter/task/{task_id}/status` | `filter.py.get_task_status(...)` |
| 取消任务 | `POST /api/filter/task/{task_id}/cancel` | `filter.py.cancel_task(...)` |

## 6.3 数据库映射

主要涉及：

- `jobs`
- `bib_entries`
- `bib_filter_links`
- `artifacts`

写入逻辑：

1. 创建 `Job(filter)`
2. 解析题录并去重
3. 写入或更新 `BibEntry`
4. 写入 `BibFilterLink`
5. 生成 `Artifact(filter_excel)`

## 6.4 页面显示来源

| 页面内容 | 数据来源 |
|---|---|
| 进度条 | `jobs.progress` 或内存任务状态 |
| 当前阶段 | `jobs.current_stage` 或任务状态接口 |
| 运行日志 | 后端任务日志 |
| 下载链接 | `Artifact(filter_excel)` |
| 文献库中的筛选评价 | `bib_filter_links` |

## 7. 文献精读链路

## 7.1 前端状态

入口组件：

- `LongTab`
- `QuantTab`
- `QualTab`

共同状态主要来自 `useReadingTaskTracker(...)`：

- `taskId`
- `isRunning`
- `progress`
- `stage`
- `logs`
- `preview`
- `downloadUrl`
- `currentStep`

另外每个页面还有自己的局部输入状态，例如：

- 上传文件状态
- 维度选择
- 自定义问题
- 提取模式

## 7.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 启动长文本 | `POST /api/reading/long/start` | `reading.py.start_long_context(...)` |
| 启动七步 | `POST /api/reading/quant/start` | `reading.py.start_quant(...)` |
| 启动四步 | `POST /api/reading/qual/start` | `reading.py.start_qual(...)` |
| 查任务状态 | `GET /api/reading/task/{task_id}/status` | `reading.py.get_task_status(...)` |
| 取消任务 | `POST /api/reading/task/{task_id}/cancel` | `reading.py.cancel_task(...)` |

## 7.3 数据库映射

主要涉及：

- `jobs`
- `job_bib_entries`
- `bib_entries`
- `reading_items`
- `artifacts`

写入逻辑：

1. 为源文件匹配或创建 `BibEntry`
2. 创建 `Job(reading_long / reading_quant / reading_qual)`
3. 绑定 `JobBibEntry(target)`
4. 保存 Markdown 结果到 `Artifact(reading_final)`
5. 将结构化结果写入 `ReadingItem`

## 7.4 页面显示来源

| 页面内容 | 数据来源 |
|---|---|
| 处理进度 | 任务状态接口 |
| 日志面板 | 后台任务日志 |
| 长文本页结果预览 | 任务状态接口返回的 `result.preview` |
| 下载按钮 | `download.ts.downloadWithAuth(...)` |
| compare 页的结构化内容 | `reading_items` |

## 8. 对比分析与综述链路

## 8.1 前端状态

长文本对比：

- `selectedDims`
- `selectedPapers`
- `allDimensions`

七步/四步对比：

- `selectedStep`
- `selectedPapers`
- `selectedSubQuestions`

这些状态分别表示：

- 当前选择的维度或步骤
- 当前参与对比的文献
- 当前用于 AI 综述的问题集合

## 8.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 读取结构化精读结果 | `GET /api/compare/jobs/{job_id}/structured` | `compare.py.get_structured_reading(...)` |
| 七步/四步综述 | `POST /api/compare/analyze` | `compare.py.analyze_comparison(...)` |
| 长文本综述 | `POST /api/compare/analyze_long` | `compare.py.analyze_long_comparison(...)` |
| 保存综述到历史 | `POST /api/history/synthesis/` | `history.py.save_synthesis(...)` |

## 8.3 数据库映射

主要涉及：

- `reading_items`
- `bib_entries`
- `jobs`
- `job_bib_entries`
- `artifacts`

处理逻辑：

1. compare 优先从 `reading_items` 聚合结构化内容
2. 创建 `Job(compare)`
3. 写入 `JobBibEntry(compare_member)`
4. 保存 compare Markdown 到 `Artifact(compare_md)`
5. 用户点击“保存到历史记录”时，再额外创建 `Job(synthesis)` 和 `Artifact(synthesis_md)`

## 8.4 页面显示来源

| 页面内容 | 数据来源 |
|---|---|
| 对比表格 | 前端 HTML 页面解析或后端结构化接口 |
| AI 综述按钮是否点亮 | 前端选中状态 + 至少两篇文献规则 |
| 综述正文 | `/api/compare/analyze*` 返回 |
| 历史综述列表 | `history.py.list_synthesis(...)` |

## 9. 我的文献库链路

## 9.1 前端状态

入口组件：

- `LibraryTab.tsx`

关键状态：

- `search`
- `journalFilter`
- `readingStatus`
- `pinnedOnly`
- `entries`
- `selectedId`
- `detail`
- `draft`
- `listLoading`
- `detailLoading`
- `saving`
- `listError`
- `detailError`
- `saveMessage`

## 9.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 拉列表 | `GET /api/library/entries` | `library.py.list_entries(...)` |
| 拉详情 | `GET /api/library/entries/{entry_id}` | `library.py.get_entry_detail(...)` |
| 保存编辑 | `PATCH /api/library/entries/{entry_id}` | `library.py.update_entry(...)` |

## 9.3 数据库映射

主要读取：

- `bib_entries`
- `bib_filter_links`
- `job_bib_entries`
- `artifacts`

主要写入：

- `bib_entries`

页面中的时间线，实质上是把以下数据聚合展示：

- 与该文献关联的精读任务
- 与该文献关联的 compare / synthesis 任务
- 相关产物文件

## 9.4 页面显示来源

| 页面内容 | 数据来源 |
|---|---|
| 左侧文献列表 | `list_entries(...)` |
| 右侧详情基础元数据 | `bib_entries` |
| 筛选评价 | `bib_filter_links` |
| 时间线 | `jobs + job_bib_entries + artifacts` |
| 下载按钮 | `download.ts.downloadWithAuth(...)` |

## 10. 提示词管理链路

## 10.1 前端状态

入口组件：

- `PromptsTab`（定义在 `App.tsx` 内）

关键状态：

- `promptType`
- `currentKey`
- `catalog`
- `effectiveContent`
- `userContent`
- `systemContent`
- `title`
- `source`
- `hasUserOverride`
- `isLoading`
- `message`

这些状态分别表示：

- 当前选中的类型和槽位
- 后端返回的目录
- 当前生效内容
- 当前用户覆盖内容
- 系统默认内容
- 当前来源与操作提示

## 10.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 拉目录 | `GET /api/prompts/catalog` | `prompts.py.prompt_catalog(...)` |
| 拉单项 | `GET /api/prompts/item?type=&key=` | `prompts.py.get_prompt_item(...)` |
| 保存我的覆盖 | `PUT /api/prompts/my` | `prompts.py.save_my_prompt(...)` |
| 恢复默认 | `DELETE /api/prompts/my?type=&key=` | `prompts.py.reset_my_prompt(...)` |
| 保存系统默认 | `PUT /api/prompts/system` | `prompts.py.save_system_prompt(...)` |

## 10.3 数据库映射

主要涉及：

- `prompt_templates`

逻辑分层：

- `scope=system`
  - 系统默认
- `scope=user`
  - 用户覆盖

运行时优先级：

1. 用户覆盖
2. 系统默认
3. 文件兜底
4. 代码兜底

## 10.4 页面显示来源

| 页面内容 | 数据来源 |
|---|---|
| 类型/步骤下拉 | `catalog` |
| 当前生效内容 | `effectiveContent` |
| 我的覆盖输入框 | `userContent` |
| 系统默认输入框 | `systemContent` |
| 来源标签 | `source` |

## 11. 历史记录与下载链路

## 11.1 前端状态

入口组件：

- `HistoryTab`

关键状态：

- `subTab`
- `readingFiles`
- `synthesisFiles`
- `loading`

## 11.2 API 映射

| 前端动作 | API | 后端函数 |
|---|---|---|
| 拉阅读/筛选/对比历史 | `GET /api/history/` | `history.py.list_history(...)` |
| 拉综述历史 | `GET /api/history/synthesis/` | `history.py.list_synthesis(...)` |
| 删除历史 | `DELETE /api/history/{filename}` | `history.py.delete_file(...)` |
| 预览文件 | `GET /api/history/{filename}/preview` | `history.py.preview_file(...)` |
| 下载文件 | `GET /api/download/{file_path:path}` | `download.py.download_file(...)` |

## 11.3 数据库映射

主要涉及：

- `jobs`
- `artifacts`
- 可选通过 `job_bib_entries` 回溯关联文献

## 11.4 页面显示来源

| 页面内容 | 数据来源 |
|---|---|
| 历史文件列表 | `artifacts` 聚合结果 |
| 预览按钮 | `openPreviewWithAuth(...)` |
| 下载按钮 | `downloadWithAuth(...)` |

## 12. 最近重点改动的影响范围

## 12.1 注册密码规则前置

影响层：

- 前端注册表单

相关文件：

- `frontend/src/RootApp.tsx`

不影响：

- 数据库
- token
- 文献业务

## 12.2 API Key 按账号隔离

影响层：

- 工作台主壳
- 三个旧 compare 页面
- 本地浏览器存储

相关文件：

- `frontend/src/App.tsx`
- `frontend/public/compare_long.html`
- `frontend/public/compare_7step.html`
- `frontend/public/compare_4step.html`

不影响：

- 数据库
- 后端 API 结构

## 12.3 七步/四步综述交互修复

影响层：

- compare 前端页面交互
- compare 后端请求参数

相关文件：

- `frontend/public/compare_7step.html`
- `frontend/public/compare_4step.html`

影响点：

- AI 综述按钮启用条件
- 跨步骤累计选题
- 已选数量提示

## 12.4 提示词中心上线

影响层：

- 后端运行时 prompt 解析
- 前端提示词管理页
- 数据库提示词模板存储

相关文件：

- `backend/prompt_registry.py`
- `backend/prompt_service.py`
- `backend/routers/prompts.py`
- `frontend/src/App.tsx`
- `backend/migrations/versions/004_add_prompt_templates.py`

## 13. 排查问题时的判断路径

## 13.1 先看页面状态，还是先看 API？

建议用下面的判断方式：

### 页面显示空白，但接口正常

优先看：

- 前端状态变量
- 前端渲染条件
- 前端选择逻辑

### 页面报 401 / Not authenticated

优先看：

- `api-fetch.ts`
- `download.ts`
- `download.py`
- 路由是否走了鉴权 fetch

### 数据库里有数据，但页面不显示

优先看：

- 后端详情接口是否返回
- 前端是否正确映射字段

### 页面能显示，但内容不对

优先看：

- 后端聚合逻辑
- `reading_items` / `bib_filter_links` / `artifacts` 等中间层表

## 14. 后续维护建议

- 新增一个重要页面时，建议补它的状态、API、数据库映射到本文件。
- 新增一个重要表时，也建议把它加入第 2 节的总映射表。
- 如果未来上线“参考文献梳理标签页”，本文件需要新增一节，重点映射：
  - `bib_references`
  - `bib_reference_citations`
  - 新的任务与产物
