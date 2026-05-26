# Deep Reading Agent 系统功能文档

> 本文档基于实际代码生成，用于确保回答基于真实功能而非猜测。
> 生成时间：2026-05-26
> 代码版本：backend/main.py v3.0.0

---

## 1. 系统架构

### 1.1 技术栈
- **后端**：FastAPI + SQLAlchemy 2.0 (异步) + SQLite
- **前端**：Vite + React（静态文件由 FastAPI 提供）
- **部署**：Cloudflare Tunnel (cloudflared)
- **AI 模型**：DeepSeek API (deepseek-v4-flash)
- **任务队列**：内存队列 (services/queue_manager.py)
- **定时任务**：APScheduler (每日 00:00 清理普通用户数据)

### 1.2 目录结构
```
deep-reading-agent/
├── backend/           # FastAPI 后端
│   ├── main.py        # 入口，路由注册
│   ├── routers/       # API 路由模块
│   ├── db/            # 数据库模型和会话
│   ├── services/      # 业务逻辑
│   └── ...
├── frontend/          # Vite React 前端
│   └── dist/          # 构建产物（由后端提供）
├── db/                # SQLite 数据库文件
│   └── app.sqlite
├── _uploads/          # 用户上传文件
└── deep_reading_results/  # 精读结果存储
```

### 1.3 服务端口
- 后端 API：`127.0.0.1:8000`
- 前端开发：`5173`（仅开发模式）
- 健康检查：`GET /health` → `{"status": "ok"}`
- WebSocket：`/ws/{task_id}`（实时进度推送）

---

## 2. 用户系统

### 2.1 角色体系
| 角色 | 权限 |
|------|------|
| `admin` | 全部权限，包括用户管理、反馈管理、系统设置 |
| `vip` | 无过期时间限制，高级功能 |
| `normal` | 基础功能，数据 24 小时后自动清理 |

### 2.2 认证方式
- JWT Token (Bearer)，登录时生成
- Token 包含 `sub`(用户ID), `type`(access/refresh), `exp`
- 环境变量 `JWT_SECRET_KEY` 控制密钥

### 2.3 API 端点
- `POST /api/auth/register` - 注册（需邀请码）
- `POST /api/auth/login` - 登录
- `POST /api/auth/refresh` - 刷新 Token
- `GET /api/auth/me` - 当前用户信息

---

## 3. 文献库 (Library)

### 3.1 核心概念
- **BibEntry**：文献元数据条目（标题、作者、年份、DOI、期刊等）
- **File**：上传的文件（PDF、Markdown）
- **ReadingItem**：用户的精读记录
- **Job**：异步任务（精读、翻译、筛选等）
- **Artifact**：任务产物（Markdown 报告、卡片等）

### 3.2 文献来源
1. **手动上传**：PDF 或 Markdown 文件
2. **Crossref**：通过 DOI 获取元数据
3. **OpenAlex**：通过标题匹配获取元数据
4. **arXiv**：支持 arXiv ID 导入

### 3.3 文献状态
- `unread` - 未读
- `reading` - 正在精读
- `completed` - 已完成
- `archived` - 已归档

### 3.4 标签系统
- 每篇文献可以有多个标签（tags 字段，JSON 数组）
- 支持标签筛选、多标签交集筛选
- **注意**：已取消文件夹层级，全面转向标签 + 元数据筛选

### 3.5 API 端点
- `GET /api/library` - 文献列表（支持分页、筛选、排序）
- `GET /api/library/{id}` - 文献详情
- `POST /api/library` - 添加文献（通过 DOI/arXiv/手动）
- `PATCH /api/library/{id}` - 更新文献（标签、笔记等）
- `DELETE /api/library/{id}` - 删除文献
- `POST /api/library/{id}/pin` - 置顶/取消置顶
- `POST /api/library/{id}/read` - 标记已读/未读

---

## 4. 精读系统 (Reading)

### 4.1 精读模式
1. **长文精读** (`long`)：14 个维度全面分析
2. **定量论文精读** (`quant`)：7 步结构化分析
3. **定性论文精读** (`qual`)：4 步结构化分析

### 4.2 长文精读维度
| 维度 | 说明 |
|------|------|
| 研究问题 | 核心研究问题 |
| 理论框架 | 理论基础 |
| 识别策略 | 因果识别策略 |
| 数据来源 | 数据描述 |
| 变量度量 | 变量测量方式 |
| 识别假设 | 关键假设 |
| 统计结果 | 主要统计结果 |
| 机制分析 | 机制检验 |
| 稳健性检验 | 稳健性测试 |
| 外部有效性 | 外部效度 |
| 贡献与局限 | 贡献和局限性 |
| 写作质量 | 写作评估 |
| 自定义问题 | 用户自定义问题 |

