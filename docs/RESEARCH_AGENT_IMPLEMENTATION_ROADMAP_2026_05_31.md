# Research Agent 实施路线图

> **创建日期**：2026-05-31
> **关联总方案**：[RESEARCH_AGENT_UPGRADE_PLAN.md](RESEARCH_AGENT_UPGRADE_PLAN.md)
> **关联任务清单**：[RESEARCH_AGENT_IMPLEMENTATION_TASKLIST.md](RESEARCH_AGENT_IMPLEMENTATION_TASKLIST.md)
> **关联实现文档**：[RESEARCH_AGENT_IMPLEMENTATION.md](RESEARCH_AGENT_IMPLEMENTATION.md)
> **部署验证清单**：[PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md](PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md)

---

## 1. 路线图定位

本文是 Research Agent 整改的**执行级路线图**，不是总方案也不是完成记录。用途：

- 把任务清单中的待做项拆成可执行的 Sprint
- 每个 Sprint 有明确的改哪些文件、加什么测试、怎么验收
- 每完成一个 Sprint，更新本文状态和实现文档
- 不动总方案（`UPGRADE_PLAN`）和任务清单（`TASKLIST`），保持它们作为稳定的方向和规格参考

---

## 2. 当前完成度快照（2026-05-31）

### 已完成（Sprint 1 之前）

| 编号 | 任务 | 关键代码位置 |
|------|------|-------------|
| P1.1 | TaskFrame | `research_agent_runtime.py:567` `build_task_frame()` |
| P1.2 | Session Working Memory | `research_agent_runtime.py:1048` `update_state_after_tool()` / `:1183` `summarize_state_for_ui()` |
| P1.3 | Result Set 对象化（基本） | `research_agent_runtime.py:1109-1126` |
| P1.4 | Continuation Resolver | `research_agent_runtime.py:628` `resolve_context_refs()` |
| P0.4 | Tool Trace 摘要（部分） | `research_agent_runtime.py:1083-1093` + 前端工作记忆面板 |
| P1.7 | Budget Policy（部分） | `research_agent_runtime.py:851` `enforce_tool_policy()` — 重复空查熔断 + search_library 限额 |
| P1.8 | Tool Adapter（部分） | `research_agent_runtime.py:771` `normalize_tool_args()` |

### 已完成（Sprint 1 — 2026-05-31）

| 编号 | 任务 | 关键代码位置 | commit |
|------|------|-------------|--------|
| S1.1 | 错误枚举补全 + SSE error 事件规范化 | `services/agent_errors.py`（新建）+ `routers/agent.py` + `research_agent_runtime.py` | `b450513e` |
| S1.2 | 前端按错误类型展示差异化提示 | `App.tsx` `getAgentErrorStyle()` + `AgentErrorCard` 增强 | `e51b5fe0` |
| S1.3 | Provider 测试连接后端接口 | 已有 `POST /api/agent/provider-check` | — |
| S1.4 | Provider 测试连接前端 UI | 已有测试连接按钮 + 结果展示 | — |
| S1.5 | Tool Trace 前端摘要增强 | `App.tsx` `AgentToolTraceCard` 统计行 + `getRuntimeNoticeTitle` 补充 | `ee40ce2d` |
| — | Runtime Notice 可折叠 + md 渲染修复 | `App.tsx` `AgentRuntimeNoticeCard` 改 `<details>` + `AgentEventBody` answer 优先 | `e19dc638` |
| — | AI 助手 md 渲染样式增强 | `index.css` `.agent-md-content` 全面美化（绿系标题/紫红加粗/渐变表格/斑马纹） | `1fd431a2` |

### 已有但非任务清单中的能力

| 能力 | 位置 |
|------|------|
| 结构化错误枚举 + runtime notice 枚举 + payload 工厂 | `services/agent_errors.py`（Sprint 1 新建） |
| 结构化错误分类（17 种错误码 + 13 种 notice 码） | `agent.py` `classify_agent_exception()` |
| Analysis Cache + 子集过滤 | `reading_candidate_analysis.py` + `research_agent_runtime.py:705-747` |
| 期刊质量知识库 | `journal_quality_kb.py` |
| 前端工作记忆/工具轨迹/工作笔记展示 | `App.tsx` AI 助手面板 |

---

## 3. Sprint 规划

### Sprint 1：补全 P0 稳定性

**目标**：错误分类完整化、provider 测试连接、tool trace UI 增强

| 编号 | 任务 | 状态 |
|------|------|------|
| S1.1 | 错误枚举补全 + SSE error 事件规范化 | ✅ 已完成 |
| S1.2 | 前端按错误类型展示差异化提示 | ✅ 已完成 |
| S1.3 | Provider 测试连接后端接口 | ✅ 已有（POST /api/agent/provider-check） |
| S1.4 | Provider 测试连接前端 UI | ✅ 已有（测试连接按钮 + 结果展示） |
| S1.5 | Tool Trace 前端摘要增强 | ✅ 已完成 |

验收标准：

