# Supplemental Reading Skill

## Description
This skill checks the generated Deep Reading Report for missing or generic content (indicating extraction failure). It then attempts to find the missing content from the original Raw Markdown file, re-runs the specific analysis step, and updates the report.

## Usage
Run the script `run_supplemental_reading.ps1` with the path to the report.

## Logic
1. Parse `Final_Deep_Reading_Report.md`.
2. Identify sections containing failure keywords (e.g., "未提供具体论文内容").
3. For each missing section:
   a. Locate the corresponding Raw MD file.
   b. Extract relevant text from Raw MD using fuzzy header matching.
   c. Call the specific `deep_reading_steps/step_N.py` with the extracted text.
   d. Replace the section in the final report.
