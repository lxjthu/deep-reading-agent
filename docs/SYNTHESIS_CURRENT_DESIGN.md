# AI 综述功能现状梳理

> 日期：2026-05-03
> 目的：梳理当前 AI 综述功能的完整设计，为后续改进提供基线

## 1. 功能概述

AI 综述功能出现在以下场景：

| 场景 | 前端页面 | 后端端点 | 提示词模式 |
|------|----------|----------|------------|
| 七步对比 - 单问题 | `compare_7step.html` | `POST /api/compare/analyze` | `single` |
| 七步对比 - 多问题 | `compare_7step.html` | `POST /api/compare/analyze` | `multi` |
| 七步对比 - 跨步骤 | `compare_7step.html` | `POST /api/compare/analyze` | `cross` |
| 四步对比 - 单问题 | `compare_4step.html` | `POST /api/compare/analyze` | `single` |
| 四步对比 - 多问题 | `compare_4step.html` | `POST /api/compare/analyze` | `multi` |
| 四步对比 - 跨步骤 | `compare_4step.html` | `POST /api/compare/analyze` | `cross` |
| 长文本对比 - 单维度 | `compare_long.html` | `POST /api/compare/analyze_long` | `single` |
| 长文本对比 - 多维度 | `compare_long.html` | `POST /api/compare/analyze_long` | `multi` |

## 2. 架构设计

```
前端 compare_*.html (iframe)
       │
       ▼
POST /api/compare/analyze 或 /analyze_long
       │
       ▼
┌─────────────────────────────────────┐
│  根据 mode 选择提示词构建函数        │
│  ├─ single → build_single_prompt()   │
│  ├─ multi → build_multi_prompt()     │
│  ├─ cross → build_cross_dim_prompt() │
│  └─ long → build_long_*_prompt()     │
└─────────────────────────────────────┘
       │
       ▼
DeepSeek LLM (deepseek-v4-flash)
       │
       ▼
┌─────────────────────────────────────┐
│  拼接最终输出                        │
│  synthesis = LLM 输出               │
│  references = build_reference_list() │
│  final_text = synthesis + references │
└─────────────────────────────────────┘
       │
       ▼
返回给前端 / 保存到历史记录
```

## 3. 提示词设计

### 3.1 系统提示词 (SYSTEM_PROMPT)

**位置**：`backend/routers/compare.py:438-445`

```
你是一位中文学术写作专家，擅长撰写规范的文献综述段落。
你的任务是根据已有的精读分析内容，综合多篇文献的观点，
写出适合直接插入学术论文文献综述部分的高质量文字。
不要捏造任何数据或结论，严格基于所提供的文献内容进行综合。
引用格式使用间注法：（第一作者姓氏等，年份），或（作者A & 作者B, 年份）。
不要在回复中包含参考文献目录，参考文献将由系统自动生成。
```

**要点**：
- 角色定位：中文学术写作专家
- 核心约束：不捏造数据，基于提供内容
- 引用格式：间注法（作者, 年份）
- 禁止项：不写参考文献目录

### 3.2 单问题提示词 (build_single_prompt)

**位置**：`backend/routers/compare.py:448-477`

**输入**：问题标签 + 多篇文献的子问题内容

**输出要求**：
- 恰好一段 8~15 句的学术性综述
- 结构：
  1. 首句：主题句，点明该问题在学界的整体关注焦点或争议
  2. 中间：逐一或分组介绍各文献的研究视角、数据、发现，比较异同
  3. 重点揭示：哪些结论已形成共识？哪些仍存在分歧或对立？
  4. 末句：指出现有研究的局限、空白或对未来研究的启示

**写作规范**：
- 行文流畅、逻辑连贯，适合直接嵌入学术论文
- 每处引用标注间注：（第一作者姓，年份）或（作者A & 作者B, 年份）
- 不要加标题、不要分小节、不要写引言或结尾感谢语
- 不要写参考文献目录（系统自动生成）

### 3.3 多问题提示词 (build_multi_prompt)

**位置**：`backend/routers/compare.py:480-513`

**输入**：步骤标签 + 子问题列表 + 多篇文献的子问题内容

**输出要求**：
- 引言（1句）：用一句话概括该步骤的整体研究图景
- 各子问题分节（共 N 节）：
  - 每节以 `### [子问题标题]` 为标题
  - 正文 1~2 段，横向比较各文献在该子问题上的数据、方法、结论
  - 明确指出共识与分歧
- 结论（1句）：点出跨问题的整体研究局限或未来方向

### 3.4 跨步骤提示词 (build_cross_dim_prompt)

**位置**：`backend/routers/compare.py:546-603`

**输入**：多篇文献的多个步骤内容（带步骤前缀如 `[第一步] 研究问题`）

**输出要求**：
- 引言（1句）：用一句话概括这批文献整体的研究图景与共性关切
- 各维度分节（共 N 节）：
  - 每节以 `### [维度名称]` 为标题
  - 正文 1~2 段，横向比较各文献在该维度的数据/方法/发现
  - 明确指出共识与分歧
  - 如该维度下有多个子问题，按子问题自然过渡，不再单独分节
- 跨维度结论（1句）：综合各维度，点出整体研究局限或未来突破方向

### 3.5 长文本单维度提示词 (build_long_single_prompt)

**位置**：`backend/routers/compare.py:516-543`