- ✅ 用户能区分 key 无效 / provider 挂了 / 上传失败 / runtime bug / 超时 / 限流（17 种 AgentErrorCode + 差异化图标/颜色）
- ✅ 保存 API Key 时有"测试连接"按钮，返回具体成功/失败原因
- ✅ 工具轨迹区域展示"搜了什么、命中几篇、为什么停"（统计行 + 可折叠 runtime notice）
- ✅ AI 助手回答有 md 渲染（绿系标题、紫红加粗、渐变表格、斑马纹等）

---

### Sprint 2：补全 P1.5 Runtime 状态机 + P1.6 Sufficiency Engine

**目标**：从"LLM 自由 tool_calls + runtime 约束"升级为"显式状态驱动的执行循环"

| 编号 | 任务 | 状态 |
|------|------|------|
| S2.1 | 定义 RuntimeState 枚举 + 状态迁移表 | ⬜ 待实施 |
| S2.2 | 实现 `research_sufficiency.py` | ⬜ 待实施 |
| S2.3 | 改造 `agent_chat` 主循环为状态驱动 | ⬜ 待实施 |
| S2.4 | 状态迁移日志 + SSE 事件增强 | ⬜ 待实施 |
| S2.5 | 单测覆盖 | ⬜ 待实施 |

验收标准：

- 主循环不再是 `for _ in range(MAX_TOOL_ROUNDS): LLM → tool_calls → execute`，而是 `state → action → transition → state`
- 每次状态迁移都有日志
- 证据不足时不再直接编答案
- 证据已够时不再继续浪费轮次

---

### Sprint 3：补全 P1.7 Budget Policy + P1.8 Tool Adapter

**目标**：分阶段预算、entry_id 校验、完整的 duplicate 检测

| 编号 | 任务 | 状态 |
|------|------|------|
| S3.1 | 提取 `tool_budget_policy.py` 独立模块 | ⬜ 待实施 |
| S3.2 | 实现分阶段预算（planner/local_search/external/proposal） | ⬜ 待实施 |
| S3.3 | 预算耗尽结构化降级输出 | ⬜ 待实施 |
| S3.4 | entry_id 格式与所有权校验 | ⬜ 待实施 |
| S3.5 | 单测覆盖 | ⬜ 待实施 |

验收标准：

- 同一工具 + 相似参数连续空结果 2 次自动熔断
- search_library 空查 ≥3 或总调用 ≥5 自动切换策略
- 外部检索默认每轮只开一个分支
- 预算耗尽时返回结构化说明（已做哪些、哪些为空、为什么停、下一步建议）
- 无效 entry_id 在 adapter 层拦截

---

### Sprint 4：补全 P1.3 Result Set 完善 + P2.1 External Consent Ticket

**目标**：Result Set 字段补全、外部检索票据化

| 编号 | 任务 | 状态 |
|------|------|------|
| S4.1 | Result Set 补全 titles/scope_label/created_at/expires_at | ⬜ 待实施 |
| S4.2 | Named Result Set 支持 | ⬜ 待实施 |
| S4.3 | 实现 `external_retrieval_policy.py` consent ticket | ⬜ 待实施 |
| S4.4 | 将 `enforce_tool_policy` 的外部检查升级为票据门禁 | ⬜ 待实施 |
| S4.5 | 前端 Consent Panel | ⬜ 待实施 |
| S4.6 | 单测覆盖 | ⬜ 待实施 |

验收标准：

- 用户说"刚才那 11 篇"时能稳定解析到完整 result set
- 无 consent ticket 时外部工具无法执行
- 前端明确展示"为什么需要联网、将访问什么、结果不会入库"

---

### Sprint 5：P2.2-P2.4 外部证据体系

**目标**：P3 外部证据容器、CNKI 增强、全文候选拆分

| 编号 | 任务 | 状态 |
|------|------|------|
| S5.1 | 外部证据容器结构（source/url/fetched_at/is_temporary） | ⬜ 待实施 |
| S5.2 | 前端 Tier Badge + P3 标记 | ⬜ 待实施 |
| S5.3 | 拆分 `lookup_fulltext_candidates` + `attach_fulltext_candidate` | ⬜ 待实施 |
| S5.4 | CNKI 结构化结果抓取接口设计 | ⬜ 待实施 |
| S5.5 | 单测覆盖 | ⬜ 待实施 |

验收标准：

- 外部结果前端明确标为 P3
- "查一下全文"不会隐式改库
- 外部结果默认不入 bib_entries/notes/artifacts

---

### Sprint 6：P2.5-P2.6 前端解释性 UI

**目标**：Result Set Card、Evidence Pack Table、Provider 状态

| 编号 | 任务 | 状态 |
|------|------|------|
| S6.1 | Result Set Card 组件 | ⬜ 待实施 |
| S6.2 | Evidence Pack Table 组件 | ⬜ 待实施 |
| S6.3 | Provider 状态 Badge | ⬜ 待实施 |
| S6.4 | Budget Stop Summary 组件 | ⬜ 待实施 |
| S6.5 | Proposal Preview Panel 增强 | ⬜ 待实施 |

