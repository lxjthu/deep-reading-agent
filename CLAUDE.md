# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Deep Reading Agent is an automated academic paper analysis system that converts PDFs into structured Obsidian-compatible Markdown reports. It uses a dual-LLM architecture with DeepSeek as the primary engine, supporting both quantitative (econometrics-style 7-step analysis) and qualitative (4-layer pyramid) research paper workflows.

## Environment Setup

```powershell
# Activate virtual environment (Windows)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

Required in `.env`:
```
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Optional: PaddleOCR remote API (enables better OCR extraction)
PADDLEOCR_REMOTE_URL=https://your-paddleocr-api-endpoint
PADDLEOCR_REMOTE_TOKEN=your-token
```

## Key Commands

```powershell
# Single paper full pipeline (extraction → deep reading → metadata)
python run_full_pipeline.py "paper.pdf"                    # Legacy pdfplumber extraction
python run_full_pipeline.py "paper.pdf" --use-paddleocr   # PaddleOCR extraction (recommended)

# Batch pipeline with hash-based dedup and smart routing (QUANT/QUAL auto-classification)
# Uses PaddleOCR by default with automatic fallback to legacy extraction
python run_batch_pipeline.py "path/to/pdfs"

# Literature pre-screening from WoS/CNKI exports
python smart_literature_filter.py "savedrecs.txt" --ai_mode reviewer --topic "Topic" --output "screened.xlsx"

# Batch quick analysis (Excel summary)
.\run_analyzer.ps1 -InputPath "path/to/pdfs" -Output "results.xlsx"

# Individual pipeline steps (PaddleOCR path - recommended)
python paddleocr_pipeline.py "paper.pdf" --out_dir "paddleocr_md"
python deep_read_pipeline.py "paddleocr_md/paper_paddleocr.md"

# Individual pipeline steps (Legacy path - fallback)
python anthropic_pdf_extract_raw.py "paper.pdf" --out_dir "pdf_raw_md"
python deep_read_pipeline.py "pdf_raw_md/paper_raw.md"
```

## Architecture

### Pipeline Flow
```
# PaddleOCR path (recommended, uses remote Layout Parsing API)
PDF → PaddleOCR MD (paddleocr_md/) → Analysis → Obsidian Metadata

# Legacy path (fallback when PaddleOCR unavailable)
PDF → Raw MD (pdf_raw_md/, pdfplumber) → Analysis → Obsidian Metadata
```
Note: Segmentation step has been removed. Extraction MD is passed directly to analyzers.
`common.load_md_sections()` parses `#` and `##` headers from extraction output natively.

### Paper Classification & Routing
`smart_scholar_lib.py` classifies papers and routes to appropriate analyzer:
- **QUANT** → `deep_read_pipeline.py` (7-step: Overview, Theory, Data, Variables, Identification, Results, Critique)
- **QUAL** → `social_science_analyzer.py` (4-layer: Context, Theory, Logic, Value)
- **IGNORE** → Skipped (editorials, metadata)

Default fallback is QUAL when classification is uncertain.

### Core Modules

| Layer | Key Files |
|-------|-----------|
| Extraction | `paddleocr_pipeline.py` (primary), `anthropic_pdf_extract_raw.py` (fallback), `paddleocr_extractor/` |
| Deep Reading | `deep_read_pipeline.py`, `deep_reading_steps/step_*.py`, `deep_reading_steps/common.py` |
| Social Science | `social_science_analyzer.py`, `link_social_science_docs.py` |
| Metadata | `inject_obsidian_meta.py`, `inject_dataview_summaries.py` |
| State | `state_manager.py` (MD5 hash dedup → `processed_papers.json`) |
| Filtering | `smart_literature_filter.py`, `parsers.py` |
| Routing | `smart_scholar_lib.py` (QUANT/QUAL classification + extraction orchestration) |

### LLM Configuration
- `deep_reading_steps/common.py`: Uses `deepseek-reasoner` for analysis steps
- `smart_scholar_lib.py`: Uses `deepseek-chat` for classification
- Text input capped at 150k chars (middle truncation for longer texts)

### Content Routing (common.py)
1. Priority 1: Semantic Index (`semantic_index.json`) if available
2. Priority 2: Section dictionary with next-section fallback
3. LLM-based section-to-step routing with fuzzy title matching
4. Positional fallback for empty steps

## Output Directories

All output dirs are gitignored and created dynamically:
- `paddleocr_md/` - PaddleOCR extraction output (primary, text-only, no images)
- `pdf_raw_md/` - Legacy pdfplumber extraction (fallback)
- `deep_reading_results/{paper_name}/` - Final reports (7 step files + Final_Deep_Reading_Report.md)
- `social_science_results_v2/` - Social science analysis outputs
- `references/` - Citation extraction and tracing
- `processed_papers.json` - State tracking (delete to force reprocessing)

## Conventions

- PowerShell scripts (`.ps1`) are Windows wrappers; use Python scripts directly on other OS
- All output Markdown includes YAML frontmatter for Obsidian Dataview compatibility
- `json_repair` library handles malformed LLM JSON responses
- PaddleOCR extraction is preferred but requires `PADDLEOCR_REMOTE_URL` and `PADDLEOCR_REMOTE_TOKEN` in `.env`
- Extraction automatically falls back to legacy pdfplumber when PaddleOCR is unavailable
- PaddleOCR markdown includes `extractor: paddleocr` in YAML frontmatter for format detection
