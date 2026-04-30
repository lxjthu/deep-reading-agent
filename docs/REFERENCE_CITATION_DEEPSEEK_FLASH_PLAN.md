# 参考文献梳理改造方案（DeepSeek Flash 版）

> 状态：**已验证通过，准备实施**  
> 适用范围：`P0 参考文献梳理标签页 + 引用关系入库` 的识别链路改造  
> 本文档用途：记录识别方案设计与验证结果，指导后续实施  
> 验证日期：2026-04-30  
> 验证脚本：`test_deepseek_references.py`

## 1. 背景

当前 `P0` 参考文献梳理链路已经具备基础骨架：

- 有独立标签页；
- 有后端任务入口；
- 有 `bib_references` / `bib_reference_citations` 入库结构；
- 有参考文献目录解析与正文引用对齐的基本流程。

但实际试运行后，当前以规则和程序化拆分为主的识别链路暴露出明显质量问题：

- 标题识别不稳定，很多条目无法可靠抽出标题；
- 错误断行导致一条题录被拆开，或多条题录被粘连；
- 文末英文摘要、附录、补充材料等内容容易被误识别为参考文献；
- 纯规则方式对中英文混排、复杂版式、双栏 PDF 的适应性不足；
- 后续如果直接用当前结果入库，会放大脏数据污染风险。

因此，需要将“参考文献识别”从“规则主导”改为“模型主导、规则辅助”的方案。

---

## 2. 本次改造的核心结论

本次方案建议采用：

- **规则负责定位候选范围**
- **DeepSeek `deepseek-v4-flash` 负责理解、分条和结构化**

不建议采用以下做法：

- 不建议继续主要依赖正则和启发式规则做题录拆分；
- 不建议把整篇 PDF 全文无差别交给模型处理；
- 不建议继续使用旧模型名 `deepseek-chat` 或 `deepseek-reasoner` 作为新方案的正式配置名。

推荐的新模型配置：

- `base_url = https://api.deepseek.com`
- `model = deepseek-v4-flash`

如果后续需要更高质量兜底，可在极少数失败样本上再评估 `deepseek-v4-pro`，但首选仍应是 `flash`。

---

## 3. 为什么改成 DeepSeek Flash

当前问题本质上不是“拿不到 PDF 文本”，而是“难以稳定理解文末内容的真实结构”。

模型相对规则的优势主要体现在：

- 能把被 PDF 提取器错误断开的多行内容合并为同一条题录；
- 能识别题录与摘要、附录、作者简介之间的语义边界；
- 能在中英文混杂、标点风格不统一时依然识别作者、年份、标题、期刊等字段；
- 能在不依赖固定格式的情况下，输出结构化 JSON。

同时，`deepseek-v4-flash` 更适合作为首期默认方案，因为它：

- 调用成本更低；
- 响应速度更快；
- 适合多次、小批量地围绕同一篇 PDF 做局部结构化。

---

## 4. 方案总原则

### 4.1 总体原则

新的识别方案遵循以下原则：

1. 不直接把整篇 PDF 丢给模型；
2. 先通过程序定位“可能的参考文献区域”；
3. 再把候选区域交给 DeepSeek 做语义判断与结构化；
4. 只接受严格 JSON 结果，不接受自由文本结果；
5. 对低置信度结果保守处理，不强行入库；
6. 保留程序化兜底链路，但不再让它作为主识别逻辑。

### 4.2 角色分工

程序层负责：

- 提取 PDF 文本；
- 定位尾部候选范围；
- 控制输入长度；
- 管理任务状态和入库；
- 校验模型输出 JSON；
- 对结果做轻量归一化。

模型层负责：

- 判断候选区中哪些内容是真正的参考文献；
- 合并错误断行；
- 正确分条；
- 结构化提取作者、年份、标题、刊物、DOI 等字段；
- 识别并忽略英文摘要、附录、补充材料、致谢、作者简介等尾部噪音。

---

## 5. 两种场景的处理策略

本次方案明确分成两种场景处理。

### 5.1 场景一：上传新的 PDF 文档进行精读

用户路径：

- 用户上传新的 PDF；
- 系统执行精读任务；
- 在精读过程中顺带完成参考文献识别。

为什么这样做：

- 精读链路本来就会读取和处理整篇 PDF；
- 可以复用已提取的正文文本、分段结果和文档上下文；
- 可以减少重复 I/O 和重复模型调用；
- 更适合后续接入上下文缓存。

该场景下建议：

- 在精读任务中增加一个独立子阶段：
  - `reference_prepare`
  - `reference_parse`
- 在精读完成后，把参考文献条目和正文引用识别结果一起落库；
- 前端仍在 `参考文献梳理` 标签页中查看，不要求精读页直接展示全部结果。

### 5.2 场景二：已有的 PDF 文档

用户路径：

- 文档已经在数据库里；
- 用户从 `参考文献梳理` 标签页选择某篇已有 PDF；
- 系统直接对该 PDF 的尾部参考文献区域做识别。