验收标准：

- 用户能理解"系统当前基于哪组文献、哪层证据、为什么需要确认"

---

### Sprint 7：P3 工具覆盖扩展

**目标**：compare/synthesis/translation/references/cards 接入 runtime

| 编号 | 任务 | 状态 |
|------|------|------|
| S7.1 | compare reading data 只读工具 | ⬜ 待实施 |
| S7.2 | synthesis proposal/execution 工具 | ⬜ 待实施 |
| S7.3 | translation 只读 + proposal 工具 | ⬜ 待实施 |
| S7.4 | references 只读工具 | ⬜ 待实施 |
| S7.5 | cards/annotations 只读 + 写工具 | ⬜ 待实施 |
| S7.6 | dimensions 只读工具 | ⬜ 待实施 |
| S7.7 | 单测覆盖 | ⬜ 待实施 |

验收标准：

- 用户常见研究工作流可在一个 agent 会话内连续完成

---

### Sprint 8：P4 性能优化

**目标**：source_text_chunks + FTS/BM25（按需）

| 编号 | 任务 | 状态 |
|------|------|------|
| S8.1 | 评估是否需要 chunk 表（基于线上数据量和响应时间） | ⬜ 待实施 |
| S8.2 | 如需要，实现 `source_text_chunks` + FTS5 | ⬜ 待实施 |
| S8.3 | 确认是否纳入 `.dra` 导出体系 | ⬜ 待实施 |

验收标准：

- 大库 evidence 检索成本下降
- 多轮 source windows 查询明显提速
- 不使用 embedding/vector

---

## 4. Sprint 1 详细执行计划

> 以下为 Sprint 1 的逐任务展开，包含文件、改动点、测试命令。后续 Sprint 的详细计划在开始实施前补充。

---

### S1.1 错误枚举补全 + SSE error 事件规范化

**目标**：把散落在 `classify_agent_exception` 中的 10+ 个硬编码错误码收敛为正式枚举，统一 SSE error 事件格式。

**改动文件**：
- 新建 `backend/services/agent_errors.py` — 错误枚举 + payload 工厂
- 改 `backend/routers/agent.py` — 用新枚举替换硬编码字符串

**实施步骤**：

- [x] **Step 1：创建 `backend/services/agent_errors.py`**

定义错误枚举和 payload 工厂函数：

```python
from __future__ import annotations
from enum import Enum
from typing import Any

class AgentErrorCode(str, Enum):
    LLM_CONNECTION_ERROR = "llm_connection_error"
    LLM_TIMEOUT = "llm_timeout"
    LLM_AUTH_ERROR = "llm_auth_error"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_BAD_REQUEST = "llm_bad_request"
    LLM_UPSTREAM_ERROR = "llm_upstream_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    AGENT_RUNTIME_ERROR = "agent_runtime_error"
    INVALID_API_KEY = "invalid_api_key"
    CONSENT_REQUIRED = "consent_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONTEXT_RESOLUTION_FAILED = "context_resolution_failed"
    UPLOAD_ERROR = "upload_error"
    DB_ERROR = "db_error"

class ErrorStage(str, Enum):
    SESSION_SETUP = "session_setup"
    LLM_COMPLETION = "llm_completion"
    TOOL_EXECUTION = "tool_execution"
    PROPOSAL_EXECUTION = "proposal_execution"
    UPLOAD = "upload"

def make_agent_error_payload(
    *,
    code: AgentErrorCode,
    message: str,
    stage: ErrorStage,
    retryable: bool = False,
    status_code: int | None = None,
    provider: str | None = None,
    tool: str | None = None,
    details: str | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code.value,
        "message": message,
        "stage": stage.value,
        "retryable": retryable,
        **({"status_code": status_code} if status_code is not None else {}),
        **({"provider": provider} if provider else {}),
        **({"tool": tool} if tool else {}),
        **({"details": details} if details else {}),
        "recommendations": recommendations or [],
    }
```

- [x] **Step 2：改造 `agent.py` 的 `classify_agent_exception` 和 `_structured_agent_error`**

将 `agent.py` 中的 `_structured_agent_error` 替换为 `make_agent_error_payload`，将硬编码字符串替换为枚举值。改动范围：`agent.py:260-405`（`classify_agent_exception` 函数）。

具体：
- 删除 `_structured_agent_error` 内联函数
- import `AgentErrorCode, ErrorStage, make_agent_error_payload`
- 将所有 `code="xxx"` 替换为 `code=AgentErrorCode.XXX`
- 将所有 `stage="xxx"` 替换为 `stage=ErrorStage.XXX`
- `_structured_agent_error(...)` 调用全部改为 `make_agent_error_payload(...)`

- [x] **Step 3：改造 `agent.py` 中 SSE error 事件输出**

当前 SSE error 事件已输出 payload dict，格式不变。确认 `_stream()` 末尾的 `yield sse_event("error", payload)` 仍正常工作。

