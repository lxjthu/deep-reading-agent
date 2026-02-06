# 方案：移除分段步骤 (Remove Segmentation Step)

## 目标

移除流水线中的分段步骤（`paddleocr_segment.py` / `smart_segment_router.py` / `deepseek_segment_raw_md.py`），让提取后的原始 MD 直接进入 QUANT 和 QUAL 分析器。

## 为什么可行

- **QUANT 路径**：`deep_read_pipeline.py` 已经会从全文自动生成 `semantic_index.json`，这是内容路由的 Priority 1。预分段是冗余的。
- **QUAL 路径**：`get_combined_text()` 对章节标题做关键词匹配，PaddleOCR 输出自带 `#` 标题结构，可以直接解析。且有 fallback 到全文的机制。

## 当前流水线 vs 新流水线

```
当前流水线:
PDF → 提取(PaddleOCR/pdfplumber) → 分段(DeepSeek) → 分类 → QUANT/QUAL分析
                                      ↑ 这一步要删

新流水线:
PDF → 提取(PaddleOCR/pdfplumber) → 分类 → QUANT/QUAL分析
```

---

## 需要修改的文件 (10 个)

### 1. `deep_reading_steps/common.py` — `load_segmented_md()`

**改动**：
- 重命名为 `load_md_sections()`，保留 `load_segmented_md` 作为兼容别名
- 解析 `# ` (h1) 标题，不仅仅是 `## ` (h2)
- 解析前先去掉 YAML frontmatter (`---...---`)
- 兜底：如果没有找到任何标题，把整段文本放入 `{"Full Text": content}`

```python
# 新的标题匹配逻辑
if line.startswith("## "):       # h2 → section boundary
    ...
elif line.startswith("# ") and not line.startswith("## "):  # h1 → section boundary
    ...
# ### 及更深层级不作为分段边界（太碎）
```

### 2. `smart_scholar_lib.py` — `ensure_segmented_md()` → `ensure_extracted_md()`

**改动**：
- 删除 `SCRIPT_MD_TO_SEG`, `SCRIPT_RAW_TO_SEG`, `PDF_SEG_DIR` 常量
- 重写函数：只做提取（PDF → MD），返回提取后的 MD 路径
- 删除所有分段 subprocess 调用
- 保留 `ensure_segmented_md()` 作为废弃别名

### 3. `run_full_pipeline.py`

**改动**：
- 删除 Step 2（分段）代码块（PaddleOCR 路径的 line 70-72，Legacy 路径的 line 84-86）
- 将提取 MD 直接传给 `deep_read_pipeline.py`（原来传的是 `segmented_md_file`）
- 删除 `PDF_SEG_MD_DIR` 常量
- 重新编号：6 阶段 → 5 阶段

### 4. `deep_read_pipeline.py`

**改动**：
- 参数名 `segmented_md_path` → `md_path`
- basename 清理：去掉 `_paddleocr` / `_raw` 后缀（原来只去掉 `_segmented`）

### 5. `social_science_analyzer.py` (v1)

**改动**：
- `main()` 文件过滤：从 `*_segmented.md` 改为接受 `*_paddleocr.md`, `*_raw.md`, `*_segmented.md`
- `load_segmented_md()`：同 common.py 的改动 — 解析 `#` 标题、去 YAML、兜底
- basename 提取：处理 `_paddleocr` / `_raw` 后缀

### 6. `social_science_analyzer_v2.py`

**改动**：同 v1

### 7. `app.py` — 3 个位置

- **Tab 2**（全流程，lines 328-338）：删除 Stage 2 分段。将提取 MD 直接传给 `common.load_segmented_md()`。阶段编号 6→5。
- **Tab 3**（批量，line 616）：调用 `ensure_extracted_md()` 替代 `ensure_segmented_md()`。更新 QUAL 分发逻辑。
- **Tab 5**（MD精读，lines 962-975）：删除分段代码块。直接传原始 MD。删除 `from paddleocr_segment import segment_paddleocr_md`。

### 8. `run_batch_pipeline.py`

**改动**：
- Line 82：调用 `ensure_extracted_md()` 替代 `ensure_segmented_md()`
- QUANT 路径：传提取 MD 给 `deep_read_pipeline.py`
- QUAL 路径：传提取 MD 目录给 `social_science_analyzer_v2.py`
- 错误信息："Segmentation failed" → "Extraction failed"

### 9. `run_social_science_task.py`

**改动**：
- 删除 `SEGMENT_SCRIPT`, `SEGMENT_SCRIPT_LEGACY`, `SEG_MD_DIR` 常量
- 删除 Step 1 分段循环
- 直接将 `PADDLEOCR_MD_DIR` 或 `RAW_MD_DIR` 传给分析器

### 10. `CLAUDE.md`

**改动**：更新流水线文档，移除分段步骤描述

---

## 不修改的文件（保留但不再被调用）

- `paddleocr_segment.py` — 保留，不删除
- `smart_segment_router.py` — 保留，不删除
- `deepseek_segment_raw_md.py` — 保留，不删除

---

## 关键设计决策

### QUAL 文件发现模式
```python
# 旧
all_files = [f for f in os.listdir(dir) if f.endswith("_segmented.md")]

# 新：接受所有提取输出
EXTRACTION_SUFFIXES = ("_paddleocr.md", "_raw.md", "_segmented.md")
all_files = [f for f in os.listdir(dir) if any(f.endswith(s) for s in EXTRACTION_SUFFIXES)]
```

### QUAL basename 提取
```python
for suffix in ("_segmented", "_paddleocr", "_raw"):
    if basename.endswith(suffix):
        basename = basename[:-len(suffix)]
        break
```

---

## 验证清单

1. **QUANT 单文件**：`python run_full_pipeline.py "test.pdf" --use-paddleocr` — 应跳过分段
2. **QUAL 批量**：`python run_batch_pipeline.py "path/to/pdfs"` — QUAL 论文无需分段
3. **GUI Tab 2**：上传 PDF → 全流程应无 Stage 2
4. **GUI Tab 5**：上传原始 MD → 直接精读，无需分段
5. **向后兼容**：已有的 `_segmented.md` 文件仍可被解析
