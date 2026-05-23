# 待实施计划表

> 说明：本文件只记录“**已经形成规划，但尚未实施**”的事项。  
> 已完成实现的功能不要重复写进来；后续新增想法也先汇总到这里，再决定优先级。

## 1. 当前待实施事项总表

| 优先级 | 事项 | 当前状态 | 前置依赖 | 关联文档 | 备注 |
|---|---|---|---|---|---|
| P14 | Markdown 原文阅读与 AI 卡片笔记 | 已讨论，待实施 | Markdown 原文或翻译产物可挂载到文献条目 | [详细方案](./2026-05-22-markdown-card-notes-plan.md) | 在隐藏阅读页基于原文/译文选段生成系统内卡片库，并导出 Obsidian 兼容的卡片与论文 Markdown。 |
| ~~P0~~ | ~~参考文献梳理标签页 + 引用关系入库~~ | **已完成（2026-05）** | 无 | [REFERENCE_CITATION_TAB_PLAN.md](./REFERENCE_CITATION_TAB_PLAN.md) | 全链路已实现：后端 7 个 API 端点（`/api/references/*`）、DeepSeek v4-flash 提取+追踪服务、`bib_references` + `bib_reference_citations` 表+迁移、前端 `ReferenceTraceTab` 组件。 |
| P0.5 | 双栏 PDF 参考文献提取修复 | **已完成（2026-05-03）** | 建议在 P0 进入实施前先修 | [REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md](./REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md) | pypdf 对 CJK 编码双栏 PDF 的文本提取完全失败（中文乱码），需切换为 pdfplumber。影响所有中文学术期刊论文的参考文献提取。 |
| P1 | PDF 题录/元数据在线匹配增强 | **已完成（2026-05-03）** | 无 | [PDF_METADATA_MATCH_PLAN.md](./PDF_METADATA_MATCH_PLAN.md) | PDF 前 1-3 页提取、DeepSeek 结构化抽取、Crossref/OpenAlex 在线候选匹配、前端匹配面板 |
| P2~P4 | AI 综述模块重构（参考文献兜底 + 提示词管理 + 引用锚点） | **已完成（2026-05-11）**，P3 提示词管理未做 | 无 | [SYNTHESIS_PROMPT_PLAN.md](./SYNTHESIS_PROMPT_PLAN.md) | P2 兜底修复（None 年份、缺作者）、P4 引用锚点（SSE 分维度流式）、二次引用过滤（DeepSeek 识别）已完成。P3 提示词管理未纳入。 |
| P2.5 | AI 综述二次引用目录过滤 | **已完成（2026-05-11）** | AI 综述模块已上线 | 无 | 改用 DeepSeek 识别综述正文实际引用的二次文献，复用 system prompt + metadata_block 缓存命中。 |
| ~~P3.5~~ | ~~批量精读（文件夹上传）~~ | **已完成（2026-05-11）** | 无 | [实施计划](./superpowers/plans/2026-05-11-batch-folder-reading.md) | 三个 Tab 各有「上传文件夹」按钮，复用单篇精读逻辑，`POST /batch/start` + `GET /batch/{batch_id}/status`。修复了 `create_reading_job` 后缺少 `flush` 导致 `scalar_one()` 找不到新 Job 的 bug。 |

| ~~P5~~ | ~~任务队列接入路由层 + 前端排队提示~~ | **已完成（2026-05）** | 无 | [MULTIUSER_PROGRESS.md](./MULTIUSER_PROGRESS.md) P12.6 节 | `reading.py` 三个 start 函数已接入 enqueue、worker 首尾调用 mark_running/mark_completed、get_task_status 返回排队信息、前端 applyStatus 处理 queued + 三个 Tab 蓝色排队 UI。 |
| ~~P6~~ | ~~用户数据一键导出/导入~~ | **已完成（2026-05）** | 无 | [设计文档](./superpowers/specs/2026-05-06-user-data-export-import-design.md) | JSON + 文件打包为 `.dra`，清空后导入策略。`data_portability.py` + `routers/data.py` 完整实现。 |
| P7 | Playwright E2E + 部署验收 | 已规划，未实施 | 建议在主要交互和文案稳定后进行 | [MULTIUSER_PROGRESS.md](./MULTIUSER_PROGRESS.md) | 属于最终验收阶段，不宜提前启动 |
| ~~P8~~ | ~~长文本精读维度用户化~~ | **已完成（2026-05）** | 无 | [CUSTOM_DIMENSION_PLAN.md](./CUSTOM_DIMENSION_PLAN.md) | 用户维度集合 + 模板市场 + AI 生成 + 文档导入 + 共享。`dimensions.py` 22 端点、`TemplateMarket.tsx`、4 张新表。 |
| P9 | 对比页 AnswerCard 三按钮（编辑/点评/AI总结） | **设计完成**，待实施 | 无 | [设计文档](./superpowers/specs/2026-05-14-compare-card-actions-design.md) | AnswerCard 级三个按钮：编辑覆盖层+回退、点评模式高亮+全局点评库、AI总结模式三种子视图。新增 `reading_item_edits` + `annotations` 两张表。 |
| P10 | 前端 ESLint 规则分级治理 | 已发现规则基线问题，待规划实施 | 前端主要功能稳定后 | 无 | 当前 `npm run lint` 被大量规则阻断，需区分真正错误、可维护性警告和 React Compiler 建议类规则，避免 lint 作为上线门禁时误伤。 |
| P11 | Online 页面提供打包版下载 | 方案 B 已确定，待 online 分支实施 | OSS 打包产物已上传；服务器需配置 OSS 凭据 | 无 | 后端动态生成短期 OSS 签名 URL，前端按钮点击后请求后端获取下载链接；当前分支只记录方案，不在 packaging 直接实现。 |
| P12 | 七步/四步小问题对比解析稳健性 | 已定位，待修复 | 无 | 无 | 2026-05-16 导出的 `.dra` 中 quant/qual 只有 step 没有 subquestion；模型输出从 `### **1. 标题**` 漂移到 `#### 1.1 标题`/`### 一、标题` 等格式，当前解析器未识别，导致对比页只能显示大维度。建议在 P9 大功能前处理。 |
| P13 | 对比页 AI 总结选中文本未进入提示词 | 打包路径已修复，待重新打包与干净数据目录验证 | 无 | 无 | 旧打包产物运行时 `PROJECT_ROOT` 指错，找不到 `prompts/compare/ai_summary.md`，因此初始化时写入了缺少 `{selected_text}` 的 fallback 提示词；`426f8d2d` 已改为 frozen 环境使用 `sys._MEIPASS`。 |