为什么要单独处理：

- 这类文档未必刚跑过精读；
- 不应要求用户为了识别参考文献而重新执行整篇精读；
- 只取尾部相关页或尾部相关文本，成本更低。

该场景下建议：

- 优先读取 PDF 尾部若干页；
- 或从已有全文文本中截取尾部区段；
- 先定位 `References / Bibliography / 参考文献` 开始位置；
- 然后把该位置之后的候选文本交给 DeepSeek；
- Prompt 中明确声明：后面可能仍有英文摘要、附录、补充材料、作者简介等，这些都不是参考文献，必须忽略。

---

## 6. 新方案的主流程

### 6.1 阶段 A：候选范围定位

输入：

- PDF 全文文本；
- 或尾部若干页文本。

处理目标：

- 找到参考文献开始位置；
- 截取足够覆盖参考文献区的候选文本；
- 尽量避免把整篇正文送给模型。

建议策略：

- 先用程序寻找以下标题或变体：
  - `References`
  - `Bibliography`
  - `Works Cited`
  - `参考文献`
- 若找到，则从该位置开始截取到文末；
- 若未找到，则从尾部若干页中选取较可能包含参考文献的部分；
- 允许多取一段缓冲区，但不要无限扩大。

### 6.2 阶段 B+C：模型识别 + 分条 + 结构化（单次调用）

> 2026-04-30 实测验证：单次 DeepSeek 调用可同时完成"识别有效参考文献区"和"分条结构化"两个任务。模型通过 `ignore` 字段自行过滤非参考文献内容，无需分两次调用。

输入：

- 候选尾部文本。

模型任务（单次完成）：

- 判断候选区中哪些是真正参考文献，哪些不是；
- 合并错误断行；
- 将多条题录稳定分开；
- 提取每条题录的结构化字段；
- 对不确定字段允许返回 `null`，禁止臆造；
- 对非参考文献内容标记 `ignore=true` 并给出原因。

明确要求模型忽略：

- 英文摘要
- 附录
- 致谢
- 作者简介
- 补充材料说明
- 各类正文残留段落

输出要求：

- 必须输出严格 JSON；
- 每条题录必须保留 `raw_text`；
- 每条题录必须有 `ignore` 字段，允许模型明确标记不是参考文献。

合并为单次调用的理由（实测依据）：

- 38 条参考文献全部正确识别，0 条误识别；
- `ignore` 字段足以承担噪音过滤职责；
- 单次调用降低约 50% 的 API 成本和延迟；
- 代码实现更简单，减少中间状态管理。

### 6.4 阶段 D：程序侧归一化与入库准备

输入：

- 模型返回的参考文献 JSON。

处理目标：

- 过滤 `ignore = true` 的条目；
- **重新顺序编号**：忽略模型返回的 `reference_order`（可能保留原文编号如 99、100），统一按 1, 2, 3... 重新编号；
- 归一化 DOI；
- 归一化作者列表；
- 清洗明显异常值；
- 生成去重键；
- 准备写入 `bib_references`。

重新编号的原因（实测发现）：

- 部分 PDF 原文参考文献编号不连续（如从 `（ 31 ）` 跳到 `（ 99 ）`）；
- 模型会忠实保留原文编号，导致 `reference_order` 不连续；
- 入库后按 `reference_order` 排序展示时会出现跳号，影响前端展示；
- 正文引用追踪时应使用重新编号后的顺序，而非原文编号。

### 6.5 阶段 E：正文引用对齐（DeepSeek 全文方案）

> 2026-04-30 实测 + DeepSeek API 文档确认：deepseek-v4-flash 上下文长度 **1M tokens**，最大输出 **384K tokens**，一篇论文全文（20-40K tokens）完全放得下。硬盘缓存默认开启，正文前缀稳定后 cache_hit 比例极高。

#### 6.5.1 为什么改用 DeepSeek 做正文引用追踪

实测对比了三种方案（`test_citation_tracing.py`，10 条参考文献）：

| 方案 | 中文 PDF hits | 英文 PDF hits | 说明 |
|---|---|---|---|
| 纯正则（现有后端） | 13 | 24 | 英文 24 条含大量 false positive |
| 正则召回 + LLM 核验 | 10 | **0** | 英文 PDF pypdf 文本质量差，LLM 全部拒绝 |
| **DeepSeek 全文直接追踪** | **9** | **8** | 中英文均有效，quote 质量最高 |

关键发现：

- 纯正则在英文 PDF 上 24 hits 但 LLM 一个都没确认——说明全是误匹配；
- Regex+LLM 在英文 PDF 上完全失效（0 hits）——pypdf 提取文本质量不足以支撑核验；
- DeepSeek 全文直接追踪是唯一在中英文都有效的方案；
- DeepSeek 还能找到描述性引用（如 "according to Smith's study..."），正则完全做不到。

#### 6.5.2 实施策略：多轮对话 + 硬盘缓存

