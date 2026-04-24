#!/usr/bin/env python3
"""Test the full pipeline with paper.pdf"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace/deep-reading-agent')

from app import run_deep_reading

# Mock Gradio progress
class MockProgress:
    def __call__(self, val, desc=""):
        print(f"[Progress] {int(val*100)}% - {desc}")

pdf_path = "/tmp/paper.pdf"
method = "Legacy (pdfplumber)"

print("=" * 60)
print("Testing Deep Reading Pipeline")
print(f"PDF: {pdf_path}")
print(f"Method: {method}")
print("=" * 60)

i = 0
for output in run_deep_reading(pdf_path, method, progress=MockProgress()):
    i += 1
    print(f"\n--- Update {i} ---")
    print(f"Stage: {output.get('stage', '')}")
    print(f"Progress: {output.get('progress', 0)}%")
    print(f"Logs:\n{output.get('logs', '')[-500:]}")  # Last 500 chars
    if output.get('preview'):
        print(f"Preview: {output['preview'][:200]}...")
    if output.get('download'):
        print(f"Download: {output['download']}")
    print("-" * 40)
