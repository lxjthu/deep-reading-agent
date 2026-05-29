# Research Agent 整改实施任务清单

> 最后更新：2026-05-28
> 关联总方案：[RESEARCH_AGENT_UPGRADE_PLAN.md](RESEARCH_AGENT_UPGRADE_PLAN.md)
> 关联实现文档：[RESEARCH_AGENT_IMPLEMENTATION.md](RESEARCH_AGENT_IMPLEMENTATION.md)
> 文档定位：把整改总方案拆成可执行任务清单，按 `P0/P1/P2`、模块、文件、接口、测试与验收标准组织。本文不是完成记录，所有条目默认为待实施。

---

## 1. 使用说明

本文用于指导后续真正实施 Research Agent 整改。推荐使用方式：

1. 先看 [RESEARCH_AGENT_UPGRADE_PLAN.md](RESEARCH_AGENT_UPGRADE_PLAN.md)，理解为什么要改、整体目标是什么。
2. 再看本文，确认本轮要做哪一个优先级、改哪些文件、增加哪些测试、如何验收。
3. 每做完一个任务，再回写实现文档和测试结果，不要直接把本文条目标记成“已完成”。

约束原则：

- 不以“多加几个工具”替代运行时重构。
- 先解决稳定性、意图理解、工作记忆和预算治理，再扩工具覆盖。
- 所有联网与写库能力都必须走明确边界，不能只靠 prompt 约束。

---

## 2. 优先级总览

| 优先级 | 主题 | 目标 | 预计收益 |
|---|---|---|---|
| P0 | 稳定性与观测 | 让 Agent 失败时可诊断、可降级、可解释 | 立刻改善线上可用性 |
| P1 | Runtime 中枢 | 建立 TaskFrame、状态机、工作记忆、预算治理 | 直接解决听不懂、幻觉、空转 |
| P2 | 外部检索与 UI | 联网授权、外部证据、结果集 UI、证据表格 | 提升可控性和可解释性 |
| P3 | 工具覆盖扩展 | compare/translation/reference/cards 等纳入 runtime | 扩大能力边界 |
| P4 | 性能优化 | FTS/chunk/source window 性能提升 | 提升大库和复杂任务体验 |

推荐里程碑顺序：

1. `P0.1-P0.4`
2. `P1.1-P1.8`
3. `P2.1-P2.6`
4. `P3.x`
5. `P4.x`

---

## 3. P0：稳定性与可观测性

### P0.1 统一 Agent 错误分类

目标：

- 把当前粗粒度的 500/502/报错字符串，拆成稳定的错误类型和前端可消费的错误码。

重点文件：

- `backend/routers/agent.py`
- `backend/utils/llm_provider.py`
- `frontend/src/App.tsx`
- `frontend/src/components` 下 AI 助手相关 UI

实施任务：

1. 统一定义错误类型枚举：
   - `provider_auth_error`
   - `provider_upstream_5xx`
   - `provider_timeout`
   - `tool_execution_error`
   - `agent_runtime_error`
   - `upload_error`
   - `consent_missing`
   - `budget_exhausted`
   - `context_resolution_failed`
2. 将 `agent_chat` 中的异常捕获从“直接转字符串”改为结构化 payload。
3. SSE 的 `error` 事件统一输出：
   - `code`
   - `message`
   - `retryable`
   - `stage`
   - `details`（必要时）
4. 前端按错误类型展示差异化提示，不再统一显示“AI 助手失败”。

验收标准：

- 用户可以区分 key 配置错、provider 挂了、上传失败、runtime bug。
- 控制台和接口日志里，错误类型可聚合统计。

建议测试：

- 模拟无效 key。
- 模拟 provider 500/超时。
- 模拟工具内部异常。
- 模拟上传失败。

---

### P0.2 API Key / Provider 检测与前端提示

目标：

- 降低“明明保存了 key 却不可用”的误诊成本。

重点文件：