利用 DeepSeek 多轮对话 API（无状态，客户端拼接历史）+ 硬盘缓存（默认开启）：

**第一轮**（构建缓存）：

```
messages = [
  {"role": "system", "content": "你是一个学术文献引用追踪专家..."},
  {"role": "user", "content": "<正文全文>\n\n<全部参考文献列表>\n\n请输出每条参考文献在正文中的引用句子。"}
]
```

- 正文全文 + 参考文献列表一次发完（< 100K tokens，远低于 1M 上限）；
- 输出所有引用链接，JSON 格式；
- 请求结束后，system + 正文 + 参考文献列表 前缀被写入硬盘缓存。

**第二轮及以后**（命中缓存，成本极低）：

如果第一轮输出被截断或需要分批输出：

```
messages = [
  {"role": "system", "content": "你是一个学术文献引用追踪专家..."},
  {"role": "user", "content": "<正文全文>\n\n<全部参考文献列表>\n\n请输出每条参考文献在正文中的引用句子。"},
  {"role": "assistant", "content": "<第一轮输出的部分结果>"},
  {"role": "user", "content": "请继续输出剩余参考文献的引用链接。"}
]
```

- 正文全文前缀完整命中缓存，只需处理新增部分；
- cache_hit 价格 0.02 元/百万 tokens，远低于未命中价格 1 元/百万 tokens。

**分批策略**（可选，当参考文献极多时）：

```
# 第一批：只问 ref 1-15
"请输出参考文献第 1-15 条的正文引用链接。"

# 第二批：正文前缀命中缓存，只问 ref 16-30
"请输出参考文献第 16-30 条的正文引用链接。"
```

#### 6.5.3 输出结构

每条引用命中的输出格式：

```json
{
  "citation_traces": [
    {
      "reference_order": 1,
      "citations": [
        {
          "quote": "正文中引用该文献的原始句子",
          "citation_style": "author_year | numeric | descriptive",
          "location_hint": "第X段 / 第X节（尽力识别）",
          "confidence": 0.9
        }
      ]
    }
  ]
}
```

程序侧处理：

- 过滤 `confidence < 0.5` 的低置信度命中；
- 用 `quote` 在正文中做子串定位，提取 `char_start` / `char_end`；
- 生成 `excerpt`（上下文窗口）；
- 写入 `bib_reference_citations` 表。

#### 6.5.4 与参考文献识别阶段的衔接

参考文献识别（阶段 B+C）和正文引用追踪（阶段 E）使用同一份正文文本：

- 两次调用共享正文前缀 → 第二次调用正文部分全部命中缓存；
- 总 API 成本 = 第一次（正文未命中） + 第二次（正文命中缓存，成本降低 98%）。

#### 6.5.5 与旧方案的关系

- 旧的正则引用追踪代码（`trace_citations` / `build_reference_patterns`）保留作为**离线兜底**；
- 在线场景全部切换为 DeepSeek 方案；
- 如果 DeepSeek 调用失败（网络/限流），临时回退到正则方案。

---

## 7. Prompt 设计

> 2026-04-30 验证结论：采用单个 Prompt 即可同时完成"参考文献区识别"和"题录结构化"。以下为已验证的 Prompt 设计。

### 7.1 Prompt A：参考文献识别 + 结构化（已验证）

目标：

- 从候选尾部文本中同时完成参考文献区识别和题录结构化；
- 通过 `ignore` 字段排除非参考文献内容。

Prompt 设计要点（对应 `PROMPT_STAGE_BC`）：

- 明确角色：学术文献参考文献解析专家；
- 说明输入来源：PDF 尾部提取的原始文本；
- 列出可能出现的噪音类型：英文摘要、附录、补充材料、致谢、作者简介；
- 输出格式：严格 JSON，`references` 数组；
- 每条必须包含 `reference_order`、`raw_text`、`authors`、`year`、`title`、`journal`、`volume`、`issue`、`pages`、`doi`、`language`、`ignore`、`ignore_reason`；
- 关键约束：不确定字段填 `null`，不得编造；非参考文献标记 `ignore=true`。

实测效果：

- 中文 PDF：38/38 条全部正确，0 条误识别；
- 英文 PDF：27/27 条全部正确，0 条误识别；
- JSON 结构稳定，`json_repair` 仅做保险，实际未触发修复。

### 7.2 Prompt B：正文引用追踪（已验证）

目标：

- 将全文正文 + 全部参考文献列表一次发给 DeepSeek；
- 要求模型输出每条参考文献在正文中的引用句子和引用方式。

Prompt 设计要点：

- 明确角色：学术文献引用追踪专家；
- 输入：全文正文 + 结构化参考文献列表；
- 说明引用可能出现的格式：数字编号 `[1]`、作者-年份 `Smith (2020)`、中文 `张三（2020）`、描述性引用；
- 输出格式：严格 JSON，每条参考文献一个 `citation_traces` 条目；
- 每条命中包含：`quote`（正文原文句子）、`citation_style`、`confidence`；
- 关键约束：quote 必须是正文的精确子串；不确定则不输出；宁缺毋滥。

