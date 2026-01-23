# Supplemental Reading Skill

## Description
This skill checks the generated Deep Reading Report for missing or generic content (indicating extraction failure). It then attempts to find the missing content from the original Raw Markdown file, re-runs the specific analysis step, and updates the report.

Additionally, it automatically manages **Obsidian Metadata**:
1. When a missing section is regenerated, it extracts metadata (Title, Authors, etc.) from the raw PDF text and injects it into the new sub-file (e.g., `4_Variables.md`) along with bidirectional links.
2. When regenerating the `Final_Deep_Reading_Report.md`, it **strips** the metadata and navigation links from the individual sub-files to ensure a clean, unified report structure with a single top-level metadata block.

## Usage
Run the script `run_supplemental_reading.ps1` with the path to the report.
To force regeneration of the final report (e.g. to clean up metadata), use the `--regenerate` flag.

```powershell
.\run_supplemental_reading.ps1 "path\to\report.md" [--regenerate]
```

## Logic
1. Parse `Final_Deep_Reading_Report.md`.
2. Extract Metadata from Raw MD (lazy load) for potential injection.
3. Identify sections containing failure keywords (e.g., "未提供具体论文内容").
4. For each missing section:
   a. Locate the corresponding Raw MD file.
   b. Extract relevant text from Raw MD using fuzzy header matching.
   c. Call the specific `deep_reading_steps/step_N.py` with the extracted text.
   d. **Inject Metadata & Links** into the newly generated step file.
5. Regenerate Final Report:
   a. Combine all 7 step files.
   b. **Strip** YAML frontmatter and Navigation sections from each step content.
   c. Prepend a single, clean YAML metadata block to the final report.
   d. Append a master Navigation section.
