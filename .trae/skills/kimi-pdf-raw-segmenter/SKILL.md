---
name: "kimi-pdf-raw-segmenter"
description: "将 PDF 原文 Markdown（逐页）按论文结构分割成 7 个部分并输出新 MD。用户希望先看原文提取质量或需要按引言/方法/数据等拆分时调用。"
---

# Kimi PDF 原文分段器

本 skill 用于把“逐页原文提取”的 Markdown（例如 `pdf_raw_md/*_raw.md`）尽量按论文结构分割为 7 个部分，并尽量保留原文内容，仅做必要的换行与排版整理。

## 适用场景

- 你已经有了 PDF 的逐页原文 Markdown（每页一个 `## Page N`，正文在 ```text 块中）
- 你希望按论文结构拆分：
  1) 引言
  2) 文献回顾
  3) 理论与假说
  4) 数据获取与清洗
  5) 变量与测量
  6) 识别策略与实证分析
  7) 结论与讨论

## 输入

- `raw_md_path`: 单个逐页原文 Markdown 路径

## 输出

- 在输出目录生成一个新的 Markdown：包含 7 个一级分段标题，每段主要由原文拼接而成

## 用法

PowerShell：

```powershell
./run_kimi_segment_raw_md.ps1 -RawMdPath "pdf_raw_md\1-QJE-原神论文_raw.md"
```

可选参数：

- `-OutDir`：输出目录（默认 `pdf_segmented_md`）
- `-Model`：模型（默认读取 `.env` 的 `OPENAI_MODEL`，未设置则 `moonshot-v1-auto`）

## 说明

- 分段边界由 Kimi 扫描全文后识别出的**顶级章节标题**（如 "1. Introduction"）决定。
- 程序会自动寻找这些标题在原文中的精确位置进行切分。

