# 题录解析增强与反向匹配设计

## 1. 背景

当前系统已有 CNKIParser（`parsers.py:89-166`）和 WoSParser，但存在多个问题导致元数据利用率低、匹配链路不完整。本设计针对 CNKI 和 WoS 两种题录格式的解析增强、反向匹配、以及 apply_match 空壳修复。

## 2. 现有问题

### 2.1 CNKIParser 问题

| 问题 | 位置 | 影响 |
|------|------|------|
| DOI 写死空字符串 `''` | `parsers.py:160` | 丢失约 40% 条目的 DOI |
| Year 仅从 PubTime 提取，忽略 `Year-年` 字段 | `parsers.py:149-151` | 少数条目年份丢失 |
| Keywords、Volume、Issue、Pages、ISSN、URL 全部丢弃 | `parsers.py:154-165` | 元数据严重浪费 |
| 多行摘要不处理 | `parsers.py:129-131` | 长摘要可能截断 |
| Authors 末尾可能带 `;` 未清理 | `parsers.py:145` | 数据噪音 |

### 2.2 WoSParser 问题

现有 WoSParser 的字段映射（`parsers.py:71-87`）基本可用，但缺少以下字段：

| 缺失字段 | WoS Tag | 说明 |
|----------|---------|------|
| Keywords | `DE`（Author Keywords）+ `ID`（Keywords Plus） | 合并两者 |
| Volume | `VL` | 卷号 |
| Issue | `IS` | 期号 |
| Pages（起止页） | `BP` + `EP` | 合并为 `1-13` 格式 |
| ISSN | `SN` | 国际标准刊号 |
| Language | `LA` | 如 `English`、`French` |
| Citation Count | `TC` | 被引次数（已有映射 `Citations=TC`，正确） |

当前 WoS DataFrame 输出列：`Title, Authors, Journal, Year, Abstract, DOI, Type, Citations, SourceType`。需新增：`Keywords, Volume, Issue, Pages, ISSN, Language`。

### 2.2 反向匹配缺失

导入 CNKI/WoS 题录创建 BibEntry 时，不会去匹配用户已上传的 PDF/MD 文件。场景：

1. 用户先上传了 PDF → 创建了 `metadata_completeness=minimal` 的 BibEntry（只有文件名标题）
2. 用户再导入 CNKI txt → 创建了 `metadata_completeness=full` 的 BibEntry
3. 两者其实是同一篇文献，但系统里变成了两条记录

### 2.3 apply_match 空壳

`library.py:503` 的 `apply_match` 端点只返回成功消息，不实际更新 BibEntry。

## 3. 设计方案

### 3.1 重写 CNKIParser（`parsers.py`）

**字段映射表：**

| CNKI 原始字段 | DataFrame 列 | 处理逻辑 |
|---|---|---|
| `Title-题名` | `Title` | 直接映射 |
| `Author-作者` | `Authors` | `;` 替换为 `; `，去尾部 `;` |
| `Source-文献来源` | `Journal` | 直接映射 |
| `Year-年` | `Year` | 优先取此字段；缺省则从 `PubTime-发表时间` 提取4位年份 |
| `DOI-DOI` | `DOI` | 有则映射，无则为空字符串 |
| `Summary-摘要` | `Abstract` | 支持多行续行 |
| `Keyword-关键词` | `Keywords` | 原样保留（`;`分隔） |
| `Volume-卷` | `Volume` | 直接映射 |
| `Period-期` | `Issue` | 直接映射 |
| `PageCount-页码` | `Pages` | 直接映射 |
| `ISSN-国际标准刊号` | `ISSN` | 直接映射 |
| `URL-网址` | `URL` | 直接映射 |
| `PubTime-发表时间` | `PubTime` | 保留原始值 |
| — | `Type` | 固定 `"Journal"` |
| — | `Citations` | 固定 `"0"` |
| `SrcDatabase-来源库` | `SourceType` | 映射为 `"CNKI"` |

**多行值处理：**

- 如果当前行不以 `Key-中文:` 开头且不是空行，追加到上一个字段值（前面加空格）
- 用于处理超长摘要等场景

### 3.2 增强 WoSParser（`parsers.py`）

现有 WoS 解析逻辑正确处理了 `AU`/`TI`/`SO`/`PY`/`AB`/`DI`/`TC`/`DT` 等核心 Tag 的多行续行。需要在 `to_dataframe` 中新增字段映射：