## 2. 各事项说明

### 2.1 PDF 题录/元数据在线匹配增强

目标：

- 保留现有本地题录匹配
- 增加 PDF 前 1-3 页文本提取
- 调用 `DeepSeek` 抽取标题、作者、年份、期刊、DOI 等线索
- 基于线索做在线候选检索与评分
- 对高置信度结果自动补全，对中等置信度结果交由前端确认

为什么优先：

- 当前你明确说“先解决题录的问题”
- 后续参考文献目录质量、综述引用质量，都直接受元数据质量影响

当前建议顺序：

1. 先做 PDF 前 1-3 页提取
2. 再做 `DeepSeek` 结构化抽取
3. 再做在线候选匹配
4. 最后接前端人工确认

### 2.0 参考文献梳理标签页 + 引用关系入库

目标：

- 新增独立标签页，对单篇源 PDF 做参考文献梳理
- 提取参考文献目录并结构化
- 将正文引用文本与参考文献条目对齐
- 以表格形式展示结果
- 将参考文献题录导入"我的文献库"
- 建立源文献 → 被引文献关系，并把具体引用文本入库

为什么重要：

- 这是对现有"文献库 + 精读 + 对比"的一个上层增强能力
- 后续做引用网络、文献追踪、综述引用质量控制都会依赖这层数据

当前建议顺序：

1. 先封装新版 `DeepSeek` 调用与 Prompt
2. 先做"已有 PDF 文档"的尾部参考文献识别最小闭环
3. 再接"新上传 PDF 精读顺带识别"
4. 然后再做导入、重匹配和增强分析

当前补充判断：

- 识别链路不再继续以纯规则拆分为主，而改为"程序定位候选范围 + `deepseek-v4-flash` 结构化解析"
- 需要在提示词中明确忽略文末可能出现的英文摘要、附录、补充材料、致谢、作者简介等非参考文献内容

#### DeepSeek v4-flash 参考文献识别能力验证（2026-04-30）

测试脚本：`test_deepseek_references.py`
测试 PDF：`_uploads/1/` 下的真实论文（中英文各一）

**测试结论：DeepSeek v4-flash 满足方案要求，可以进入实施阶段。**

测试数据：

| 指标 | 中文 PDF（管理世界论文） | 英文 PDF（金融学论文） |
|---|---|---|
| DeepSeek 提取条目 | 38 | 27 |
| 旧规则拆分条目 | 2 | 3 |
| DeepSeek 提升倍数 | **19x** | **9x** |
| authors 覆盖率 | 100% | 100% |
| year 覆盖率 | 100% | 100% |
| title 覆盖率 | 100% | 100% |
| journal 覆盖率 | 100% | 96% |
| doi 覆盖率 | 0% | 0% |
| volume 覆盖率 | 29% | 44% |
| pages 覆盖率 | 29% | 48% |
| language 覆盖率 | 100% | 100% |
| ignore 误识别 | 0 | 0 |
| DB 写入测试 | 通过 | 通过 |

关键发现：

1. **标题识别率 100%**——完全解决了旧规则标题识别不稳定的痛点
2. **作者识别率 100%**——中文顿号分隔、英文逗号分隔均正确处理，含特殊字符也能还原
3. **无效内容零误识别**——DeepSeek 没有把尾部非参考文献内容错误标记为参考文献
4. **JSON 结构稳定**——每条输出都包含 `raw_text`、`authors`、`year`、`title`、`journal`、`ignore` 等必要字段
5. **数据库写入兼容**——输出结构可直接映射到 `bib_references` 表，无需额外转换
6. **缓存命中**——第二次调用同一 PDF 时 cache_hit 从 0 升至 1536，验证了缓存策略可行性
7. **DOI 覆盖率 0%**——测试 PDF 的 pypdf 提取文本中 DOI 信息本身缺失，非模型问题；使用 PaddleOCR 提取后预计会改善

