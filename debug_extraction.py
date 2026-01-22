import os
from extractor import PDFExtractor

def debug_pdf():
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
    print("EXTRACTED TEXT PREVIEW (First 1000 chars):")
    print("-" * 30)
    print(text[:1000])
    print("-" * 30)
    print("EXTRACTED TEXT PREVIEW (Middle 1000 chars):")
    print("-" * 30)
    mid = len(text) // 2
    print(text[mid:mid+1000])

if __name__ == "__main__":
    debug_pdf()