**输出要求**：与单问题类似，但输入为长文本维度内容（截取前 2000 字符）

### 3.6 长文本多维度提示词 (build_long_multi_prompt)

**位置**：`backend/routers/compare.py:606-631`

**输出要求**：与多问题类似，但输入为长文本维度内容（截取前 1200 字符/维度）

## 4. 参考文献目录生成

### 4.1 核心函数

**函数**：`build_reference_list(papers: list) -> str`
**位置**：`backend/routers/compare.py:390-435`

**逻辑**：
1. 遍历每篇 paper 的元数据
2. APA 格式作者处理：
   - 无作者 → "佚名"
   - 1 人 → 直接写
   - 2-3 人 → 逗号和 `&` 连接
   - 超过 3 人 → 前 3 人 + "等"
3. 年份缺失 → 直接显示原值（已知问题：会显示 `None`）
4. 按第一作者姓氏排序
5. 返回格式：`\n\n---\n\n## 参考文献\n\n{ref_block}`

### 4.2 已知问题

| 问题 | 表现 | 根因 |
|------|------|------|
| 年份显示 None | `佚名 (None). 生态产品价值实现...` | 年份字段为空时未兜底 |
| 作者显示佚名 | `佚名 (2023). 论文标题...` | 元数据缺失作者 |
| 正文引用退化 | `（文献1）、（文献2）` | 提示词约束不够强 |
| 引用与目录不对应 | 正文用泛化指代，目录用真实元数据 | 缺少强制锚点机制 |

## 5. 前端触发流程

### 5.1 启用条件

```javascript
const canSynthesize = paperCount >= 2 && selectedCount >= 1;
```

- 至少选择 2 篇文献
- 至少勾选 1 个问题/维度

### 5.2 调用流程

1. 用户勾选文献 + 问题 → 点击 "🤖 生成 AI 综述" 按钮
2. 前端判断 mode：`cross` / `multi` / `single`
3. 构造 `paperData` 数组，每篇包含元数据 + 选中的子问题内容
4. 弹出 API Key 输入框
5. 调用 `POST /api/compare/analyze`
6. 显示 `result.synthesis` 内容
7. 用户点击 "💾 保存到历史记录" → 调用 `POST /api/history/synthesis/`

## 6. 综述历史保存

### 6.1 保存端点

**端点**：`POST /api/history/synthesis/`
**位置**：`backend/routers/history.py:327-425`

**流程**：
1. 通过 `bib_entry_ids` 或 `papers` 标题匹配找到关联文献
2. 创建 `Job(job_type="synthesis")`
3. 写入 `JobBibEntry(role="synthesis_member")` 关联文献
4. 生成 Markdown 文件，包含 YAML 头部
5. 写入 `Artifact(artifact_type="synthesis_md")`

### 6.2 保存的文件格式

```markdown
# AI文献综述：{dimension}

**生成时间**：{timestamp}
**涉及文献**：{papers}
**维度/步骤**：{dimension}

---

{content}
```

## 7. 代码结构总结

### 7.1 后端文件

| 文件 | 职责 |
|------|------|
| `backend/routers/compare.py` | 综述生成核心路由 + 提示词 + 参考文献生成 |
| `backend/routers/history.py` | 综述历史保存与查询 |

### 7.2 前端文件

| 文件 | 职责 |
|------|------|
| `frontend/public/compare_7step.html` | 七步对比页面 |
| `frontend/public/compare_4step.html` | 四步对比页面 |
| `frontend/public/compare_long.html` | 长文本对比页面 |
| `frontend/src/App.tsx` | 对比标签页入口 + 综述历史展示 |

### 7.3 关键函数索引

| 函数 | 位置 | 作用 |
|------|------|------|
| `SYSTEM_PROMPT` | compare.py:438 | 系统提示词 |
| `build_single_prompt()` | compare.py:448 | 单问题提示词 |
| `build_multi_prompt()` | compare.py:480 | 多问题提示词 |
| `build_cross_dim_prompt()` | compare.py:546 | 跨步骤提示词 |
| `build_long_single_prompt()` | compare.py:516 | 长文本单维度提示词 |
| `build_long_multi_prompt()` | compare.py:606 | 长文本多维度提示词 |
| `build_reference_list()` | compare.py:390 | 参考文献目录生成 |
| `build_paper_header()` | compare.py:381 | 文献头部格式化 |
| `format_inline_citation()` | compare.py:365 | 间注格式化 |
| `analyze_comparison()` | compare.py:634 | 七步/四步综述端点 |
| `analyze_long_comparison()` | compare.py:709 | 长文本综述端点 |

## 8. 与 P2 任务的关联

P2（参考文献目录兜底修复）主要涉及：

1. **年份 None 问题**：`build_reference_list()` 中 `year` 缺失时直接显示原值
2. **作者佚名问题**：元数据缺失时的兜底格式
3. **提示词约束问题**：正文引用退化为 "文献1/文献2"

这些问题分散在：
- 提示词层（SYSTEM_PROMPT + 各 build_*_prompt）
- 程序层（build_reference_list）
- 数据层（bib_entries 元数据完整性）

## 9. 现有规划文档

- `docs/SYNTHESIS_PROMPT_PLAN.md` - 综述提示词重构规划（468 行）
- `docs/PENDING_PLANS.md` - 待实施计划表（P2/P3/P4 相关）
