#!/usr/bin/env python3
"""
Local PaddleOCR PDF Extraction Module

Uses PPStructureV3 (PaddlePaddle) for local GPU-accelerated PDF to Markdown conversion.
Output format is fully compatible with the remote PaddleOCR API pipeline.

Requirements:
    pip install "paddlex[ocr]==3.4.1"

Usage:
    # Single file
    python paddleocr_local.py "paper.pdf"

    # Directory (batch)
    python paddleocr_local.py "E:\\pdf\\003"

    # Custom output directory
    python paddleocr_local.py "paper.pdf" --out_dir "my_output"
"""

import argparse
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton engine
# ---------------------------------------------------------------------------

_engine = None
_engine_kwargs = {}


def _get_engine(**kwargs) -> "PPStructureV3":
    """Lazily initialize and cache the PPStructureV3 engine (singleton).

    The engine is heavy (~1-2 GB GPU memory) so we only create it once.
    Subsequent calls return the cached instance.  If *kwargs* differ from
    the cached version the engine is re-created.
    """
    global _engine, _engine_kwargs

    if _engine is not None and kwargs == _engine_kwargs:
        return _engine

    # Suppress PaddleX model-source-check prompt that blocks in CI / headless
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    logger.info("Initializing PPStructureV3 engine (local GPU) ...")
    from paddleocr import PPStructureV3  # delayed import

    _engine = PPStructureV3(lang="ch", **kwargs)
    _engine_kwargs = kwargs.copy()
    logger.info("PPStructureV3 engine ready.")
    return _engine


def is_available() -> bool:
    """Check whether local PaddleOCR (paddleocr + paddlex) is importable."""
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_pdf_local(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    use_table_recognition: bool = True,
    use_formula_recognition: bool = True,
    use_chart_recognition: bool = False,
    use_doc_orientation_classify: bool = False,
) -> Tuple[str, Dict]:
    """Extract a single PDF to Markdown using the local PPStructureV3 engine.

    The output file uses the same naming convention and YAML frontmatter as
    the remote PaddleOCR API path so that downstream modules (paddleocr_segment,
    deep_read_pipeline, etc.) work without modification.

    Args:
        pdf_path: Path to the source PDF file.
        out_dir: Directory for the generated ``.md`` file.
        use_table_recognition: Enable table structure recognition.
        use_formula_recognition: Enable LaTeX formula recognition.
        use_chart_recognition: Enable chart/figure parsing.
        use_doc_orientation_classify: Enable automatic page orientation correction.

    Returns:
        Tuple of ``(md_file_path, metadata_dict)``.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- initialise engine ---
    engine_kwargs = {}
    if not use_table_recognition:
        engine_kwargs["use_table_recognition"] = False
    if not use_formula_recognition:
        engine_kwargs["use_formula_recognition"] = False
    if use_chart_recognition:
        engine_kwargs["use_chart_recognition"] = True
    if use_doc_orientation_classify:
        engine_kwargs["use_doc_orientation_classify"] = True

    engine = _get_engine(**engine_kwargs)

    # --- run prediction ---
    logger.info(f"Running PPStructureV3 on: {pdf_path.name}")
    results = list(engine.predict(str(pdf_path)))

    # --- collect per-page markdown ---
    # Each result is a LayoutParsingResultV2 (dict-like).
    # result.markdown -> dict with keys:
    #   markdown_texts (str), page_index (int),
    #   page_continuation_flags (tuple[bool, bool])
    page_markdowns = []
    for page_result in results:
        md_info = getattr(page_result, "markdown", None)
        if isinstance(md_info, dict):
            md_text = md_info.get("markdown_texts", "")
        elif isinstance(md_info, str):
            md_text = md_info
        else:
            md_text = ""
        page_markdowns.append(md_text or "")

    # Merge pages respecting continuation flags
    merged_parts = []
    for i, page_result in enumerate(results):
        md_info = getattr(page_result, "markdown", {})
        flags = md_info.get("page_continuation_flags", (False, False)) if isinstance(md_info, dict) else (False, False)
        continued_from_prev = flags[0] if len(flags) > 0 else False

        if continued_from_prev and merged_parts:
            # This page continues from the previous one — join without double newline
            merged_parts[-1] = merged_parts[-1].rstrip() + "\n" + page_markdowns[i].lstrip()
        else:
            merged_parts.append(page_markdowns[i])

    total_pages = len(page_markdowns)
    body = "\n\n".join(merged_parts).strip()

    # --- build output markdown with YAML frontmatter ---
    now = datetime.now().isoformat(timespec="seconds")

    lines = [
        "---",
        f"title: {pdf_path.name}",
        f"source_pdf: {pdf_path.name}",
        "extractor: paddleocr",
        "extract_mode: local_gpu",
        f"extract_date: {now}",
        f"total_pages: {total_pages}",
        "---",
        "",
        body,
    ]

    content = "\n".join(lines)

    # --- write file ---
    out_name = pdf_path.stem + "_paddleocr.md"
    out_path = out_dir / out_name
    out_path.write_text(content, encoding="utf-8")
    logger.info(f"Saved: {out_path}  ({total_pages} pages, {len(content)} chars)")

    metadata = {
        "title": pdf_path.name,
        "abstract": "",
        "keywords": [],
        "sections": [],
        "extractor": "paddleocr",
        "extract_mode": "local_gpu",
        "stats": {
            "total_pages": total_pages,
            "total_chars": len(body),
        },
    }

    return str(out_path), metadata


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _iter_pdfs(input_path: str) -> list:
    """Return a sorted list of PDF file paths from a file or directory."""
    if os.path.isfile(input_path) and input_path.lower().endswith(".pdf"):
        return [input_path]

    pdfs = []
    for root, _, files in os.walk(input_path):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdfs.append(os.path.join(root, f))
    return sorted(pdfs)


def main():
    parser = argparse.ArgumentParser(
        description="Extract PDF to Markdown using local PaddleOCR (GPU)"
    )
    parser.add_argument("input_path", help="PDF file or directory containing PDFs")
    parser.add_argument("--out_dir", default="paddleocr_md", help="Output directory (default: paddleocr_md)")
    parser.add_argument("--no_table", action="store_true", help="Disable table recognition")
    parser.add_argument("--no_formula", action="store_true", help="Disable formula recognition")
    parser.add_argument("--chart", action="store_true", help="Enable chart parsing")
    parser.add_argument("--orientation", action="store_true", help="Enable document orientation correction")
    args = parser.parse_args()

    pdfs = _iter_pdfs(args.input_path)
    if not pdfs:
        logger.error("No PDF files found.")
        return 1

    os.makedirs(args.out_dir, exist_ok=True)

    success = 0
    for pdf_path in pdfs:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {os.path.basename(pdf_path)}")
        try:
            md_path, metadata = extract_pdf_local(
                pdf_path,
                out_dir=args.out_dir,
                use_table_recognition=not args.no_table,
                use_formula_recognition=not args.no_formula,
                use_chart_recognition=args.chart,
                use_doc_orientation_classify=args.orientation,
            )
            logger.info(f"Output: {md_path}")
            logger.info(f"Pages: {metadata['stats']['total_pages']}, "
                        f"Chars: {metadata['stats']['total_chars']}")
            success += 1
        except Exception as e:
            logger.error(f"Failed to process {pdf_path}: {e}")
            continue

    logger.info(f"\n{'='*60}")
    logger.info(f"Done. {success}/{len(pdfs)} files processed successfully.")
    return 0 if success == len(pdfs) else 1


if __name__ == "__main__":
    sys.exit(main())
