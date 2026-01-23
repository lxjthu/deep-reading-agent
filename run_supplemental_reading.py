import os
import sys
import re
import glob
import argparse
import yaml  # Make sure pyyaml is installed: pip install pyyaml

# Ensure we can import deep_reading_steps
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import metadata injector
try:
    from inject_obsidian_meta import extract_metadata_from_text, read_first_two_pages, inject_frontmatter, add_bidirectional_links
except ImportError:
    # If running from root, simple import works if path is right, but inject_obsidian_meta is in root
    # sys.path is already current dir usually
    try:
        sys.path.append(r"d:\code\skill")
        from inject_obsidian_meta import extract_metadata_from_text, read_first_two_pages, inject_frontmatter, add_bidirectional_links
    except ImportError:
        print("Warning: Could not import inject_obsidian_meta. Metadata injection will be skipped.")
        extract_metadata_from_text = None


from deep_reading_steps import (
    step_1_overview, step_2_theory, step_3_data, 
    step_4_vars, step_5_identification, step_6_results, step_7_critique
)

from deep_reading_steps.common import DEEP_READING_DIR, save_step_result

STEP_MAPPING = {
    "1 Overview": {"module": step_1_overview, "keywords": ["Introduction", "Overview", "引言"], "file": "1_Overview.md"},
    "2 Theory": {"module": step_2_theory, "keywords": ["Theory", "Model", "Hypothesis", "Theoretical", "理论"], "file": "2_Theory.md"},
    "3 Data": {"module": step_3_data, "keywords": ["Data", "Sample", "Source", "数据"], "file": "3_Data.md"},
    "4 Variables": {"module": step_4_vars, "keywords": ["Variable", "Measure", "Measurement", "变量"], "file": "4_Variables.md"},
    "5 Identification": {"module": step_5_identification, "keywords": ["Identification", "Strategy", "Empirical", "Equation", "识别"], "file": "5_Identification.md"},
    "6 Results": {"module": step_6_results, "keywords": ["Result", "Finding", "Estimate", "结果"], "file": "6_Results.md"},
    "7 Critique": {"module": step_7_critique, "keywords": ["Conclusion", "Discussion", "Limitation", "结论"], "file": "7_Critique.md"}
}

REPORT_PATH = r"d:\code\skill\deep_reading_results\Final_Deep_Reading_Report.md"
RAW_DIR = r"d:\code\skill\pdf_raw_md"

def find_raw_file(report_content):
    # Extract filename from: # Deep Reading Report: 1-..._segmented.md
    match = re.search(r"# Deep Reading Report: (.*)_segmented\.md", report_content)
    if match:
        base_name = match.group(1)
        raw_path = os.path.join(RAW_DIR, f"{base_name}_raw.md")
        if os.path.exists(raw_path):
            return raw_path
        files = os.listdir(RAW_DIR)
        for f in files:
            if base_name in f:
                return os.path.join(RAW_DIR, f)
    return None

