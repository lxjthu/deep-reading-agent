---
name: "obsidian-metadata-injector"
description: "Extracts paper metadata (Title, Author, Journal, Date) and injects Obsidian-style YAML frontmatter and bidirectional links into markdown reports. Invoke when organizing deep reading outputs for Obsidian."
---

# Obsidian Metadata Injector

本 skill 用于将论文元数据（标题、作者、期刊、年份）以 Obsidian 兼容的 YAML Frontmatter 格式注入到现有的 Markdown 报告中，并自动构建文档间的双向链接（Wikilinks）。

## 适用场景

- 你已经生成了 `deep_reading_results` 目录下的多个 Markdown 报告。
- 你希望将这些报告导入 Obsidian 进行知识管理。
- 你需要自动提取论文元数据，避免手动填写。
- 你希望在“分步报告”与“总报告”之间建立导航链接。

## 输入

- `source_md`: 包含论文原文（或至少包含标题页信息）的 Markdown 文件路径（例如 `pdf_segmented_md/xxx_segmented.md`），用于提取元数据。
- `target_dir`: 包含待处理 Markdown 报告的目录（例如 `deep_reading_results`）。

## 功能细节

1.  **元数据提取**：调用 LLM 从 `source_md` 的前 2000 个字符中智能提取：
    -   `title`: 论文标题
    -   `authors`: 作者列表
    -   `journal`: 发表期刊
    -   `year`: 发表年份
    -   `tags`: 自动生成标签（如 `#paper`, `#economics`, `#deep-reading`）

2.  **Frontmatter 注入**：
    -   在 `target_dir` 下的所有 `.md` 文件顶部插入 YAML 块。
    -   如果文件已有 Frontmatter，则更新或保留（策略可选）。

3.  **双向链接构建**：
    -   在 `Final_Deep_Reading_Report.md` 中添加指向各分步文件（`1_Overview`, `2_Theory`...）的链接索引。
    -   在各分步文件中添加指向 `Final_Deep_Reading_Report.md` 的返回链接。

## 用法

PowerShell:

```powershell
.\run_obsidian_injector.ps1 -SourceMd "pdf_segmented_md\1-QJE-原神论文_segmented.md" -TargetDir "deep_reading_results"
```