| WoS Tag | DataFrame 列 | 处理逻辑 |
|---------|-------------|---------|
| `DE`（Author Keywords）+ `ID`（Keywords Plus） | `Keywords` | 合并，用 `;` 分隔 |
| `VL` | `Volume` | 直接映射 |
| `IS` | `Issue` | 直接映射 |
| `BP` + `EP` | `Pages` | 合并为 `BP-EP` 格式，无 EP 则仅 BP |
| `SN` | `ISSN` | 直接映射 |
| `LA` | `Language` | 直接映射 |
| `TC` | `Citations` | 已有，保持 |

解析阶段（`parse()`）无需改动——已有的多行续行逻辑会正确读取 `VL`/`IS`/`BP`/`EP`/`SN`/`LA` 等标签。只需在 `to_dataframe()` 中增加映射。

### 3.3 persist_filter_results 增加反向匹配（`filter.py`）

在 `persist_filter_results` 中，每创建/更新一个 BibEntry 后，执行反向匹配：

```
对每条新创建的 BibEntry（来自CNKI/WoS）:
  1. 获取该用户所有 source_file_id IS NOT NULL 的 BibEntry（排除自身）
  2. 用 title_match_score 匹配：
     - 如果 DOI 都有且一致 → 直接匹配（score=1.0）
     - 否则 title_match_score >= 0.72 → 匹配
  3. 匹配命中时：
     - 将 source_file_id 从旧 BibEntry 迁移到新 BibEntry
     - 更新 reading_status
     - 用 CNKI/WoS 数据只补新 BibEntry 的空字段
     - 旧 BibEntry 如果无其他关联（无 Job、无 BibFilterLink），则删除
```

### 3.4 apply_match 实现实际更新（`library.py`）

将 `apply_high_confidence_match()`（已存在于 `metadata_match_service.py:64`）接入 `apply_match` 端点：

```
1. 重新执行 match_online 获取候选列表
2. 取 candidate_index 对应的候选
3. 只补 BibEntry 中的空字段（不覆盖已有值）
4. 重新计算 metadata_completeness
5. 更新 dedup_key
```

### 3.5 不改的部分

- 不动在线匹配的 Crossref/OpenAlex 逻辑
- 不动前端 MetadataMatchPanel
- 不新增数据库迁移
- 不自动触发在线搜索，仅依赖导入数据

## 4. 数据流

```
CNKI/WoS txt 上传 → detect_file_type="bibliography" → 筛选Tab开始
  → Parser.parse() → 标准化 DataFrame（含完整元数据）
  → AI 筛选评估
  → persist_filter_results():
      对每条记录：
        1. compute_dedup_key → 找或创建 BibEntry
        2. 【新增】reverse_match_to_existing_files():
             在用户所有 source_file_id 非空的 BibEntry 中找匹配
             匹配策略：DOI 精确匹配 OR title_match_score >= 0.72
             命中 → 迁移 source_file_id + 补空字段 + 清理旧条目
        3. compute_metadata_completeness → 通常为 "full"
```

## 5. 影响范围

| 文件 | 改动内容 |
|------|---------|
| `parsers.py` CNKIParser | 重写字段映射，补全 DOI/Keywords/Volume/Issue/Pages/ISSN，处理多行值 |
| `parsers.py` WoSParser | `to_dataframe()` 增加 Keywords/Volume/Issue/Pages/ISSN/Language 映射 |
| `filter.py` persist_filter_results | 新增反向匹配逻辑，利用 DataFrame 中新增的 Keywords/Volume/Issue 等字段 |
| `filter.py` persist_filter_results | Keywords、ISSN 等新字段写入 BibEntry（需确认 BibEntry 模型是否有对应字段） |
| `library.py` apply_match | 接入实际更新逻辑 |

## 6. BibEntry 模型字段检查

当前 BibEntry 模型（`db/models.py`）已有字段：

- `title`, `authors_json`, `year`, `doi`, `journal`, `abstract` ✓
- `keywords_json` ✓（可写入 Keywords）
- `venue_type` ✓（可写入 Type）
- `citation_count` ✓（可写入 Citations）

**缺失字段**（需确认是否新增或忽略）：

- `volume` — 当前模型中无此字段，但 `metadata_match_service.py` 中 `apply_high_confidence_match` 引用了 `volume`/`issue`/`pages`
- `issue` — 同上
- `pages` — 同上
- `issn` — 当前模型中无此字段
- `language` — 当前模型中无此字段
- `url` — 当前模型中无此字段

建议：Volume/Issue/Pages 在 `metadata_match_service.py` 中已被引用但模型中缺失，说明之前的设计就预期这些字段存在。本次新增这三个字段到 BibEntry 模型，并做 Alembic migration。ISSN/Language/URL 暂不存入 BibEntry（避免模型膨胀），仅存在 DataFrame 中用于 AI 筛选参考。