- [x] **Step 4：为 `research_agent_runtime.py` 的 runtime notice 使用新枚举**

`enforce_tool_policy` 和 `build_stop_summary` 中的 code 字段（如 `"consent_required"`、`"budget_exhausted"`、`"context_required"`）目前是硬编码字符串。将这些改为引用 `AgentErrorCode` 枚举。

- [x] **Step 5：跑编译检查**

```powershell
python -m compileall backend/services/agent_errors.py backend/routers/agent.py backend/services/research_agent_runtime.py
```

- [x] **Step 6：跑现有单测确认不回归**

```powershell
python -m unittest backend.tests.test_research_agent_runtime backend.tests.test_agent_tool_registry
```

- [x] **Step 7：commit**

---

### S1.2 前端按错误类型展示差异化提示

**目标**：前端收到 SSE error 事件后，按 `code` 字段展示不同的图标、颜色、文案和操作建议。

**改动文件**：
- 改 `frontend/src/App.tsx` — AI 助手错误处理区域

**实施步骤**：

- [x] **Step 1：在 AI 助手错误处理区域增加 code → 提示映射**

在 `App.tsx` 中找到处理 SSE `error` 事件的逻辑，增加一个 `getErrorMessage(errorPayload)` 辅助函数：

```typescript
function getAgentErrorDisplay(payload: Record<string, any>): {
  title: string;
  icon: string;
  color: string;
  details: string[];
  actions: string[];
} {
  const code = payload?.code || '';
  switch (code) {
    case 'llm_auth_error':
    case 'invalid_api_key':
      return {
        title: 'API Key 认证失败',
        icon: '🔑',
        color: 'text-red-600',
        details: ['请检查 API Key 是否有效、是否与当前 Provider 类型匹配。'],
        actions: ['重新设置 API Key'],
      };
    case 'llm_connection_error':
      return {
        title: '模型服务连接失败',
        icon: '🔌',
        color: 'text-orange-600',
        details: ['无法连接到上游模型服务。'],
        actions: ['检查网络', '稍后重试'],
      };
    case 'llm_timeout':
      return {
        title: '模型响应超时',
        icon: '⏱️',
        color: 'text-orange-600',
        details: ['上游模型响应超时，建议缩小问题范围后重试。'],
        actions: ['缩小范围重试'],
      };
    case 'llm_rate_limited':
      return {
        title: '触发限流',
        icon: '🚦',
        color: 'text-yellow-600',
        details: ['上游模型触发限流，请稍后再试。'],
        actions: ['稍后重试'],
      };
    case 'llm_upstream_error':
      return {
        title: '上游模型服务异常',
        icon: '⚠️',
        color: 'text-red-600',
        details: ['上游模型服务暂时不可用（5xx）。'],
        actions: ['稍后重试', '这是服务端问题，不是你的操作有误'],
      };
    case 'tool_execution_error':
      return {
        title: '工具执行失败',
        icon: '🔧',
        color: 'text-orange-600',
        details: [payload?.details || '工具执行过程中发生错误。'],
        actions: ['检查输入', '尝试缩小范围'],
      };
    case 'consent_required':
      return {
        title: '需要授权',
        icon: '🔐',
        color: 'text-blue-600',
        details: ['当前操作需要联网授权。'],
        actions: ['确认是否允许联网检索'],
      };
    case 'budget_exhausted':
      return {
        title: '工具调用预算耗尽',
        icon: '🔋',
        color: 'text-yellow-600',
        details: ['本轮工具调用已达上限。'],
        actions: ['基于当前结果继续提问', '缩小范围后重试'],
      };
    default:
      return {
        title: 'AI 助手执行失败',
        icon: '❌',
        color: 'text-red-600',
        details: [payload?.message || '未知错误。'],
        actions: ['刷新后重试'],
      };
  }
}
```

- [x] **Step 2：在错误展示区域使用映射函数**

找到当前展示 AI 助手错误消息的位置，替换为使用 `getAgentErrorDisplay` 的结构化展示。

- [x] **Step 3：前端构建验证**

```powershell
cd frontend && npm run build
```

- [x] **Step 4：commit**

---

### S1.3 Provider 测试连接后端接口

**目标**：新增一个轻量后端接口，用用户当前 API Key 实际调用一次 LLM API，返回可达性与错误类型。

**改动文件**：
- 改 `backend/routers/agent.py` — 新增 `/api/agent/test-provider` 端点

**实施步骤**：

- [ ] **Step 1：新增端点 `POST /api/agent/test-provider`**

在 `agent.py` 中新增：