实测效果（`test_citation_tracing.py`，每篇 10 条参考文献）：

| 指标 | 中文 PDF | 英文 PDF |
|---|---|---|
| LLM-direct 命中数 | 9 | 8 |
| 有命中的文献数 | 7/10 | 6/10 |
| 发现描述性引用 | 是 | 是 |
| 正则方案作为对照 | 13（含误匹配） | 24（含大量误匹配） |

DeepSeek 独有能力（正则做不到）：

- 找到描述性引用（如 "according to Smith's study on platform competition"）；
- 区分同名作者的不同文献；
- 在 pypdf 提取质量差的文本中仍然能工作。

缓存策略：

- Prompt A 和 Prompt B 共享正文前缀 → 第二次调用正文部分命中硬盘缓存；
- 如需分批输出，正文前缀持续命中缓存，成本递减。

---

## 8. 推荐 JSON 输出结构

建议统一要求模型返回以下结构：

```json
{
  "references": [
    {
      "reference_order": 1,
      "raw_text": "Smith, J. (2020)...",
      "authors": ["Smith, J."],
      "year": 2020,
      "title": "Platform Competition",
      "journal": "Journal of Tests",
      "volume": "10",
      "issue": "2",
      "pages": "1-20",
      "doi": "10.1000/platform",
      "language": "en",
      "ignore": false,
      "ignore_reason": null
    }
  ]
}
```

补充约束：

- `references` 必须是数组；
- `reference_order` 尽量按原顺序给出；
- `ignore=true` 时必须给出 `ignore_reason`；
- 程序只处理 `ignore=false` 的条目；
- 程序必须保留模型原始输出以便调试。

---

## 9. DeepSeek API 调用约束

### 9.1 基础配置

新方案统一采用 OpenAI 兼容访问方式：

- `base_url = https://api.deepseek.com`
- `api_key = DEEPSEEK_API_KEY`

模型参数（deepseek-v4-flash）：

- 上下文长度：**1M tokens**
- 最大输出：**384K tokens**
- 价格：输入 1 元/百万 tokens（缓存命中 0.02 元），输出 2 元/百万 tokens
- 硬盘缓存：默认开启，无需额外配置

### 9.2 模型名

推荐模型：

- `deepseek-v4-flash`

说明：

- 这是本方案的默认模型名；
- 新方案不再把 `deepseek-chat` 当成正式配置名；
- 如后续发现少量复杂样本质量不足，可评估是否对失败样本单独兜底到 `deepseek-v4-pro`。

### 9.3 输出要求与重试策略

接口调用时建议：

- 使用非流式输出；
- 设置 `response_format={"type": "json_object"}` 要求结构化 JSON；
- system 或 user prompt 中必须包含 `json` 字样并给出 JSON 样例；
- 合理设置 `max_tokens`，防止 JSON 字符串被中途截断（**必须设 `max_tokens=16384`**，复杂场景可增至 32768）。

#### 空内容重试策略（必须实现）

根据 DeepSeek 官方文档说明：

> 在使用 JSON Output 功能时，API 有概率会返回空的 content。我们正在积极优化该问题。

因此所有 DeepSeek 调用必须实现以下重试逻辑：

```python
MAX_RETRIES = 3

def call_deepseek_with_retry(client, messages, **kwargs) -> dict:
    kwargs.setdefault("max_tokens", 16384)
    for attempt in range(MAX_RETRIES):
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            extra_body={"thinking": {"type": "disabled"}},
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            **kwargs,
        )
        raw = response.choices[0].message.content
        if raw and raw.strip():
            return json_repair.repair_json(raw, return_objects=True)
        # 空内容，重试
        logger.warning(f"DeepSeek returned empty content (attempt {attempt+1}/{MAX_RETRIES})")
    # 全部重试失败，回退兜底
    return None
```

重试策略要点：

- 最多重试 3 次；
- 每次重试之间不增加延迟（空内容问题与限流无关）；
- 如果 prompt 中包含 `json` 样例但仍返回空内容，可尝试微调 prompt 措辞后重试；
- 全部重试失败后回退到旧规则链路作为兜底；
- 所有重试结果（成功/失败/空内容次数）应记录到任务日志中。

---

## 10. 对现有 P0 架构的影响

本次方案是“识别链路改造”，不是“整套 P0 推翻重来”。

可以继续复用的部分：

- 前端 `参考文献梳理` 标签页；
- 任务体系 `jobs / job_bib_entries / artifacts`；
- 数据库存储 `bib_references / bib_reference_citations`；
- 文献库导入逻辑；
- 结果表格展示逻辑。

需要重点替换的部分：

- 当前基于规则的参考文献分条逻辑；
- 当前基于启发式的标题抽取逻辑；
- 当前对尾部非参考文献内容缺乏语义排除能力的部分。

建议理解为：

