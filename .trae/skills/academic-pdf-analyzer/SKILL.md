---
name: "academic-pdf-analyzer"
description: "Batch processes academic PDFs to extract structured research info (Deep Reading style) into a concise table and generate Stata code. Invoke when analyzing papers for econometrics."
---

# Academic PDF Analyzer & Stata Code Generator

This skill specializes in extracting structured academic information from PDF documents and generating corresponding Stata code for econometric analysis.
It is optimized for **concise, table-ready output** based on the **Deep Reading Framework** (Acemoglu Level).

## Core Capabilities

1.  **PDF Processing**:
    - Identify and read PDFs from specified folders.
    - Handle encoding (UTF-8, GBK).
    - Suggest or implement OCR for scanned documents.

2.  **Structured Extraction (Table-Friendly)**:
    Extracts key information into 7 dimensions (Simplified Chinese):
    - **1. Big Picture**: Research Theme, Scientific Problem, Core Contribution.
    - **2. Theory**: Theoretical Foundation, Core Hypothesis.
    - **3. Data**: Data Source, Sample Characteristics.
    - **4. Measurement**: Dependent Variable (Y), Independent Variable (X), Control Variables.
    - **5. Identification**: Econometric Model, Identification Strategy (IV/DID etc.), Mechanism.
    - **6. Results**: Core Findings.
    - **7. Critique**: Weakness/Achilles' Heel.

3.  **Stata Code Generation**:
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
    - The script generates a Markdown report with a **Summary Table** for each paper.
    - It also aggregates results into an Excel file (optional).

## Output Template (Markdown)

### [Paper Title]

**Authors**: ... | **Journal**: ... | **Year**: ...

#### 核心要素提取表 (Deep Reading Extraction)

| 维度 | 要素 | 内容提取 |
| :--- | :--- | :--- |
| **1. 全景扫描** | **研究主题** | ... |
| | **科学问题** | ... |
| | **核心贡献** | ... |
| **2. 理论基础** | **理论框架** | ... |
| | **核心假说** | ... |
| **3. 数据** | **数据来源** | ... |
| | **样本特征** | ... |
| **4. 变量** | **被解释变量 (Y)** | ... |
| | **核心解释变量 (X)** | ... |
| | **控制变量** | ... |
| **5. 识别策略** | **计量模型** | ... |
| | **识别挑战与策略** | ... |
| | **工具/机制变量** | ... |
| **6. 结果与评价** | **主要发现** | ... |
| | **研究不足** | ... |

#### Stata 代码建议
```stata
* Code to replicate the methodology
...
```
