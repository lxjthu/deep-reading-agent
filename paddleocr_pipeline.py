#!/usr/bin/env python3
"""
PaddleOCR Pipeline - Unified entry point for PDF extraction

Provides PaddleOCR-based extraction with automatic fallback to legacy
pdfplumber extraction when the PaddleOCR API is unavailable.
"""

import argparse
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_pdf_with_paddleocr(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    download_images: bool = False,
    use_table_recognition: bool = True,
    use_formula_recognition: bool = True,
    use_chart_recognition: bool = False,
    use_doc_orientation_classify: bool = False,
    max_pages_per_chunk: int = 10,
) -> Tuple[str, Dict]:
    """
    Extract PDF using PaddleOCR remote API.

    Args:
        pdf_path: Path to the PDF file
        out_dir: Output directory for markdown files
        download_images: Whether to download images (default: False for speed)
        use_table_recognition: Enable table recognition (default: True)
        use_formula_recognition: Enable formula recognition (default: True)
        use_chart_recognition: Enable chart parsing (default: False)
        use_doc_orientation_classify: Enable doc orientation correction (default: False)
        max_pages_per_chunk: Max pages per API call for chunking (default: 10)

    Returns:
        Tuple of (markdown_path, metadata_dict)

    Raises:
        ConnectionError, TimeoutError: When API is unavailable
    """
    from paddleocr_extractor import PaddleOCRPDFExtractor

    extractor = PaddleOCRPDFExtractor(
        use_table_recognition=use_table_recognition,
        use_formula_recognition=use_formula_recognition,
        use_chart_recognition=use_chart_recognition,
        use_doc_orientation_classify=use_doc_orientation_classify,
        max_pages_per_chunk=max_pages_per_chunk,
    )

    # Use extract_pdf for full extraction
    result = extractor.extract_pdf(
        pdf_path,
        out_dir=out_dir,
        download_images=download_images
    )

    md_path = result["markdown_path"]

    # Extract metadata using text_only method for richer parsing
    text_result = extractor.extract_text_only(pdf_path)

    metadata = {
        "title": text_result.get("title", ""),
        "abstract": text_result.get("abstract", ""),
        "keywords": text_result.get("keywords", []),
        "sections": text_result.get("sections", []),
        "extractor": "paddleocr",
        "stats": result.get("stats", {})
    }

    return md_path, metadata


def extract_pdf_local_paddleocr(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    use_table_recognition: bool = True,
    use_formula_recognition: bool = True,
    use_chart_recognition: bool = False,
    use_doc_orientation_classify: bool = False,
) -> Tuple[str, Dict]:
    """
    Extract PDF using local PaddleOCR (GPU via PPStructureV3).

    Args:
        pdf_path: Path to the PDF file
        out_dir: Output directory for markdown files
        use_table_recognition: Enable table recognition (default: True)
        use_formula_recognition: Enable formula recognition (default: True)
        use_chart_recognition: Enable chart parsing (default: False)
        use_doc_orientation_classify: Enable doc orientation correction (default: False)

    Returns:
        Tuple of (markdown_path, metadata_dict)

    Raises:
        ImportError: When paddleocr/paddlex is not installed
    """
    from paddleocr_local import extract_pdf_local
    return extract_pdf_local(
        pdf_path, out_dir,
        use_table_recognition=use_table_recognition,
        use_formula_recognition=use_formula_recognition,
        use_chart_recognition=use_chart_recognition,
        use_doc_orientation_classify=use_doc_orientation_classify,
    )


def extract_pdf_legacy(pdf_path: str, out_dir: str = "paddleocr_md") -> Tuple[str, Dict]:
    """
    Fallback extraction using legacy pdfplumber/pypdf method.

    This mimics anthropic_pdf_extract_raw.py but outputs to paddleocr_md
    with a similar format for compatibility.

    Args:
        pdf_path: Path to the PDF file
        out_dir: Output directory for markdown files

    Returns:
        Tuple of (markdown_path, metadata_dict)
    """
    from pypdf import PdfReader
    import pdfplumber

    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Extract text per page (hybrid method)
    texts = []
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            t = page.extract_text() or ""
            texts.append(t)

        # If pypdf extracted nothing, try pdfplumber
        if not any(t.strip() for t in texts):
            texts = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    texts.append(t)
    except Exception as e:
        logger.warning(f"pypdf failed, trying pdfplumber: {e}")
        texts = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                texts.append(t)

    # Extract PDF metadata
    metadata = {"pages": len(texts)}
    try:
        reader = PdfReader(str(pdf_path))
        meta = reader.metadata
        if meta:
            metadata.update({
                "title": str(getattr(meta, "title", "") or ""),
                "author": str(getattr(meta, "author", "") or ""),
                "subject": str(getattr(meta, "subject", "") or ""),
            })
    except Exception:
        pass

    # Render markdown (similar format to PaddleOCR output for compatibility)
    now = datetime.now().isoformat(timespec="seconds")

    lines = [
        "---",
        f"title: {pdf_path.name}",
        f"source_pdf: {pdf_path.name}",
        "extractor: pdfplumber_fallback",
        "extract_mode: hybrid",
        f"extract_date: {now}",
        "---",
        "",
        f"# {pdf_path.name}",
        "",
        "*Extraction method: pdfplumber/pypdf (fallback)*",
        "",
        "## Text Content",
        "",
    ]

    # Combine all pages into continuous text (similar to PaddleOCR output)
    full_text = "\n\n".join(texts)
    lines.append(full_text)

    content = "\n".join(lines)

    # Save markdown
    out_name = pdf_path.stem + "_paddleocr.md"
    out_path = out_dir / out_name
    out_path.write_text(content, encoding="utf-8")

    logger.info(f"[Fallback] Saved: {out_path}")

    return str(out_path), {
        "title": metadata.get("title", ""),
        "abstract": "",
        "keywords": [],
        "sections": [],
        "extractor": "pdfplumber_fallback",
        "stats": {"total_pages": len(texts)}
    }


