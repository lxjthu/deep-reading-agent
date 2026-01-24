import os
import argparse
from extractor import PDFExtractor
from deep_analyzer import DeepAnalyzer

def main():
    parser = argparse.ArgumentParser(description="Acemoglu-Level Deep Paper Reader")
    parser.add_argument("pdf_path", help="Path to the PDF file to read deeply")
    parser.add_argument("--output_dir", default="deep_reports", help="Directory to save the deep reading report")
    args = parser.parse_args()

    # Verify input file
    if not os.path.exists(args.pdf_path):
        print(f"Error: File not found at {args.pdf_path}")
        return

    # Create output directory
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    print(f"🚀 Starting Acemoglu-Level Deep Reading for: {os.path.basename(args.pdf_path)}")
    print("---------------------------------------------------------------")

    # 1. Extract Text
    print("📖 Phase 1: Extracting full text from PDF...")
    extractor = PDFExtractor()
    text = extractor.extract_content(args.pdf_path)
    
    if not text:
        print("Error: Failed to extract text from PDF.")
        return
    print(f"   Success! Extracted {len(text)} characters.")

    # 2. Initialize Analyzer
    analyzer = DeepAnalyzer()
    if not analyzer.kimi_client:
        print("Error: Kimi API Key is missing. Cannot proceed with long-context reading.")
        return

    # 3. Deep Analysis
    print("🧠 Phase 2: Running Deep Analysis (Map-Reduce Strategy)...")
    print("   - Step 1: Parsing structure (Kimi)...")
    print("   - Step 2: Distributed Deep Reading (Kimi + DeepSeek-R1)...")
    print("     > Agent A: Value Assessment")
    print("     > Agent B: Theory & Hypotheses")
    print("     > Agent C: Data Audit")
    print("     > Agent D: Econometrics")
    print("   - Step 3: Synthesis & Mechanism Mapping (DeepSeek-R1)...")
    
    results = analyzer.analyze_paper_deeply(text, filename=os.path.basename(args.pdf_path))
    
    if "error" in results:
        print(f"❌ Analysis Failed: {results['error']}")
        return

    # 4. Generate Report
    filename = os.path.splitext(os.path.basename(args.pdf_path))[0]
    output_path = os.path.join(args.output_dir, f"{filename}_deep_report.md")
    
    print(f"📝 Phase 3: Generating Deep Report at {output_path}...")
    analyzer.generate_deep_report(results, output_path)
    
    print("---------------------------------------------------------------")
    print("✅ Deep Reading Complete! Enjoy your Acemoglu-style report.")

if __name__ == "__main__":
    main()
