# 精读去重提取优化

> 日期：2026-05-17
> 状态：已实施

## 背景

精读任务（长文本/七步/四步）在元数据提取和参考文献提取上存在重复调用 LLM 的问题：

### 元数据重复提取

每次精读任务中，`extract_front_matter()` + `extract_metadata_with_llm()` 被调用**两次**：

1. **inline 调用**：在报告生成流程中提取元数据，用于 YAML frontmatter（长文本 ~line 1208、七步 ~line 1370、四步 ~line 1530）
2. **`_try_update_bib_metadata()` 内部调用**：更新 BibEntry 记录时再次调用同一对函数（~line 655）

两次调用传入相同文件、相同 API Key，产出相同结果，是纯粹的浪费——每次精读多花一次 DeepSeek LLM 调用的时间和费用。

### 参考文献无条件重提

`_try_extract_references()` 在每次精读结束时都会调用 `extract_references_deepseek()` + `trace_citations_deepseek()`，不检查该 BibEntry 是否已有参考文献记录。重复精读同一篇论文时，已有的参考文献会被删除后重新提取，覆盖可能的人工修正。

## 实施方案

### 1. 元数据提取去重

**改动文件**：`backend/routers/reading.py`

**`_try_update_bib_metadata()` 函数**（~line 642）：

- 新增 `metadata: Optional[dict] = None` 参数
- 当 `metadata` 已传入时，跳过 `extract_front_matter()` 和 `extract_metadata_with_llm()` 调用，直接使用传入的 metadata
- 当 `metadata` 未传入（`None`）时，保持原有行为作为兜底

**三个调用点**（长文本 ~line 1219、七步 ~line 1381、四步 ~line 1533）：

- 将 inline 已提取的 `metadata` 变量通过 `metadata=metadata` 传入 `_try_update_bib_metadata()`

**效果**：每次精读减少一次 LLM 调用（`extract_metadata_with_llm`）和一次 PDF 解析（`extract_front_matter`）。

### 2. 参考文献跳过

**改动文件**：`backend/routers/reading.py`

**`_try_extract_references()` 函数**（~line 820）：

- 在函数开头新增异步数据库查询，检查 `bib_references` 表中是否已有该 `bib_entry_id` 的记录（`LIMIT 1`）
- 如果已存在，记录日志并返回空列表，跳过后续的 `extract_references_deepseek()` 和 `trace_citations_deepseek()` 调用
- 新增 `BibReference` 到模块级 import（line 26）

**手动入口不受影响**：`routers/references.py` 的 `start_reference_trace()` 端点没有跳过逻辑——用户主动触发"梳理参考文献"时始终执行完整提取。

**效果**：重复精读同一篇论文时，参考文献提取的两次 DeepSeek 调用（提取 + 梳理引用位置）被完全跳过。

## 影响分析

| 场景 | 改动前 | 改动后 |
|------|--------|--------|
| 首次精读 | 元数据提取×2, 参考文献提取×1 | 元数据提取×1, 参考文献提取×1 |
| 重复精读 | 元数据提取×2, 参考文献提取×1（覆盖旧数据） | 元数据提取×1, 参考文献跳过 |
| 手动梳理参考文献 | 无条件执行 | 无变化（不受此改动影响） |

### 安全性

- 元数据更新仍采用"只补空字段"策略，不会覆盖已有数据
- 参考文献跳过仅检查存在性（`LIMIT 1`），不检查质量或完整性
- `metadata_completeness` 字段在 `_try_update_bib_metadata` 中仍会重新计算
- 向后兼容：`_try_update_bib_metadata()` 不传 `metadata` 参数时行为与改动前一致

### 无数据库迁移

本次改动不涉及数据库 schema 变更，不需要 Alembic migration。
