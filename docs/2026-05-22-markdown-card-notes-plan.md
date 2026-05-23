# Markdown 原文阅读与 AI 卡片笔记功能规划

> 状态：已讨论，待实施  
> 日期：2026-05-22  
> 目标：把 Markdown 原文、译文阅读与 AI 卡片笔记接成一条可在系统内管理、又可迁移到 Obsidian 的阅读整理链路。

## 1. 目标与范围

新增一套面向 Markdown 论文的阅读制卡能力：

1. 文献库中的论文可以挂载 Markdown 原文。
2. 已有数据库中的 Markdown、从精读入口传入的 Markdown、从翻译入口传入的 Markdown，都可由后端格式化后进入阅读器。
3. 用户在阅读页选中文本后，可以基于选段、上下文和可选自定义提示词生成 AI 卡片。
4. 卡片作为系统内一等资产进入卡片库，同时保存为 Obsidian 友好的 Markdown 文件镜像。
5. 在线版可以打包下载卡片与关联论文 Markdown，方便后续直接放入 Obsidian。

第一版不做：

- 原文选段持久高亮。
- 精确段落锚点回跳。
- 卡片之间的自动链接推荐。
- Markdown 挂载后自动跑参考文献梳理。
- 多个历史译文版本的阅读切换器。

## 2. 已确认的产品决策

### 2.1 阅读页形态

- 阅读页做成工作台内的隐藏路由，不加入顶部一级导航。
- 从文献库、翻译结果等入口进入阅读页。
- 阅读页是长文阅读与制卡主界面，不复用现有只读 Markdown 预览页。

建议路由：

- `/workspace/library/:entryId/reader?view=original`
- `/workspace/library/:entryId/reader?view=translated`
- `/workspace/library/cards`

### 2.2 PDF 与 Markdown 并存

- 同一篇论文允许 PDF 与 Markdown 并存。
- 现有 `BibEntry.source_file_id` 保持当前主源文件语义，避免影响现有精读、预览和参考文献梳理流程。
- 新增专用 Markdown 原文绑定字段，例如 `BibEntry.markdown_source_file_id`。
- 老数据中若 `source_file_id` 已经是 Markdown，阅读器需要兼容读取，并可在后端挂载流程中补齐专用绑定。

### 2.3 翻译入口的阅读规则

- 从翻译入口进入阅读器时，默认展示最近一次成功翻译生成的 `translation_md`。
- 如果翻译任务的原始输入本来就是 Markdown，阅读页允许用户主动切换到原文。
- 如果翻译任务的原始输入是 PDF，第一版只在阅读器中展示译文 Markdown：
  - 不额外持久化翻译过程中临时抽取的 PDF 原文 Markdown。
  - 不提供“切换到原文 Markdown”。
- 卡片必须记录用户生成卡片时所读的版本：
  - `original`
  - `translated`

### 2.4 卡片归宿与导出

- 卡片先作为系统内卡片库资产，不只挂在单篇原文下。
- 卡片库入口放在“我的文献库”内。
- 下载包导出卡片和对应版本的规范化论文 Markdown：
  - 原文卡链接原文论文笔记。
  - 译文卡链接译文论文笔记。
  - 一篇论文同时有原文卡与译文卡时，两个论文版本都导出。

## 3. 用户流程

### 3.1 文献库原文阅读

1. 用户进入“我的文献库”。
2. 对指定文献上传或选择已存在的 Markdown 原文。
3. 系统将 Markdown 挂到该 `BibEntry`。
4. 用户点击“阅读并制卡”进入隐藏阅读页。
5. 阅读页展示论文元数据、正文、引用关系侧栏和已有卡片。

### 3.2 精读入口接入

1. 用户在精读流程上传 Markdown。
2. 后端创建或匹配 `BibEntry`。
3. 后端同时把该 Markdown 挂载为原文阅读版本。
4. 精读结果仍按现有任务链路生成；阅读制卡能力复用同一篇文献的 Markdown 原文。

### 3.3 翻译入口接入

1. 用户从翻译入口上传或选择源文件。
2. 翻译任务成功后生成 `translation_md`。
3. 翻译结果提供“阅读译文并制卡”入口。
4. 阅读器默认打开最新成功译文。
5. 若源文件也是 Markdown，用户可切回原文后再选段制卡。

### 3.4 选段制卡

1. 用户在阅读页选中文本。
2. 页面显示浮动操作层：
   - 选段预览。
   - 可选提示词输入框。
   - `AI 卡片` 按钮。
3. 用户点击生成。
4. 后端以当前阅读版本、论文元数据、选段、前后文和自定义提示词生成卡片。
5. 卡片保存成功后：
   - 出现在当前论文关联卡片列表。
   - 出现在文献库卡片库。
   - 同步生成 Markdown 文件镜像。