def extract_with_fallback(
    pdf_path: str,
    out_dir: str = "paddleocr_md",
    download_images: bool = False,
    use_table_recognition: bool = True,
    use_formula_recognition: bool = True,
    use_chart_recognition: bool = False,
    use_doc_orientation_classify: bool = False,
    max_pages_per_chunk: int = 10,
    no_fallback: bool = False,
    force_local: bool = False,
) -> Tuple[str, Dict]:
    """
    Extract PDF with automatic fallback.

    Fallback chain: Remote PaddleOCR API → Local PaddleOCR (GPU) → pdfplumber.
    Use *force_local* to skip the remote API and go straight to local GPU.

    Args:
        pdf_path: Path to the PDF file
        out_dir: Output directory for markdown files
        download_images: Whether to download images (PaddleOCR only)
        use_table_recognition: Enable table recognition (default: True)
        use_formula_recognition: Enable formula recognition (default: True)
        use_chart_recognition: Enable chart parsing (default: False)
        use_doc_orientation_classify: Enable doc orientation correction (default: False)
        max_pages_per_chunk: Max pages per API call for chunking (default: 10)
        no_fallback: If True, disable automatic fallback and raise errors directly
        force_local: If True, skip remote API and use local PaddleOCR GPU directly

    Returns:
        Tuple of (markdown_path, metadata_dict)
    """
    ocr_kwargs = dict(
        use_table_recognition=use_table_recognition,
        use_formula_recognition=use_formula_recognition,
        use_chart_recognition=use_chart_recognition,
        use_doc_orientation_classify=use_doc_orientation_classify,
    )

    # --- force_local: skip remote, go straight to local GPU ---
    if force_local:
        logger.info(f"Local PaddleOCR (GPU) extraction for: {pdf_path}")
        if no_fallback:
            return extract_pdf_local_paddleocr(pdf_path, out_dir, **ocr_kwargs)
        try:
            return extract_pdf_local_paddleocr(pdf_path, out_dir, **ocr_kwargs)
        except Exception as e:
            logger.warning(f"Local PaddleOCR failed ({type(e).__name__}: {e}), falling back to pdfplumber")
            return extract_pdf_legacy(pdf_path, out_dir)

    # --- no_fallback: only try remote API ---
    if no_fallback:
        logger.info(f"PaddleOCR extraction (no fallback) for: {pdf_path}")
        return extract_pdf_with_paddleocr(
            pdf_path, out_dir, download_images,
            max_pages_per_chunk=max_pages_per_chunk,
            **ocr_kwargs,
        )

    # --- normal mode: remote API → local GPU → pdfplumber ---
    try:
        logger.info(f"Attempting PaddleOCR remote API extraction for: {pdf_path}")
        return extract_pdf_with_paddleocr(
            pdf_path, out_dir, download_images,
            max_pages_per_chunk=max_pages_per_chunk,
            **ocr_kwargs,
        )
    except ValueError as e:
        logger.warning(f"PaddleOCR not configured (missing credentials): {e}")
    except (ConnectionError, TimeoutError) as e:
        logger.warning(f"PaddleOCR API unavailable: {e}")
    except Exception as e:
        logger.warning(f"PaddleOCR remote extraction failed ({type(e).__name__}: {e})")

    # Fallback to local GPU
    try:
        logger.info(f"Attempting local PaddleOCR (GPU) extraction for: {pdf_path}")
        return extract_pdf_local_paddleocr(pdf_path, out_dir, **ocr_kwargs)
    except ImportError:
        logger.warning("Local PaddleOCR not installed (paddleocr/paddlex missing), falling back to pdfplumber")
    except Exception as e:
        logger.warning(f"Local PaddleOCR failed ({type(e).__name__}: {e}), falling back to pdfplumber")

    # Final fallback: pdfplumber
    return extract_pdf_legacy(pdf_path, out_dir)


