import os
import re
import yaml
import logging
import argparse
from datetime import datetime
from smart_scholar_lib import SmartScholar

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
SOCIAL_RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_science_results_v2")
PDF_RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_raw_md")

class MetadataFixer:
    def __init__(self):
        self.scholar = SmartScholar()

    def extract_metadata_from_raw(self, basename):
        """
        Try to get metadata from raw_md file (first 2 pages) using lightweight AI.
        """
        raw_md_path = os.path.join(PDF_RAW_DIR, f"{basename}_raw.md")
        if not os.path.exists(raw_md_path):
            logger.warning(f"Raw MD not found for {basename}")
            return None

        # Read first 3000 chars (approx 2 pages)
        try:
            with open(raw_md_path, 'r', encoding='utf-8') as f:
                content = f.read(3000)
        except Exception as e:
            logger.error(f"Error reading raw MD: {e}")
            return None

        # Lightweight AI Call
        system_prompt = """
        You are a Bibliographic Metadata Extractor. Extract the paper's metadata from the provided text.
        
        Output JSON ONLY:
        {
            "title": "Exact Title",
            "authors": "Author 1, Author 2",
            "journal": "Journal Name",
            "year": "YYYY",
            "genre": "Case Study/Review/etc"
        }
        If a field is missing, use empty string "".
        """
        
        try:
            # Re-use SmartScholar's client for consistency
            response = self.scholar.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract metadata from this text:\n\n{content}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            import json
            import json_repair
            res_content = response.choices[0].message.content
            meta = json_repair.repair_json(res_content, return_objects=True)
            return meta
        except Exception as e:
            logger.error(f"AI Extraction failed: {e}")
            return None

    def update_file_frontmatter(self, file_path, metadata):
        """
        Updates the YAML frontmatter of a markdown file with new metadata.
        Preserves existing fields (like 'gaps', 'contributions').
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse existing frontmatter
            frontmatter_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
            existing_data = {}
            body = content
            
            if frontmatter_match:
                fm_text = frontmatter_match.group(1)
                try:
                    existing_data = yaml.safe_load(fm_text) or {}
                except yaml.YAMLError:
                    logger.warning(f"Invalid YAML in {file_path}, overwriting.")
                body = content[frontmatter_match.end():]
            else:
                # If no frontmatter, create it
                pass

            # Merge metadata (Priority: metadata > existing_data)
            # But we want to keep specific fields like 'gaps' from existing
            
            # 1. Update standard fields
            existing_data['title'] = metadata.get('title', existing_data.get('title', ''))
            existing_data['authors'] = metadata.get('authors', existing_data.get('authors', ''))
            existing_data['journal'] = metadata.get('journal', existing_data.get('journal', ''))
            existing_data['year'] = metadata.get('year', existing_data.get('year', ''))
            
            # 2. Handle Tags
            tags = existing_data.get('tags', [])
            if tags is None:
                tags = []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(',')]
            
            new_tags = ["SocialScience", "DeepReading"]
            if metadata.get('genre'):
                new_tags.append(metadata['genre'])
            
            # Deduplicate tags
            final_tags = list(set(tags + new_tags))
            existing_data['tags'] = final_tags
            
            # 3. Ensure date exists
            if 'date' not in existing_data:
                existing_data['date'] = datetime.now().strftime('%Y-%m-%d')

            # Reconstruct content
            new_fm = yaml.dump(existing_data, allow_unicode=True, sort_keys=False).strip()
            new_content = f"---\n{new_fm}\n---\n{body}"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            return True
        except Exception as e:
            logger.error(f"Failed to update {file_path}: {e}")
            return False

    def process_folder(self, folder_name, force=False):
        folder_path = os.path.join(SOCIAL_RESULTS_DIR, folder_name)
        if not os.path.isdir(folder_path):
            return

        logger.info(f"Checking {folder_name}...")
        
        # 1. Check if metadata is missing (check L1 or Full Report)
        needs_update = force
        if not needs_update:
            # Naive check: read L1 file
            l1_file = os.path.join(folder_path, f"{folder_name}_L1_Context.md")
            if os.path.exists(l1_file):
                with open(l1_file, 'r', encoding='utf-8') as f:
                    head = f.read(500)
                    if "journal:" not in head or "year:" not in head:
                        needs_update = True
            else:
                needs_update = True
            
        if not needs_update:
            logger.info(f"Metadata looks complete for {folder_name}, skipping AI.")
            return

        logger.info(f"Fetching metadata for {folder_name}...")
        meta = self.extract_metadata_from_raw(folder_name)
        
        if not meta:
            logger.error(f"Could not extract metadata for {folder_name}")
            return

        # 2. Update all MD files in folder
        for fname in os.listdir(folder_path):
            if fname.endswith(".md"):
                fpath = os.path.join(folder_path, fname)
                if self.update_file_frontmatter(fpath, meta):
                    logger.info(f"Updated {fname}")

def main():
    parser = argparse.ArgumentParser(description="Fix metadata for Social Science reports")
    parser.add_argument("--target", help="Specific folder name to process (optional)")
    parser.add_argument("--force", action="store_true", help="Force update even if metadata looks complete")
    args = parser.parse_args()

    fixer = MetadataFixer()

    if args.target:
        fixer.process_folder(args.target, force=args.force)
    else:
        if not os.path.exists(SOCIAL_RESULTS_DIR):
            logger.error(f"Directory not found: {SOCIAL_RESULTS_DIR}")
            return
            
        folders = os.listdir(SOCIAL_RESULTS_DIR)
        logger.info(f"Found {len(folders)} folders to scan.")
        
        for folder in folders:
            fixer.process_folder(folder, force=args.force)

if __name__ == "__main__":
    main()