- `frontend/src/App.tsx`
- `backend/utils/llm_provider.py`
- `backend/routers/agent.py`

实施任务：

1. 在前端设置 API Key 时，增加“测试连接”动作。
2. 对 `sk-` 的 provider 选择给出更明确提示。
3. 保存时把 `provider + raw_key` 的状态展示清楚。
4. 后端增加轻量 `provider ping` 能力，返回模型可达性与错误类型。
5. 前端显示最近一次检测状态与时间。

验收标准：

- 用户看到的是“DeepSeek key 无效”或“MiMo 上游异常”，而不是笼统失败。
- provider 选错时，前端能明显提醒。

建议测试：

- 正确 key + 正确 provider。
- 正确 key + 错误 provider。
- key 正确但 provider 上游 502。

---

### P0.3 inbox 上传链路排查与恢复

目标：

- 让 `upload-folder` 失败时至少可定位、可解释、可重试。

重点文件：

- `backend/routers/agent.py`
- `backend/db/models.py`
- `frontend/src/App.tsx`

实施任务：

1. 梳理 `/api/agent/inbox/upload-folder` 的完整链路：
   - multipart 接收
   - 文件落盘/持久化
   - batch 记录保存
   - agent preferences 更新
2. 在关键步骤增加结构化日志。
3. 细化上传失败提示，不再把服务错误表现成“未选择文件/没有文件”。
4. 明确上传成功后的 batch 状态对象格式，供后续 `scan_input_folder` 使用。

验收标准：

- 上传失败时，开发可从日志快速定位。
- 用户可以知道是服务异常，不会被误导为“当前没有文件可扫”。

---

### P0.4 Tool Trace 与调试摘要

目标：

- 降低“Agent 看起来在忙，但不知道到底做了什么”的黑箱感。

重点文件：

- `backend/routers/agent.py`
- `frontend/src/App.tsx`

实施任务：

1. 为每轮会话生成更稳定的 `tool trace summary`。
2. 每次工具调用记录：
   - 规范化后的参数摘要
   - 是否命中
   - 是否空结果
   - 是否被 budget policy 截断
3. 在前端新增轻量摘要区，而不是只展示原始 JSON。

验收标准：

- 用户能看懂“搜了什么、为什么停下、下一步需要什么”。

---

## 4. P1：Runtime 中枢重构

### P1.1 新增 TaskFrame

目标：

- 把自然语言输入转换成结构化任务，作为 runtime 的第一步。

建议新增文件：

- `backend/services/research_task_frame.py`

需要联动的文件：

- `backend/routers/agent.py`
- `backend/services/agent_tool_registry.py`

任务拆分：

1. 定义 `TaskFrame` 数据结构。
2. 定义基础意图枚举：
   - `library_lookup`
   - `evidence_question`
   - `compare_entries`
   - `summarize_topic`
   - `find_fulltext`
   - `cnki_search`
   - `check_status`
   - `start_job`
3. 支持 continuation 语义标记：
   - `same_result_set`
   - `selected_entries`
   - `named_result_set`
   - `explicit_entry_ids`
4. 对模糊输入输出 `ambiguities` 列表。

验收标准：

- Runtime 能在真正调用工具前先拿到结构化任务对象。
- “继续上一轮这些文献”不会直接走自由工具调用。

建议测试：

- 普通查库问题。
- 承接上一轮结果集的问题。
- 模糊追问与歧义输入。

---

### P1.2 新增 Session Working Memory

目标：

- 让会话状态从“文本历史”升级为“可执行工作记忆”。

建议新增文件：

- `backend/services/research_session_state.py`

需要联动的文件：

- `backend/routers/agent.py`
- `backend/db/models.py`（如需持久化字段调整时再评估）

任务拆分：

1. 设计统一 state schema：
   - `active_task_frame`
   - `last_result_set`
   - `named_result_sets`
   - `selected_entries`
   - `last_evidence_pack`
   - `pending_external_consent`
   - `pending_proposal`
   - `recent_tool_trace`
   - `budget_snapshot`