需要关注的点：

- 当前 `pypdf` 文本提取在某些 PDF 上无法识别 "References" 标题（候选区长度为 0），需改善候选区定位逻辑
- 对于长参考文献列表，分块处理后第二块可能返回 0 条——需优化分块边界策略
- 单篇 PDF 处理耗时约 57-68 秒（含 API 调用），实际生产需异步化

#### 复杂 PDF 验证：多论文合辑 + 跨页参考文献（2026-04-30）

测试脚本：`test_complex_pdf.py`
测试 PDF：`_uploads/yaojiaquan.pdf`（《管理世界》2024 年第 2 期合辑 PDF，23 页）

**结论：DeepSeek 能正确处理多论文合辑 PDF 的参考文献混排，100% 提取 + 0% 误识别。**

PDF 结构复杂度：
- 两篇论文共用一个 PDF
- 目标论文参考文献 (1)-(49) 在第 15-16 页，被"下转第 133 页"标记打断
- 另一篇论文的参考文献 (34)-(45)、英文标题和摘要插在中间
- 目标论文续页参考文献 (50)-(52) 在第 17 页"上接第 116 页"标记后
- 附录含第二组参考文献 (1)-(4)，需排除

| 指标 | 结果 |
|---|---|
| 目标论文参考文献提取 | **52/52（100%）** |
| 另一篇论文参考文献泄露 | **0 条** |
| 附录参考文献混入 | **0 条** |
| 编号连续性 | 1-52 连续 |
| 关键修复 | 设置 `max_tokens=16384`（默认值导致截断 48/52） |

关键发现：

1. **必须显式设置 `max_tokens`**——默认值导致续页后 4 条参考文献被截断
2. **程序侧需清除续页标记**——"下转/上接第 X 页"标记需正则清除
3. **程序侧需预过滤噪音**——附录表格、英文摘要、期刊页眉等需过滤，减少候选文本行数（785→270）
4. **Prompt 需告知续页结构**——明确说明"续页后仍有参考文献"和预期条目数

#### 尾注法 PDF 验证（2026-04-30）

测试脚本：`test_complex_pdf.py`
测试 PDF：`_uploads/1/fc3fde00-...pdf`（《中国土地科学》2025 年第 11 期，11 页）

**结论：DeepSeek 天然支持尾注法（GB/T 7714 `［N］` 格式），无需额外适配。**

| 指标 | 结果 |
|---|---|
| 参考文献 | **40/40（100%）** |
| 误识别 | **0 条** |
| 跨英文摘要续页 | [38]-[40] 正确提取 |
| GB/T 7714 格式 | 正确解析 `[J]` 期刊标记 |

#### 全部验证汇总

| PDF 类型 | 文件 | 结果 | 误识别 |
|---|---|---|---|
| 中文尾注区 PDF | `1aff535f` | 38/38 | 0 |
| 英文尾注区 PDF | `976953fb` | 27/27 | 0 |
| 合辑 PDF（跨论文+续页） | `yaojiaquan` | 52/52 | 0 |
| 尾注法 PDF（GB/T 7714） | `fc3fde00` | 40/40 | 0 |

#### 正文引用追踪验证（2026-04-30）

测试脚本：`test_citation_tracing.py`
对比三种方案：纯正则、正则召回+LLM 核验、DeepSeek 全文直接追踪

**结论：DeepSeek 全文直接追踪是唯一在中英文都有效的方案，应替代现有纯正则方案。**

| 指标 | 中文 PDF | 英文 PDF |
|---|---|---|
| DeepSeek 全文追踪 hits | 9 | 8 |
| 有命中的文献数 | 7/10 | 6/10 |
| 纯正则 hits（含误匹配） | 13 | 24 |
| 正则+LLM 核验 hits | 10 | **0**（完全失效） |
| DeepSeek 发现描述性引用 | 是 | 是 |

关键发现：

1. **正则+LLM 核验在英文 PDF 上完全失效**（0 hits）——pypdf 提取文本质量不足以支撑核验
2. **DeepSeek 能发现正则找不到的描述性引用**（如 "according to Smith's study on..."）
3. **1M 上下文完全够用**——论文全文 20-40K tokens，远低于上限
4. **硬盘缓存策略可行**——参考文献识别和正文引用追踪共享正文前缀，第二次调用正文部分全部命中缓存
5. **输出可写入 `bib_reference_citations` 表**——quote 作为精确子串可定位 char_start/char_end

需要关注的点（新增 2026-05-03）：

- 当前验证的 4 个 PDF 均为**单栏排版**或 pypdf 可正常解码的类型
- **双栏 CJK 字体 PDF** 上 pypdf 文本提取完全失败（中文全部乱码），参考文献提取 0 条
- 该问题影响所有中文学术期刊双栏排版的 PDF，是 P0 上线的阻塞项

### 2.1 双栏 PDF 参考文献提取修复

**状态：已完成（2026-05-03）**

目标：

