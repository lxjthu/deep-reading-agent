# Markdown 原文阅读与 AI 卡片笔记功能规划

## Summary

新增一套“Markdown 阅读制卡”能力，核心目标是把论文原文、译文和 AI 卡片笔记接成一条可持续整理的链路：

- 文献库中的论文可挂载 Markdown 原文。
- 已有数据库中的 Markdown、从精读入口传入的 Markdown、从翻译入口传入的 Markdown，都可由后端直接格式化后进入阅读器。
- 阅读器是工作台内的隐藏页面，不加入顶部一级导航。
- 用户在阅读页选中文本后生成 AI 卡片，卡片进入系统内卡片库，并可打包下载到 Obsidian。
- 翻译入口默认打开最新成功译文；若原始来源本身是 Markdown，用户可切换回原文。

## Implementation Changes

### 1. 阅读源版本模型

阅读器统一支持两类 Markdown 阅读版本：

- `original`
  - 原始 Markdown 论文。
- `translated`
  - 翻译任务生成的 `translation_md` 产物。

来源解析规则固定为：

- 从“我的文献库”进入阅读器：
  - 默认打开 `original` Markdown。
- 从“翻译”入口进入阅读器：
  - 默认打开最近一次成功翻译得到的 `translation_md`。
- 翻译来源如果原始输入也是 Markdown：
  - 阅读页显示版本切换控件，可在译文与原文之间切换。
- 翻译来源如果原始输入是 PDF：
  - 第一版只在阅读器中显示译文 Markdown。
  - 不额外持久化 PDF 抽取出的原文 Markdown。
  - 不提供“切换到原文 Markdown”。

### 2. Markdown 挂载策略

新增统一的 Markdown 原文挂载能力，避免只依赖文献库手动上传。

挂载来源包括：

- 文献库详情页手动上传 Markdown 原文。
- 旧数据中 `BibEntry.source_file_id` 已经绑定 Markdown 的条目。
- 精读入口传入的 Markdown 文件。
- 翻译入口传入的 Markdown 原文。

实现原则：

- 保留现有 `source_file_id` 的主源文件语义，避免 PDF 与 Markdown 互相覆盖。
- 为论文新增专用 Markdown 原文字段，例如 `markdown_source_file_id`。
- 后端提供统一绑定辅助逻辑：
  - 当输入文件类型是 Markdown 时，优先挂到 `markdown_source_file_id`。
  - 若旧条目本身 `source_file_id` 就是 Markdown，阅读器可兼容回退读取。
- 不修改用户上传的原始 Markdown 文件。
- 阅读页与 Obsidian 下载包使用后端生成的“规范化 Markdown 投影”。

### 3. 规范化论文 Markdown

后端在阅读与导出时生成规范化论文 Markdown：

- 元数据以 `BibEntry` 为主：
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
- 原始 Markdown 正文结构尽量保留。
- 若原文自带 YAML frontmatter：
  - 阅读器避免重复展示。
  - 导出时统一生成系统规范 frontmatter。
- 导出时论文 Markdown 增加卡片回链区。

第一版不做：

- 持久高亮。
- 精确段落锚点回跳。
- 原文文本被卡片反向改写。

### 4. 阅读页

新增隐藏阅读路由，例如：

- `/workspace/library/:entryId/reader?view=original`
- `/workspace/library/:entryId/reader?view=translated`

阅读页包含：

- 顶部论文元数据区。
- 中央 Markdown 正文阅读区。
- 左侧引用关系侧栏。
- 关联卡片入口与当前论文卡片列表。
- 文本选中后的浮动制卡面板。

引用侧栏第一版复用现有引用关系：

- “引用了哪些文献”
- “被哪些库内文献引用”

数据优先来自：

- `BibReference`
- `BibReferenceCitation`
- 已匹配的 `BibEntry`

若当前论文还没有引用梳理结果：

- 阅读页提示可手动触发参考文献梳理。
- 不在 Markdown 挂载时自动调用 AI 做引用提取。

### 5. AI 卡片生成

用户选中文本后浮窗提供：

- 选段预览。
- 可选自定义提示词输入。
- `AI 卡片` 按钮。

生成规则：

- 默认输出中文。
- 无自定义提示词时使用预制“原子阅读卡”提示词。
- 有自定义提示词时按用户要求总结，但仍必须输出完整卡片结构。
- 生成时给模型的上下文包括：
  - 当前阅读版本。
  - 论文元数据。
  - 选中文本。
  - 选段前后文。
  - 用户提示词。

默认卡片结构：

- 卡片标题
- 一句话总结
- 核心观点
- 依据/证据
- 阅读笔记
- 启发或研究用途

卡片来源必须记录当前阅读版本：

- 从原文选段生成：
  - `source_version = original`
  - 关联原始 Markdown 文件。
- 从译文选段生成：
  - `source_version = translated`
  - 关联对应 `translation_md` 产物。
- 两者都归属同一 `BibEntry`。

## Interfaces And Data

### 1. 数据模型

#### `BibEntry`

新增字段：

- `markdown_source_file_id`
  - 指向原始 Markdown 文件。
  - 与现有 PDF 源文件可并存。

#### 新增 `CardNote`

建议字段：

- `id`
- `owner_user_id`
- `source_bib_entry_id`
- `source_version`
  - `original` / `translated`
