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
            entry = {
                'Title': r.get('TI', ''),
                'Authors': authors,
                'Journal': r.get('SO', ''),
                'Year': r.get('PY', ''),
                'Abstract': r.get('AB', ''),
                'DOI': r.get('DI', ''),
                'Type': r.get('DT', r.get('PT', '')),
                'Citations': r.get('TC', '0'),
                'SourceType': 'WoS'
            }
            data.append(entry)
        return pd.DataFrame(data)

class CNKIParser(BaseParser):
    def __init__(self, file_path):
        self.file_path = file_path
        self.records = []

    def parse(self):
        """Parses the CNKI plain text export."""
        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            return []

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(self.file_path, 'r', encoding='gb18030') as f: # CNKI often uses GBK/GB18030
                lines = f.readlines()

        current_record = {}
        
        # Regex to match "Key-ChineseKey: Value"
        # e.g., "Title-题名: ..."
        field_pattern = re.compile(r"^([A-Za-z]+)-([\u4e00-\u9fa5]+):\s*(.*)")
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Check for new record start
            if line.startswith("SrcDatabase-"):
                if current_record:
                    self.records.append(current_record)
                current_record = {}
            
            match = field_pattern.match(line)
            if match:
                key = match.group(1) # e.g. Title
                # cn_key = match.group(2) # e.g. 题名
                value = match.group(3)
                current_record[key] = value
            else:
                # Handle multi-line abstract or other fields if necessary
                # CNKI exports usually put abstract on one line, but just in case
                pass

        # Append last record
        if current_record:
            self.records.append(current_record)
            
        logger.info(f"Parsed {len(self.records)} records from {self.file_path} (CNKI)")
        return self.records

    def to_dataframe(self):
        data = []
        for r in self.records:
            # Clean Authors (replace ; with ; )
            authors = r.get('Author', '').replace(';', '; ')
            
            # Extract Year from PubTime (e.g., 2026-01-23 17:54)
            year = ''
            pub_time = r.get('PubTime', '')
            year_match = re.search(r'\d{4}', pub_time)
            if year_match:
                year = year_match.group(0)
            
            entry = {
                'Title': r.get('Title', ''),
                'Authors': authors,
                'Journal': r.get('Source', ''), # CNKI uses Source for Journal Name
                'Year': year,
                'Abstract': r.get('Summary', ''), # CNKI uses Summary
                'DOI': '', # CNKI plain text often lacks DOI
                'Type': 'Journal', # Default to Journal
                'Citations': '0', # Not provided in this format
                'SourceType': 'CNKI'
            }
            data.append(entry)
        return pd.DataFrame(data)

def get_parser(file_path):
    """Factory method to detect format and return appropriate parser."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            header = f.read(1024)
    except:
        try:
            with open(file_path, 'r', encoding='gb18030') as f:
                header = f.read(1024)
        except:
            return None

    if "FN Clarivate" in header or "VR 1.0" in header:
        return WoSParser(file_path)
    elif "SrcDatabase-" in header or "Title-题名" in header:
        return CNKIParser(file_path)
    else:
        # Default fallback or error
        return None
