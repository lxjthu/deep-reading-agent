# Academic PDF Analyzer & Stata Generator

This tool automates the extraction of academic information from PDF papers and generates Stata code for econometric analysis.

## Features
- **Batch Processing**: Scans folders for PDFs.
- **Info Extraction**: Background, Significance, Methodology, Conclusions.
- **Variable Detection**: Dependent, Independent, Controls.
- **Code Generation**: Auto-generates Stata (`.do`) code snippets.
- **Export**: Saves results to Excel (`results.xlsx`).

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: You may need to download the Spacy model:*
   ```bash
   python -m spacy download en_core_web_sm
   ```

2. (Optional) OCR Support:
   - Install `tesseract-ocr` on your system.
   - Uncomment the OCR section in `extractor.py`.

## Usage

Run the analyzer on a folder of PDFs:

```bash
python main.py "path/to/your/pdf_folder"
```

The results will be saved to `results.xlsx` in the current directory.
