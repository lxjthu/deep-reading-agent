"""Standalone source parsing. CNKI/WoS tag logic adapted from parsers.py.
No web application imports. Physical PDF page numbers are one-based.
"""
from __future__ import annotations
import hashlib
import re
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from statistics import median


def sha256(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def read_text(path):
    data = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'gb18030', 'latin-1'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('Cannot decode input')


def ordered_pdf_text(page):
    """Keep full-width bands, then read the left and right column within each band."""
    blocks=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            text=''.join(span['text'] for span in line.get('spans',[]))
            blocks.append((*line['bbox'],text+'\n',len(blocks),0))
    mid=page.rect.width/2
    left=[b for b in blocks if b[2]<=mid+12 and len(b[4].strip())>8]
    right=[b for b in blocks if b[0]>=mid-12 and len(b[4].strip())>8]
    if len(left)<8 or len(right)<8 or min(median(b[2]-b[0] for b in side) for side in (left,right)) < page.rect.width*.28:
        return page.get_text('text',sort=True),'single-column-or-unknown'
    spans=sorted([b for b in blocks if b[0]<mid-12 and b[2]>mid+12],key=lambda b:b[1])
    remaining=[b for b in blocks if b not in spans]; output=[]; lower=-1
    def band(items):
        cols=([b for b in items if (b[0]+b[2])/2<mid],[b for b in items if (b[0]+b[2])/2>=mid])
        text=[]
        for column in cols:
            rows=[]
            for block in sorted(column,key=lambda b:b[1]):
                if rows and abs(rows[-1][0][1]-block[1])<3: rows[-1].append(block)
                else: rows.append([block])
            for row in rows: text.append(''.join(b[4].rstrip('\n') for b in sorted(row,key=lambda b:b[0])))
        return '\n'.join(text)
    for span in spans:
        current=[b for b in remaining if b[1]<span[1]]
        output.append(band(current)); remaining=[b for b in remaining if b not in current]
        output.append(span[4])
    output.append(band(remaining))
    return '\n'.join(s for s in output if s),'two-column-bands'


def parse_bibliography(path, format='auto'):
    text = read_text(path)
    if format == 'auto':
        format = 'cnki' if 'SrcDatabase-' in text or 'Title-题名' in text else 'wos' if re.search(r'^PT |^FN ', text, re.M) else ''
    records, current, last = [], {}, None
    if format == 'cnki':
        for line in text.splitlines():
            if line.startswith('SrcDatabase-') and current:
                records.append(current); current = {}; last = None
            match = re.match(r'^([A-Za-z]+)-[^:]+:\s*(.*)', line.strip())
            if match:
                last = match[1]; current[last] = match[2]
            elif line.strip() and last:
                current[last] += ' ' + line.strip()
        if current: records.append(current)
    elif format == 'wos':
        for line in text.splitlines():
            if line.startswith(('FN ', 'VR ', 'EF')): continue
            if line.startswith('PT '):
                if current: records.append(current)
                current = {'PT': line[3:].strip()}; last = 'PT'; continue
            if line == 'ER':
                if current: records.append(current)
                current = {}; last = None; continue
            if re.match(r'^[A-Z0-9]{2} ', line):
                last = line[:2]; value = line[3:].strip()
                if last in ('AU', 'AF'): current.setdefault(last, []).append(value)
                else: current[last] = value
            elif line.startswith('   ') and last:
                if last in ('AU', 'AF'): current[last].append(line.strip())
                else: current[last] += ' ' + line.strip()
        if current: records.append(current)
    else:
        raise ValueError('Unsupported bibliography format; expected native CNKI/WoS text')
    normalized = []
    mapping = {'title': 'Title', 'authors': 'Author', 'journal': 'Source', 'year': 'Year', 'abstract': 'Summary', 'doi': 'DOI', 'keywords': 'Keyword'} if format == 'cnki' else {'title': 'TI', 'authors': 'AU', 'journal': 'SO', 'year': 'PY', 'abstract': 'AB', 'doi': 'DI', 'keywords': 'DE'}
    for index, raw in enumerate(records):
        row = {key: raw.get(tag, '') for key, tag in mapping.items()}
        if isinstance(row['authors'], str): row['authors'] = [v.strip() for v in row['authors'].split(';') if v.strip()]
        if not row['year']:
            match = re.search(r'\d{4}', raw.get('PubTime', '')); row['year'] = match[0] if match else ''
        row.update(source_type=format, source_record=index + 1, raw=raw)
        normalized.append(row)
    if not normalized: raise ValueError('No bibliography records found')
    return {'format': format, 'records': normalized, 'warnings': [{'record': i + 1, 'code': 'missing_'+field} for i, r in enumerate(normalized) for field in ('title','abstract') if not r[field]], 'file_sha256': sha256(Path(path).read_bytes())}


def extract_document(path, exclusions=None, ocr_command=None, tessdata=None, ocr_language='eng'):
    """exclusions: [{page,start,end,reason}] using raw page character offsets.
    Exclusions are explicit reviewed selections; raw pages and exclusion text remain.
    Explicit local tessdata enables OCR on pages without a text layer.
    """
    path = Path(path)
    if path.name.lower().endswith('.source.md'):
        raise ValueError('Source-description sidecar is not a paper body')
    if ocr_command:
        raise ValueError('OCR execution is not configured; supply a provenance-labelled OCR Markdown derivative')
    digest = sha256(path.read_bytes()); pages = []; warnings = []; ocr_pages=[]
    if tessdata:
        if not re.fullmatch(r'[a-z_]+(?:\+[a-z_]+)*',ocr_language): raise ValueError('Invalid OCR language')
        for language in ocr_language.split('+'):
            if not (Path(tessdata)/(language+'.traineddata')).is_file(): raise ValueError('Missing OCR language data: '+language)
    if path.suffix.lower() == '.pdf':
        try:
            import pymupdf as fitz
        except ImportError as exc:
            raise RuntimeError('PDF extraction requires PyMuPDF') from exc
        with fitz.open(path) as pdf:
            for n, page in enumerate(pdf):
                # Blocks sorted vertically preserve paragraph geometry better than character concatenation.
                raw,layout = ordered_pdf_text(page)
                images = len(page.get_images())
                text_layer=bool(raw.strip())
                if not text_layer and tessdata:
                    textpage=page.get_textpage_ocr(language=ocr_language,dpi=200,full=True,tessdata=str(Path(tessdata).resolve()))
                    raw=page.get_text('text',textpage=textpage,sort=True); layout='local-tesseract-ocr'; ocr_pages.append(n+1)
                pages.append({'page': n + 1, 'text': raw, 'image_count': images, 'text_layer': text_layer,'layout':layout})
                if not raw.strip(): warnings.append({'page': n + 1, 'code': 'ocr_required'})
                elif images: warnings.append({'page': n + 1, 'code': 'text_layer_with_images_ocr_origin_unverified'})
        extraction = 'pdf_text_layer'
    elif path.suffix.lower() in ('.md', '.markdown', '.txt'):
        pages = [{'page': None, 'text': read_text(path), 'image_count': 0, 'text_layer': True}]
        extraction = 'text'
    else: raise ValueError('Expected PDF, Markdown, or plain text')
    evidence = []; segments = []; removed = []
    for page in pages:
        raw = page['text']
        spans = sorted([e for e in (exclusions or []) if e.get('page') == page['page']], key=lambda x: x['start'])
        previous = 0
        for e in spans:
            if not (previous <= e['start'] < e['end'] <= len(raw)) or not e.get('reason'):
                raise ValueError('Exclusion offsets overlap, are out of range, or lack a reason')
            previous = e['end']
        if len(re.findall(r'Abstract\s*[:：]', unicodedata.normalize('NFKC',raw), re.I)) > 1:
            warnings.append({'page': page['page'], 'code': 'multiple_abstracts_review_required'})
        allowed = []; previous = 0
        for e in spans:
            allowed.append((previous, e['start'])); removed.append({**e, 'text': raw[e['start']:e['end']]}); previous = e['end']
        allowed.append((previous, len(raw)))
        for a, b in allowed:
            segments.append(raw[a:b])
            for match in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', raw[a:b]):
                quote = match[0].strip()
                if not quote: continue
                start, end = a + match.start(), a + match.end()
                for chunk_start in range(start,end,1800):
                    chunk_end=min(chunk_start+1800,end); chunk=raw[chunk_start:chunk_end]
                    evidence.append({'id': 'ev-' + sha256(f'{digest}:{sha256(raw)}:{page["page"]}:{chunk_start}:{chunk_end}')[:16], 'file_sha256': digest, 'page_text_sha256':sha256(raw), 'page': page['page'], 'paragraph': len(evidence) + 1, 'start': chunk_start, 'end': chunk_end, 'text': chunk, 'sha256': sha256(chunk)})
    if not pages or not any(p['text'].strip() for p in pages):
        if path.suffix.lower()!='.pdf': raise ValueError('Empty text document')
    return {'title': path.stem, 'file_sha256': digest, 'extraction_version':'layout-bands-v2','text': '\n\n'.join(segments), 'pages': pages, 'evidence': evidence, 'warnings': warnings, 'extraction': extraction, 'ocr_executed': bool(ocr_pages), 'ocr_pages':ocr_pages,'ocr_language':ocr_language if ocr_pages else None,'ocr_data_hashes':{lang:sha256((Path(tessdata)/(lang+'.traineddata')).read_bytes()) for lang in ocr_language.split('+')} if ocr_pages else {}, 'exclusions': removed}


def match_bibliography(document, records):
    def normal(s): return re.sub(r'[^\w]', '', s).lower()
    title = normal(document.get('title', '')); body = normal(document.get('text', '')[:2000]); result = []
    for index, record in enumerate(records):
        candidate = normal(record.get('title', ''))
        if not candidate: continue
        similarity = SequenceMatcher(None, title, candidate).ratio()
        score = 1.0 if candidate in body and similarity >= .75 else similarity
        if score >= .65:
            result.append({'record_index': index, 'title': record['title'], 'score': round(score, 4), 'basis': 'title_in_source' if score == 1 and candidate in body else 'filename_title_similarity', 'adopted': False})
    return sorted(result, key=lambda r: -r['score'])
