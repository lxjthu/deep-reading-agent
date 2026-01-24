import os
import sys
import subprocess

# Define exact paths
base_dir = r"d:\code\skill\deep_reading_results"
folder_name = r"2-CFPS-DID-长期护理保险制度何以破解“一人失能，全家失衡”困局——基于农村子女劳动供给的视角_卢素兰"
target_dir = os.path.join(base_dir, folder_name)

raw_base_dir = r"d:\code\skill\pdf_raw_md"
raw_file_name = r"2-CFPS-DID-长期护理保险制度何以破解“一人失能，全家失衡”困局——基于农村子女劳动供给的视角_卢素兰_raw.md"
raw_file = os.path.join(raw_base_dir, raw_file_name)

print(f"Using Python: {sys.executable}")
print(f"Target Dir Exists: {os.path.exists(target_dir)}")
print(f"Raw File Exists: {os.path.exists(raw_file)}")

# Run Dataview Injector
print("Running Dataview Injector...")
subprocess.run([sys.executable, "inject_dataview_summaries.py", target_dir], check=True)

# Run Obsidian Meta Injector
print("Running Obsidian Meta Injector...")
subprocess.run([sys.executable, "inject_obsidian_meta.py", raw_file, target_dir, "--raw_md", raw_file], check=True)
