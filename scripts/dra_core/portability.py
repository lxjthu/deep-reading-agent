"""Lossless local snapshots and quarantined website .dra imports.
Website tables/attachments are retained verbatim; no ORM or production writes.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from contextlib import contextmanager

FORMAT = 'deep-reading-local-1'
MAX_BYTES = 2 * 1024 ** 3


@contextmanager
def staging_directory(parent):
    parent=Path(parent).resolve(); stage=parent/('dra-stage-'+uuid.uuid4().hex)
    stage.mkdir()
    try: yield str(stage)
    finally:
        if stage.resolve().parent == parent and stage.name.startswith('dra-stage-'): shutil.rmtree(stage)


def _hash(data): return hashlib.sha256(data).hexdigest()


def _members(zf):
    seen = set(); total = 0
    for member in zf.infolist():
        name = member.filename.replace('\\', '/')
        parts = PurePosixPath(name).parts
        if not parts or name.startswith('/') or any(p in ('..', '.') or ':' in p for p in parts):
            raise ValueError('Unsafe archive path')
        if stat.S_ISLNK(member.external_attr >> 16): raise ValueError('Archive symlinks are forbidden')
        key = name.rstrip('/').casefold()
        if key in seen: raise ValueError('Duplicate archive path')
        seen.add(key); total += member.file_size
        if total > MAX_BYTES or len(seen) > 100000: raise ValueError('Archive exceeds extraction limit')
        if not member.is_dir(): yield member, name


def inspect_archive(path):
    with zipfile.ZipFile(path) as zf:
        members = list(_members(zf)); names = {n for _, n in members}
        if 'manifest.json' not in names: raise ValueError('Missing manifest.json')
        manifest = json.loads(zf.read('manifest.json'))
        local = manifest.get('format') == FORMAT
        if not local and 'format_version' not in manifest: raise ValueError('Unrecognized archive format')
        if not local and manifest['format_version'] != 1: raise ValueError('Unsupported website format_version')
        if local:
            for name, digest in manifest.get('files', {}).items():
                if name not in names or _hash(zf.read(name)) != digest: raise ValueError('Archive content hash mismatch: ' + name)
            if names - {'manifest.json'} != set(manifest.get('files', {})): raise ValueError('Unmanifested archive content')
        tables = {}
        for _, name in members:
            if not local and name.startswith('data/') and name.endswith('.json'):
                rows = json.loads(zf.read(name))
                if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows): raise ValueError('Invalid table: ' + name)
                tables[Path(name).stem] = len(rows)
        return {'kind': 'local' if local else 'website_dra', 'manifest': manifest, 'files': len(members) - 1, 'tables': tables, 'warnings': [] if local else ['Website import preserves raw fields and attachments in an isolated namespace; local projection is not a production database restore.', *manifest.get('errors', []), *manifest.get('missing_files', [])]}


def export_workspace(workspace, destination):
    workspace, destination = Path(workspace).resolve(), Path(destination).resolve()
    if not (workspace / 'workspace.json').is_file(): raise ValueError('Not a workspace: workspace.json missing')
    if destination.is_relative_to(workspace): raise ValueError('Export destination must be outside workspace')
    if destination.exists(): raise FileExistsError(destination)
    files = []
    for path in workspace.rglob('*'):
        if path.is_symlink(): raise ValueError('Workspace symlinks cannot be exported')
        if path.is_file() and path.name not in ('.lock','.write.lock') and not path.name.startswith('.env'):
            files.append((path, 'workspace/' + path.relative_to(workspace).as_posix()))
    manifest = {'format': FORMAT, 'schema_version': 1, 'files': {name: _hash(path.read_bytes()) for path, name in files}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as temp: temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
            for path, name in files: zf.write(path, name)
        inspect_archive(temporary); temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'completed', 'path': str(destination), 'files': len(files), 'format': FORMAT}


def import_archive(path, workspace):
    info = inspect_archive(path); workspace = Path(workspace).resolve()
    if workspace.exists() and any(workspace.iterdir()): raise ValueError('Import requires an empty destination; existing and edited workspaces are never overwritten')
    workspace.parent.mkdir(parents=True, exist_ok=True)
    with staging_directory(workspace.parent) as tmp:
        stage = Path(tmp)
        with zipfile.ZipFile(path) as zf:
            for member, name in _members(zf):
                if info['kind'] == 'local':
                    if name == 'manifest.json': continue
                    if not name.startswith('workspace/'): raise ValueError('Unexpected local archive root')
                    target = stage / name.removeprefix('workspace/')
                else: target = stage / 'imports' / 'website' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open('wb') as dst: shutil.copyfileobj(src, dst)
        if info['kind'] == 'website_dra':
            raw_root = stage / 'imports' / 'website'; maps = {}; projected = []
            from .prompt_loader import PACKAGE
            schema=json.loads((PACKAGE/'assets/website-schema.json').read_text(encoding='utf-8'))
            tables={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in (raw_root/'data').glob('*.json')}
            owners={str(r['owner_user_id']) for rows in tables.values() for r in rows if r.get('owner_user_id') is not None}
            if len(owners)>1: raise ValueError('Archive contains mixed user ownership; isolate one user export')
            for table in sorted((raw_root / 'data').glob('*.json')):
                rows = json.loads(table.read_text(encoding='utf-8'))
                maps[table.stem] = {str(r['id']): f'{table.stem}-{uuid.uuid4().hex}' for r in rows if r.get('id') is not None}
                if table.stem == 'bib_entries':
                    for row in rows:
                        metadata={**row,'authors':json.loads(row.get('authors_json') or '[]')}
                        projected.append({'entry_id': maps[table.stem].get(str(row.get('id')), uuid.uuid4().hex), 'title': row.get('title', ''), 'metadata': metadata,'tags':json.loads(row.get('user_tags_json') or '[]'),'notes':row.get('user_note'),'sources':[], 'migration_source': 'imports/website/data/bib_entries.json', 'source_id': row.get('id')})
            mapped=stage/'imports/mapped'; mapped.mkdir(parents=True)
            relation_warnings=[]
            for table,rows in tables.items():
                output=[]
                if table not in schema['tables']: relation_warnings.append({'table':table,'reason':'unknown table retained verbatim; relationships unverified'})
                for row in rows:
                    item=dict(row)
                    if row.get('id') is not None: item['id']=maps[table][str(row['id'])]
                    for field,target in schema['tables'].get(table,{}).get('foreign_keys',{}).items():
                        if row.get(field) is None: continue
                        target_table=target.split('.')[0]
                        if target_table=='users': item[field]='local-owner'; continue
                        if str(row[field]) in maps.get(target_table,{}): item[field]=maps[target_table][str(row[field])]
                        else: relation_warnings.append({'table':table,'id':row.get('id'),'field':field,'target':row[field],'reason':'unresolved reference preserved'})
                    output.append(item)
                (mapped/(table+'.json')).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
            # Build usable local source links while preserving all original files/tables.
            from .io_services import extract_document
            for entry in projected:
                row=entry['metadata']
                for field in ('source_file_id','markdown_source_file_id'):
                    fid=row.get(field)
                    candidates=[p for p in (raw_root/'files').glob('*') if p.stem==str(fid)] if fid else []
                    if len(candidates)==1 and candidates[0].suffix.lower() in ('.pdf','.md','.markdown'):
                        source=candidates[0]; doc=extract_document(source); doc.update(entry_id=entry['entry_id'],title=entry['title'])
                        folder=stage/'sources'/entry['entry_id']; folder.mkdir(parents=True,exist_ok=True)
                        target=folder/(doc['file_sha256']+'.json'); target.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
                        entry['sources'].append({'path':source.relative_to(stage).as_posix(),'extracted':target.relative_to(stage).as_posix(),'sha256':doc['file_sha256']})
                    elif fid: relation_warnings.append({'entry_id':entry['entry_id'],'field':field,'reason':'source attachment absent or unsupported; raw preserved'})
            (stage / 'library').mkdir(exist_ok=True)
            (stage/'library/index.json').write_text(json.dumps({'entries':projected},ensure_ascii=False,indent=2),encoding='utf-8')
            (stage / 'library' / 'website-projection.json').write_text(json.dumps(projected, ensure_ascii=False, indent=2), encoding='utf-8')
            (raw_root / 'id-map.json').write_text(json.dumps(maps, ensure_ascii=False, indent=2), encoding='utf-8')
            (mapped/'migration-checks.json').write_text(json.dumps({'warnings':relation_warnings,'embedded_json_ids':'preserved in original JSON fields; not automatically rewritten','schema_version':info['manifest'].get('schema_version')},ensure_ascii=False,indent=2),encoding='utf-8')
            info['warnings'].extend(relation_warnings)
            (stage / 'workspace.json').write_text(json.dumps({'schema_version': 1, 'migration': {'kind': 'website_dra', 'projection': 'library/website-projection.json', 'relations': 'Original foreign keys are preserved in raw namespace; id-map provides explicit correspondence. Projection adoption requires review.'}}), encoding='utf-8')
        workspace.mkdir(exist_ok=True)
        for child in stage.iterdir(): shutil.move(str(child), str(workspace / child.name))
    return {'status': 'completed', 'workspace': str(workspace), **info}
