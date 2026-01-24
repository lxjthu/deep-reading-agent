import argparse
import os
import re
import yaml
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def _env(name, default=None):
    return os.getenv(name, default)

def get_client():
    api_key = _env("OPENAI_API_KEY")
    base_url = _env("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=base_url)

def extract_metadata_from_text(text):
    client = get_client()
    if not client:
        print("Warning: No OpenAI API key found. Using placeholder metadata.")
        return {
            "title": "Unknown Title",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown",
            "tags": ["paper"]
        }

    prompt = f"""
    Extract the following metadata from the academic paper text provided below.
    The text comes from the first few pages of the raw PDF extraction.
    
    Return ONLY a JSON object with these keys:
    - title: string (Full paper title)
    - authors: list of strings (Full names of all authors)
    - journal: string (Journal name if visible, e.g. "The Quarterly Journal of Economics", or "Working Paper" if explicitly stated or implied by "NBER", "IZA" etc.)
    - year: string or int (Publication or draft year)
    
    Text (First 2 pages content):
    {text}
    """

    try:
        resp = client.chat.completions.create(
            model=_env("OPENAI_MODEL", "moonshot-v1-auto"),
            messages=[
                {"role": "system", "content": "You are a precise academic metadata extractor. Return JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = resp.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        return {
            "title": "Unknown Title",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown",
            "tags": ["paper"]
        }

def read_first_two_pages(path):
    """
    Reads the raw markdown file and extracts content roughly corresponding to the first 2 pages.
    Since raw md has '## Page N' markers, we can use that.
    """
    if not os.path.exists(path):
        return ""
        
    content = []
    page_count = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith("## Page "):
                page_count += 1
                if page_count > 2:
                    break
            content.append(line)
            
    return "".join(content)

def read_source_md(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def has_frontmatter(content):
    return content.startswith("---\n")

def inject_frontmatter(content, metadata):
    # 1. Parse existing frontmatter if present
    existing_meta = {}
    body_content = content
    
    if has_frontmatter(content):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            try:
                fm_str = content[4:end_idx]
                existing_meta = yaml.safe_load(fm_str) or {}
                body_content = content[end_idx+5:]
            except Exception as e:
                print(f"Warning: Failed to parse existing frontmatter: {e}")
    
    # 2. Merge metadata (Priority: New Metadata > Existing Metadata for core fields, but keep other existing fields)
    # Actually, for core fields (Title, Authors), we probably trust the dedicated extraction more than random previous runs?
    # BUT, wait. Dataview Summarizer injected rich fields (e.g. research_theme). We MUST preserve them.
    # The 'metadata' argument contains only basic info (Title, Author...).
    
    merged_meta = existing_meta.copy()
    merged_meta.update(metadata) # Overwrite basic info with fresh extraction (or keep existing if we trust it more? Let's overwrite to ensure consistency)
    
    # Special handling for tags: merge them
    tags = set()
    
    # Add existing tags
    if "tags" in existing_meta:
        if isinstance(existing_meta["tags"], list):
            tags.update(existing_meta["tags"])
        elif isinstance(existing_meta["tags"], str):
            tags.add(existing_meta["tags"])
            
    # Add new tags
    if "tags" in metadata:
        if isinstance(metadata["tags"], list):
            tags.update(metadata["tags"])
        elif isinstance(metadata["tags"], str):
            tags.add(metadata["tags"])
            
    # Always ensure deep-reading tag
    tags.add("paper")
    tags.add("deep-reading")
    
    merged_meta["tags"] = list(tags)

    # 3. Dump to YAML
    yaml_str = yaml.safe_dump(merged_meta, allow_unicode=True, sort_keys=False).strip()
    
    frontmatter_block = f"---\n{yaml_str}\n---\n\n"
    
    return frontmatter_block + body_content

def add_bidirectional_links(content, filename, all_files):
    # Strategy:
    # If this is Final Report, add links to all Steps.
    # If this is a Step, add link to Final Report.
    
    is_final = "Final" in filename
    
    links_section = "\n\n## 导航 (Navigation)\n\n"
    
    if is_final:
        # Link to steps
        steps = [f for f in all_files if f != filename and f.endswith(".md")]
        # Sort steps by number if possible
        steps.sort()
        
        links_section += "**分步分析文档：**\n"
        for s in steps:
            # Remove extension for wikilink
            link_name = os.path.splitext(s)[0]
            links_section += f"- [[{link_name}]]\n"
    else:
        # Link to Final
        final_files = [f for f in all_files if "Final" in f and f.endswith(".md")]
        if final_files:
            link_name = os.path.splitext(final_files[0])[0]
            links_section += f"**返回总报告：** [[{link_name}]]\n"
            
    # Check if links section already exists to avoid duplication
    if "## 导航 (Navigation)" in content:
        return content # Already added
        
    return content + links_section

def main():
    parser = argparse.ArgumentParser(description="Inject Obsidian metadata and links")
    parser.add_argument("source_md", help="Source markdown file (segmented or raw) to extract metadata from")
    parser.add_argument("target_dir", help="Directory containing markdown files to update")
    parser.add_argument("--raw_md", help="Optional path to the original raw PDF markdown for better metadata extraction", default=None)
    args = parser.parse_args()

    source_text = ""
    if args.raw_md and os.path.exists(args.raw_md):
        print(f"Reading raw MD for metadata (first 2 pages): {args.raw_md}")
        source_text = read_first_two_pages(args.raw_md)
    else:
        print(f"Reading source MD for metadata (fallback): {args.source_md}")
        # If segmented, just read the first chunk
        full_text = read_source_md(args.source_md)
        source_text = full_text[:3000] # Increase limit slightly for fallback

    print("Extracting metadata...")
    metadata = extract_metadata_from_text(source_text)
    print(f"Metadata: {metadata}")
    
    if not os.path.exists(args.target_dir):
        print(f"Target dir not found: {args.target_dir}")
        return

    all_files = [f for f in os.listdir(args.target_dir) if f.endswith(".md")]
    
    for filename in all_files:
        path = os.path.join(args.target_dir, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 1. Inject Frontmatter (with MERGE now)
        new_content = inject_frontmatter(content, metadata)
        
        # 2. Add Links
        new_content = add_bidirectional_links(new_content, filename, all_files)
        
        if new_content != content:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {filename}")
        else:
            print(f"Skipped (no change): {filename}")

if __name__ == "__main__":
    main()