- 前端和数据库层基本复用；
- 后端识别核心实现改成 `DeepSeek Flash + 程序化约束`。

---

## 11. 与上下文缓存的关系

新方案天然适合和上下文缓存结合。

### 11.1 对新上传 PDF

在精读链路中顺带做参考文献识别时，可以复用：

- 已提取的正文文本；
- 已建立的文档上下文；
- 可能已有的稳定提示词前缀；
- 同一篇文档的多轮调用上下文。

这是“充分利用上下文缓存”的主要收益点。

### 11.2 对已有 PDF

已有 PDF 不一定能吃到完整精读上下文缓存，但仍可做轻量缓存：

- 对同一篇文档尾部文本做预处理缓存；
- 对相同 Prompt 前缀做稳定化；
- 对重试调用复用已定位的参考文献候选区。

---

## 12. 风险与控制策略

### 12.1 风险一：模型仍会误识别摘要或附录

控制策略：

- 先程序截尾部候选范围；
- 再在 Prompt 中明确“后续可能仍有摘要、附录等，必须忽略”；
- 输出中加入 `ignore` 字段。

### 12.2 风险二：模型返回 JSON 不稳定或返回空内容

已知问题（DeepSeek 官方确认）：

> 在使用 JSON Output 功能时，API 有概率会返回空的 content。

控制策略：

- 所有调用必须实现重试逻辑（最多 3 次，见 9.3 节）；
- Prompt 中必须包含 `json` 字样和 JSON 样例；
- 合理设置 `max_tokens` 防止截断；
- 程序侧用 `json_repair` 做容错解析；
- 程序侧做 schema 校验（必填字段、类型检查）；
- 全部重试失败后回退兜底逻辑；
- 记录空内容发生次数到任务日志，便于后续统计分析。

### 12.3 风险三：模型臆造字段

控制策略：

- 在 Prompt 中明确“不确定返回 null，不得编造”；
- 对 DOI、年份、页码等字段做程序侧校验；
- 低质量条目不自动导入文献库。

### 12.4 风险四：成本过高

控制策略：

- 只处理尾部候选区，不处理整篇全文；
- 优先使用 `deepseek-v4-flash`；
- 新上传 PDF 复用精读上下文；
- 对多次失败样本再考虑更高成本模型。

### 12.5 风险五：分块边界截断导致第二块返回 0 条（实测发现）

实测现象：

- 8000 字符分块后，第二块（8000-13000）返回 0 条参考文献。

可能原因：

- 分块在条目中间截断，模型无法拼合；
- 第二块剩余文本太短或结构不完整。

控制策略：

- 分块时优先在换行符处截断（当前已做，但策略可加强）；
- 如果第二块返回 0 条，尝试与前一块合并重试；
- 或直接放宽单块大小到 12000-15000 字符（实测 8000 字符块返回 38 条，模型完全能处理更长的块）；
- 考虑不固定分块，而是按参考文献条目的自然边界分批。

### 12.6 风险六：pypdf 文本提取影响标题检测（实测发现）

实测现象：

- 某些 PDF 用 pypdf 提取后，"参考文献" 标题虽存在但被合并到长行中，导致程序无法定位。

控制策略：

- 优先使用 PaddleOCR 提取的 Markdown 作为输入源（保留换行和格式）；
- pypdf 作为后备时，加强标题检测：除了精确匹配，增加模糊匹配和上下文推断；
- 未找到标题时，兜底策略为取最后 3-5 页文本。

### 12.7 风险七：合辑 PDF 多论文参考文献混排（实测发现）

实测现象：

- 中文学术期刊常以合辑 PDF 形式发布，一篇 PDF 包含多篇论文；
- 一篇论文的参考文献可能被另一篇论文整块打断（"下转/上接"标记）；
- DeepSeek 默认输出限制可能导致续页后的参考文献被截断（48/52 → 缺 4 条）。

控制策略：

- 程序侧清除"下转第 X 页"/"上接第 X 页"标记；
- 程序侧预过滤非参考文献内容（附录表格、英文摘要、期刊页眉等）；
- **必须显式设置 `max_tokens=16384`**（默认值导致长 JSON 被截断）；
- Prompt 中明确告知"续页后仍有参考文献"和"预期约 XX 条"。

### 12.8 风险八：`max_tokens` 默认值导致 JSON 截断（实测发现）

实测现象：

- 不设置 `max_tokens` 时，复杂 PDF（52 条参考文献）仅返回 48 条；
- `finish_reason=stop` 但 JSON 不完整——模型认为已输出足够内容。

控制策略：

- **所有 DeepSeek JSON Output 调用必须设置 `max_tokens=16384`**；
- 复杂场景（参考文献 > 40 条）可适当增加到 32768；
- 检查 `finish_reason`：若为 `length` 则需增大 `max_tokens` 重试。

---

## 13. 推荐实施顺序

验证已通过，以下是实施推进顺序：