```python
@router.post("/test-provider")
async def test_provider(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    provider = body.get("provider", "deepseek").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    base_url, model, display_name = _resolve_provider(provider)
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            temperature=0,
        )
        return {
            "status": "ok",
            "provider": display_name,
            "model": model,
            "message": f"{display_name} 连接成功",
        }
    except openai.AuthenticationError:
        return {"status": "auth_error", "provider": display_name, "message": f"{display_name} 认证失败，请检查 API Key"}
    except openai.RateLimitError:
        return {"status": "ok", "provider": display_name, "model": model, "message": f"{display_name} 连接成功（触发限流但 Key 有效）"}
    except openai.APIConnectionError:
        return {"status": "connection_error", "provider": display_name, "message": f"无法连接到 {display_name}，请检查网络"}
    except openai.Timeout:
        return {"status": "timeout", "provider": display_name, "message": f"{display_name} 响应超时"}
    except openai.InternalServerError:
        return {"status": "upstream_error", "provider": display_name, "message": f"{display_name} 上游服务异常"}
    except Exception as exc:
        return {"status": "error", "provider": display_name, "message": f"测试失败：{str(exc)[:200]}"}
```

注意：复用 `agent.py` 中已有的 `_resolve_provider()` 函数（该函数根据 provider 名称返回 `base_url, model, display_name`）。

- [ ] **Step 2：编译检查**

```powershell
python -m compileall backend/routers/agent.py
```

- [ ] **Step 3：本地手动验证**

启动后端后，用 curl 或浏览器测试：

```powershell
curl -X POST http://localhost:8000/api/agent/test-provider -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"api_key":"sk-xxx","provider":"deepseek"}'
```

- [ ] **Step 4：commit**

---

### S1.4 Provider 测试连接前端 UI

**目标**：在 API Key 设置区域增加"测试连接"按钮。

**改动文件**：
- 改 `frontend/src/App.tsx` — API Key 设置区域

**实施步骤**：

- [ ] **Step 1：找到 API Key 设置 UI，增加"测试连接"按钮**

在 AI 助手的设置/API Key 输入区域旁边，新增一个按钮，点击后：
1. 调用 `POST /api/agent/test-provider`
2. 展示返回的 `status` 和 `message`
3. 按返回状态显示绿色/红色/黄色提示

- [ ] **Step 2：展示最近一次测试状态**

保存最近一次测试结果到组件 state，在 API Key 输入框下方持续展示。

- [ ] **Step 3：前端构建验证**

```powershell
cd frontend && npm run build
```

- [ ] **Step 4：commit**

---

### S1.5 Tool Trace 前端摘要增强

**目标**：工具轨迹区域展示"搜了什么、命中几篇、为什么停"的人类可读摘要。

**改动文件**：
- 改 `frontend/src/App.tsx` — tool trace 展示区域

**实施步骤**：

- [x] **Step 1：增强 tool trace 渲染**

当前前端已展示 `recent_tool_trace`。增强为：
- 每条 trace 显示：工具名 + 查询摘要 + 命中数 + 是否空结果
- 空结果条目用灰色/斜体
- 被策略拦截的条目用橙色标记
- 最后增加一行总结："共 N 次工具调用，M 次命中，K 次被策略拦截"

- [x] **Step 2：增加 Budget Stop Summary 展示**

当 `last_stop_summary` 不为空时，在工作记忆区域展示：
- 为什么停止（预算耗尽 / 轮次上限）
- 当前结果集大小
- 建议下一步

- [x] **Step 3：前端构建验证**

```powershell
cd frontend && npm run build
```

- [x] **Step 4：commit**

---

## 5. Sprint 2 详细执行计划

> 状态驱动 Runtime + Sufficiency Engine

---

### S2.1 定义 RuntimeState 枚举 + 状态迁移表

**目标**：定义显式状态机，替代当前的 `for _ in range(MAX_TOOL_ROUNDS)` 循环。

**改动文件**：
- 新建 `backend/services/research_agent_runtime.py` 中新增 `RuntimeState` 枚举和 `transition()` 函数

**实施步骤**：

- [ ] **Step 1：在 `research_agent_runtime.py` 中新增状态枚举**

```python
from enum import Enum

class RuntimeState(str, Enum):
    UNDERSTAND = "understand"
    RESOLVE_CONTEXT = "resolve_context_refs"
    RETRIEVE_LOCAL = "retrieve_local"
    ASSESS_SUFFICIENCY = "assess_sufficiency"
    ASK_CLARIFICATION = "ask_clarification"
    REQUEST_EXTERNAL_CONSENT = "request_external_consent"
    RETRIEVE_EXTERNAL = "retrieve_external"
    MERGE_EVIDENCE = "merge_evidence"
    SYNTHESIZE_ANSWER = "synthesize_answer"
    PREPARE_PROPOSAL = "prepare_proposal"
    EXECUTE_CONFIRMED = "execute_confirmed"
    FINISH = "finish"
```

- [ ] **Step 2：定义状态迁移逻辑 `transition(current_state, task_frame, evidence_status, policy_result) → RuntimeState`**

迁移规则：
- `UNDERSTAND` → 根据 task_frame.intent 分支：
  - continuation 且无 context → `ASK_CLARIFICATION`
  - needs_local_search → `RESOLVE_CONTEXT`（如有 continuation_ref）或 `RETRIEVE_LOCAL`
  - needs_external → `REQUEST_EXTERNAL_CONSENT`
  - needs_write → `PREPARE_PROPOSAL`
  - check_status → `FINISH`（直接回答）
