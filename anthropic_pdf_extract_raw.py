import argparse
import os
from datetime import datetime

import pdfplumber
from pypdf import PdfReader


def _safe_str(value):
    if value is None:
        return ""
    return str(value)


def extract_text_per_page(pdf_path: str, method: str) -> list[str]:
    if method not in {"pypdf", "pdfplumber", "hybrid"}:
        raise ValueError("method must be one of: pypdf, pdfplumber, hybrid")

    texts: list[str] = []

    if method in {"pypdf", "hybrid"}:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            t = page.extract_text() or ""
            texts.append(t)

        if method == "pypdf":
            return texts

        if any(t.strip() for t in texts):
            return texts

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            texts.append(t)

    return texts


def extract_metadata(pdf_path: str) -> dict:
    try:
        reader = PdfReader(pdf_path)
        meta = reader.metadata
        return {
            "title": _safe_str(getattr(meta, "title", None)),
            "author": _safe_str(getattr(meta, "author", None)),
            "subject": _safe_str(getattr(meta, "subject", None)),
            "creator": _safe_str(getattr(meta, "creator", None)),
            "producer": _safe_str(getattr(meta, "producer", None)),
            "creation_date": _safe_str(getattr(meta, "creation_date", None)),
            "modification_date": _safe_str(getattr(meta, "modification_date", None)),
            "pages": len(reader.pages),
        }
    except Exception:
        return {"pages": ""}


def render_markdown(filename: str, pdf_path: str, method: str, pages_text: list[str]) -> str:
    meta = extract_metadata(pdf_path)
    now = datetime.now().isoformat(timespec="seconds")
    header = [
        f"# PDF 原文提取 (Anthropic pdf 技能思路)",
        "",
        f"- Filename: {filename}",
        f"- Method: {method}",
        f"- Extracted At: {now}",
        f"- Pages: {meta.get('pages', '')}",
    ]

    for k in ["title", "author", "subject", "creator", "producer", "creation_date", "modification_date"]:
        v = _safe_str(meta.get(k, "")).strip()
        if v:
            header.append(f"- {k}: {v}")

    body: list[str] = []
    for idx, text in enumerate(pages_text, start=1):
        body.append("")
        body.append(f"## Page {idx}")
        body.append("")
        body.append("```text")
        body.append(text.rstrip("\n"))
        body.append("```")

    return "\n".join(header + body) + "\n"


def iter_pdfs(input_path: str) -> list[str]:
    if os.path.isfile(input_path) and input_path.lower().endswith(".pdf"):
        return [input_path]

    pdfs: list[str] = []
    for root, _, files in os.walk(input_path):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdfs.append(os.path.join(root, f))
    return sorted(pdfs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract raw PDF text into Markdown (Anthropic pdf skill approach)")
    parser.add_argument("input_path", help="Folder containing PDFs or path to a single PDF")
    parser.add_argument("--out_dir", default="pdf_raw_md", help="Output directory for markdown files")
    parser.add_argument("--method", default="hybrid", choices=["hybrid", "pypdf", "pdfplumber"], help="Extraction method")
    args = parser.parse_args()

    pdfs = iter_pdfs(args.input_path)
    if not pdfs:
        print("No PDF files found.")
        return

    os.makedirs(args.out_dir, exist_ok=True)

    for pdf_path in pdfs:
        filename = os.path.basename(pdf_path)
        pages_text = extract_text_per_page(pdf_path, method=args.method)
        md = render_markdown(filename=filename, pdf_path=pdf_path, method=args.method, pages_text=pages_text)
        out_name = os.path.splitext(filename)[0] + "_raw.md"
        out_path = os.path.join(args.out_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

