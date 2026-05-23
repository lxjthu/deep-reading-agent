import os
import re
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class BaseParser:
    def parse(self):
        raise NotImplementedError
    
    def to_dataframe(self):
        raise NotImplementedError

class WoSParser(BaseParser):
    def __init__(self, file_path):
        self.file_path = file_path
        self.records = []

    def parse(self):
        """Parses the Web of Science plain text file."""
        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            return []

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(self.file_path, 'r', encoding='latin-1') as f:
                lines = f.readlines()

        current_record = {}
        last_tag = None
        
        for line in lines:
            line = line.rstrip('\n')
            if not line: continue
            if line.startswith('FN ') or line.startswith('VR '): continue
            
            if line.startswith('PT '):
                current_record = {}
                last_tag = 'PT'
                continue
                
            if line.startswith('ER'):
                if current_record:
                    self.records.append(current_record)
                continue

            if len(line) > 2 and line[0:2].isupper() and line[2] == ' ':
                tag = line[0:2]
                content = line[3:].strip()
                if tag == 'AU' or tag == 'AF':
                    if tag not in current_record: current_record[tag] = []
                    current_record[tag].append(content)
                else:
                    current_record[tag] = content
                last_tag = tag
            elif line.startswith('   '):
                content = line.strip()
                if last_tag:
                    if last_tag == 'AU' or last_tag == 'AF':
                        current_record[last_tag].append(content)
                    else:
                        current_record[last_tag] += " " + content
            
        logger.info(f"Parsed {len(self.records)} records from {self.file_path} (WoS)")
        return self.records

    def to_dataframe(self):
        data = []
        for r in self.records:
            authors = "; ".join(r.get('AU', []))
            de = r.get('DE', '')
            id_kw = r.get('ID', '')
            kw_parts = [p.strip() for p in [de, id_kw] if p.strip()]
            keywords = '; '.join(kw_parts)

            pages = r.get('BP', '')
            ep = r.get('EP', '')
            page_count = r.get('PG', '')
            if pages and ep:
                pages = f"{pages}-{ep}"
            elif not pages and ep:
                pages = ep
            elif not pages and page_count:
                pages = page_count

            entry = {
                'Title': r.get('TI', ''),
                'Authors': authors,
                'Journal': r.get('SO', ''),
                'Year': r.get('PY', ''),
                'Abstract': r.get('AB', ''),
                'DOI': r.get('DI', ''),
                'Keywords': keywords,
                'Volume': r.get('VL', ''),
                'Issue': r.get('IS', ''),
                'Pages': pages,
                'ISSN': r.get('SN', ''),
                'Language': r.get('LA', ''),
                'Type': r.get('DT', r.get('PT', '')),
                'Citations': r.get('TC', '0'),
                'SourceType': 'WoS',
            }
            data.append(entry)
        return pd.DataFrame(data)

class CNKIParser(BaseParser):
    def __init__(self, file_path):
        self.file_path = file_path
        self.records = []

    def parse(self):
        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            return []

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(self.file_path, 'r', encoding='gb18030') as f:
                lines = f.readlines()

        current_record = {}
        last_key = None
        field_pattern = re.compile(r"^([A-Za-z]+)-([\u4e00-\u9fa5]+):\s*(.*)")

        for line in lines:
            line = line.rstrip('\n').rstrip('\r')
            if not line.strip():
                last_key = None
                continue

            if line.startswith("SrcDatabase-"):
                if current_record:
                    self.records.append(current_record)
                current_record = {}
                last_key = None

            match = field_pattern.match(line.strip())
            if match:
                key = match.group(1)
                value = match.group(3)
                current_record[key] = value
                last_key = key
            elif last_key and not line.strip().startswith("SrcDatabase-"):
                current_record[last_key] = current_record.get(last_key, '') + ' ' + line.strip()

        if current_record:
            self.records.append(current_record)

        logger.info(f"Parsed {len(self.records)} records from {self.file_path} (CNKI)")
        return self.records

    def to_dataframe(self):
        data = []
        for r in self.records:
            authors = r.get('Author', '').replace(';', '; ').rstrip('; ').strip()

            year = r.get('Year', '').strip()
            if not year:
                pub_time = r.get('PubTime', '')
                year_match = re.search(r'\d{4}', pub_time)
                year = year_match.group(0) if year_match else ''

            entry = {
                'Title': r.get('Title', ''),
                'Authors': authors,
                'Journal': r.get('Source', ''),
                'Year': year,
                'Abstract': r.get('Summary', ''),
                'DOI': r.get('DOI', ''),
                'Keywords': r.get('Keyword', ''),
                'Volume': r.get('Volume', ''),
                'Issue': r.get('Period', ''),
                'Pages': r.get('PageCount', ''),
                'ISSN': r.get('ISSN', ''),
                'URL': r.get('URL', ''),
                'PubTime': r.get('PubTime', ''),
                'Type': 'Journal',
                'Citations': '0',
                'SourceType': 'CNKI',
            }
            data.append(entry)
        return pd.DataFrame(data)

def get_parser(file_path):
    """Factory method to detect format and return appropriate parser.
    Supports .txt, .doc (via antiword), and .docx (via python-docx)."""
    import subprocess
    import tempfile
    import os
    
    # Handle .doc files by converting to text first
    if file_path.lower().endswith('.doc'):
        try:
            result = subprocess.run(['antiword', file_path], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                # Write converted text to temp file
                fd, temp_path = tempfile.mkstemp(suffix='.txt')
                try:
                    os.write(fd, result.stdout.encode('utf-8'))
                    os.close(fd)
                    file_path = temp_path  # Use converted text for parsing
                except:
                    os.close(fd)
                    raise
        except Exception as e:
            logger.warning(f"antiword failed for {file_path}: {e}")
    
    try:
        # Try reading with utf-8 first
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            # Read larger header to handle binary noise at start (.doc files)
            header = f.read(8192)
    except:
        try:
            with open(file_path, 'r', encoding='gb18030', errors='replace') as f:
                header = f.read(8192)
        except:
            return None

    # WoS format detection - search in larger window, case-insensitive
    if "FN Clarivate" in header or "VR 1.0" in header or "Clarivate Analytics Web of Science" in header:
        logger.info(f"Detected WoS format for {file_path}")
        return WoSParser(file_path)
    elif "SrcDatabase-" in header or "Title-题名" in header:
        logger.info(f"Detected CNKI format for {file_path}")
        return CNKIParser(file_path)
    else:
        # Log header preview for debugging
        safe_preview = header[:500].replace('\n', ' ').replace('\r', '')
        logger.warning(f"Unsupported file format for {file_path}. Header preview: {safe_preview}...")
        return None