- `RESOLVE_CONTEXT` → 成功 → `RETRIEVE_LOCAL`；失败 → `ASK_CLARIFICATION`
- `RETRIEVE_LOCAL` → `ASSESS_SUFFICIENCY`
- `ASSESS_SUFFICIENCY` →
  - sufficient → `SYNTHESIZE_ANSWER`
  - insufficient + 用户允许联网 → `REQUEST_EXTERNAL_CONSENT`
  - insufficient + 用户不允许 → `SYNTHESIZE_ANSWER`（基于有限证据回答并说明不足）
  - conflicted → `SYNTHESIZE_ANSWER`（标注冲突）
- `REQUEST_EXTERNAL_CONSENT` → 用户同意 → `RETRIEVE_EXTERNAL`；拒绝 → `SYNTHESIZE_ANSWER`
- `RETRIEVE_EXTERNAL` → `MERGE_EVIDENCE`
- `MERGE_EVIDENCE` → `SYNTHESIZE_ANSWER`
- `SYNTHESIZE_ANSWER` → `FINISH`
- `PREPARE_PROPOSAL` → 等待确认 → `EXECUTE_CONFIRMED`
- `EXECUTE_CONFIRMED` → `FINISH`
- `ASK_CLARIFICATION` → `FINISH`（等待用户下一轮）

- [ ] **Step 3：为每个状态定义允许的工具集**

```python
STATE_ALLOWED_TOOLS: dict[RuntimeState, set[str]] = {
    RuntimeState.RETRIEVE_LOCAL: {
        "search_library", "research_search", "get_evidence_pack",
        "get_source_windows", "get_entry_detail", "get_reading_context",
        "count_library", "analyze_reading_candidates", "filter_analysis_cache",
        "scan_input_folder", "get_job_status",
    },
    RuntimeState.RETRIEVE_EXTERNAL: {
        "search_cnki", "lookup_english_fulltext",
    },
    RuntimeState.PREPARE_PROPOSAL: {
        "start_reading", "start_batch_reading", "import_folder_and_start_reading",
    },
}
```

其他状态不允许调用工具（LLM 应直接生成回答或提问）。

- [ ] **Step 4：单测**

验证迁移表覆盖所有状态、所有分支。

```powershell
python -m unittest backend.tests.test_research_agent_runtime
```

- [ ] **Step 5：commit**

---

### S2.2 实现 `research_sufficiency.py`

**目标**：检索完成后先判断"证据是否够回答"，再决定下一步。

**改动文件**：
- 新建 `backend/services/research_sufficiency.py`

**实施步骤**：

- [ ] **Step 1：创建 sufficiency 判定函数**

```python
from __future__ import annotations
from typing import Any
from enum import Enum

class SufficiencyLevel(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIALLY_SUFFICIENT = "partially_sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICTED = "conflicted"
    NEEDS_USER_CHOICE = "needs_user_choice"

def assess_evidence_sufficiency(
    *,
    question_type: str,
    evidence_count: int,
    entry_coverage: int,
    tier_distribution: dict[str, int],
    conflict_level: str = "none",
    scope_confidence: float = 1.0,
) -> dict[str, Any]:
    p0 = tier_distribution.get("P0", 0)
    p1 = tier_distribution.get("P1", 0)
    p2 = tier_distribution.get("P2", 0)

    has_original_source = p0 > 0
    has_user_content = p1 > 0
    has_ai_content = p2 > 0
    has_any_evidence = evidence_count > 0

    if conflict_level in ("high", "critical"):
        return {
            "level": SufficiencyLevel.CONFLICTED,
            "reason": "不同层级证据之间存在冲突",
            "recommendation": "在回答中标注冲突，并说明以哪个来源为准",
        }

    if not has_any_evidence:
        return {
            "level": SufficiencyLevel.INSUFFICIENT,
            "reason": "没有任何证据命中",
            "recommendation": "考虑联网检索或要求用户澄清",
        }

    if question_type in ("fact", "definition", "metadata"):
        if has_original_source:
            return {
                "level": SufficiencyLevel.SUFFICIENT,
                "reason": "事实类问题有原始来源支撑",
            }
        elif has_user_content:
            return {
                "level": SufficiencyLevel.PARTIALLY_SUFFICIENT,
                "reason": "有用户笔记但缺少原始来源",
                "recommendation": "回答时标注主要依据用户笔记",
            }
        else:
            return {
                "level": SufficiencyLevel.PARTIALLY_SUFFICIENT,
                "reason": "仅依赖 AI 生成内容",
                "recommendation": "回答时明确标注依据主要是 AI 笔记",
            }

    if question_type in ("summary", "compare", "synthesize"):
        if entry_coverage >= 3 and has_original_source:
            return {
                "level": SufficiencyLevel.SUFFICIENT,
                "reason": f"综述类问题覆盖 {entry_coverage} 篇文献且有原始来源",
            }
        elif entry_coverage >= 1 and (has_original_source or has_user_content):
            return {
                "level": SufficiencyLevel.PARTIALLY_SUFFICIENT,
                "reason": f"覆盖 {entry_coverage} 篇文献，部分有原始来源",
                "recommendation": "基于可用证据回答，标注覆盖不足之处",
            }
        else:
            return {
                "level": SufficiencyLevel.INSUFFICIENT,
                "reason": f"仅覆盖 {entry_coverage} 篇文献且缺少高质量来源",
                "recommendation": "建议先检索更多文献或联网补充",
            }

    if question_type in ("search", "list", "count"):
        if has_any_evidence:
            return {
                "level": SufficiencyLevel.SUFFICIENT,
                "reason": "检索类问题有命中结果",
            }
        else:
            return {
                "level": SufficiencyLevel.INSUFFICIENT,
                "reason": "检索无结果",
            }

    return {
        "level": SufficiencyLevel.PARTIALLY_SUFFICIENT,
        "reason": "无法确定问题类型，基于可用证据尽力回答",
    }
```