- 将 `deepseek_refs.py` 的文本提取层从 pypdf 切换为 pdfplumber
- 解决 CJK 自定义编码 PDF 的中文乱码问题
- 解决双栏布局 PDF 的文本阅读顺序问题
- 后续阶段复用 PaddleOCR 已提取的 markdown 文本，避免重复读取 PDF

实施内容：

- `extract_candidate_text()` 改用 pdfplumber，自动检测双栏并启用 `use_text_flow=True`
- `extract_body_text()` 同样改用 pdfplumber
- `extract_references_deepseek()` fallback 逻辑改用 pdfplumber
- `trace_citations_deepseek()` body_text 提取改用 pdfplumber
- 新增 `_is_two_column()` 双栏检测辅助函数
- 新增 `_extract_page_text()` 统一页面文本提取函数
- 移除 `from pypdf import PdfReader` 依赖

关联文档：[REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md](./REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md)

### 2.2 AI 综述模块重构（P2 参考文献兜底 + P3 提示词管理 + P4 引用锚点）

**状态：已完成（2026-05-11）**，P3 提示词管理未纳入。

#### 已完成的改动

**P2 — 参考文献目录兜底修复**

- `_safe_year()` 辅助函数统一处理 `None` 年份 → `"年份不详"`
- `format_cite_tag()` / `format_inline_citation()` 内部 None 兜底
- 全文 8 处 `dict.get('year', 'n.d.')` 替换为 `_safe_year()`
- `bib_entry_to_paper_data()` 补上 `volume/issue/pages` 字段
- `build_gbt7714_references()` 主要和二次引用均输出完整 GB/T 7714 格式（含年份、卷期、页码）
- 参考文献条目之间增加空行分隔
- 产物文件名改为 `综述-日期-主要作者.md`

**P4 — 综述引用锚点强化 + SSE 流式返回**

- `/synthesis` 和 `/synthesis_long` 改为 `StreamingResponse(media_type="text/event-stream")`
- 每个维度生成完立即推送 `event: dimension` 事件，前端逐维度显示
- 完成后推送 `event: complete`，出错推送 `event: error`
- 前端 3 个 HTML 文件（`compare_7step.html`、`compare_4step.html`、`compare_long.html`）改用 `fetch + ReadableStream` 读取
- 流式期间底部显示"综述中……"提示
- 维度内容不再截断（移除 `CONTENT_CHAR_LIMIT = 3000`），DeepSeek 支持百万上下文
- OpenAI client timeout 统一设为 300 秒，Vite proxy timeout 调至 10 分钟

**P3 — 文献综述提示词纳入提示词管理（未实施）**

- 将当前 `compare.py` 中硬编码的综述 prompt 迁入提示词管理
- 新增 `synthesis` 类型，支持系统默认 + 用户覆盖
- 建议槽位：`synthesis.system` / `synthesis.citation_guard` / `synthesis.compare_single` / `synthesis.compare_multi` / `synthesis.compare_cross` / `synthesis.long_single` / `synthesis.long_multi`

### 2.2.1 AI 综述二次引用目录过滤（P2.5）

**状态：已完成（2026-05-11）**

**方案**：综述正文全部维度拼接完成后，将正文 + 所有候选二次引用文献列表交给 DeepSeek，让它识别正文实际引用了哪些二次引用文献。

**实施**：

1. `_collect_flat_secondary_refs()` — 将 bib_refs 展平为编号列表
2. `_build_secondary_ref_check_prompt()` — 构建识别 prompt
3. 调用 `deepseek-v4-flash`（temperature=0.1, max_tokens=500），复用 `SYNTHESIS_SYSTEM_PROMPT` + `metadata_block` 前缀保持缓存命中
4. `_parse_cited_ref_ids()` — 解析返回的编号（S1,S3 等）
5. `_filter_bib_refs_by_indices()` — 按编号过滤 bib_refs
6. 过滤后的 bib_refs 传给 `build_gbt7714_references()`

**涉及文件**：`backend/routers/compare.py`

### ~~2.3 文献综述提示词纳入提示词管理~~

> 已合并至 2.2 节。

### ~~2.4 综述引用锚点强化~~

> 已合并至 2.2 节。

### 2.5 任务队列接入路由层 + 前端排队提示

**状态：已完成（2026-05）**

已完成：

- `backend/services/queue_manager.py`：`TaskQueueManager` 类（入队/出队/排队位置/预估等待/并发跟踪）+ `mark_running` 保留 `task_type`
- `backend/tests/test_queue_manager.py`：30 个单元测试全通过
- 支持 quant/qual/long/reference/filter 五种任务类型
- `backend/routers/reading.py`：三个 start 函数（long/quant/qual）已调用 `task_queue.enqueue()`，三个 worker 函数首尾调用 `mark_running()` / `mark_completed()`，`cancel_task` 亦调用 `mark_completed()`
- `backend/routers/reading.py`：`get_task_status` 已先查 `task_queue.get_task_queue_info(task_id)`，排队中返回 `status=queued` + `queue_position` + `estimated_wait_seconds/minutes`
- 前端 `App.tsx`：`applyStatus` 已处理 `status=queued`（progress=0、stage 显示排队信息、继续轮询）
- 前端 LongTab / QuantTab / QualTab：三个 Tab 均已添加蓝色排队 UI（`bg-blue-50` + `animate-pulse` 进度条）

