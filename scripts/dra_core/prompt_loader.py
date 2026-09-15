from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
VARIABLE = re.compile(r'(?<!\{)\{([a-zA-Z_][a-zA-Z_0-9]*)\}(?!\})')


class PromptLoader:
    def __init__(self, workspace=None, package=None):
        self.package = Path(package or PACKAGE)
        self.workspace = Path(workspace) if workspace else None
        raw = json.loads((self.package / 'prompts/catalog.json').read_text(encoding='utf-8'))
        rows = raw.get('prompts', raw.get('slots', raw)) if isinstance(raw, dict) else raw
        self.catalog = rows if isinstance(rows, dict) else {row['id']: row for row in rows}
        if self.workspace and (self.workspace/'prompts/catalog.json').exists():
            for row in json.loads((self.workspace/'prompts/catalog.json').read_text(encoding='utf-8'))['prompts']:
                if not row['id'].startswith('custom.') or not re.fullmatch(r'[\w.-]+',row['id']): raise ValueError('Invalid custom prompt ID')
                self.catalog[row['id']]=row

    def load(self, slot, variables=None, override=None):
        meta = self.catalog[slot]
        rel = meta['path']
        path = self.package / rel
        if not path.exists() and not rel.startswith('prompts/'):
            path = self.package / 'prompts' / rel
        source = 'builtin'
        if self.workspace:
            local = self.workspace / 'prompts' / (slot + '.md')
            if local.exists():
                path, source = local, 'workspace'
        if override:
            path, source = Path(override), 'explicit'
        content = path.read_text(encoding='utf-8-sig')
        body = re.sub(r'\A---\r?\n.*?\r?\n---\r?\n', '', content, count=1, flags=re.S)
        if meta.get('unescape_double_braces'): body=body.replace('{{','{').replace('}}','}')
        if not body.strip():
            raise ValueError(f'Empty prompt: {slot}')
        required = set(VARIABLE.findall(body))
        declared = set(meta.get('variables', []))
        if required - declared:
            raise ValueError(f'Undeclared variables in {slot}: {sorted(required-declared)}')
        values = variables or {}
        if required - values.keys():
            raise ValueError(f'Missing variables in {slot}: {sorted(required-values.keys())}')
        rendered = VARIABLE.sub(lambda match: str(values[match.group(1)]), body)
        return rendered, {'id': slot, 'source': source, 'path': rel if source == 'builtin' else str(path), 'version': meta.get('version', 1), 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'rendered_sha256': hashlib.sha256(rendered.encode()).hexdigest(), 'upstream': meta.get('source')}

    def check(self):
        errors = []
        for slot, meta in self.catalog.items():
            try:
                self.load(slot, {name: 'CHECK' for name in meta.get('variables', [])})
            except (ValueError, OSError, KeyError) as e:
                errors.append({'slot': slot, 'error': str(e)})
        return {'count': len(self.catalog), 'errors': errors}