### 4.3 定量精读步骤
1. 核心贡献识别
2. 理论框架评估
3. 方法论批判
4. 实证结果解读
5. 局限性分析
6. 实践意义
7. 未来方向

### 4.4 精读流程
1. 用户选择文件和模式
2. 系统提取 PDF 文本（extractor.py）
3. 调用 DeepSeek API 逐维度分析
4. 生成 Markdown 报告存储到 `deep_reading_results/`
5. 创建 Artifact 记录关联到 BibEntry
6. 通过 WebSocket 推送进度

### 4.5 API 端点
- `POST /api/reading/start` - 开始精读
- `GET /api/reading/status/{job_id}` - 查询进度
- `GET /api/reading/result/{job_id}` - 获取结果
- `POST /api/reading/cancel/{job_id}` - 取消任务

---

## 5. AI 助手 (Agent)

### 5.1 功能
- **文献检索**：基于对话内容检索相关文献
- **精读问答**：针对已精读文献提问
- **对比分析**：多篇文献对比
- **综述生成**：基于文献集合生成综述
- **上传处理**：支持批量上传文件到 Inbox

### 5.2 工具调用 (Tool Calling)
Agent 使用 DeepSeek 的 function calling 能力，可用工具包括：
- `search_library` - 检索用户文献库
- `read_paper` - 读取指定文献内容
- `compare_papers` - 对比多篇文献
- `generate_synthesis` - 生成综述
- `upload_files` - 处理上传文件

### 5.3 会话管理
- `AgentSession` 表记录会话
- 支持多轮对话，历史消息保留
- 最大 12 轮历史

### 5.4 API 端点
- `POST /api/agent/chat` - 发送消息（SSE 流式返回）
- `GET /api/agent/sessions` - 会话列表
- `DELETE /api/agent/sessions/{id}` - 删除会话
- `POST /api/agent/settings` - 更新设置（如输入文件夹路径）

---

## 6. 翻译系统 (Translation)

### 6.1 功能
- 全文翻译（PDF/Markdown）
- 摘要翻译
- 支持 DeepSeek API 翻译

### 6.2 翻译流程
1. 提取文本（PDF 用 PDFExtractor，Markdown 直接读取）
2. 分段调用 DeepSeek API 翻译
3. 合并结果存储为 Markdown
4. 创建 Artifact 关联到 BibEntry

### 6.3 注意
- 翻译结果存储在 `deep_reading_results/{user_id}/{job_id}/`
- 通过 `GET /api/translation/result/{job_id}` 获取
- **常见问题**：用户可能不知道翻译结果在哪里查看（在文献卡片的「翻译」标签页）

### 6.4 API 端点
- `POST /api/translation/start` - 开始翻译
- `GET /api/translation/status/{job_id}` - 查询进度
- `GET /api/translation/result/{job_id}` - 获取结果

---

## 7. 对比系统 (Compare)

### 7.1 功能
- 多篇文献对比分析
- 生成对比表格和综述

### 7.2 API 端点
- `POST /api/compare` - 创建对比任务
- `GET /api/compare/{job_id}` - 获取对比结果

---

## 8. 筛选系统 (Filter)

### 8.1 功能
- 基于条件筛选文献库
- 支持 AI 自动筛选（根据描述判断相关性）
- 生成筛选报告

### 8.2 API 端点
- `POST /api/filter` - 创建筛选任务
- `GET /api/filter/{job_id}` - 获取筛选结果

---

## 9. 卡片系统 (Cards)

### 9.1 功能
- 文献卡片笔记
- 支持 Markdown 编辑
- 标签和分类

### 9.2 API 端点
- `GET /api/cards` - 卡片列表
- `POST /api/cards` - 创建卡片
- `PATCH /api/cards/{id}` - 更新卡片
- `DELETE /api/cards/{id}` - 删除卡片

---

## 10. 反馈系统 (Feedback)

### 10.1 数据模型
- `UserFeedback` 表：用户反馈
- `FeedbackEvent` 表：反馈事件追踪
- `AdminAuditLog` 表：管理员操作审计

### 10.2 反馈类型
- `bug` - 程序错误
- `feature` - 功能建议
- `question` - 使用问题
- `data_issue` - 数据问题
- `translation` - 翻译问题
- `reading_quality` - 精读质量
- `other` - 其他

### 10.3 反馈状态
- `open` → `triaged` → `in_progress` → `resolved` / `closed`
- 支持 `reopened`

