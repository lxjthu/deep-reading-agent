"""Immutable local Markdown source versions and explicit adoption."""
from __future__ import annotations
import json
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .workspace import atomic_json, digest


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError('Invalid local identifier')
    return value


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _readable_document(doc, text, version_id, markdown, mapping=None):
    """Build fresh offsets in the selected Markdown, keeping provenance separate."""
    mapping = mapping or []
    page = {'page': None, 'printed_page': None, 'start': 0, 'end': len(text), 'text': text}
    evidence = []
    for match in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', text):
        for start in range(match.start(), match.end(), 1800):
            end = min(start + 1800, match.end())
            original = [dict(r) for m in mapping if m['clean_start'] < end and m['clean_end'] > start for r in m.get('source_ranges', [])]
            clean = {'source_file': markdown, 'source_version_id': version_id, 'start': start, 'end': end,
                     'match_method': 'cleaned_markdown_exact', 'physical_page': None}
            evidence.append({'id': 'ev-' + digest(f'{version_id}:{digest(text.encode())}:{start}:{end}'.encode())[:16],
                'text': text[start:end], 'page': None, 'start': start, 'end': end, 'global_start': start, 'global_end': end,
                'sha256': digest(text[start:end].encode()), 'source_file': markdown, 'source_version_id': version_id,
                'source_ranges': [clean] + original, 'original_source_ranges': original,
                'citation_basis': 'selected_markdown_not_pdf_verbatim'})
    return {**doc, 'text': text, 'pages': [page], 'evidence': evidence, 'source_map': mapping,
            'file_sha256': digest(text.encode()), 'citation_basis': 'selected_markdown_not_pdf_verbatim'}


def resolve_document(workspace, entry):
    """Resolve an explicitly adopted version, otherwise retain legacy source selection."""
    if isinstance(entry, str): entry = workspace.get(entry)
    active = entry.get('active_source_version')
    if active:
        folder = workspace.path(f'sources/{_id(entry["entry_id"])}/versions/{_id(active)}')
        manifest = _read(folder / 'manifest.json')
        md = folder / manifest.get('markdown_path', 'clean.md')
        md = workspace.path(md.relative_to(workspace.root))
        doc = _read(workspace.path((folder / manifest.get('document_path', 'document.json')).relative_to(workspace.root)))
        selected_text = md.read_text(encoding='utf-8')
        if selected_text != doc.get('text'):
            doc = _readable_document(doc, selected_text, active, md.relative_to(workspace.root).as_posix())
            doc['page_mapping_status'] = 'invalidated_by_manual_edit'
        doc.update(text=selected_text, source_version_id=active,
                   source_markdown=md.relative_to(workspace.root).as_posix(),
                   source_manifest=(folder / 'manifest.json').relative_to(workspace.root).as_posix())
    elif entry.get('sources'):
        src = entry['sources'][-1]
        doc = _read(workspace.path(src['extracted']))
        md = workspace.path(src['markdown']) if src.get('markdown') else None
        if md:
            selected_text = md.read_text(encoding='utf-8')
            if selected_text != doc.get('text'):
                doc = _readable_document(doc, selected_text, src.get('version_id', src.get('extraction_id')), src.get('markdown'))
                doc['page_mapping_status'] = 'invalidated_by_manual_edit'
        doc.update(source_version_id=src.get('version_id', src.get('extraction_id', src.get('sha256'))),
                   source_markdown=src.get('markdown'), source_manifest=src.get('manifest'))
    else:
        doc = {'text': entry.get('metadata', {}).get('abstract', ''), 'evidence': [], 'pages': []}
    doc.update(entry_id=entry['entry_id'], title=entry['title'], metadata=entry.get('metadata', {}))
    doc['source_sha256'] = digest(doc['text'].encode('utf-8'))
    return doc


