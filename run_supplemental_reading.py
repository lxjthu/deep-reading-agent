import os
import sys
import re
import glob

# Ensure we can import deep_reading_steps
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from deep_reading_steps import (
    step_1_overview, step_2_theory, step_3_data, 
    step_4_vars, step_5_identification, step_6_results, step_7_critique
)

from deep_reading_steps.common import DEEP_READING_DIR, save_step_result

STEP_MAPPING = {
    "1 Overview": {"module": step_1_overview, "keywords": ["Introduction", "Overview", "引言"]},
    "2 Theory": {"module": step_2_theory, "keywords": ["Theory", "Model", "Hypothesis", "Theoretical", "理论"]},
    "3 Data": {"module": step_3_data, "keywords": ["Data", "Sample", "Source", "数据"]},
    "4 Variables": {"module": step_4_vars, "keywords": ["Variable", "Measure", "Measurement", "变量"]},
    "5 Identification": {"module": step_5_identification, "keywords": ["Identification", "Strategy", "Empirical", "Equation", "识别"]},
    "6 Results": {"module": step_6_results, "keywords": ["Result", "Finding", "Estimate", "结果"]},
    "7 Critique": {"module": step_7_critique, "keywords": ["Conclusion", "Discussion", "Limitation", "结论"]}
}

REPORT_PATH = r"d:\code\skill\deep_reading_results\Final_Deep_Reading_Report.md"
RAW_DIR = r"d:\code\skill\pdf_raw_md"

def find_raw_file(report_content):
    # Extract filename from: # Deep Reading Report: 1-..._segmented.md
    match = re.search(r"# Deep Reading Report: (.*)_segmented\.md", report_content)
    if match:
        base_name = match.group(1)
        # Try finding the raw file
        # It could be base_name + "_raw.md"
        # Or search for similar name
        raw_path = os.path.join(RAW_DIR, f"{base_name}_raw.md")
        if os.path.exists(raw_path):
            return raw_path
            
        # Fallback: list files and fuzzy match
        files = os.listdir(RAW_DIR)
        for f in files:
            if base_name in f:
                return os.path.join(RAW_DIR, f)
    return None

