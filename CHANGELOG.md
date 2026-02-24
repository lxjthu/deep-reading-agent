# Changelog

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