1. **封装 DeepSeek 调用与 Prompt** — 将已验证的 `PROMPT_STAGE_BC` 和调用逻辑封装为后端服务；
2. **替换已有 PDF 场景的识别链路** — 在 `backend/routers/references.py` 中替换 `split_references()` + `parse_reference_metadata()` 为 DeepSeek 调用；
3. **跑通已有 PDF 端到端** — 从标签页选择 PDF → 触发任务 → DeepSeek 识别 → 入库 → 前端展示；
4. **再接"新上传 PDF 精读顺带识别"** — 在精读任务中增加 `reference_prepare` / `reference_parse` 子阶段；
5. **补缓存统计和失败重试策略** — 记录 `cache_hit_tokens`，对失败样本自动重试或回退旧规则；
6. **前端增强** — 增加"模型识别说明 / 忽略原因"展示。

原因：

- 已有 PDF 场景改动最小；
- 验证最直接；
- 更容易快速看到识别质量提升；
- 不会先把精读主流程变得复杂。

---

## 14. 已验证结论

以下结论已通过 `test_deepseek_references.py` 和 `test_citation_tracing.py` 实测确认。

### 14.1 参考文献识别（Prompt A）

| 验证项 | 结果 |
|---|---|
| DeepSeek 能否正确识别参考文献条目 | 中文 38/38，英文 27/27 |
| 能否过滤非参考文献噪音 | 0 条误识别 |
| JSON 结构是否稳定 | 稳定，`json_repair` 未触发 |
| 能否合并错误断行 | 能，中文 `（ 1 ）` 格式、英文 author-year 格式均正确处理 |
| 输出是否可映射到 `bib_references` 表 | DB 写入+回滚测试通过 |
| 上下文缓存是否生效 | 第二次调用 cache_hit=1536 tokens |
| 与旧规则对比 | DeepSeek 38 vs 旧规则 2（中文），DeepSeek 27 vs 旧规则 3（英文） |
| 字段覆盖率 | authors/year/title/journal/language 均 100% |
| DOI 覆盖率 | 0%（pypdf 提取文本本身不含 DOI，非模型问题） |
| 单篇处理耗时 | 57-82 秒（含 API 调用） |

### 14.2 正文引用追踪（Prompt B）

| 验证项 | 结果 |
|---|---|
| DeepSeek 能否找到正文引用 | 中文 9 hits/10 refs，英文 8 hits/10 refs |
| 与纯正则对比 | 正则中文 13（含误匹配）/英文 24（含大量误匹配） |
| 与正则+LLM 核验对比 | 正则+LLM 中文 10/英文 **0**（英文完全失效） |
| 能否找到描述性引用 | 能（正则做不到） |
| quote 是否为正文精确子串 | 是 |
| 上下文长度是否够用 | 1M tokens，论文全文（20-40K）远低于上限 |
| 硬盘缓存是否可用 | 是，共享正文前缀时 cache_hit 极高 |

### 14.3 复杂 PDF 验证：多论文合辑 + 跨页参考文献（yaojiaquan.pdf）

> 验证日期：2026-04-30
> 测试脚本：`test_complex_pdf.py`
> PDF 来源：《管理世界》2024 年第 2 期合辑 PDF（23 页）

#### PDF 结构特征

该 PDF 是一本中文学术期刊的合辑，包含两篇完整论文：

1. **目标论文**：姚加权等《人工智能如何提升企业生产效率？》
   - 参考文献 (1)-(49) 在第 15-16 页
   - "下转第 133 页"标记后，被另一篇论文整块插入
   - "上接第 116 页"标记后，参考文献 (50)-(52) 续上
   - 总计 52 条参考文献，跨 3 个页面区域分布

2. **另一篇论文**：孙震等《平台运营商并购的福利分析》
   - 参考文献 (34)-(45) 插在目标论文参考文献中间
   - 含完整英文标题、摘要、关键词
   - 主题为平台并购与市场竞争，与目标论文完全无关

#### 测试结果

| 验证项 | 结果 |
|---|---|
| 目标论文参考文献提取 | **52/52**（100%） |
| 另一篇论文参考文献泄露 | **0 条**（完全排除） |
| 编号连续性 | 1-52 连续（程序侧重新编号） |
| 附录参考文献(1)-(4) | 未混入 |
| 英文摘要/Summary | 未混入 |
| 续页标记处理 | 清除"下转/上接"标记后模型正常解析 |
| JSON 结构稳定性 | 稳定，`finish_reason=stop` |

#### 关键发现

1. **`max_tokens` 必须显式设置**：默认输出限制导致 48/52（缺少续页后的 4 条）。设置 `max_tokens=16384` 后完整提取 52/52。
2. **续页标记清除**：程序侧用正则 `（\s*(?:下转|上接)\s*第\s*\d+\s*页\s*）` 清除续页标记，避免干扰模型。
3. **噪音过滤**：程序侧预过滤附录表格数据、英文摘要、期刊页眉等非参考文献内容，将候选文本从 785 行精简到 270 行。
4. **Prompt 关键指令**：必须明确告知模型"续页后仍有参考文献"和"预期约 50-52 条"。