- [ ] **Step 2：单测**

新建 `backend/tests/test_research_sufficiency.py`，覆盖：
- 事实类问题：有 P0 → sufficient；只有 P2 → partially
- 综述类问题：覆盖 3+ 篇且有 P0 → sufficient；覆盖 0 篇 → insufficient
- 无任何证据 → insufficient
- 有冲突 → conflicted
- 检索类：有结果 → sufficient

```powershell
python -m unittest backend.tests.test_research_sufficiency
```

- [ ] **Step 3：commit**

---

### S2.3 改造 `agent_chat` 主循环为状态驱动

**目标**：把 `for _ in range(MAX_TOOL_ROUNDS)` 改为状态驱动循环。

**改动文件**：
- 改 `backend/routers/agent.py` — `agent_chat` 函数（`:2254-2475`）

**实施步骤**：

- [ ] **Step 1：在 `_stream()` 中引入状态机**

改造 `agent_chat` 的主循环（当前在 `agent.py:2298-2434`）。核心改动：

```python
# 替换当前的 for _ in range(MAX_TOOL_ROUNDS):
from backend.services.research_agent_runtime import RuntimeState, transition, STATE_ALLOWED_TOOLS
from backend.services.research_sufficiency import assess_evidence_sufficiency

current_state = RuntimeState.UNDERSTAND
# ... build_task_frame, resolve_context_refs 已在前面完成 ...

# 初始状态迁移
current_state = transition(current_state, task_frame, None, None)
await _replace_session_state(db, session, state={**state, "runtime_state": current_state.value})

while current_state != RuntimeState.FINISH:
    if current_state == RuntimeState.ASK_CLARIFICATION:
        # LLM 生成澄清问题，直接返回
        # ... 调用 LLM 一次，无工具 ...
        break

    if current_state == RuntimeState.SYNTHESIZE_ANSWER:
        # LLM 基于已有证据生成回答
        # ... 调用 LLM 一次，无工具 ...
        break

    if current_state in (RuntimeState.RETRIEVE_LOCAL, RuntimeState.RETRIEVE_EXTERNAL):
        allowed = STATE_ALLOWED_TOOLS.get(current_state, set())
        # 调用 LLM，tools 限制为 allowed
        response = client.chat.completions.create(
            ...,
            tools=[t for t in TOOL_SCHEMAS if t["function"]["name"] in allowed],
        )
        # 如果 LLM 返回 tool_calls → 执行 → 更新 state → 迁移状态
        # 如果 LLM 返回文本 → 视为回答 → 迁移到 FINISH

    if current_state == RuntimeState.ASSESS_SUFFICIENCY:
        # 从 state 中提取 tier_distribution, evidence_count 等
        assessment = assess_evidence_sufficiency(...)
        state["sufficiency_assessment"] = assessment
        current_state = transition(current_state, task_frame, assessment, None)

    if current_state == RuntimeState.REQUEST_EXTERNAL_CONSENT:
        # 生成 consent 请求 SSE 事件，等待用户确认
        # ... yield consent SSE ...
        break

    if current_state == RuntimeState.PREPARE_PROPOSAL:
        # LLM 生成 proposal
        # ... 调用 LLM，allowed tools = propose_write tools ...
        break

    if current_state == RuntimeState.EXECUTE_CONFIRMED:
        # 执行已确认的 proposal
        break

    # 安全阀：防止无限循环
    budget_guard += 1
    if budget_guard > MAX_TOOL_ROUNDS * 2:
        break
```

**注意**：这是一个较大的改动，需要分步实施，每步都跑测试。建议先在一个 feature flag 后面实现，与旧循环并存，确认新循环可用后再移除旧代码。

- [ ] **Step 2：保持 SSE 事件兼容**

新循环必须继续输出与现有前端兼容的 SSE 事件：`session`、`tool_call`、`tool_result`、`proposal`、`answer`、`error`、`done`。新增 `state_transition` 事件供前端展示当前阶段。