### 10.4 优先级
- `P0` - 紧急
- `P1` - 高
- `P2` - 中
- `P3` - 低（默认）

### 10.5 处理原则（重要）
1. **先诊断，不直接改代码** - 可能是操作问题
2. **先联系用户确认** - 建议正确操作方法
3. **改代码前必须向用户确认** - 只有确认是系统性问题才修复
4. **标记为 `triaged` 而非 `resolved`** - 等待确认

### 10.6 API 端点
- `POST /api/feedback` - 提交反馈（需登录）
- `GET /api/feedback/my` - 我的反馈列表
- `GET /api/feedback/admin` - 管理员查看所有反馈（需 admin）
- `GET /api/feedback/admin/{id}` - 单条反馈详情
- `PATCH /api/feedback/admin/{id}` - 更新反馈（状态、优先级、回复）
- `POST /api/feedback/admin/{id}/events` - 添加评论/事件

---

## 11. 管理员功能 (Admin)

### 11.1 用户管理
- 查看所有用户
- 修改用户角色（admin/vip/normal）
- 禁用/启用用户
- 生成邀请码

### 11.2 系统监控
- 查看系统统计（用户数量、任务数量、存储使用）
- 查看管理员审计日志

### 11.3 API 端点
- `GET /api/admin/users` - 用户列表
- `PATCH /api/admin/users/{id}` - 更新用户
- `GET /api/admin/stats` - 系统统计
- `GET /api/admin/audit-logs` - 审计日志

---

## 12. 上传系统 (Upload)

### 12.1 支持的文件类型
- `.pdf` - PDF 论文
- `.md`, `.markdown` - Markdown 文件
- 其他：通过 `detect_file_type()` 检测

### 12.2 存储结构
```
_uploads/
└── {user_id}/
    └── {file_id}_{filename}
```

### 12.3 文件绑定
- 上传文件后绑定到 BibEntry
- 支持批量上传（UploadBatch）

### 12.4 API 端点
- `POST /api/upload` - 上传文件
- `POST /api/upload/batch` - 批量上传
- `GET /api/upload/{file_id}` - 获取文件信息

---

## 13. 维度系统 (Dimensions)

### 13.1 功能
- 自定义精读维度
- 维度模板管理
- 支持长文精读的自定义问题

### 13.2 API 端点
- `GET /api/dimensions` - 维度列表
- `POST /api/dimensions` - 创建维度
- `PATCH /api/dimensions/{id}` - 更新维度
- `DELETE /api/dimensions/{id}` - 删除维度

---

## 14. Prompt 系统

### 14.1 功能
- 管理精读提示词模板
- 支持自定义提示词
- 按精读模式分类

### 14.2 API 端点
- `GET /api/prompts` - 提示词列表
- `POST /api/prompts` - 创建提示词
- `PATCH /api/prompts/{id}` - 更新提示词
- `DELETE /api/prompts/{id}` - 删除提示词

---

## 15. 数据库模型（关键表）

### 15.1 users
- `id`, `username`, `email`, `password_hash`, `role`, `vip_expires_at`, `is_active`, `token_version`

### 15.2 bib_entries
- 文献元数据：标题、作者、年份、DOI、期刊、摘要、标签等

### 15.3 files
- 上传文件记录：文件名、类型、存储路径、大小、页数等

### 15.4 jobs
- 异步任务：类型（reading/translation/filter/compare）、状态、进度、错误信息等

### 15.5 artifacts
- 任务产物：类型（report/card/translation）、存储路径、关联 job_id

### 15.6 agent_sessions / agent_messages
- AI 助手会话和消息记录

### 15.7 user_feedback / feedback_events
- 反馈系统和事件追踪

---

## 16. 定时任务

### 16.1 每日清理（00:00）
- 清理普通用户（`role='normal'`）的过期数据
- 删除 24 小时前的上传文件和结果
- 保留 VIP 和 Admin 用户数据

### 16.2 启动恢复
- 服务器重启时，将 `pending`/`running` 状态的任务标记为 `failed`
- 防止挂起任务占用资源

---

## 17. 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 密钥 | `dev-jwt-secret-change-me` |
| `JWT_ALGORITHM` | JWT 算法 | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token 过期时间 | 60 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token 过期时间 | 30 |
| `UPLOAD_DIR` | 上传文件目录 | `_uploads` |
| `RESULTS_DIR` | 结果存储目录 | `deep_reading_results` |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - |

---

## 18. 已知限制和注意事项