## 4. 阅读器设计

### 4.1 页面布局

阅读页建议分为三块：

- 左侧侧栏：
  - 论文引用了哪些文献。
  - 哪些库内文献引用了当前论文。
  - 引用数据缺失时的参考文献梳理入口。
- 中间正文：
  - 当前阅读版本的 Markdown 正文。
  - 论文元数据头视图。
  - 文本选区与浮动制卡交互。
- 右侧或正文内辅助区：
  - 当前论文卡片列表。
  - 跳转卡片库入口。
  - 当前版本标识与可用版本切换。

### 4.2 元数据与 Markdown 正规化

阅读页与导出包使用后端生成的规范化 Markdown 投影，不直接改写用户上传文件。

论文元数据优先来自 `BibEntry`：

- 标题
- 作者
- 期刊
- 年份
- 卷号
- 期号
- 页码
- DOI
- 摘要
- 关键词

处理约定：

- 原始 Markdown 正文结构尽量保留。
- 若上传 Markdown 自带 YAML frontmatter：
  - 阅读页避免重复展示。
  - 导出时统一生成系统规范 frontmatter。
- 论文导出文件追加卡片回链区。

### 4.3 引用关系侧栏

第一版复用现有数据：

- `BibReference`
- `BibReferenceCitation`
- 已匹配的 `BibEntry`

展示逻辑：

- “引用了”来自当前论文的 `BibReference`。
- “被引用”来自其他库内论文中 `matched_bib_entry_id == 当前论文` 的引用关系。
- 若当前论文尚无引用梳理结果：
  - 侧栏显示空状态。
  - 提供手动触发现有参考文献梳理任务的入口。

## 5. 数据模型规划

### 5.1 BibEntry

新增字段建议：

```text
markdown_source_file_id TEXT NULL REFERENCES files(id)
```

用途：

- 保存论文原始 Markdown 阅读版本的文件绑定。
- 与现有 `source_file_id` 并存。

兼容规则：

- 若 `markdown_source_file_id` 存在，阅读原文优先使用它。
- 若不存在，但 `source_file_id` 指向 Markdown，则回退使用 `source_file_id`。

### 5.2 CardNote

新增专用卡片表，不把卡片塞进现有 `Annotation`。

建议字段：

```text
id
owner_user_id
source_bib_entry_id
source_version
source_markdown_file_id
source_translation_artifact_id
title
summary
tags_json
selected_text
context_before
context_after
user_prompt
body_markdown
storage_path
created_at
updated_at
expires_at
```

字段约定：

- `source_version` 取值：
  - `original`
  - `translated`
- 原文卡：
  - 记录 `source_markdown_file_id`。
  - `source_translation_artifact_id` 为空。
- 译文卡：
  - 记录对应 `translation_md` 的 artifact id。
  - `source_markdown_file_id` 可为空。
- 卡片永远归属一个 `source_bib_entry_id`。

### 5.3 文件镜像

卡片 DB 记录是系统主索引与主数据源，同时同步真实 Markdown 文件镜像。

建议用户笔记目录结构：

```text
notes/
  cards/
    card-<card-id>-<slug>.md
  papers/
    paper-<bib-id>-original.md
    paper-<bib-id>-translated.md
```

文件名要求：

- 含稳定 ID。
- 标题修改不导致链接完全失效。
- 标题部分做文件名清洗。

## 6. AI 卡片生成

### 6.1 默认卡片结构

默认提示词生成中文“原子阅读卡”：

- 卡片标题。
- 一句话总结。
- 核心观点。
- 依据/证据。
- 阅读笔记。
- 启发、用途或与研究问题的关系。

### 6.2 生成输入

后端生成请求应提供：

- 当前阅读版本。
- 论文元数据。
- 选中文本。
- 选段前后文。
- 可选用户提示词。
- 用户 DeepSeek API Key。

### 6.3 提示词管理

新增提示词类型，例如：

```text
prompt_type = card_note
prompt_key = atomic_card_writer
```

纳入现有提示词优先级：

1. 用户覆盖。
2. 系统默认。
3. 文件兜底。
4. 代码兜底。

模型输出建议固定为 JSON：

```json
{
  "title": "卡片标题",
  "summary": "一句话总结",
  "tags": ["tag-a", "tag-b"],
  "body_markdown": "卡片正文"
}
```

用户自定义提示词只改变卡片内容侧重点，不应破坏系统所需结构字段与来源回链。

## 7. API 规划

### 7.1 Markdown 挂载与阅读器

- `POST /api/library/entries/{entry_id}/markdown`
  - 为指定文献上传并绑定 Markdown 原文。
