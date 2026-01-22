import os
import re
from extractor import PDFExtractor

def debug_keywords():
    folder = "pdf"
    files = [f for f in os.listdir(folder) if f.endswith(".pdf")]
    if not files:
        print("No PDF files found.")
        return

    # Pick the first file
    file_path = os.path.join(folder, files[0])
    print(f"Analyzing file: {file_path}")
    
    extractor = PDFExtractor()
    text = extractor.extract_content(file_path)
    
    print("-" * 30)
    print("Keyword Search:")
    
    keywords = ["被解释变量", "解释变量", "控制变量", "研究背景", "结论"]
    for kw in keywords:
        matches = re.findall(f".{{0,20}}{kw}.{{0,20}}", text)
        print(f"Keyword '{kw}': {len(matches)} matches")
        for m in matches[:3]:
            print(f"  Context: ...{m}...")

if __name__ == "__main__":
    debug_keywords()
