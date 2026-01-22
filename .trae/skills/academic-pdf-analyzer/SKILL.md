---
name: "academic-pdf-analyzer"
description: "Batch processes academic PDFs to extract research info, variables, and generate Stata code. Invoke when analyzing research papers or extracting data for econometrics."
---

# Academic PDF Analyzer & Stata Code Generator

This skill specializes in extracting structured academic information from PDF documents and generating corresponding Stata code for econometric analysis.

## Core Capabilities

1.  **PDF Processing**:
    - Identify and read PDFs from specified folders.
    - Handle encoding (UTF-8, GBK).
    - Suggest or implement OCR for scanned documents.

2.  **Content Extraction**:
    - **Background**: Summarize research background (200-300 words).
    - **Significance**: Theoretical and practical significance.
    - **Logic**: Describe research flow/process.
    - **Methodology**: Detailed steps.
    - **Conclusions**: 3-5 core findings.

3.  **Variable Extraction (Econometrics Focus)**:
    - **Dependent Variable (Y)**: Name and definition.
    - **Independent Variable (X)**: Name and definition.
    - **Mechanism/Mediator**: Name and definition.
    - **Instrumental Variable (IV)**: Name and definition.
    - **Control Variables**: List of controls.

4.  **Stata Code Generation**:
    - Based on the extracted "Methodology" and "Variables", generate precise Stata code.
    - Include data loading, variable declaration, and regression commands (e.g., `reg`, `reghdfe`, `ivreg2`).

## Usage Workflow

1.  **Input**: User provides a folder path or specific PDF files.
2.  **Process**:
    - **Preferred Method**: Use the pre-configured PowerShell script `run_analyzer.ps1` which handles the virtual environment automatically.
      ```powershell
      .\run_analyzer.ps1 -InputPath "path/to/pdfs" -Output "results.xlsx"
      ```
    - Alternatively, invoke the python script directly using the virtual environment:
      ```powershell
      .\venv\Scripts\python main.py "path/to/pdfs" --output "results.xlsx"
      ```
3.  **Output**:
    - The script generates an Excel file with the results.
    - **Read the Excel file** or the script output to present the key findings to the user in the conversation.
    - Present extracted info in a Markdown table for immediate review.
    - Provide the Stata code block.

## Output Template

For each paper:

### [Paper Title]

**1. Research Summary**
| Section | Content |
| :--- | :--- |
| **Background** | ... |
| **Significance** | ... |
| **Methodology** | ... |
| **Conclusions** | ... |

**2. Variable Definitions**
| Type | Variable Name | Definition | Measurement |
| :--- | :--- | :--- | :--- |
| Dependent | ... | ... | ... |
| Independent | ... | ... | ... |
| Mechanism | ... | ... | ... |
| Control | ... | ... | ... |

**3. Stata Code**
```stata
* Code to replicate the methodology
...
```