- [ ] **Step 3：跑现有单测确认不回归**

```powershell
python -m unittest backend.tests.test_research_agent_runtime backend.tests.test_agent_tool_registry backend.tests.test_research_retrieval
```

- [ ] **Step 4：本地功能验证**

启动后端，在前端 AI 助手中测试：
- "库里有多少论文" → 走 count_library
- "帮我找关于 XX 的文献" → 走 retrieve_local → assess_sufficiency → synthesize
- "刚才那些论文继续分析" → 走 resolve_context → retrieve_local
- "去知网搜一下" → 走 request_external_consent

- [ ] **Step 5：commit**

---

### S2.4 状态迁移日志 + SSE 事件增强

**目标**：每次状态迁移输出日志，前端可展示当前阶段。

**改动文件**：
- 改 `backend/services/research_agent_runtime.py` — `transition()` 增加日志
- 改 `frontend/src/App.tsx` — 展示当前 runtime 状态

**实施步骤**：

- [ ] **Step 1：在 `transition()` 中增加 `logging.debug`**

记录 `from_state → to_state`、触发条件、task_frame.intent。

- [ ] **Step 2：新增 SSE `state_transition` 事件**

在 `agent.py` 的主循环中，每次状态迁移后 yield：

```python
yield sse_event("state_transition", {
    "from": prev_state.value,
    "to": current_state.value,
    "intent": task_frame.get("intent"),
})
```

- [ ] **Step 3：前端展示当前阶段**

在前端 AI 助手面板中，接收 `state_transition` 事件，展示当前阶段文本（如"正在检索本地文献库"、"正在评估证据充分性"、"正在生成回答"）。

- [ ] **Step 4：commit**

---

### S2.5 Sprint 2 单测覆盖

**目标**：确保状态机和 sufficiency engine 的核心逻辑有单测保护。

**新增/扩展的测试文件**：
- `backend/tests/test_research_agent_runtime.py` — 新增状态迁移测试
- `backend/tests/test_research_sufficiency.py` — 新建

**测试用例**：

- [ ] **T1：`transition()` 迁移表覆盖测试**

验证所有 `RuntimeState` 的所有出口都有对应迁移。

- [ ] **T2：`transition()` 边界测试**

- UNDERSTAND + library_lookup + no continuation → RETRIEVE_LOCAL
- UNDERSTAND + library_lookup + continuation + no result_set → ASK_CLARIFICATION
- RETRIEVE_LOCAL + evidence found → ASSESS_SUFFICIENCY
- ASSESS_SUFFICIENCY + sufficient → SYNTHESIZE_ANSWER
- ASSESS_SUFFICIENCY + insufficient + user wants external → REQUEST_EXTERNAL_CONSENT
- ASSESS_SUFFICIENCY + insufficient + no external → SYNTHESIZE_ANSWER

- [ ] **T3：sufficiency 判定测试**

覆盖 S2.2 中所有 SufficiencyLevel 分支。

- [ ] **T4：STATE_ALLOWED_TOOLS 一致性测试**

验证每个状态的 allowed tools 与 agent_tool_registry 中的工具名一致。

---

## 6. Sprint 3-8 概要（详细计划在实施前补充）

### Sprint 3 详细计划

> 补全 P1.7 Budget Policy + P1.8 Tool Adapter
> 实施前展开

### Sprint 4 详细计划

> 补全 P1.3 Result Set + P2.1 External Consent Ticket
> 实施前展开

### Sprint 5 详细计划

> P2.2-P2.4 外部证据体系
> 实施前展开

### Sprint 6 详细计划

> P2.5-P2.6 前端解释性 UI
> 实施前展开

### Sprint 7 详细计划

> P3 工具覆盖扩展
> 实施前展开

### Sprint 8 详细计划

> P4 性能优化
> 实施前展开

---

## 7. 部署节奏

每完成一个 Sprint 后：

1. 更新本文对应状态（⬜ → ✅ 或 ⚠️）
2. 更新 `RESEARCH_AGENT_IMPLEMENTATION.md` 的已实现能力描述
3. 按 `PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md` 执行部署
4. 部署后在 `docs/` 下写简要上线记录（改动范围、验证结果）

---

## 8. 文档更新规则

| 文档 | 职责 | 何时更新 |
|------|------|---------|
| `RESEARCH_AGENT_UPGRADE_PLAN.md` | 总方向和原则 | 只在方向/原则变更时更新 |
| `RESEARCH_AGENT_IMPLEMENTATION_TASKLIST.md` | 完整任务规格 | 只在任务拆分/优先级变更时更新 |
| 本文（`ROADMAP`） | 执行级路线图和 Sprint 状态 | 每个 Sprint 完成时更新状态 |
| `RESEARCH_AGENT_IMPLEMENTATION.md` | 已实现能力记录 | 每次真实实现后更新 |
| `PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md` | 部署验证清单 | 每次部署前核对 |
