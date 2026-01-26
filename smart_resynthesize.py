import os
import re
import sys

def clean_content(text):
    """
    Strips YAML frontmatter and Navigation sections from text.
    """
    # 1. Strip YAML Frontmatter (between --- and --- at start)
    # Match start of string, ---, content, ---, newline
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
    
    # 2. Strip Navigation section
    # Look for "## 导航" or "## Navigation" and remove everything after
    nav_markers = ["## 导航", "## Navigation"]
    for marker in nav_markers:
        if marker in text:
            text = text.split(marker)[0]
            
    return text.strip()

def resynthesize_report(paper_dir):
    paper_basename = os.path.basename(paper_dir)
    final_report_path = os.path.join(paper_dir, "Final_Deep_Reading_Report.md")
    
    print(f"Resynthesizing report for: {paper_basename}")
    
    steps = [
        "1_Overview", "2_Theory", "3_Data", "4_Variables", 
        "5_Identification", "6_Results", "7_Critique"
    ]
    
    combined_content = f"# Deep Reading Report: {paper_basename}\n\n"
    
    for step in steps:
        step_file = os.path.join(paper_dir, f"{step}.md")
        if os.path.exists(step_file):
            print(f"  Processing {step}...")
            with open(step_file, 'r', encoding='utf-8') as sf:
                raw_content = sf.read()
                cleaned = clean_content(raw_content)
                
                step_title = step.replace('_', ' ')
                combined_content += f"## {step_title}\n\n"
                combined_content += cleaned + "\n\n"
        else:
            print(f"  Warning: {step}.md not found")
            
    with open(final_report_path, 'w', encoding='utf-8') as f:
        f.write(combined_content)
        
    print(f"Done. Saved to {final_report_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python smart_resynthesize.py <paper_output_directory>")
        sys.exit(1)
        
    target_dir = sys.argv[1]
    resynthesize_report(target_dir)