1. **翻译结果查看位置**：翻译完成后，结果在文献卡片的「翻译」标签页，不是在单独页面
2. **检索优化**：AI 助手检索时，用户可以通过限定年份、期刊、方法来缩小范围
3. **normal 用户数据清理**：24 小时后自动清理，重要数据需及时下载
4. **并发限制**：翻译任务使用线程池，默认 max_workers=5
5. **WebSocket 连接**：任务进度通过 WebSocket 推送，断开后需手动刷新
6. **localhost:8000 路由异常**：curl localhost:8000 可能返回前端 HTML，应使用 127.0.0.1:8000

---

## 19. 文件索引

### 关键文件位置
- 入口：`backend/main.py`
- 路由：`backend/routers/*.py`
- 模型：`backend/db/models.py`
- 认证：`backend/auth/dependencies.py`, `backend/auth/security.py`
- 任务队列：`backend/services/queue_manager.py`
- PDF 提取：`extractor.py`
- 前端构建：`frontend/dist/`
- 数据库：`db/app.sqlite`
- 上传文件：`_uploads/`
- 精读结果：`deep_reading_results/`

---

## 20. 前端架构

### 20.1 技术栈
- **框架**：React + TypeScript
- **构建工具**：Vite
- **路由**：react-router-dom
- **Markdown 渲染**：marked
- **状态管理**：Zustand (store/auth.ts)
- **HTTP 请求**：原生 fetch (lib/api-fetch.ts)

### 20.2 主要页面/标签页
App.tsx 中定义的 TABS：

| 标签页 | ID | 功能 |
|--------|-----|------|
| 文献筛选 | `filter` | 基于条件筛选文献库 |
| 长文本精读 | `long` | 14 维度全面精读 |
| 长文本对比 | `compare-long` | 多篇长文对比 |
| 七步精读 | `quant` | 定量论文 7 步分析 |
| 七步对比 | `compare-7step` | 多篇定量对比 |
| 四步精读 | `qual` | 定性论文 4 步分析 |
| 四步对比 | `compare-4step` | 多篇定性对比 |
| 全文翻译 | `translation` | PDF/Markdown 翻译 |
| 我的文献库 | `library` | 文献库管理（LibraryTab.tsx） |
| 参考文献梳理 | `references` | 参考文献管理 |
| 提示词管理 | `prompts` | Prompt 模板管理 |
| 历史记录 | `history` | 任务历史 |
| 卡片笔记 | `cards` | 卡片笔记（CardLibrary.tsx） |
| AI 助手 | `agent` | AI 对话助手 |

### 20.3 关键组件
- **LibraryTab.tsx** - 文献库主界面
  - 文献列表（支持标签筛选、排序）
  - 文献详情面板（元数据、时间线、AI 评论）
  - 编辑对话框（标题、作者、年份、DOI、标签、笔记）
  - 元数据匹配面板（MetadataMatchPanel）
  - 引用格式对话框（RefFormatModal）
  - 全文查找功能（FullTextLookup）

- **CardLibrary.tsx** - 卡片笔记库
- **MarkdownReader.tsx** - Markdown 阅读器
- **TranslationTab.tsx** - 翻译界面
- **ReferenceTraceTab.tsx** - 参考文献追踪
- **CompareView.tsx** - 对比视图
- **TemplateMarket.tsx** - 模板市场
- **DimensionManager.tsx** - 维度管理
- **AdminPage.tsx** - 管理员后台

### 20.4 认证状态
- 使用 Zustand 管理全局认证状态
- Token 存储在 localStorage
- API Key 按用户隔离存储（`deepseek_api_key:{username}`）
- 未登录时自动跳转登录页

### 20.5 文件上传
- 支持拖拽上传
- 支持文件夹批量上传（webkitdirectory）
- 限制：PDF/Markdown 文件，最多 200 个
- 分片上传（4MB chunk）

---

## 21. 部署信息

### 21.1 生产环境
- **域名**：https://deepreading.qzz.io/
- **隧道**：Cloudflare Tunnel (cloudflared)
- **服务器**：VM-59-191-ubuntu
- **自动启动**：systemd 服务

### 21.2 启动脚本
- `start.sh` - 启动所有服务（后端、前端、隧道）
- `healthcheck.sh` - 健康检查（每分钟 cron）
- `daily_health_check.sh` - 每日健康报告（03:00 cron）
- `auto_fix.sh` - 自动修复脚本
- `generate_report.py` - 报告生成

### 21.3 监控
- 后端 PID、前端 PID、隧道 PID
- 磁盘使用率、内存使用率
- 数据库大小
- 隧道错误日志

---

*本文档由 AI 基于实际代码生成，用于确保回答准确性。如有更新需求，请重新运行代码扫描。*
