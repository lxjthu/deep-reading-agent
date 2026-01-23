# Batch PDF Processor Skill

## Description
This skill enables batch processing of all PDF files in a specified directory.
It iterates through the PDFs, checks if a corresponding Deep Reading Report already exists, and skips processed files to save time and resources.
For unprocessed files, it triggers the full Deep Reading Pipeline.

## Usage
Run the script `run_batch_pipeline.ps1` with the path to the PDF directory.

```powershell
.\run_batch_pipeline.ps1 "d:\code\skill\pdf"
```

## Logic
1. Scan the target directory for `.pdf` files.
2. For each PDF:
   a. Determine the expected output directory (e.g., `deep_reading_results/{pdf_basename}`).
   b. Check if `Final_Deep_Reading_Report.md` exists in that directory.
   c. If exists -> Skip with a message.
   d. If not exists -> Call `run_full_pipeline.py` for this PDF.