2. 封装 state 读写辅助函数，不再在 router 内零散更新 JSON。
3. 引入 version 字段，方便后续 state schema 演进。

验收标准：

- 当前会话拥有稳定的结构化工作状态。
- 不再需要从 message 文本里回推上一轮结果。

---

### P1.3 Result Set 对象化

目标：

- 把“上一轮搜出来的文献集合”变成正式对象，而不是临时文本。

建议新增内容：

- `research_session_state.py` 中的 `ResultSet` 结构

需要联动的文件：

- `backend/routers/agent.py`
- `backend/services/research_retrieval.py`
- 前端 AI 助手结果展示组件

任务拆分：

1. 设计 `ResultSet` 字段：
   - `result_set_id`
   - `source_tool`
   - `query_summary`
   - `entry_ids`
   - `titles`
   - `count`
   - `scope_label`
   - `created_at`
   - `expires_at`
2. 本地检索成功后自动创建 result set。
3. 会话中允许引用最近 result set 和命名 result set。

验收标准：

- 用户说“刚才那 11 篇”时，系统能稳定解析到结果集。

---

### P1.4 Continuation Resolver

目标：

- 解决跨轮代词承接与集合承接问题。

建议新增能力：

- `resolve_context_refs()` 解析器

重点文件：

- `backend/services/research_session_state.py`
- `backend/services/research_task_frame.py`
- `backend/services/research_agent_runtime.py`

任务拆分：

1. 先解析 `selected_entries`。
2. 再解析 `last_result_set`。
3. 再解析 `named_result_sets`。
4. 最后尝试 `last_evidence_pack`。
5. 若都失败，进入澄清，而不是让模型猜。

验收标准：

- 不再出现凭空构造 `entry_ids` 的问题。
- 代词追问需要时能稳定触发澄清。

---

### P1.5 Runtime 状态机

目标：

- 用显式状态机替代“LLM 自由循环 tool calls”。

建议新增文件：

- `backend/services/research_agent_runtime.py`

状态建议：

- `understand`
- `resolve_context_refs`
- `retrieve_local`
- `assess_sufficiency`
- `ask_clarification`
- `request_external_consent`
- `retrieve_external`
- `merge_evidence`
- `synthesize_answer`
- `prepare_proposal`
- `execute_confirmed_action`
- `finish`

任务拆分：

1. 把 `agent_chat` 的主循环逻辑下沉到 runtime。
2. router 只保留：
   - 请求校验
   - session 读写入口
   - SSE 输出
3. runtime 决定每个阶段允许哪些工具。
4. runtime 决定什么时候停止，而不是只看有没有 tool_calls。

验收标准：

- 同类问题路径更稳定。
- agent 不再轻易“走偏后一直偏”。

---

### P1.6 Sufficiency Engine

目标：

- 检索完成后先判断“够不够回答”，再决定是否继续检索或申请联网。

建议新增文件：

- `backend/services/research_sufficiency.py`

判断维度：

- `evidence_count`
- `entry_coverage`
- `tier_distribution`
- `conflict_level`
- `scope_confidence`
- `question_type`

输出建议：

- `sufficient`
- `partially_sufficient`
- `insufficient`
- `conflicted`
- `needs_user_choice`

验收标准：

- 证据不足时不会直接编答案。
- 证据已够时不会继续浪费轮次。

---

### P1.7 Budget Policy

目标：

- 用预算治理替代简单的 `MAX_TOOL_ROUNDS`。

建议新增文件：

- `backend/services/tool_budget_policy.py`

预算类型：

- `planner_budget`
- `local_search_budget`
- `external_budget`
- `proposal_budget`
- `duplicate_call_guard`

关键规则：