def extract_metadata_from_paddleocr_md(md_path: str) -> Dict:
    """
    Parse metadata from PaddleOCR markdown file.

    Reads YAML frontmatter and applies extract_text_only patterns
    for additional metadata extraction.

    Args:
        md_path: Path to the PaddleOCR markdown file

    Returns:
        Dict with title, authors, abstract, keywords, sections
    """
    import re
    import yaml

    md_path = Path(md_path)
    if not md_path.exists():
        return {}

    content = md_path.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    metadata = {}
    if content.startswith("---\n"):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            try:
                fm_str = content[4:end_idx]
                metadata = yaml.safe_load(fm_str) or {}
            except Exception:
                pass

    # Extract body content (after frontmatter)
    body = content
    if content.startswith("---\n"):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            body = content[end_idx + 5:]

    # Extract additional metadata from body
    # Title: first substantial line
    if not metadata.get("title"):
        for line in body.split('\n')[:20]:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('*') and len(line) > 10:
                metadata["title"] = line
                break

    # Abstract (Chinese pattern)
    if not metadata.get("abstract"):
        match = re.search(r'摘要[：:]\s*(.+?)(?=\n\n|关键词|中图分类号|Keywords)', body, re.DOTALL)
        if match:
            metadata["abstract"] = match.group(1).strip()

    # Keywords (Chinese pattern)
    if not metadata.get("keywords"):
        match = re.search(r'关键词[：:]\s*(.+?)(?=\n|中图分类号)', body)
        if match:
            keywords = match.group(1)
            metadata["keywords"] = [k.strip() for k in re.split(r'[；;,，]', keywords) if k.strip()]

    # Sections (Chinese numbered pattern)
    if not metadata.get("sections"):
        sections = []
        pattern = r'(?:^|\n)##?\s*([一二三四五六七八九十]+[、\.])\s*(.+?)(?=\n)'
        for match in re.finditer(pattern, body):
            sections.append({
                "number": match.group(1),
                "title": match.group(2).strip()
            })
        if sections:
            metadata["sections"] = sections

    return metadata


def iter_pdfs(input_path: str) -> list:
    """
    Find all PDF files in a path (file or directory).

    Args:
        input_path: Path to a PDF file or directory containing PDFs

    Returns:
        List of PDF file paths
    """
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
        description="Extract PDF to Markdown using PaddleOCR (with fallback)"
    )
    parser.add_argument("input_path", help="PDF file or directory containing PDFs")
    parser.add_argument("--out_dir", default="paddleocr_md", help="Output directory")
    parser.add_argument("--download_images", action="store_true",
                        help="Download images (slower, default: text only)")
    parser.add_argument("--force_fallback", action="store_true",
                        help="Skip PaddleOCR, use legacy extraction")
    parser.add_argument("--no_table", action="store_true",
                        help="Disable table recognition")
    parser.add_argument("--no_formula", action="store_true",
                        help="Disable formula recognition")
    parser.add_argument("--chart", action="store_true",
                        help="Enable chart parsing")
    parser.add_argument("--orientation", action="store_true",
                        help="Enable document orientation correction")
    parser.add_argument("--max_pages", type=int, default=10,
                        help="Max pages per API call chunk (default: 10)")
    parser.add_argument("--no_fallback", action="store_true",
                        help="Disable automatic fallback to pdfplumber on PaddleOCR failure")
    parser.add_argument("--local", action="store_true",
                        help="Use local PaddleOCR GPU instead of remote API")
    args = parser.parse_args()

    pdfs = iter_pdfs(args.input_path)
    if not pdfs:
        logger.error("No PDF files found.")
        return 1

    os.makedirs(args.out_dir, exist_ok=True)

    for pdf_path in pdfs:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {os.path.basename(pdf_path)}")

        try:
            if args.force_fallback:
                md_path, metadata = extract_pdf_legacy(pdf_path, args.out_dir)
            elif args.local:
                md_path, metadata = extract_pdf_local_paddleocr(
                    pdf_path, args.out_dir,
                    use_table_recognition=not args.no_table,
                    use_formula_recognition=not args.no_formula,
                    use_chart_recognition=args.chart,
                    use_doc_orientation_classify=args.orientation,
                )
            else:
                md_path, metadata = extract_with_fallback(
                    pdf_path, args.out_dir, args.download_images,
                    use_table_recognition=not args.no_table,
                    use_formula_recognition=not args.no_formula,
                    use_chart_recognition=args.chart,
                    use_doc_orientation_classify=args.orientation,
                    max_pages_per_chunk=args.max_pages,
                    no_fallback=args.no_fallback,
                )

            logger.info(f"Output: {md_path}")
            logger.info(f"Extractor: {metadata.get('extractor', 'unknown')}")
            if metadata.get("title"):
                logger.info(f"Title: {metadata['title'][:50]}...")

        except Exception as e:
            logger.error(f"Failed to process {pdf_path}: {e}")
            continue

    logger.info(f"\n{'='*60}")
    logger.info(f"Done. Processed {len(pdfs)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
