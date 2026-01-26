import os
import argparse
import pandas as pd
from tqdm import tqdm
from extractor import PDFExtractor
from llm_analyzer import LLMAnalyzer
from smart_scholar_lib import SmartScholar

def main():
    parser = argparse.ArgumentParser(description="Academic PDF Analyzer (Smart Batch Mode)")
    parser.add_argument("input_path", help="Folder containing PDFs or path to a single PDF (or markdown file)")
    parser.add_argument("--output", default="results.xlsx", help="Output Excel file path")
    parser.add_argument("--markdown_dir", default="reports", help="Directory to save individual markdown reports")
    parser.add_argument("--force", action="store_true", help="Force re-process all files, ignoring existing results.")
    args = parser.parse_args()

    # Create markdown output directory
    if not os.path.exists(args.markdown_dir):
        os.makedirs(args.markdown_dir)

    # 1. Load Existing Results (Incremental Logic)
    existing_df = pd.DataFrame()
    processed_files = set()
    
    if os.path.exists(args.output) and not args.force:
        try:
            existing_df = pd.read_excel(args.output)
            if "Filename" in existing_df.columns:
                processed_files = set(existing_df["Filename"].astype(str).tolist())
            print(f"Loaded existing results: {len(processed_files)} files already processed.")
        except Exception as e:
            print(f"Warning: Could not read existing Excel file: {e}. Starting fresh.")

    files_to_process = []
    if os.path.isfile(args.input_path):
        files_to_process.append(args.input_path)
    elif os.path.isdir(args.input_path):
        for root, dirs, files in os.walk(args.input_path):
            for file in files:
                # Modified to accept both .pdf and .md files
                if file.lower().endswith(".pdf") or file.lower().endswith(".md"):
                    # Check if already processed
                    if not args.force and file in processed_files:
                        continue
                    files_to_process.append(os.path.join(root, file))
    
    if not files_to_process:
        if processed_files:
            print("All files have already been processed. Use --force to re-run.")
        else:
            print("No PDF or Markdown files found.")
        return

    print(f"Found {len(files_to_process)} NEW files to process.")

    extractor = PDFExtractor()
    analyzer = LLMAnalyzer()
    scholar = SmartScholar() # Helper for classification
    
    if not analyzer.client:
        print("CRITICAL: OpenAI API Key missing. Please check .env file.")
        return
        
    results = []

    for file_path in tqdm(files_to_process, desc="Processing Files"):
        try:
            filename = os.path.basename(file_path)
            
            # 1. Extract Text
            if file_path.lower().endswith(".md"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                text = extractor.extract_content(file_path)
                
            if not text:
                print(f"Skipping {filename} (empty text)")
                continue

            # 2. Classify (New Step)
            # Use first 3000 chars for classification
            paper_type = scholar.classify_paper(text[:3000])
            # print(f"  [{paper_type}] {filename}")

            # 3. Analyze Content (Adaptive Mode)
            analysis = analyzer.analyze(text, filename=filename, mode=paper_type)
            
            if "error" in analysis:
                print(f"Error analyzing {filename}: {analysis['error']}")
                continue

            # 4. Generate Individual Markdown Report
            md_path = os.path.join(args.markdown_dir, f"{os.path.splitext(filename)[0]}_report.md")
            analyzer.generate_markdown_report(analysis, md_path)
            
            # 5. Compile Result for Excel
            b = analysis.get('basic', {})
            o = analysis.get('overview', {})
            t = analysis.get('theory', {})
            d = analysis.get('data', {})
            m = analysis.get('measurement', {})
            i = analysis.get('identification', {})
            r = analysis.get('results', {})

            row = {
                "Filename": filename,
                "Type": paper_type, # Add Type column
                "Title": b.get("title", ""),
                "Authors": b.get("authors", ""),
                "Journal": b.get("journal", ""),
                "Year": b.get("year", ""),
                
                "Research Theme": o.get("theme", ""),
                "Problem": o.get("problem", ""),
                "Contribution": o.get("contribution", ""),
                
                "Theory/Constructs": t.get("theory_base", ""), # Mapped
                "Hypothesis/Framework": t.get("hypothesis", ""), # Mapped
                
                "Data/Case": d.get("data_source", ""), # Mapped
                "Sample/Context": d.get("sample_info", ""), # Mapped
                
                "Dep. Var/Outcome": m.get("dep_var", ""), # Mapped
                "Indep. Var/Condition": m.get("indep_var", ""), # Mapped
                "Controls/Context": m.get("controls", ""), # Mapped
                
                "Model/Method": i.get("model", ""), # Mapped
                "Strategy/Path": i.get("strategy", ""), # Mapped
                "IV/Mechanism": i.get("iv_mechanism", ""), # Mapped
                
                "Findings": r.get("findings", ""),
                "Weakness": r.get("weakness", ""),
                
                "Stata Code": analysis.get("stata_code", "")
            }
            results.append(row)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    # Save to Excel
    if results:
        new_df = pd.DataFrame(results)
        
        if not existing_df.empty and not args.force:
            # Append new results to existing ones
            final_df = pd.concat([existing_df, new_df], ignore_index=True)
            print(f"Appending {len(new_df)} new records to existing {len(existing_df)} records.")
        else:
            final_df = new_df
            
        try:
            final_df.to_excel(args.output, index=False)
            print(f"\nProcessing complete. Results saved to {args.output}")
        except PermissionError:
            print(f"\nERROR: Could not write to {args.output}. File might be open.")
            backup_name = args.output.replace(".xlsx", f"_new_{len(results)}.xlsx")
            final_df.to_excel(backup_name, index=False)
            print(f"Saved to backup file instead: {backup_name}")
            
        print(f"Markdown reports saved to: {args.markdown_dir}")
    else:
        print("\nNo results extracted.")

if __name__ == "__main__":
    main()