### 2.6 用户数据一键导出/导入

**状态：已完成（2026-05）**

设计文档：[2026-05-06-user-data-export-import-design.md](./superpowers/specs/2026-05-06-user-data-export-import-design.md)

方案：JSON + 文件打包为 `.dra`（zip 格式），清空后导入策略。已实施：`data_portability.py` + `routers/data.py` + 前端入口。

### 2.8 批量精读（文件夹上传）（P3.5）

**状态：已完成（2026-05-11）**

**实施内容**：

- 后端 `reading.py` 新增 `BatchReadingRequest` 模型、`POST /batch/start` 和 `GET /batch/{batch_id}/status` 两个端点
- `POST /batch/start`：接收 `file_ids` + `mode`，循环为每个文件创建 Job 并设 `batch_id`，复用单篇精读的 `create_reading_job` + worker 线程
- `GET /batch/{batch_id}/status`：按 `Job.batch_id` 聚合查询所有 job 状态，返回 total/completed/failed/running/queued + 每篇 task 明细
- 前端三个精读 Tab（LongTab / QuantTab / QualTab）各增加「上传文件夹」按钮（`webkitdirectory`）、文件预览弹窗、`useBatchReadingTracker` hook 管理轮询状态、批量进度面板
- 前端错误处理：检查 `startRes.ok` + 校验 queued 计数，全部失败时抛出明确错误不再盲目轮询
- 修复 `create_reading_job` 后缺少 `await db.flush()` 导致 `scalar_one()` 抛 `NoResultFound` 的 bug

**关键决策**：
- 文件类型过滤：前端过滤 `.pdf/.md/.markdown`，递归子目录
- 重复处理：批量模式 `force_overwrite=true` 静默覆盖
- 进度展示：内联进度面板（当前第 N/M 篇 + 文件列表状态），每 2 秒轮询

无需 Alembic 迁移（`batch_id` 字段已存在于 `jobs` 表）。

### 2.9 对比页 AnswerCard 三按钮（P9）

**状态：设计完成，待实施**

设计文档：[2026-05-14-compare-card-actions-design.md](./superpowers/specs/2026-05-14-compare-card-actions-design.md)

#### 功能概述

在对比页（长文本/七步/四步）的每张 AnswerCard 上增加三个按钮：

1. **编辑/保存**：直接编辑维度文本，保存为覆盖层（不破坏原始 AI 精读结果），支持回退到原始
2. **点评**：进入点评模式后可选中文字高亮+写笔记，点评存入全局点评库
3. **AI 总结**：进入 AI 总结模式后可选中文字点击 AI 总结，三种子视图切换（只显示总结/只显示原文/同时显示）

#### 实施提示词（给明天的自己）

##### Step 1：数据库层（先做）

**1.1 新增两张表 — `backend/db/models.py`**

- `ReadingItemEdit`：`reading_item_id`(FK+CASCADE) + `owner_user_id`(FK) + `edited_content`(TEXT) + `created_at` + `updated_at`，UNIQUE(item_id, owner_user_id)
- `Annotation`：`id`(UUID TEXT PK) + `owner_user_id`(FK) + `source_type`(CHECK 'compare_card','ai_summary','library_note') + `source_id`(TEXT) + `bib_entry_id`(TEXT nullable) + `selected_text`(TEXT nullable) + `note`(TEXT NOT NULL) + `char_start`/`char_end`(INT nullable) + `is_ai_generated`(INT default 0) + `color`(TEXT nullable) + `created_at` + `updated_at`

**1.2 Alembic 迁移脚本**

- 文件：`backend/migrations/versions/012_add_edits_and_annotations.py`（编号接当前最新）
- 创建两张表及索引

**1.3 PromptTemplate CHECK 约束**

- `models.py` 的 `PromptTemplate` 的 `prompt_type` CHECK 约束需加入 `'compare'`
- 同步写 Alembic 迁移修改约束（或放在同一个迁移脚本里）

**1.4 级联清理**

- `cleanup.py` 的 `cleanup_expired()` 中增加：`reading_item_edits` 跟随 `reading_items` ON DELETE CASCADE 自动处理；`annotations` 按 `owner_user_id` 匹配过期用户清理
- 数据导入导出 `data_portability.py`：导出/导入时包含这两张表

##### Step 2：后端 API（再写路由）

**2.1 编辑覆盖 API — 加在 `compare.py`**

- `PUT /api/compare/reading-items/{item_id}/edit` — 权限校验：reading_item.owner_user_id == user.id
- `DELETE /api/compare/reading-items/{item_id}/edit` — 同上

**2.2 点评 CRUD API — 新建 `backend/routers/annotations.py`**

独立 router，因为 annotations 是全局资源：

- `POST /api/annotations` — 创建
- `GET /api/annotations` — 查询（query: source_type?, source_id?, is_ai?, bib_entry_id?）
- `PUT /api/annotations/{id}` — 更新
- `DELETE /api/annotations/{id}` — 删除
- 记得到 `main.py` 注册 router

**2.3 AI 总结 API — 加在 `compare.py`**