def import_markdown(workspace, input, entry_id, source_url=None):
    entry_id = _id(entry_id)
    workspace.get(entry_id)
    source = Path(input).absolute()
    if source.is_symlink(): raise ValueError('Input symlinks are forbidden')
    source = source.resolve()
    root = source if source.is_dir() else source.parent
    files = list(source.rglob('*')) if source.is_dir() else [source]
    if any(p.is_symlink() for p in files): raise ValueError('Input symlinks are forbidden')
    mds = [p for p in files if p.is_file() and p.suffix.lower() in ('.md', '.markdown') and not p.name.endswith('.source.md')]
    if not mds: raise ValueError('No Markdown paper found')
    numbered = []
    for p in mds:
        match = re.fullmatch(r'(?:page[_ -]?)?(\d+)', p.stem, re.I)
        numbered.append(int(match[1]) if match else None)
    if len(mds) > 1 and (None in numbered or len(set(numbered)) != len(numbered)):
        raise ValueError('Ambiguous page order: provide uniquely numbered page_N Markdown files')
    explicit = len(mds) > 1 or numbered[0] is not None
    pairs = sorted(zip(numbered, mds), key=lambda v: v[0] or 0)
    warnings = []
    if explicit:
        nums = [n for n, _ in pairs]
        missing = sorted(set(range(1, max(nums) + 1)) - set(nums)) if max(nums) < 100000 else []
        if 0 in nums: raise ValueError('Physical pages start at 1')
        if missing: warnings.append({'code': 'missing_pages', 'pages': missing})
    raw_files = []; images = {}; segments = []; pages = []; offset = 0
    for number, path in pairs:
        raw = path.read_bytes()
        encoding = 'utf-8-sig'
        try: decoded = raw.decode(encoding)
        except UnicodeDecodeError:
            encoding = 'gb18030'; decoded = raw.decode(encoding)
        text = decoded.replace('\r\n', '\n').replace('\r', '\n')
        relative = path.relative_to(root).as_posix()
        raw_files.append({'path': 'original/' + relative, 'sha256': digest(raw), 'encoding': encoding,
                          'normalization': 'decode then CRLF/CR to LF', 'normalized_sha256': digest(text.encode())})
        pages.append({'page': number if explicit else None, 'printed_page': None, 'start': offset,
                      'end': offset + len(text), 'text': text, 'source_file': 'original/' + relative})
        segments.append(text); offset += len(text) + 2
        refs = re.findall(r'!\[[^\]]*\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)', text)
        refs += re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)', text, re.I)
        for ref in refs:
            parsed = urlsplit(ref)
            if parsed.scheme or parsed.netloc:
                warnings.append({'code': 'external_image_not_copied', 'reference': ref}); continue
            relative_ref = Path(unquote(parsed.path))
            candidate = path.parent / relative_ref
            resolved = candidate.resolve()
            if candidate.is_symlink() or not resolved.is_relative_to(root) or relative_ref.is_absolute():
                raise ValueError('Image path escapes selected material')
            if resolved.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'):
                warnings.append({'code': 'unsupported_image', 'reference': ref}); continue
            if resolved.is_file(): images[resolved.relative_to(root).as_posix()] = resolved
            else: warnings.append({'code': 'missing_image', 'reference': ref})
    text = '\n\n'.join(segments)
    if not text.strip(): raise ValueError('Empty Markdown')
    if len({item['sha256'] for item in raw_files}) != len(raw_files): warnings.append({'code': 'duplicate_page_content'})
    version_id = 'raw-' + digest({'files': raw_files, 'images': {k: digest(v.read_bytes()) for k,v in images.items()}, 'url': source_url})[:24]
    folder = workspace.path(f'sources/{entry_id}/versions/{version_id}')
    with workspace.lock():
        entry = workspace.get(entry_id)
        if (folder / 'manifest.json').exists(): return {'status': 'duplicate', 'entry_id': entry_id, 'version_id': version_id, 'warnings': warnings}
        folder.mkdir(parents=True, exist_ok=True)
        for _, path in pairs:
            target = folder / 'original' / path.relative_to(root); target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        for name, path in images.items():
            target = folder / 'original' / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        (folder / 'raw.md').write_text(text, encoding='utf-8', newline='\n')
        evidence = []
        for page in pages:
            for match in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', page['text']):
                for start in range(match.start(), match.end(), 1800):
                    end = min(start + 1800, match.end()); quote = page['text'][start:end]
                    evidence.append({'id': 'ev-' + digest(f'{version_id}:{page["source_file"]}:{start}:{end}'.encode())[:16], 'text': quote, 'page': page['page'], 'start': start, 'end': end, 'sha256': digest(quote.encode()), 'source_file': page['source_file'], 'source_version_id': version_id, 'global_start': page['start'] + start, 'global_end': page['start'] + end})
        doc = {'entry_id': entry_id, 'title': entry['title'], 'text': text, 'pages': pages, 'evidence': evidence,
               'file_sha256': digest(text.encode()), 'warnings': warnings, 'extraction': 'external_ocr_markdown', 'page_mapping_status': 'explicit_export' if explicit else 'unknown'}
        atomic_json(folder / 'document.json', doc)
        manifest = {'schema_version': 1, 'version_id': version_id, 'parent_version_id': None,
                    'source_kind': 'external_ocr_markdown', 'raw_sha256': raw_files[0]['sha256'] if len(raw_files)==1 else digest(raw_files),
                    'normalized_sha256': digest(text.encode()), 'clean_sha256': None, 'original_pdf_sha256': next((s['sha256'] for s in reversed(entry.get('sources', [])) if s.get('path','').lower().endswith('.pdf')), None),
                    'external_source': {'url': source_url, 'provider_version': None, 'export_time': None, 'declared_by': 'user'},
                    'page_mapping_status': 'explicit_export' if explicit else 'unknown', 'status': 'original',
                    'markdown_path': 'raw.md', 'document_path': 'document.json', 'raw_files': raw_files,
                    'images': [{'path': 'original/'+k, 'sha256': digest(v.read_bytes())} for k,v in images.items()], 'warnings': warnings}
        atomic_json(folder / 'manifest.json', manifest)
        rel = folder.relative_to(workspace.root).as_posix()
        entry.setdefault('sources', []).append({'path': rel+'/raw.md', 'markdown': rel+'/raw.md', 'extracted': rel+'/document.json',
                                                'manifest': rel+'/manifest.json', 'sha256': manifest['raw_sha256'], 'version_id': version_id})
        entries = [e for e in workspace.entries() if e['entry_id'] != entry_id] + [entry]
        atomic_json(workspace.path('library/index.json'), {'entries': entries})
    return {'status': 'completed', 'entry_id': entry_id, 'version_id': version_id, 'manifest_path': rel+'/manifest.json', 'warnings': warnings}


