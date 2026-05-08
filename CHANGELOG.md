# Changelog

## [Unreleased] - 2026-05-08

### Features

- Add user-customizable dimension sets for long reading: `dimension_sets` + `dimension_items` tables, default dimension seeding, dimensions router (`backend/dimension_seed.py`, `backend/routers/dimensions.py`, migration 007)

### Fixes

- Fix `ModuleNotFoundError: No module named 'new_architecture'` by adding project root to `sys.path` in `backend/main.py` before any backend imports

---

## 1.3.0 - 2026-05-03

### Features

- Add Windows executable packaging with PyInstaller: single-file exe (91MB), auto-config launcher, install script, build automation (`deep-reading-agent.spec`, `build_windows.py`, `launcher.py`, `install.bat`, `build_and_test.ps1`)
- Multi-user system with JWT authentication, workspace isolation, task archiving, and admin management (P0-P7)
- Prompt center with user-level prompt overrides
- Reference tracing: extract and trace citations from papers
- Compare long reading with multi-select dimensions and cross-dimension synthesis
- Auto deploy via GitHub webhook

### Fixes

- Pass user-provided API key to reference extraction instead of relying on env var
- Prevent `MultipleResultsFound` in prompt_templates query
- Daily cleanup at 00:00 + recover hanging jobs on startup
- Fix literature filter display showing all items; fix download path mismatch
- Fix cross-step dimension selection loss and key persistence
- Remove hardcoded `DEPLOY_SECRET`; require env variable

### Documentation

- Add multi-user concurrency analysis and migration plan for 10+ concurrent users
- Add API key flow troubleshooting and deployment architecture guide

---

## 1.2.0 - 2026-02-24

### Features

- Add supplementary restatement pass (Step 6/6) to fix missed English blocks in Chinese restatement output: detects paragraphs with >65% ASCII letters, groups adjacent English paragraphs into patches, skips references/bibliography section, re-restates via DeepSeek and stitches back in-place (`translation_pipeline.py`)

---

## 1.1.1 - 2026-02-24

### Fixes

- Fix repeated `---` YAML separators in Chinese restatement output (`translation_pipeline.py`): `__yaml__` chunk no longer passed through LLM restatement; leading YAML blocks stripped from restated non-YAML chunks
- Remove unused dependencies from `requirements.txt`; make `paddlex` optional
- Add CN mirror fallback for pip install in `start.bat`

---

## 1.1.0

- Add Chinese restatement pipeline (Tab 6) for economics papers
- Localize GUI to Chinese, reorder tabs, add prompt editor
- Add Gradio GUI, PaddleOCR local GPU extraction, QUAL metadata extractor

## 1.0.1

- Fix duplicate API call in extraction; enhance metadata injection
- Add QUICKSTART tutorial and pymupdf dependency

## 1.0.0

- Initial release: dual-LLM deep reading pipeline (QUANT 7-step + QUAL 4-layer)
- Smart Literature Filter with WoS/CNKI support
- PaddleOCR remote API extraction with pdfplumber fallback