- `source_markdown_file_id`
  - 原文卡使用。
- `source_translation_artifact_id`
  - 译文卡使用。
- `title`
- `summary`
- `tags_json`
- `selected_text`
- `context_before`
- `context_after`
- `user_prompt`
- `body_markdown`
- `storage_path`
- `created_at`
- `updated_at`
- `expires_at`

### 2. 提示词

在提示词系统中新增卡片笔记类型，例如：

- `prompt_type = card_note`

至少新增一个提示词槽位：

- `atomic_card_writer`

该提示词纳入现有优先级：

1. 用户覆盖
2. 系统默认
3. 文件兜底
4. 代码兜底

模型输出采用结构化 JSON，至少包含：

- `title`
- `summary`
- `tags`
- `body_markdown`

### 3. 后端接口

新增或扩展接口：

- `POST /api/library/entries/{entry_id}/markdown`
  - 为指定文献上传并绑定 Markdown 原文。
- `GET /api/library/entries/{entry_id}/reader?view=original|translated`
  - 返回阅读页所需内容：
    - 当前阅读版本
    - 元数据
    - Markdown 内容
    - 引用关系
    - 关联卡片摘要
    - 可切换版本信息
- `POST /api/cards/from-selection`
  - 根据当前阅读版本中的选段生成并保存卡片。
- `GET /api/cards`
  - 卡片库列表，支持论文、标签、时间筛选。
- `GET /api/cards/{card_id}`
  - 卡片详情。
- `PATCH /api/cards/{card_id}`
  - 编辑标题、标签、正文。
- `DELETE /api/cards/{card_id}`
  - 删除卡片。
- `GET /api/cards/export`
  - 下载 Obsidian 兼容 ZIP 包。

### 4. 前端入口

#### 文献库

新增：

- Markdown 原文上传/替换按钮。
- “阅读并制卡”入口。
- “卡片库”子入口。

#### 精读入口

当精读输入是 Markdown 时：

- 创建/匹配 `BibEntry` 后自动挂载 Markdown 原文阅读版本。

#### 翻译入口

翻译完成后：

- 提供“阅读译文并制卡”入口。
- 打开阅读器时默认 `view=translated`。
- 若原始输入是 Markdown，阅读页允许切换到 `original`。

## Obsidian Export

系统内部卡片既存数据库，也同步生成 Markdown 文件镜像。

导出 ZIP 结构建议：

```text
cards/
  card-<id>-<title>.md

papers/
  paper-<bib-id>-original.md
  paper-<bib-id>-translated.md
```

导出规则：

- 原文卡片链接规范化原文论文笔记。
- 译文卡片链接规范化译文论文笔记。
- 如果一篇论文同时有原文卡与译文卡：
  - 两个论文版本都导出。
- 卡片 Markdown 包含：
  - 来源论文 wikilink
  - 来源版本
  - 选段摘录
  - 一句话总结
  - 标签
  - 创建时间
- 论文 Markdown 包含：
  - 规范化 frontmatter
  - 正文
  - 关联卡片回链区

## Test Plan

### Backend

- 旧数据中 `source_file_id` 为 Markdown 时，阅读器能正确读取原文。
- 文献已有 PDF 时，补传 Markdown 不覆盖 PDF。
- 精读入口传入 Markdown 后，自动挂载为原文阅读版本。
- 翻译入口：
  - 默认打开最新成功 `translation_md`。
  - 原始输入为 Markdown 时可切换原文。
  - 原始输入为 PDF 时不显示原文 Markdown 切换。
- AI 制卡：
  - 原文卡记录原始 Markdown 来源。
  - 译文卡记录 translation artifact 来源。
  - 无自定义提示词时使用默认提示词。
  - 有自定义提示词时仍产出完整结构化卡片。
  - AI 返回缺字段或非法 JSON 时给出明确错误。
- 卡片编辑、删除会同步数据库与 Markdown 文件镜像。
- Obsidian ZIP：
  - 原文卡导出原文论文页。
  - 译文卡导出译文论文页。
  - 双版本卡片同时存在时两个论文版本都导出。
  - wikilink 与回链区正确。
- 数据生命周期：
  - `CardNote` 纳入 `.dra` 导出/导入。
  - normal 用户清理逻辑清除卡片数据与文件镜像。
  - migration、schema version、导入导出顺序与 id remap 检查同步完成。

### Frontend

- 文献库可上传 Markdown 原文并进入阅读器。
- 文本选中后显示浮动制卡面板。
- 卡片生成后能在阅读页和卡片库中查看。
- 翻译页进入阅读器时默认显示译文。
- 译文与原文切换控件仅在有原始 Markdown 时出现。
- 下载包后可在 Obsidian 中打开论文与卡片双链。

## Assumptions

- 第一版卡片是系统内一等资产，不使用现有 `Annotation` 代替。
- 第一版不做段落级定位锚点与持久高亮。
- 第一版不自动对新挂载 Markdown 执行参考文献梳理。
- 第一版译文阅读默认使用最新成功翻译版本，不做历史译文版本选择器。
- 数据库改动实施时必须同步：
  - ORM
  - Alembic migration
  - `data_portability.py`
  - normal 用户清理逻辑
  - `CURRENT_SCHEMA_VERSION`
- 按当前仓库工作流，代码完成后先做验证与简要说明；用户本地验证通过后再补技术文档与文档导航。