- `POST /api/compare/ai-summary` — 接收 `{ text, api_key, reading_item_id, bib_entry_id?, char_start?, char_end? }`
- 从 `prompt_service.get_effective_prompt_map('compare')` 获取 `ai_summary` 提示词
- 替换 `{selected_text}` 占位符
- 调用 `deepseek-v4-flash`（复用 compare.py 中已有的 OpenAI client）
- 创建 `annotations` 记录（`is_ai_generated=1`, `source_type='ai_summary'`）
- 返回 `{ summary, annotation_id }`

**2.4 修改现有 `GET /api/compare/reading-data`**

在 `compare.py` 的 `get_reading_data()` 和 `build_compare_response()` 中：

- 查询同一批 `reading_item_id` 的 `ReadingItemEdit`
- 查询同一批 `reading_item_id` 的 `Annotation`（source_type IN ('compare_card', 'ai_summary')）
- 在响应的每个维度项中增加 `edit: { edited_content } | null` 和 `annotations: [...]` 字段

**⚠️ 改完 compare.py 务必验证路由完整性**：`python -c "from backend.routers.compare import router; [print(r.path) for r in router.routes]"`

##### Step 3：提示词管理

**3.1 `backend/prompt_registry.py`**

- `PROMPT_REGISTRY` 新增 `"compare"` 类型，含 `"ai_summary"` 槽位
- `PROMPT_TYPE_LABELS` 新增 `"compare": "对比分析"`

**3.2 提示词文件**

- 创建 `prompts/compare/ai_summary.md`，内容见设计文档 5.2 节

**3.3 `prompt_service.py`**

- `ensure_builtin_prompt_templates()` 会自动处理新槽位（幂等导入），无需额外改动

##### Step 4：前端（最后做）

**4.1 `useCompareData.ts`**

- `DimItem` 接口增加 `edit?: { edited_content: string } | null`
- `DimItem` 接口增加 `annotations?: Annotation[]`
- 新增 `Annotation` 接口定义

**4.2 `AnswerCard.tsx` — 核心改动，最大工作量**

新增状态：`cardMode: 'normal' | 'editing' | 'annotating' | 'ai_summarizing'`、`aiDisplayMode`、编辑文本、选区状态等

- 普通模式：右上角三个图标按钮（笔/气泡/闪电），有编辑覆盖时显示「已编辑」小标签
- 编辑模式：内容变 textarea，底部「保存」「回退到原始」「取消」
- 点评模式：渲染高亮标注（用 `<mark>` 包裹 selected_text 片段），mouseup 检测 Selection 弹出浮窗
- AI 总结模式：顶部切换条（三个 radio/pill），选中文字后出现「总结」按钮

关键实现技巧：
- 高亮渲染：将 Markdown 文本按 annotations 的 char_start/char_end 拆分，非高亮部分正常 md2html，高亮部分包裹 `<mark class="compare-annotation-highlight">`
- 文字选择：监听 `mouseup` 事件，用 `window.getSelection()` 获取选中文本和位置
- 模式管理：AccordionPanel 管理 `cardModes` 状态，每张卡片独立持有模式；支持维度级批量切换（header 三按钮）和单卡独立切换
- char_start/char_end 失效处理：如果存在 edit 覆盖，标注按 `selected_text` 做文本匹配而非偏移定位

**4.3 `AccordionPanel.tsx`**

- 新增 props：`apiKey`、`onModeChange` 回调
- 管理 `cardModes: Record<string, CardMode>`，每张卡片独立模式
- 维度 header 三按钮（编辑/点评/AI总结）批量切换，单卡按钮独立切换
- 传递给 AnswerCard：`isActive`（derived from cardModes）、`cardMode`、`onModeChange`

**4.4 `compare.css`**

所有新样式在 `.compare-root` 作用域下：
- `.compare-root .card-action-bar` — 按钮栏
- `.compare-root .card-edit-area` — textarea
- `.compare-root .compare-annotation-highlight` — 高亮
- `.compare-root .annotation-popup` — 点评浮窗
- `.compare-root .ai-display-switch` — AI 子视图切换条
- `.compare-root .ai-summary-item` — 总结条目
- keyframes 加 `compare-` 前缀

**4.5 `App.tsx` PromptsTab**

- `promptType` 选项增加 `compare`（类型下拉出现「对比分析」）

#### 实施顺序

1. `models.py` + Alembic 迁移（两张新表 + PromptTemplate CHECK 约束加 'compare'）
2. `prompt_registry.py` + `prompts/compare/ai_summary.md`
3. `compare.py`：修改 `get_reading_data` + 新增 edit 端点 + 新增 ai-summary 端点
4. 新建 `annotations.py`：CRUD 端点 + `main.py` 注册 router
5. `cleanup.py`：annotations 清理逻辑
6. `data_portability.py`：导出/导入两张新表
7. 前端 `useCompareData.ts`：扩展数据接口
8. 前端 `AnswerCard.tsx` + `AccordionPanel.tsx` + `compare.css`
9. 前端 `App.tsx` PromptsTab：新增 compare 类型
10. 端到端测试 + router 完整性验证

### 2.7 Playwright E2E + 部署验收