def persist_candidate(workspace, plan, result, run_id):
    run_id = _id(run_id); doc = plan['documents'][0]; entry_id = _id(doc['entry_id'])
    cleanup = result['cleanup']; text = cleanup['text']; validation = cleanup['validation']
    version_id = 'clean-' + run_id
    folder = workspace.path(f'sources/{entry_id}/versions/{version_id}')
    sha = digest(text.encode('utf-8'))
    with workspace.lock():
        if (folder / 'manifest.json').exists():
            existing = _read(folder / 'manifest.json')
            if existing['clean_sha256'] != sha or digest((folder/'clean.md').read_bytes()) != sha:
                raise ValueError('Candidate already exists with different or edited content')
            return {'version_id': version_id, 'manifest_path': (folder/'manifest.json').relative_to(workspace.root).as_posix(), 'clean_path': (folder/'clean.md').relative_to(workspace.root).as_posix(), 'status': existing['status']}
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'clean.md').write_text(text, encoding='utf-8', newline='\n')
        for name, value in [('changes', cleanup['changes']), ('source-map', cleanup['source_map']), ('validation', validation)]: atomic_json(folder/(name+'.json'), value)
        clean_doc = _readable_document(doc, text, version_id, (folder/'clean.md').relative_to(workspace.root).as_posix(), cleanup['source_map'])
        clean_doc['source_kind'] = 'cleaned_markdown'
        atomic_json(folder/'document.json', clean_doc)
        status = 'candidate' if validation.get('passed') is True and validation.get('model_reviewed') is True and not validation.get('unresolved') else 'needs_review'
        manifest = {'schema_version': 1, 'version_id': version_id, 'run_id': run_id, 'entry_id': entry_id,
                    'parent_version_id': doc.get('source_version_id'), 'parent_sha256': doc['source_sha256'],
                    'parent_markdown': doc.get('source_markdown'), 'source_kind': 'cleaned_markdown', 'raw_sha256': doc['source_sha256'],
                    'clean_sha256': sha, 'status': status, 'markdown_path': 'clean.md', 'document_path': 'document.json',
                    'mapping_path': 'source-map.json', 'changes_path': 'changes.json', 'validation_path': 'validation.json', 'files': {name: digest((folder/name).read_bytes()) for name in ('clean.md','changes.json','source-map.json','validation.json','document.json')}}
        atomic_json(folder/'manifest.json', manifest)
    return {'version_id': version_id, 'manifest_path': (folder/'manifest.json').relative_to(workspace.root).as_posix(), 'clean_path': (folder/'clean.md').relative_to(workspace.root).as_posix(), 'status': status}