#### 程序侧优化（新增）

- `clean_continuation_markers()`：正则清除"下转第 X 页"/"上接第 X 页"标记
- `looks_like_ref_entry()`：识别 `(N)` 编号开头的行
- `looks_like_table_data()`：过滤附录表格数据
- `NON_REF_PATTERNS`：过滤页码、期刊页眉、英文摘要标记等
- 候选文本按 `--- SECTION BREAK ---` 分段，帮助模型理解结构

### 14.4 尾注法 PDF 验证：GB/T 7714 格式 + 跨英文摘要续页（fc3fde00.pdf）

> 验证日期：2026-04-30
> 测试脚本：`test_complex_pdf.py`
> PDF 来源：《中国土地科学》2025 年第 11 期（11 页）

#### PDF 结构特征

该 PDF 使用**尾注法**（endnote style），与之前验证的尾注区（reference list）格式不同：

- 参考文献 `［1］`-`［40］` 使用**全角方括号**编号
- 采用 **GB/T 7714** 格式：`作者. 标题 [J]. 期刊, 年, 卷(期): 页码.`
- 标题为 `参考文献（References）:` 格式
- 参考文献 [1]-[37] 在第 9-10 页
- 参考文献 [38]-[40] 在第 11 页**英文摘要之后**（跨摘要续页）
- 中英文参考文献混排

#### 测试结果

| 验证项 | 结果 |
|---|---|
| 参考文献 | **40/40（100%）** |
| 误识别 | **0 条** |
| 编号连续性 | 1-40 连续 |
| 跨英文摘要续页 | [38]-[40] 正确提取 |
| GB/T 7714 格式识别 | 正确解析 `[J]` 期刊标记 |
| 中英文混排 | 正确区分语言 |
| 全角方括号 `［N］` | 正确识别 |

#### 关键发现

1. **DeepSeek 天然支持多种参考文献格式**：无需针对尾注法/尾注区/GB/T 7714/APA 等格式分别适配
2. **跨摘要续页无需特殊处理**：程序侧 SECTION BREAK 机制足以帮助模型理解结构
3. **全角标点符号不影响识别**：`［N］`、`［J］` 等全角标记被正确解析
4. **候选文本预过滤有效**：英文摘要、期刊页眉等噪音被程序侧和模型侧双重过滤

---

## 15. 当前建议结论

测试已验证，将参考文献识别重构为"候选范围定位 + DeepSeek `deepseek-v4-flash` 单次结构化解析"的方案切实可行。

核心决策：

- **单次模型调用**替代原方案的两阶段调用（实测 ignore 字段足以过滤噪音）；
- **优先使用 PaddleOCR 提取的 Markdown** 作为输入源（解决 pypdf 标题检测问题）；
- **分块策略需优化**（考虑放大块尺寸或按自然边界分批）；
- **必须显式设置 `max_tokens=16384`**（避免 JSON 输出被截断）；
- **程序侧清除续页标记 + 预过滤噪音**（合辑 PDF 场景）；
- 新上传 PDF 在精读中顺带完成参考文献识别；
- 已有 PDF 直接对尾部参考文献候选区做识别。

---

## 16. 本文档范围说明

本文档是专项规划文档，已从"规划"进入"验证通过"状态。

当前状态：

- 方案已形成并写入 `docs`；
- 已通过 `test_deepseek_references.py` 完成基础实测验证（中文 38/38、英文 27/27）；
- 已通过 `test_complex_pdf.py` 完成复杂场景验证（合辑 PDF 52/52、尾注法 PDF 40/40）；
- **全部 4 篇测试 PDF 均 100% 提取、0% 误识别**；
- 进入实施阶段。

---

## 17. 场景一实施：精读顺带识别参考文献

### 17.1 问题发现

实施场景一时发现：完成精读后，前端"参考文献梳理"标签页仍显示"该文献未梳理"。

**根因分析**：

`reading.py` 中的 `_try_extract_references` 函数只完成了以下步骤：

1. 调用 DeepSeek 识别参考文献 ✓
2. 调用 DeepSeek 追踪正文引用 ✓
3. 生成文件产物（Excel/Markdown/JSON） ✓
4. **将数据写入 `BibReference` / `BibReferenceCitation` 表** ✗ 缺失

而前端判断"是否已梳理"的逻辑是查询 `BibReference` 表：

```python
# references.py:850-852
has_reference_trace = (
    await db.execute(
        select(BibReference.id)
        .where(BibReference.source_bib_entry_id == entry.id)
    )
).first() is not None
```

由于没有执行第 4 步，数据库中无记录，前端自然显示"未梳理"。

### 17.2 修复方案

修改 `_try_extract_references` 函数，在生成文件产物后，创建独立的 `reference_trace` 类型 Job 并调用 `persist_trace_success` 完成数据入库。