1. 相同工具 + 相似参数连续空结果超过阈值则熔断。
2. `search_library` 失败多次后必须切换策略或澄清。
3. 外部检索默认每轮只开一个分支。
4. proposal 每轮只允许一个主 proposal。

验收标准：

- 不再轻易出现一连串空搜把预算烧完。
- 预算停止时有结构化摘要，而不是只有“上限到了”。

---

### P1.8 Tool Adapter 层

目标：

- 把参数归一化、权限与预算检查从 prompt 中拿出来。

建议改造文件：

- `backend/services/agent_tool_registry.py`
- `backend/routers/agent.py`
- 新 runtime 文件

任务拆分：

1. 为工具加 adapter 层：
   - wildcard 归一化
   - 默认值修正
   - consent 检查
   - budget 检查
   - duplicate 检查
2. 把 `*` 的支持范围显式收敛。
3. 对不合法的 `entry_ids` 先做格式和所有权校验。

验收标准：

- 运行时层能在工具真正执行前做兜底和修正。

---

## 5. P2：联网授权、外部证据与前端解释性

### P2.1 External Consent Ticket

目标：

- 让外部检索从“prompt 约束”升级为“runtime 票据门禁”。

建议新增文件：

- `backend/services/external_retrieval_policy.py`

票据字段：

- `ticket_id`
- `allowed_tools`
- `allowed_query`
- `allowed_entry_ids`
- `created_at`
- `expires_at`
- `scope`

验收标准：

- 没票据时外部工具不能执行。
- 授权范围清晰可见。

---

### P2.2 外部证据容器

目标：

- 把 P3 外部结果作为临时 evidence 管理，而不是和本地证据混淆。

任务拆分：

1. 为外部结果建立统一结构：
   - 来源
   - URL
   - 抓取时间
   - 关联 entry_id/result_set
   - 是否仅临时
2. 前端明确显示为 P3。
3. 默认不写入 bib_entries、notes、artifacts。

验收标准：

- 用户一眼能看出哪些信息来自外部临时线索。

---

### P2.3 CNKI 工具第二阶段增强

目标：

- 从“只给 URL”升级到“授权后可做结构化抓取”。

重点文件：

- `backend/services/agent_external_retrieval.py`

任务拆分：

1. 保留当前 URL 生成能力。
2. 增加结构化检索结果抓取接口设计。
3. 明确抓取结果默认仅进入外部 evidence，不直接改库。

验收标准：

- 中文文献检索不再只是“打开一堆标签页”。

---

### P2.4 英文全文候选与 attach proposal 分离

目标：

- 明确区分“查候选”和“绑定候选”。

任务拆分：

1. 将现有全文检索路线拆为：
   - `lookup_fulltext_candidates`
   - `attach_fulltext_candidate`
2. 查候选属于外部只读。
3. attach 必须 proposal-first。

验收标准：

- 不会因为“查一下全文”就隐式改库。

---

### P2.5 Result Set UI 与 Evidence Table

目标：

- 让用户能看见当前工作对象和证据基础。

重点文件：

- `frontend/src/App.tsx`
- AI 助手相关组件

任务拆分：

1. 新增 `Result Set Card`。
2. 新增 `Evidence Pack Table`。
3. 新增 `Tier Badge`。
4. 新增“为什么停下”的摘要区。

验收标准：

- 用户知道系统当前基于哪组文献、哪层证据回答。

---

### P2.6 Provider 状态与联网确认面板

目标：

- 把外部检索和 provider 状态显式化。

任务拆分：

1. UI 展示 provider 当前状态。
2. 外部检索前显示 consent panel：
   - 为什么需要联网
   - 将访问哪些来源
   - 结果默认不会入库
3. 错误时明确区分 provider 层和 agent 层。

验收标准：

- 用户不再把“上游模型挂了”和“智能体逻辑差”混在一起。

---

## 6. P3：工具覆盖扩展

这一层只在 P0/P1 基本稳定后再推进。

