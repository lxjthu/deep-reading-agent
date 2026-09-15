from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ('library', 'sources', 'prompts', 'runs', 'artifacts'):
            (self.root / name).mkdir(exist_ok=True)
        with self.lock():
            if not (self.root / 'workspace.json').exists():
                atomic_json(self.root / 'workspace.json', {'schema_version': 1, 'workspace_id': uuid.uuid4().hex})
            if not (self.root / 'library/index.json').exists():
                atomic_json(self.root / 'library/index.json', {'entries': []})

    @contextmanager
    def lock(self, timeout=10):
        path = self.root / '.write.lock'
        started = time.monotonic()
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() - started >= timeout:
                    raise RuntimeError('Workspace busy; inspect .write.lock owner before recovering a stale lock')
                time.sleep(.05)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    def path(self, relative):
        result = (self.root / relative).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError('Path escapes workspace')
        return result

    def entries(self):
        return json.loads((self.root / 'library/index.json').read_text(encoding='utf-8'))['entries']

    def get(self, entry_id):
        return next(e for e in self.entries() if e['entry_id'] == entry_id)

    def update(self, entry):
        with self.lock():
            entries = self.entries()
            entries = [e for e in entries if e['entry_id'] != entry['entry_id']] + [entry]
            atomic_json(self.root / 'library/index.json', {'entries': entries})
        return entry

    def artifact(self, entry_id, kind, content, suffix='.md', origin='ai'):
        name = f'{kind}-{time.time_ns()}-{uuid.uuid4().hex[:6]}{suffix}'
        folder = self.path(f'artifacts/{entry_id}')
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        with path.open('x', encoding='utf-8') as f:
            f.write(content)
        meta = {'path': str(path.relative_to(self.root)), 'sha256': digest(path.read_bytes()), 'origin': origin, 'kind': kind}
        atomic_json(path.with_suffix(path.suffix + '.json'), meta)
        return meta