def extract_context_from_raw(raw_path, keywords):
    print(f"Extracting context for {keywords} from {os.path.basename(raw_path)}...")
    with open(raw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    clean_text = ""
    code_blocks = re.findall(r"```text\n(.*?)\n```", content, re.DOTALL)
    if code_blocks:
        clean_text = "\n".join(code_blocks)
    else:
        clean_text = content

    lines = clean_text.split('\n')
    start_idx = -1
    
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
        return "\n".join(extracted_lines[:1500])
        
    print(f"Warning: No specific section found for {keywords}. Returning first 30k chars.")
    return clean_text[:30000]

def strip_frontmatter_and_nav(content):
    # Strip YAML Frontmatter
    if content.startswith("---"):
        try:
            end_idx = content.find("\n---\n", 3)
            if end_idx != -1:
                content = content[end_idx+5:].strip()
        except:
            pass
            
    # Strip Navigation
    nav_marker = "## 导航 (Navigation)"
    if nav_marker in content:
        content = content.split(nav_marker)[0].strip()
        
    return content

def main():
    print(f"Imported yaml module: {yaml}")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("report_path", nargs="?", default=REPORT_PATH)
    parser.add_argument("--regenerate", action="store_true", help="Force regenerate the final report from sub-files")
    args = parser.parse_args()
    
    report_path = args.report_path

    if not os.path.exists(report_path):
        print(f"Report not found: {report_path}")
        return
        
    # Dynamically determine DEEP_READING_DIR from report_path
    # This overrides the import from common.py which might use default or env var from parent process
    # but run_supplemental_reading.py is often run as subprocess.
    # The report is always inside the DEEP_READING_DIR.
    global DEEP_READING_DIR
    DEEP_READING_DIR = os.path.dirname(os.path.abspath(report_path))
    print(f"Set DEEP_READING_DIR to: {DEEP_READING_DIR}")

    print(f"Checking report: {report_path}")
    with open(report_path, 'r', encoding='utf-8') as f:
        report_content = f.read()

    raw_file = find_raw_file(report_content)
    if raw_file:
        print(f"Identified Raw MD: {raw_file}")
    else:
        print("Could not identify Raw MD file from report.")

    # Prepare metadata if possible (lazy load)
    metadata = None
    if raw_file and extract_metadata_from_text:
        print("Extracting metadata for injection...")
        try:
            raw_text = read_first_two_pages(raw_file)
            metadata = extract_metadata_from_text(raw_text)
            if metadata:
                print(f"Metadata ready: {metadata.get('title', 'Unknown')}")
        except Exception as e:
            print(f"Error extracting metadata: {e}")

    section_matches = list(re.finditer(r"^## (\d+ [A-Za-z]+|Overview|Theory|Data|Variables|Identification|Results|Critique)", report_content, re.MULTILINE))
    
    processed_any = False
    
    if not args.regenerate:
        for i, match in enumerate(section_matches):
            section_title = match.group(1)
            
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
                if not raw_file:
                    print("Error: Cannot extract context without raw file.")
                    continue

                context = extract_context_from_raw(raw_file, step_info['keywords'])
                print(f"Running module {step_info['module'].__name__}...")
                
                fake_key = f"Supplement {step_info['keywords'][0]}"
                sections = {fake_key: context}
                
                try:
                    result = step_info['module'].run(sections)
                    if result:
                        print(f"Step {map_key} completed successfully.")
                        
                        # INJECT METADATA IMMEDIATELY
                        if metadata and 'file' in step_info:
                            out_file = os.path.join(DEEP_READING_DIR, step_info['file'])
                            if os.path.exists(out_file):
                                print(f"Injecting metadata into {step_info['file']}...")
                                with open(out_file, 'r', encoding='utf-8') as f:
                                    f_content = f.read()
                                
                                # All files list for links
                                all_files = [f for f in os.listdir(DEEP_READING_DIR) if f.endswith(".md")]
                                
                                new_content = inject_frontmatter(f_content, metadata)
                                new_content = add_bidirectional_links(new_content, step_info['file'], all_files)
                                
                                with open(out_file, 'w', encoding='utf-8') as f:
                                    f.write(new_content)
                    else:
                        print(f"Step {map_key} returned no result.")
                except Exception as e:
                    print(f"Error running step {map_key}: {e}")
            else:
                print(f"[OK] Section '{section_title}' looks fine ({len(section_text)} chars).")
    else:
        print("Forcing regeneration of Final Report...")
        processed_any = True

    if processed_any:
        print("\nRegenerating Final Report...")
        
        final_report = ""
        
        # Header (Metadata)
        if metadata:
            try:
                # Use yaml.safe_dump
                yaml_str = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
                final_report += f"---\n{yaml_str}\n---\n\n"
            except Exception as e:
                print(f"Error dumping yaml: {e}")
                header_match = re.search(r"^---.*?---\n", report_content, re.DOTALL)
                if header_match:
                    final_report += header_match.group(0)
        else:
            header_match = re.search(r"^---.*?---\n", report_content, re.DOTALL)
            if header_match:
                final_report += header_match.group(0)
        
        # Title line
        if metadata:
            # We don't have base_name here easily unless we parse report_path again
            # But we can just use the Title from metadata
            final_report += f"# Deep Reading Report: {metadata.get('title', 'Untitled')}\n\n"
        else:
            title_line_match = re.search(r"^# Deep Reading Report:.*$", report_content, re.MULTILINE)
            if title_line_match:
                final_report += "\n" + title_line_match.group(0) + "\n\n"
            else:
                final_report += "\n# Deep Reading Report\n\n"
            
        files_order = [
            "1_Overview.md", "2_Theory.md", "3_Data.md", "4_Variables.md", 
            "5_Identification.md", "6_Results.md", "7_Critique.md"
        ]
        
        for fname in files_order:
            fpath = os.path.join(DEEP_READING_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    clean_content = strip_frontmatter_and_nav(content)
                    final_report += clean_content + "\n\n"
            else:
                print(f"Warning: Part file {fname} not found.")

        final_report += "## 导航 (Navigation)\n\n**分步分析文档：**\n"
        for fname in files_order:
             final_report += f"- [[{fname.replace('.md', '')}]]\n"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(final_report)
        print(f"Updated report saved to {report_path}")
    else:
        print("No missing sections detected and no regeneration requested. Report is up to date.")

if __name__ == "__main__":
    main()