```python
def _try_extract_references(...) -> list[dict]:
    # 1. DeepSeek 识别参考文献
    references = extract_references_deepseek(file_path)
    # 2. DeepSeek 追踪正文引用
    references = trace_citations_deepseek(file_path, references)
    # 3. 生成文件产物
    artifact_files = write_trace_outputs(user_id, task_id, source_title, references)
    # 4. 创建 reference_trace Job 并写入数据库（新增）
    ref_task_id = str(uuid.uuid4())
    asyncio.run(_create_ref_trace_job_and_persist(
        ref_task_id, user_id, bib_entry_id, references, artifact_files,
    ))
    return artifact_files
```

### 17.3 Artifact 重复创建问题

#### 为什么会重复

精读流程中有**两个独立的任务**会创建 Artifact 记录：

| 任务 | Job 类型 | 负责创建的 Artifact |
|------|----------|---------------------|
| 精读任务 | `reading_long` / `reading_quant` / `reading_qual` | `reading_final`（精读报告） |
| 参考文献梳理任务 | `reference_trace` | `references_excel`、`citation_trace_md` 等 |

在修复前的代码中，精读任务的 `finalize_reading_success` 函数会将 `ref_artifacts` 合并到 `all_artifacts` 中一起写入：

```python
# 修复前（会产生重复）
all_artifacts = [{"artifact_type": "reading_final", "absolute_path": report_path}] + ref_artifacts
finalize_reading_success(task_id, ..., all_artifacts, ...)
```

修复后，`_try_extract_references` 内部调用 `persist_trace_success`，该函数会为 `ref_artifacts` 创建 Artifact 记录（`job_id = ref_task_id`）。

如果不修改调用处，`ref_artifacts` 会被创建两次：

```
第一次：persist_trace_success 创建 → job_id = ref_task_id（reference_trace Job）
第二次：finalize_reading_success 创建 → job_id = task_id（精读 Job）
```

#### 如何避免重复

修改三个调用处（`run_long_context_task`、`run_quant_task`、`run_qual_task`），从 `all_artifacts` 中移除 `ref_artifacts`：

```python
# 修复后（避免重复）
# ref_artifacts 已由 _try_extract_references → persist_trace_success 写入数据库
# 此处只传入精读报告的 artifact
all_artifacts = [{"artifact_type": "reading_final", "absolute_path": report_path}]
finalize_reading_success(task_id, ..., all_artifacts, ...)
```

#### 数据流向图

```
精读任务 (task_id, job_type=reading_*)
    │
    ├── 精读分析 → 生成 reading_final artifact
    │               └── finalize_reading_success 写入 DB (job_id = task_id)
    │
    └── _try_extract_references
            │
            ├── DeepSeek 识别 + 追踪
            ├── write_trace_outputs 生成文件
            │
            └── _create_ref_trace_job_and_persist
                    │
                    ├── 创建 reference_trace Job (ref_task_id)
                    └── persist_trace_success 写入 DB (job_id = ref_task_id)
                            │
                            ├── BibReference 表 ← 参考文献条目
                            ├── BibReferenceCitation 表 ← 正文引用
                            └── Artifact 表 ← references_excel 等
```

### 17.4 前端查询路径

前端"参考文献梳理"标签页的查询路径：

```
1. GET /api/references/entries
   → 查询所有带 PDF 的 BibEntry
   → 对每个 entry 查询 BibReference 表判断 has_reference_trace

2. GET /api/references/entries/{entry_id}/summary
   → 查询 BibReference 统计数量
   → 查询 latest_reference_task 获取最新 reference_trace 类型 Job

3. GET /api/references/entries/{entry_id}/references
   → 查询 BibReference 列表展示
```

关键点：`latest_reference_task` 函数过滤 `job_type == "reference_trace"`：

```python
# references.py:809-822
latest_job = (
    await db.execute(
        select(Job)
        .join(JobBibEntry, JobBibEntry.job_id == Job.id)
        .where(
            Job.owner_user_id == user_id,
            Job.job_type == "reference_trace",  # ← 关键过滤条件
            JobBibEntry.bib_entry_id == entry_id,
            JobBibEntry.role == "reference_source",
        )
        .order_by(Job.created_at.desc())
    )
).scalars().first()
```

因此必须创建独立的 `reference_trace` 类型 Job，而不能复用精读 Job。

### 17.5 修改清单

| 文件 | 修改位置 | 修改内容 |
|------|----------|----------|
| `backend/routers/reading.py` | `_try_extract_references` (L531-568) | 新增数据库写入逻辑 |
| `backend/routers/reading.py` | `_create_ref_trace_job_and_persist` (L571-610) | 新增函数：创建 Job + 调用 persist |
| `backend/routers/reading.py` | `run_long_context_task` (L795) | 从 all_artifacts 移除 ref_artifacts |
| `backend/routers/reading.py` | `run_quant_task` (L924) | 从 all_artifacts 移除 ref_artifacts |
| `backend/routers/reading.py` | `run_qual_task` (L1043) | 从 all_artifacts 移除 ref_artifacts |