目标：

- 为核心登录、上传、筛选、精读、对比、文献库、提示词管理补最终验收测试
- 完成部署前的本地收口与验收准备

当前不优先的原因：

- 仍有交互和元数据链路在迭代
- 现在启动 E2E 容易反复推翻测试用例

### 2.10 前端 ESLint 规则分级治理

**状态：已发现规则基线问题，待规划实施。**

背景：

- 当前 `frontend/eslint.config.js` 启用了 `@eslint/js`、`typescript-eslint`、`eslint-plugin-react-hooks`、`react-refresh` 的 recommended 配置。
- `npm run lint` 会被大量既有代码阻断，已观察到约 150 个 error / 5 个 warning。
- 主要集中在 `react-hooks/set-state-in-effect`、`@typescript-eslint/no-explicit-any`、`no-unused-vars`、`react-refresh/only-export-components`、`preserve-caught-error` 等规则。
- 其中一部分更像规则分级或框架演进带来的基线问题，不应在数据库迁移、业务功能上线等分支中顺手大范围修改。

未来治理方向：

1. 先盘点规则来源与风险等级，把规则分成三类：必须阻断构建的真实错误、应逐步修复的可维护性问题、暂不适合当前代码库的建议类规则。
2. 短期将 React Compiler/React Hooks 建议类规则降为 warning 或局部关闭，保留语法错误、未定义变量、明显类型错误等高价值 error。
3. 中期单独开 `codex/frontend-lint-baseline` 分支，分批清理 `any`、未使用变量、异常处理等低风险问题。
4. 长期恢复更严格的 lint 门禁，并在 CI/上线前明确区分 `lint:strict` 与 `lint:baseline`，避免未来规则升级再次阻断全项目。

不在当前 PostgreSQL/Redis 迁移分支处理，避免污染数据库迁移 diff。

### 2.11 Online 页面提供打包版下载

**状态：方案 B 已确定，待 online 分支实施。**

背景：

- 当前 Windows 打包产物已上传到阿里云 OSS：`oss://lxj-pdf-upload/releases/DeepReadingAgent-Web-2026-05-18.zip`。
- 私有 bucket 的签名 URL 有有效期，不适合把 7 天链接直接硬编码到 online 前端页面。
- 若使用公共读固定链接，维护简单但会暴露下载入口，存在流量费用与转发风险。

推荐方案：

1. online 后端新增获取下载链接接口，例如 `GET /api/download-app/windows`。
2. 服务器环境变量配置 OSS 信息与对象路径：
   - `ALIYUN_OSS_ENDPOINT=https://oss-cn-wuhan-lr.aliyuncs.com`
   - `ALIYUN_OSS_BUCKET=lxj-pdf-upload`
   - `ALIYUN_OSS_APP_OBJECT=releases/DeepReadingAgent-Web-2026-05-18.zip`
   - `ALIYUN_ACCESS_KEY_ID`
   - `ALIYUN_ACCESS_KEY_SECRET`
3. 后端接口即时生成短期签名 URL，建议有效期 1 小时到 24 小时。
4. 前端 online 页面增加“下载 Windows 打包版”按钮，点击后请求该接口并跳转到返回的签名 URL。
5. AccessKey 只放服务器环境变量，禁止进入前端 bundle、仓库文件或文档示例真实值。

实施边界：

- 当前 `packaging` 分支只记录方案，不直接实现 online 下载入口。
- 后续切到 `online` 分支后再补后端接口、前端按钮与服务器环境变量配置。

后续换包方式：

- 上传新 zip 到 `releases/` 目录，文件名带版本或日期。
- 更新服务器环境变量 `ALIYUN_OSS_APP_OBJECT` 指向新对象。
- 无需修改前端静态链接，也无需每 7 天重新部署。

### 2.12 七步/四步小问题对比解析稳健性

**状态：已定位，待修复。**

现象：

- 导入 `export_20260510_test002.dra` 后，七步/四步对比页能显示小问题级卡片。
- 导入 `export_20260516_test001.dra` 后，只能显示七步/四步的大 step 维度。

已验证差异：

- `export_20260510_test002.dra` 的 `reading_items` 中包含 `quant/qual` 的 `subquestion` 记录，例如 `quant.step1.q1`。
- `export_20260516_test001.dra` 的 `reading_items` 中 `quant` 只有 49 条 `step`，`qual` 只有 20 条 `step`，没有任何 `subquestion`。

根因：

- 当前 `parse_markdown_numbered_sections()` 只识别很窄的标题格式：七步 `### **1. 标题**`，四步 `## 1. 标题`。
- 2026-05-16 那批模型输出格式漂移为 `#### 1.1 标题`、`#### 1. 标题`、`### 一、标题`、`## Step 4: ...` 等，导致入库阶段没有拆出小问题。

修复方向：

1. 放宽后端小问题解析器，支持多种 Markdown 标题格式，并生成稳定 item_key。
2. 对历史只有 `step` 的 `ReadingItem` 提供补齐逻辑：从 step content 重新拆出 `subquestion` 并入库。
3. 强化七步/四步提示词格式要求，但不能只依赖模型严格遵守。

优先级判断：

