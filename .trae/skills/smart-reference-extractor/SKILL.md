---
name: "smart-reference-extractor"
description: "Extracts bibliography/references from segmented academic paper Markdown files into a structured Excel table using LLM-based pattern recognition. Invoke when user wants to parse references, create a bibliography list, or extract citations to Excel."
---

# Smart Reference Extractor

This skill parses the "References" or "Bibliography" section of a segmented paper Markdown file (produced by the segmentation skill) and outputs a structured Excel file.

## Features
- **Intelligent Pattern Recognition**: Uses DeepSeek to analyze the citation format (APA, MLA, Chicago, etc.) and generate custom regex for splitting and parsing.
- **Structured Output**: Extracts Author, Year, Title, Journal, Volume/Issue, and Pages into separate columns.
- **Batch Processing**: Can handle long reference lists efficiently using the generated patterns.

## Usage

### 1. Run the Extractor

Use the provided PowerShell wrapper or Python script directly.

**Command:**
```powershell
.\run_reference_extractor.ps1 "path/to/paper_segmented.md"
```

**Output:**
- An Excel file named `references.xlsx` (or similar) in the same directory as the input file.

### 2. Python Direct Usage

```bash
python extract_references.py "path/to/paper_segmented.md" --out_file "my_refs.xlsx"
```

## Requirements
- `segmented_md` file must exist and contain a "References" or "Bibliography" header (e.g., `## 8. References`).
- `DEEPSEEK_API_KEY` must be set in `.env`.
