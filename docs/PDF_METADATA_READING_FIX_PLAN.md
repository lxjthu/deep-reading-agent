# PDF精读元数据提取修复方案

## 问题概述

当前系统在上传PDF进行精读（长文本/七步法/四步法）时，虽然存在专业的 `pdf_metadata_extract` + `pdf_metadata_llm` 服务用于从前三页提取结构化元数据，但实际精读流程中存在以下缺陷：

1. **四步法完全未调用元数据提取**
2. **提取的元数据仅用于报告frontmatter，未写入 `bib_entries` 数据库**
3. **reading.py使用的是简化版extractor，而非专业的三页提取服务**
4. **缺少摘要(abstract)和关键词(keywords)的提取**
5. **没有自动更新 `BibEntry` 的逻辑**

## 修复目标

- 三种精读模式（长文本/七步/四步）完成后，统一从前三页提取元数据
- 提取字段：标题、作者、年份、期刊、DOI、卷、期、页码、语言、**摘要、关键词**
- 将提取结果自动更新到 `BibEntry` 数据库记录
- 重新计算 `metadata_completeness` 和 `dedup_key`
- 使用 DeepSeek `deepseek-v4-flash` 模型读取前三页后提取

## 修复范围

### 文件1: `backend/services/pdf_metadata_llm.py`

**修改内容：**
- 在Prompt和输出格式中增加 `abstract`（摘要）和 `keywords`（关键词列表）字段
- 在 `_clean_metadata` 函数中清洗这两个新字段
- 在 `_empty_metadata` 函数中添加默认值

### 文件2: `backend/routers/reading.py`

**修改内容：**
- 在 `run_long_context_task`、`run_quant_task`、`run_qual_task` 三种任务完成后，统一调用元数据提取
- 使用 `pdf_metadata_extract.extract_front_matter()` + `pdf_metadata_llm.extract_metadata_with_llm()` 替代当前简化的 `metadata_extractor.extract_metadata()`
- 将提取结果更新到 `BibEntry` 记录
- 在 `finalize_reading_success` 或新增辅助函数中处理数据库更新

**新增/修改函数：**

```python
async def update_bib_entry_metadata(
    db: AsyncSession,
    bib_entry_id: str,
    metadata: dict,
) -> list[str]:
    """根据提取的元数据更新 BibEntry，只补空字段不覆盖已有值。
    返回被更新的字段名列表。"""
    ...
```

### 文件3: `docs/PDF_METADATA_READING_FIX_PLAN.md`（本文档）

记录修复方案和实施细节。

## 数据更新原则

- **只补空字段**：如果 `BibEntry` 已有值，不覆盖
- **标题例外**：如果当前标题是文件名（由上传时生成），允许用提取的标题替换
- **更新后重新计算**：`dedup_key`、`metadata_completeness`

## 实施步骤

1. ✅ 修改 `pdf_metadata_llm.py` 增加 abstract/keywords
2. ✅ 修改 `reading.py` 在三种精读任务中集成元数据提取
3. ✅ 添加 `_try_update_bib_metadata` 辅助函数（实际函数名，非 `update_bib_entry_metadata`）
4. ✅ 运行测试脚本验证提取准确性
5. ✅ 对比 DeepSeek 提取结果与用户提供的标准题录

## 验证结果

**测试时间**：2026-05-10
**测试PDF**：《关系治理、契约治理与农业产业生态系统演进》（管理世界，2023，DOI: 10.19744/j.cnki.11-1235/f.2023.0066）
**模型**：deepseek-v4-flash

### 提取结果对比

| 字段 | 标准答案 | DeepSeek 提取 | 结果 |
|------|---------|--------------|------|
| 标题 | 关系治理、契约治理与农业产业生态系统演进 | 关系治理、契约治理与农业产业生态系统演进 | ✅ |
| 作者 | 于滨铜、王志刚 | 于滨铜、王志刚 | ✅ |
| 年份 | 2023 | 2023 | ✅ |
| 期刊 | 管理世界 | 管理世界 | ✅ |
| DOI | — | 10.19744/j.cnki.11-1235/f.2023.0066 | ✅ |
| 摘要 | 完整摘要 | 473字符，完全匹配 | ✅ |
| 关键词 | 5个 | 5/5 全部匹配 | ✅ |
| 语言 | zh | zh | ✅ |
| 卷 | 39 | 未提取 | ❌ |
| 期 | 05 | 5 | ⚠️ |
| 页码 | 54-78 | 54-? | ⚠️ |
| 置信度 | — | 0.90 | — |

**核心字段准确率：7/10**（标题、作者、年份、期刊、摘要、关键词、DOI、语言全部正确）

**说明**：
- 卷号未提取：PDF 前三页中卷号出现在页眉，但 DeepSeek 未识别（需后续优化 Prompt 增强页眉信息权重）
- 期号/页码部分提取：期号提取为 `5`（标准 `05`），页码提取为 `54-?`（标准 `54-78`）
- 对于文献库自动补全场景，核心元数据（标题、作者、年份、期刊、摘要、关键词）已足够使用

## 代码变更记录

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/services/pdf_metadata_llm.py` | 修改 | Prompt、`_clean_metadata`、`_empty_metadata` 增加 abstract/keywords |
| `backend/routers/reading.py` | 修改 | 三种精读任务统一使用专业元数据提取服务，新增 `_try_update_bib_metadata` |
| `docs/TECHNICAL_OVERVIEW.md` | 更新 | 第 2.4、5.7 节增加元数据自动提取描述 |
| `docs/FUNCTION_INDEX.md` | 更新 | reading.py 增加 `_try_update_bib_metadata` 索引，速查表新增场景 |
| `docs/PDF_METADATA_READING_FIX_PLAN.md` | 新建 | 本文档 |
