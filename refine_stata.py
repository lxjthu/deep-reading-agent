import os
import argparse
import json
from tqdm import tqdm
from llm_analyzer import LLMAnalyzer
from stata_refiner import StataRefiner

def main():
    parser = argparse.ArgumentParser(description="Stata Code Refiner (Acemoglu Edition)")
    parser.add_argument("--reports_dir", default="reports", help="Directory containing markdown reports")
    args = parser.parse_args()

    if not os.path.exists(args.reports_dir):
        print(f"Directory {args.reports_dir} not found.")
        return

    # Find all MD files
    md_files = [f for f in os.listdir(args.reports_dir) if f.endswith(".md")]
    
    if not md_files:
        print("No markdown reports found to refine.")
        return

    print(f"Found {len(md_files)} reports. Starting expert refinement...")
    
    refiner = StataRefiner()

    for md_file in tqdm(md_files, desc="Refining Stata Code"):
        md_path = os.path.join(args.reports_dir, md_file)
        
        # Read the MD file to extract context (Methodology & Variables)
        # We use a simple heuristic to read the content back from MD
        # In a production system, we might prefer reading the JSON intermediate files if we saved them
        # But here we parse the MD text we generated.
        
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check if already refined
        if "(Expert Refined)" in content:
            print(f"Skipping {md_file}: Already refined.")
            continue

        # Extract Methodology
        methodology = "N/A"
        if "### 研究方法" in content:
            methodology = content.split("### 研究方法")[1].split("###")[0].strip()
            
        # Extract Variables
        variables = "N/A"
        if "### 变量信息" in content:
            variables = content.split("### 变量信息")[1].split("##")[0].strip()
            
        if methodology == "N/A" and variables == "N/A":
            print(f"Skipping {md_file}: Could not parse context.")
            continue
            
        # Call the Expert Agent
        refined_code = refiner.refine_code(methodology, variables, filename=md_file)
        
        # Update the MD file
        refiner.update_markdown_report(md_path, refined_code)

    print("\nRefinement Complete! Check your reports for expert Stata code.")

if __name__ == "__main__":
    main()