- 该问题会影响新精读入库质量，也影响历史 `.dra` 修复，建议排在 P9 对比页大功能之前处理。

### 2.13 对比页 AI 总结选中文本未进入提示词

**状态：打包路径已修复，待重新打包与干净数据目录验证。**

现象：

- 对比页卡片进入 AI 总结模式后，选中文字并点击“AI总结”，DeepSeek 返回类似“请提供您需要总结的学术文本片段”的提示。
- 说明前端交互能进入 AI 总结链路，但最终发给模型的 prompt 中没有包含实际选中文字。

已验证：

- 前端 `AnswerCard.tsx` 会把选中文字作为 `text` 字段 POST 到 `/api/compare/ai-summary`。
- 后端 `compare.py` 会读取 `body["text"]`，并执行 `payload.effective_content.replace("{selected_text}", text)`。
- 源码开发库 `db/app.sqlite` 中 `compare.ai_summary` 系统提示词包含 `{selected_text}`。
- 打包产物数据目录 `dist/DeepReadingAgent/data/db/app.sqlite` 中同一条系统提示词缺少 `{selected_text}`，内容是旧 fallback：只要求总结“用户选中的学术文本片段”，但没有把片段插进去。

根因：

- 旧打包产物运行时 `PROJECT_ROOT` 指向错误位置，导致 `prompt_registry` 找不到已经打进包内的 `prompts/compare/ai_summary.md`。
- 提示词文件找不到时，初始化逻辑走 `get_builtin_fallback()`，把缺少 `{selected_text}` 的旧 fallback 写入打包版数据库。
- 这不是前端未发送选中文字；选中文字已经进入 `/api/compare/ai-summary` 请求，但错误提示词没有占位符，后端 `.replace("{selected_text}", text)` 无命中。
- 新提交 `426f8d2d fix(packaging): use sys._MEIPASS for PROJECT_ROOT in frozen builds` 已将 frozen 环境下的资源根目录改为 `sys._MEIPASS`，应能正确读取包内 `prompts/`。

验证方向：

1. 用包含 `426f8d2d` 的代码重新执行 `python build_web_dist.py`。
2. 使用干净的打包数据目录启动，确认新建的 `compare.ai_summary` 系统提示词来自 `prompts/compare/ai_summary.md` 且包含 `{selected_text}`。
3. 在本地打包产物中登录、进入对比页、选中文字并执行 AI 总结，确认模型收到真实选中文本。
4. 若需要兼容已经生成过错误提示词的旧数据目录，再单独评估一次性修复脚本或提示词重置入口。

## 3. 建议实施顺序

建议后续按下面顺序推进：

1. ~~`双栏 PDF 参考文献提取修复`~~（已完成 2026-05-03）
2. ~~`参考文献梳理标签页 + 引用关系入库`~~（已完成 2026-05）
3. ~~`PDF 题录/元数据在线匹配增强`~~（已完成 2026-05-03）
4. ~~`任务队列接入路由层 + 前端排队提示`~~（已完成 2026-05）
5. `对比页 AI 总结选中文本未进入提示词`（P13，路径修复已提交，需重新打包并用干净数据目录验证）
6. `七步/四步小问题对比解析稳健性`（P12，先修解析器和历史补齐，再做更大的对比页交互）
7. `Online 页面提供打包版下载`（P11，切到 online 分支实施后端签名 URL 接口与前端下载按钮）
8. `文献综述提示词纳入提示词管理`（P3，作为 AI 综述模块剩余项单独推进）
9. `对比页 AnswerCard 三按钮 — 编辑/点评/AI总结`（P9，设计完成，实施工作量约 2 天）
10. `Playwright E2E + 部署验收`（P7）

## 4. 待补充区域

后续如果你有新想法，建议按下面格式追加：

| 优先级 | 事项 | 当前状态 | 前置依赖 | 关联文档 | 备注 |
|---|---|---|---|---|---|
| PX | 待补充事项 | 已讨论/待规划/已规划 | 无/依赖某项 | 文档路径 | 补一句目的即可 |

## 5. 当前说明

本文件是“计划表”，不是实施记录。

后续当某个计划开始进入真实实施或实施中途发生范围变化时，需同步实时更新以下基础文档，避免规划、代码与维护文档脱节：

- `docs/DATABASE_SCHEMA.md`
- `docs/FUNCTION_INDEX.md`
- `docs/STATE_AND_API_MAP.md`
- `docs/TECHNICAL_OVERVIEW.md`

更新原则：

- 涉及数据库表 / 字段 / 关系变化时，立即更新 `DATABASE_SCHEMA.md`
- 涉及关键入口函数、主流程函数、核心组件函数变化时，立即更新 `FUNCTION_INDEX.md`
- 涉及前端状态、后端 API、数据库映射变化时，立即更新 `STATE_AND_API_MAP.md`
- 涉及整体架构、模块职责、数据流变化时，立即更新 `TECHNICAL_OVERVIEW.md`

当前不在这里写：

- 已完成功能
- 临时测试结果
- 本地运行日志
- git 提交信息

这些内容继续分别记录在：

- `MULTIUSER_PROGRESS.md`
- 专项规划文档
- 测试与实现记录