def adopt(workspace, run_id):
    run_id = _id(run_id)
    with workspace.lock():
        matches = list(workspace.path('sources').glob(f'*/versions/clean-{run_id}/manifest.json'))
        if len(matches) != 1: raise ValueError('Expected exactly one cleanup candidate for run')
        path = workspace.path(matches[0].relative_to(workspace.root)); manifest = _read(path); folder = path.parent
        entry = workspace.get(manifest['entry_id']); current = resolve_document(workspace, entry)
        for name, expected in manifest.get('files', {}).items():
            if name not in ('clean.md','changes.json','source-map.json','validation.json','document.json') or digest((folder/name).read_bytes()) != expected:
                raise ValueError('Candidate validation or mapping files have been edited')
        if digest((folder/'clean.md').read_bytes()) != manifest['clean_sha256']: raise ValueError('Candidate has been edited')
        if entry.get('active_source_version') == manifest['version_id']:
            return {'status': 'adopted', 'entry_id': entry['entry_id'], 'version_id': manifest['version_id']}
        validation = _read(folder/'validation.json')
        if validation.get('model_reviewed') is not True or not (validation.get('passed') is True or validation.get('valid') is True or validation.get('status') == 'passed') or validation.get('unresolved'):
            raise ValueError('Cleanup validation requires review; candidate cannot be adopted')
        if current.get('source_version_id') != manifest['parent_version_id'] or current['source_sha256'] != manifest['parent_sha256']:
            raise ValueError('Parent source changed; refusing stale candidate adoption')
        entry['active_source_version'] = manifest['version_id']
        manifest['status'] = 'adopted'; atomic_json(path, manifest)
        atomic_json(workspace.path('library/index.json'), {'entries': [e for e in workspace.entries() if e['entry_id'] != entry['entry_id']] + [entry]})
    return {'status': 'adopted', 'entry_id': entry['entry_id'], 'version_id': manifest['version_id']}




def inspect_markdown(workspace, entry_id):
    """Return deterministic structure diagnostics plus import provenance warnings."""
    from .markdown_cleanup import inspect_document
    doc = resolve_document(workspace, entry_id)
    result = inspect_document(doc)
    result['source_version_id'] = doc.get('source_version_id')
    result['source_sha256'] = doc['source_sha256']
    result['import_warnings'] = doc.get('warnings', [])
    if doc.get('source_manifest'):
        manifest = _read(workspace.path(doc['source_manifest']))
        result['page_mapping_status'] = doc.get('page_mapping_status', manifest.get('page_mapping_status', 'unknown'))
        result['source_files_intact'] = all(digest(workspace.path((workspace.path(doc['source_manifest']).parent / f['path']).relative_to(workspace.root)).read_bytes()) == f['sha256'] for f in manifest.get('raw_files', []))
    return result
