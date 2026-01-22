import os
import argparse
import pandas as pd
from tqdm import tqdm
from extractor import PDFExtractor
from llm_analyzer import LLMAnalyzer

def main():
    parser = argparse.ArgumentParser(description="Academic PDF Analyzer (LLM-Enhanced)")
    parser.add_argument("input_path", help="Folder containing PDFs or path to a single PDF")
    parser.add_argument("--output", default="results.xlsx", help="Output Excel file path")
    parser.add_argument("--markdown_dir", default="reports", help="Directory to save individual markdown reports")
    args = parser.parse_args()

    # Create markdown output directory
    if not os.path.exists(args.markdown_dir):
        os.makedirs(args.markdown_dir)

    files_to_process = []
    if os.path.isfile(args.input_path):
        files_to_process.append(args.input_path)
    elif os.path.isdir(args.input_path):
        for root, dirs, files in os.walk(args.input_path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    files_to_process.append(os.path.join(root, file))
    
    if not files_to_process:
        print("No PDF files found.")
        return

    print(f"Found {len(files_to_process)} PDF files.")

    extractor = PDFExtractor()
    analyzer = LLMAnalyzer()
    
    if not analyzer.client:
        print("CRITICAL: OpenAI API Key missing. Please check .env file.")
        return
        
    results = []

    for file_path in tqdm(files_to_process, desc="Processing PDFs with LLM"):
        try:
            filename = os.path.basename(file_path)
            
            # 1. Extract Text
            text = extractor.extract_content(file_path)
            if not text:
                print(f"Skipping {filename} (empty text)")
                continue

            # 2. Analyze Content (LLM)
            analysis = analyzer.analyze(text, filename=filename)
            
            if "error" in analysis:
                print(f"Error analyzing {filename}: {analysis['error']}")
                continue

            # 3. Generate Individual Markdown Report
            md_path = os.path.join(args.markdown_dir, f"{os.path.splitext(filename)[0]}_report.md")
            analyzer.generate_markdown_report(analysis, md_path)
            
            # 4. Compile Result for Excel
            # Helper to truncate references for Excel (take top 5 lines)
            refs = analysis.get("data_methods", {}).get("references", "")
            
            # Handle list or string format for references
            if isinstance(refs, list):
                refs_short = "\n".join([str(r) for r in refs[:5]])
                # Convert list to string for Markdown report if needed later
                # But here we just need refs_short string for Excel
            elif isinstance(refs, str):
                refs_short = "\n".join(refs.split('\n')[:5])
            else:
                refs_short = str(refs)
            
            row = {
                "Filename": filename,
                "Title": analysis.get("title", ""),
                "Authors": analysis.get("authors", ""),
                "Journal": analysis.get("journal", ""),
                "Year": analysis.get("year", ""),
                "Background": analysis.get("background", ""),
                "Significance": analysis.get("significance", ""),
                "Logic": analysis.get("logic", ""),
                "Methodology": analysis.get("methodology_summary", ""),
                "Conclusions": analysis.get("conclusions", ""),
                "Dep. Var": analysis.get("variables", {}).get("dependent", ""),
                "Indep. Var": analysis.get("variables", {}).get("independent", ""),
                "Mechanism": analysis.get("variables", {}).get("mechanism", ""),
                "Instrumental": analysis.get("variables", {}).get("instrumental", ""),
                "Controls": analysis.get("variables", {}).get("controls", ""),
                "Data Source": analysis.get("data_methods", {}).get("data_source", ""),
                "Measurements": analysis.get("data_methods", {}).get("measurements", ""),
                "References (Top 5)": refs_short,
                "Stata Code": analysis.get("stata_code", "")
            }
            results.append(row)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    # Save to Excel
    if results:
        df = pd.DataFrame(results)
        df.to_excel(args.output, index=False)
        print(f"\nProcessing complete. Results saved to {args.output}")
        print(f"Markdown reports saved to: {args.markdown_dir}")
    else:
        print("\nNo results extracted.")

if __name__ == "__main__":
    main()