- `GET /api/library/entries/{entry_id}/reader?view=original|translated`
  - 返回阅读器所需数据：
    - 当前版本。
    - 可切换版本。
    - 论文元数据。
    - Markdown 内容。
    - 引用关系摘要。
    - 关联卡片摘要。

### 7.2 卡片

- `POST /api/cards/from-selection`
  - 根据当前阅读版本中的选段生成并保存卡片。
- `GET /api/cards`
  - 卡片库列表。
  - 支持按论文、标签、创建时间筛选。
- `GET /api/cards/{card_id}`
  - 卡片详情。
- `PATCH /api/cards/{card_id}`
  - 编辑标题、标签和正文。
- `DELETE /api/cards/{card_id}`
  - 删除卡片及其文件镜像。
- `GET /api/cards/export`
  - 下载 Obsidian 兼容 ZIP 包。

## 8. 前端规划

### 8.1 我的文献库

新增：

- Markdown 原文上传/替换按钮。
- “阅读并制卡”入口。
- 卡片库子入口。

### 8.2 翻译页

翻译成功结果新增：

- “阅读译文并制卡”入口。

进入阅读器时：

- 默认打开最新成功译文。
- 只有当原始输入是 Markdown 时，阅读器显示“原文/译文”切换。

### 8.3 卡片库

第一版支持：

- 按来源论文查看。
- 按标签筛选。
- 按创建时间排序。
- 查看卡片详情。
- 编辑卡片标题、标签与正文。
- 删除卡片。
- 跳回来源论文阅读页。

## 9. Obsidian 导出规划

下载包结构建议：

```text
cards/
  card-<id>-<title>.md

papers/
  paper-<bib-id>-original.md
  paper-<bib-id>-translated.md
```

### 9.1 卡片 Markdown

frontmatter 至少包含：

- 卡片 ID。
- 标题。
- 来源论文 ID。
- 来源版本。
- 来源论文 wikilink。
- 创建时间。
- 标签。
- 一句话总结。
- 选段摘录。

正文包含：

- AI 卡片正文。
- 来源摘录。
- 来源论文回链。

### 9.2 论文 Markdown

frontmatter 至少包含：

- 论文 ID。
- 标题。
- 作者。
- 期刊。
- 年份。
- 卷号。
- 期号。
- 页码。
- DOI。
- 摘要。
- 关键词。
- 当前版本。

正文包含：

- 规范化后的论文正文。
- 关联卡片回链区。

## 10. 测试与验收

### 10.1 后端测试

- 旧数据中 `source_file_id` 是 Markdown 时，阅读器能读取原文。
- 文献已有 PDF 时，补传 Markdown 不覆盖 PDF。
- 精读入口传入 Markdown 后，自动挂载为原文阅读版本。
- 翻译入口默认打开最新成功 `translation_md`。
- 翻译源文件为 Markdown 时，阅读器允许译文/原文切换。
- 翻译源文件为 PDF 时，阅读器不显示原文 Markdown 切换。
- 原文卡记录原始 Markdown 来源。
- 译文卡记录 `translation_md` artifact 来源。
- 无自定义提示词时使用默认卡片提示词。
- 有自定义提示词时仍返回完整结构化卡片。
- AI 返回空内容、非法 JSON、缺字段时返回明确错误。
- 卡片编辑与删除会同步数据库与 Markdown 文件镜像。
- ZIP 导出：
  - 原文卡导出原文论文页。
  - 译文卡导出译文论文页。
  - 原文卡与译文卡并存时两个论文版本都导出。
  - wikilink 与回链区正确。

### 10.2 前端验收

- 文献库可上传 Markdown 原文并进入阅读器。
- 阅读器可展示元数据、正文、引用侧栏与关联卡片。
- 文本选中后出现浮动制卡面板。
- 卡片生成后能在阅读页和卡片库看到。
- 翻译页进入阅读器时默认显示译文。
- 原文/译文切换只在原始 Markdown 可用时出现。
- 下载包放入 Obsidian 后，论文与卡片链接可用。

## 11. 实施约束

该功能涉及数据库、用户数据导入导出和核心阅读流程，实施时必须同步检查：

- `backend/db/models.py`
- Alembic migration
- `docs/DATABASE_SCHEMA.md`
- `backend/services/data_portability.py`
- `CURRENT_SCHEMA_VERSION`
- normal 用户 24h 清理逻辑
- 自增主键和跨表引用的导入 id remap

按当前项目工作流：

- 先实施与验证功能。
- 用户本地验证通过后，再补正式技术文档、经验总结和文档导航更新。
- 在功能未验证前，不把文档写成“已完成”。