def extract_context_from_raw(raw_path, keywords):
    print(f"Extracting context for {keywords} from {os.path.basename(raw_path)}...")
    with open(raw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract text from code blocks
    clean_text = ""
    code_blocks = re.findall(r"```text\n(.*?)\n```", content, re.DOTALL)
    if code_blocks:
        clean_text = "\n".join(code_blocks)
    else:
        clean_text = content

    lines = clean_text.split('\n')
    start_idx = -1
    
    # 1. Search for Numbered Header: "3. Data", "III. Data"
    for i, line in enumerate(lines):
        line = line.strip()
        if re.match(r"^(\d+|[IVX]+)[\.\s]", line):
            for kw in keywords:
                if kw.lower() in line.lower():
                    start_idx = i
                    print(f"Found header match at line {i}: {line}")
                    break
        if start_idx != -1:
            break
            
    # 2. Search for loose header (short line)
    if start_idx == -1:
        for i, line in enumerate(lines):
            line = line.strip()
            if len(line) < 50 and len(line) > 3:
                 for kw in keywords:
                    if kw.lower() in line.lower() and not line.endswith('.'):
                        start_idx = i
                        print(f"Found loose match at line {i}: {line}")
                        break
            if start_idx != -1:
                break

    if start_idx != -1:
        extracted_lines = lines[start_idx:]
        # Return up to 1500 lines (generous context)
        return "\n".join(extracted_lines[:1500])
        
    print(f"Warning: No specific section found for {keywords}. Returning first 30k chars.")
    return clean_text[:30000]

def main():
    if len(sys.argv) > 1:
        report_path = sys.argv[1]
    else:
        report_path = REPORT_PATH

    if not os.path.exists(report_path):
        print(f"Report not found: {report_path}")
        return

    print(f"Checking report: {report_path}")
    with open(report_path, 'r', encoding='utf-8') as f:
        report_content = f.read()

    raw_file = find_raw_file(report_content)
    if not raw_file:
        print("Could not identify Raw MD file from report.")
        # Try to guess from the directory if only one file exists? No, risky.
        return
    print(f"Identified Raw MD: {raw_file}")

    # Split report into sections to identify missing ones
    # We use regex to find sections like "## 1 Overview", "## 2 Theory"
    section_matches = list(re.finditer(r"^## (\d+ [A-Za-z]+|Overview|Theory|Data|Variables|Identification|Results|Critique)", report_content, re.MULTILINE))
    
    processed_any = False
    
    for i, match in enumerate(section_matches):
        section_title = match.group(1) # e.g. "3 Data"
        
        # Normalize title key for STEP_MAPPING
        map_key = None
        for k in STEP_MAPPING.keys():
            if k in section_title:
                map_key = k
                break
        
        if not map_key:
            continue
            
        start_idx = match.end()
        end_idx = section_matches[i+1].start() if i + 1 < len(section_matches) else len(report_content)
        section_text = report_content[start_idx:end_idx].strip()
        
        # Check for failure indicators
        is_missing = False
        if "未提供具体论文内容" in section_text:
            is_missing = True
        elif "文本内容为空" in section_text:
            is_missing = True
        elif "generic" in section_text.lower() and "framework" in section_text.lower():
            is_missing = True
        elif len(section_text) < 150: 
            is_missing = True
            
        if is_missing:
            print(f"\n[!] Section '{section_title}' appears missing. Launching supplemental reading...")
            processed_any = True
            
            step_info = STEP_MAPPING[map_key]
            
            # Extract context
            context = extract_context_from_raw(raw_file, step_info['keywords'])
            
            # Run step
            print(f"Running module {step_info['module'].__name__}...")
            
            # Create a fake sections dict that the step expects
            # The key should ideally match what the step looks for. 
            # Step 4 looks for "Variable" in key. Step 3 looks for "Data".
            fake_key = f"Supplement {step_info['keywords'][0]}"
            sections = {fake_key: context}
            
            try:
                result = step_info['module'].run(sections)
                if result:
                    print(f"Step {map_key} completed successfully.")
                else:
                    print(f"Step {map_key} returned no result.")
            except Exception as e:
                print(f"Error running step {map_key}: {e}")
        else:
            print(f"[OK] Section '{section_title}' looks fine ({len(section_text)} chars).")

    if processed_any:
        print("\nRegenerating Final Report...")
        
        # Re-read the latest partial files
        final_report = ""
        
        # Header (Metadata) - preserve from original report
        header_match = re.search(r"^---.*?---\n", report_content, re.DOTALL)
        if header_match:
            final_report += header_match.group(0)
        
        # Title line
        title_line_match = re.search(r"^# Deep Reading Report:.*$", report_content, re.MULTILINE)
        if title_line_match:
            final_report += "\n" + title_line_match.group(0) + "\n\n"
            
        # Files order matching STEP_MAPPING keys sorted
        # Or just hardcoded
        files_order = [
            "1_Overview.md", "2_Theory.md", "3_Data.md", "4_Variables.md", 
            "5_Identification.md", "6_Results.md", "7_Critique.md"
        ]
        
        # Also need to check if 4_Vars produced 4_Variables.md or 4_Vars.md
        # step_4_vars.py saves to "4_Variables" -> 4_Variables.md
        
        for fname in files_order:
            fpath = os.path.join(DEEP_READING_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Ensure it has the header "## X Title"
                    # The steps usually return content starting with "## ..." or just text.
                    # Let's check if we need to add the header.
                    # Step 1 returns text starting with "## 1 Overview" (usually handled by prompt or post-processing)
                    # Actually step_1 saves the result directly.
                    # Let's trust the file content but ensure spacing.
                    final_report += content + "\n\n"
            else:
                print(f"Warning: Part file {fname} not found.")

        # Navigation
        final_report += "## 导航 (Navigation)\n\n**分步分析文档：**\n"
        for fname in files_order:
             final_report += f"- [[{fname.replace('.md', '')}]]\n"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(final_report)
        print(f"Updated report saved to {report_path}")
    else:
        print("No missing sections detected. Report is up to date.")

if __name__ == "__main__":
    main()