### P3.1 compare / synthesis 接入 runtime

目标：

- 让 compare 和 synthesis 不再作为旁路能力存在。

重点文件：

- `backend/routers/compare.py`
- `frontend/src/components/CompareView.tsx`
- runtime 层

任务：

1. 接入 compare 读能力。
2. 接入 synthesis proposal / execution。
3. 与 result set 和 evidence pack 联动。

---

### P3.2 translation / references / cards / annotations 接入 runtime

目标：

- 把目前系统已有的重要研究工具统一纳入 runtime。

重点文件：

- `backend/routers/translation.py`
- `backend/routers/references.py`
- cards/annotations 相关 router 和 service

任务：

1. 先纳入只读能力。
2. 再纳入 proposal-first 写能力。
3. 统一纳入证据和工作记忆模型。

---

## 7. P4：性能优化与检索加速

### P4.1 source windows 与原文 chunk 检索

目标：

- 提升大文档、多轮证据抽取性能。

候选方向：

- `source_text_chunks`
- SQLite FTS5 / PostgreSQL FTS
- lexical chunk index

约束：

- 不引入 embedding/vector。
- 若新增缓存表，需明确是否纳入 `.dra` 导出体系。

---

## 8. 每轮实施的推荐顺序

如果按 1-2 周一个小周期推进，建议顺序如下：

### Sprint A

- `P0.1` 错误分类
- `P0.2` provider 检测
- `P0.4` tool trace 摘要

### Sprint B

- `P1.1` TaskFrame
- `P1.2` Session Working Memory
- `P1.3` Result Set

### Sprint C

- `P1.4` Continuation Resolver
- `P1.5` Runtime 状态机
- `P1.6` Sufficiency Engine

### Sprint D

- `P1.7` Budget Policy
- `P1.8` Tool Adapter
- `P2.1` External Consent Ticket

### Sprint E

- `P2.2-P2.6`
- 小范围纳入 `P3.1`

---

## 9. 测试清单模板

每完成一个大项，至少补以下测试维度：

### 单元测试

- TaskFrame 解析
- ResultSet 生成与引用
- Continuation Resolver
- Sufficiency 判定
- Budget 熔断
- consent gate 拦截

### 集成测试

- 本地查库 -> result set -> 追问总结
- 本地证据不足 -> 请求联网授权
- proposal-first 执行
- provider 错误降级
- upload-folder 错误提示

### 手工回归

- 空文献库
- 已有 50+ 文献的大库搜索
- 多轮追问
- 中文 CNKI 检索
- 英文全文候选查看
- 提案确认与拒绝

---

## 10. 首个落地版本的定义

如果要定义一个“先上线、先见效”的最小整改版本，建议目标不是功能最全，而是下面四件事成立：

1. 会听上下文：
   - 能稳定承接上一轮结果集。
2. 不乱编对象：
   - 不凭空构造 entry_ids、标题集合、引用对象。
3. 不乱烧轮次：
   - 遇到重复空查会切换策略或请求澄清。
4. 不乱联网：
   - 所有外部检索都要走明确授权。

只要这四件事做稳，Research Agent 的主观体验就会明显提升，后续再扩 compare/translation/reference/cards 的收益才会放大。

---

## 11. 文档更新规则

后续实施时，建议遵循以下文档规则：

1. 本文只维护“待做清单”和实施优先级。
2. 已完成内容写入 [RESEARCH_AGENT_IMPLEMENTATION.md](RESEARCH_AGENT_IMPLEMENTATION.md)。
3. 如果某个阶段范围变大，再拆专项文档，例如：
   - `RESEARCH_AGENT_RUNTIME_PHASE2_PLAN.md`
   - `RESEARCH_AGENT_EXTERNAL_EVIDENCE_PLAN.md`
   - `RESEARCH_AGENT_UI_PLAN.md`
4. 未经真实实现、测试、用户确认，不把本文条目标记成完成。
