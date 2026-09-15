"""Rebuildable, portable, explicitly selected offline reading snapshots."""
from __future__ import annotations
from functools import partial
from html import escape as esc
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import base64
import re
import shutil
import time
import uuid
from .workspace import Workspace, atomic_json, digest
from .reader_render import render

ASSETS = Path(__file__).resolve().parents[2]/'assets/reader'
STATUS = {'completed':'已生成，内容待验收','failed':'执行失败','waiting_for_native':'等待原生回答','running':'执行中','cancelled':'已取消','candidate':'AI 清洗候选','adopted':'已采纳清洗稿','needs_review':'需要核查','validated':'校验通过，尚未采纳'}

def _json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}

def _page(title, body):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' data:; font-src \'self\'; connect-src \'none\'; object-src \'none\'; base-uri \'none\'"><title>'+esc(title)+'</title><link rel="stylesheet" href="assets/reader.css"><link rel="stylesheet" href="assets/katex/katex.min.css"><script defer src="assets/katex/katex.min.js"></script><script defer src="assets/reader.js"></script></head><body class="dra-reader"><main><header><a href="index.html">文献首页</a><span>本地阅读快照</span></header><h1>'+esc(title)+'</h1>'+body+'</main></body></html>'

def build(workspace, entry_ids=None, include_pdf=False):
    workspace = workspace if isinstance(workspace,Workspace) else Workspace(workspace)
    entries = workspace.entries()
    if entry_ids:
        missing=set(entry_ids)-{e['entry_id'] for e in entries}
        if missing: raise ValueError('Unknown entry IDs: '+', '.join(sorted(missing)))
        entries=[e for e in entries if e['entry_id'] in entry_ids]
    build_id=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    out=workspace.path('reader/'+build_id);out.mkdir(parents=True)
    shutil.copytree(ASSETS,out/'assets')
    # Prefer source titles over export filenames when bibliographic metadata is absent.
    entries=[dict(e) for e in entries]
    for entry in entries:
        if entry.get('metadata',{}).get('title'):
            entry['title']=entry['metadata']['title']
        else:
            for source in entry.get('sources',[]):
                if source.get('markdown'):
                    text=workspace.path(source['markdown']).read_text(encoding='utf-8-sig')
                    title=re.search(r'^#\s+(.+)$',text,re.M)
                    if title:
                        entry['title']=title[1].strip();break
    names={e['entry_id']:'entry-'+digest(e['entry_id'])[:16]+'.html' for e in entries}
    warnings=[];inputs={}; runs=[]
    for path in workspace.root.glob('runs/*/state.json'):
        state=_json(workspace.path(path.relative_to(workspace.root)))
        plan=_json(workspace.path(path.parent.relative_to(workspace.root)/'plan.json'))
        members=[d['entry_id'] for d in plan.get('documents',[]) if 'entry_id' in d]
        # Never leak unselected collection members through a partial selection.
        if members and all(e in names for e in members): runs.append((state,plan,path.parent))
    artifacts={}
    for state,plan,folder in runs:
        for artifact in state.get('artifacts',[]):
            artifact_path=artifact.get('path') or artifact.get('clean_path')
            if artifact_path: artifacts[str(Path(artifact_path))]=(state,plan,folder)

    def load(path):
        path=workspace.path(path);inputs[str(path.relative_to(workspace.root))]=digest(path.read_bytes())
        return path.read_text(encoding='utf-8-sig')

    def panel(text, title, path=None, detail=None, role='reading'):
        key='panel-'+digest(str(path)+title+role)[:16]
        image_map=None; image_root=Path(path).parent if path else None
        if path:
            manifest=_json(Path(path).parent/'manifest.json')
            if manifest.get('parent_markdown'):
                parent=workspace.path(manifest['parent_markdown']); manifest=_json(parent.parent/'manifest.json'); image_root=parent.parent
            if manifest.get('images'):
                image_map={}
                for item in manifest['images']:
                    rel=item['path']; candidate=image_root/rel
                    if candidate.is_symlink() or any(p.is_symlink() for p in candidate.parents):continue
                    if not candidate.resolve().is_relative_to(image_root.resolve()):continue
                    image_map[rel]=candidate
                    if rel.startswith('original/'):image_map[rel[len('original/'):]]=candidate
        rendered=render(text,path,out,image_root,namespace=key,image_map=image_map);warnings.extend(rendered['warnings'])
        download='document-'+uuid.uuid4().hex[:12]+'.md';(out/download).write_text(text,encoding='utf-8')
        return key,title,'<section data-panel id="'+key+'"><a download data-download64="'+base64.b64encode(text.encode('utf-8')).decode('ascii')+'" href="'+download+'">下载 MD</a><details open><summary>章节目录</summary><nav>'+rendered['toc']+'</nav></details>'+('<details><summary>来源与处理记录</summary><pre>'+esc(json.dumps(detail,ensure_ascii=False,indent=2))+'</pre></details>' if detail else '')+'<article>'+rendered['html']+'</article></section>'

    def controls(panels):
        return '<div class="controls"><label>阅读版本 <select data-versions>'+''.join('<option value="'+k+'">'+esc(t)+'</option>' for k,t,_ in panels)+'</select></label><button data-print>打印</button><label>字号 <input data-font type="range" min="14" max="28" value="18"></label><label>行宽 <input data-width type="range" min="600" max="1500" value="1000"></label><span>页内查找：Ctrl+F / ⌘F</span></div>'

    def evidence(plan, folder):
        items=[]
        for doc in plan.get('documents',[]):
            for ev in doc.get('evidence',[]):
                items.append((ev.get('id',ev.get('evidence_id','')),ev.get('text',ev.get('quote','')),{'source_version':doc.get('source_version_id',doc.get('file_sha256','未知')),'物理页':ev.get('page'),'印刷页':ev.get('printed_page'),'字符范围':[ev.get('start'),ev.get('end')],'匹配状态':'原始提取位置；未等同 PDF 人工核验'}))
        result=_json(workspace.path(folder.relative_to(workspace.root)/'result.json'))
        for step in result.get('steps',{}).values():
            for n,ev in enumerate(step.get('source_evidence',[])):
                items.append((str(ev.get('id',ev.get('evidence_id',n+1))),ev.get('quote',ev.get('text','')),{'匹配状态':'已在冻结原文定位' if ev.get('locations') else '未定位','locations':ev.get('locations',[])}))
        return '<details><summary>证据与冻结来源（'+str(len(items))+'）</summary>'+''.join('<details class="evidence"><summary>'+esc(str(k))+'</summary><blockquote>'+esc(q)+'</blockquote><pre>'+esc(json.dumps(d,ensure_ascii=False,indent=2))+'</pre></details>' for k,q,d in items)+'</details>'

    rows=[];all_types=set();collections=[]
    for entry in entries:
        eid=entry['entry_id'];panels=[];extras=[];types=set();seen=set()
        for n,source in enumerate(entry.get('sources',[])):
            for field in ('markdown',):
                if source.get(field):
                    path=workspace.path(source[field])
                    if path.is_file(): panels.append(panel(load(source[field]),'原文 '+str(n+1),path,source));seen.add(path)
            if source.get('path'):
                path=workspace.path(source['path'])
                if include_pdf and path.suffix.lower()=='.pdf' and path.is_file():
                    dest='source-'+digest(path.read_bytes())[:20]+'.pdf';shutil.copyfile(path,out/dest);extras.append('<p><a href="'+dest+'#page=1">原始 PDF（物理页从 1 开始）</a></p>')
        for manifest_path in workspace.path('sources/'+eid+'/versions').glob('*/manifest.json'):
            manifest=_json(workspace.path(manifest_path.relative_to(workspace.root)))
            for field in ('raw_path','clean_path','markdown_path','text_path'):
                if manifest.get(field):
                    path=(manifest_path.parent/manifest[field]).resolve()
                    if not path.is_relative_to(manifest_path.parent.resolve()): raise ValueError('Version path escapes version directory')
                    if path.is_file() and path not in seen:
                        label=STATUS.get(manifest.get('status'),manifest.get('status','来源版本'))
                        validation=_json(manifest_path.parent/manifest.get('validation_path','validation.json'))
                        if validation and not validation.get('passed'):label='清洗候选，需要核查'
                        panels.append(panel(load(path.relative_to(workspace.root)),label+' · 版本 '+str(len(panels)+1),path,manifest));seen.add(path)
            for default,field in [('changes.json','changes_path'),('source-map.json','mapping_path'),('validation.json','validation_path')]:
                rel=manifest.get(field,default);path=(manifest_path.parent/rel).resolve()
                if not path.is_relative_to(manifest_path.parent.resolve()):raise ValueError('Mapping path escapes version directory')
                if path.is_file():extras.append('<details><summary>'+esc(default+' · '+manifest.get('version_id',manifest_path.parent.name))+'</summary><pre>'+esc(load(path.relative_to(workspace.root)))+'</pre></details>')
        for path in workspace.path('artifacts/'+eid).glob('*.md'):
            meta=_json(path.with_suffix('.md.json'));kind=meta.get('kind','报告');types.add(kind)
            context=artifacts.get(str(path.relative_to(workspace.root)))
            label=('人工稿' if meta.get('origin')=='user' else 'AI 候选，内容待验收')+' · '+kind
            panels.append(panel(load(path.relative_to(workspace.root)),label,path,meta))
            if context:extras.append(evidence(context[1],context[2]))
        for state,plan,folder in runs:
            if eid in [d['entry_id'] for d in plan.get('documents',[])]:extras.append('<p>'+esc(str(state.get('task',''))+'：'+STATUS.get(state.get('status'),str(state.get('status','未知'))))+'</p>')
        for manifest_path in workspace.path('sources/'+eid+'/versions').glob('*/manifest.json'):
            manifest=_json(manifest_path)
            if not manifest.get('parent_markdown'):continue
            parent=workspace.path(manifest['parent_markdown'])
            clean=workspace.path((manifest_path.parent/manifest.get('markdown_path','clean.md')).relative_to(workspace.root))
            if parent.is_file() and clean.is_file():
                pair=[panel(load(p.relative_to(workspace.root)),label,p,manifest,role='compare-'+manifest_path.parent.name) for p,label in [(parent,'冻结原稿'),(clean,'清洗稿')]]
                extras.append('<details><summary>原稿与清洗稿对照 · '+esc(manifest_path.parent.name)+'</summary><div class="compare">'+''.join('<section><h3>'+esc(t)+'</h3>'+h.replace('data-panel','data-comparison')+'</section>' for _,t,h in pair)+'</div></details>')
        if not panels:extras.append('<p class="notice">暂无全文或报告；可导入 PDF / Markdown 后重新构建。</p>')
        extras.insert(0,'<p class="notice">此页为构建时快照，后续研究或人工修改需重新构建。'+('' if include_pdf else '此快照未包含 PDF。')+'</p>')
        body=controls(panels)+''.join(h for _,_,h in panels)+''.join(extras)
        (out/names[eid]).write_text(_page(entry.get('title') or eid,body),encoding='utf-8')
        metadata=entry.get('metadata',{});authors=metadata.get('authors',[]);authors='；'.join(authors) if isinstance(authors,list) else str(authors)
        types.add('全文' if panels else '仅题录');all_types.update(types)
        rows.append('<div class="entry" data-entry data-types="'+esc(' '.join(types),quote=True)+'"><h2><a href="'+names[eid]+'">'+esc(entry.get('title') or eid)+'</a></h2><p>'+esc(authors+' '+str(metadata.get('year',''))+' · '+' / '.join(types)+' · '+', '.join(entry.get('tags',[])))+'</p></div>')
    for state,plan,folder in runs:
        members=[d['entry_id'] for d in plan.get('documents',[])]
        if len(members)<2:continue
        panels=[]
        for artifact in state.get('artifacts',[]):
            artifact_path=artifact.get('path') or artifact.get('clean_path')
            if not artifact_path:continue
            path=workspace.path(artifact_path)
            if path.suffix=='.md' and path.is_file():panels.append(panel(load(artifact_path),str(state.get('task','集合报告')),path,artifact))
        name='collection-'+digest(folder.name)[:16]+'.html';title=str(state.get('task','集合报告'))+' · '+folder.name
        body='<p>'+esc(STATUS.get(state.get('status'),str(state.get('status'))))+'</p><ul>'+''.join('<li><a href="'+names[e]+'">'+esc(next(x.get('title',e) for x in entries if x['entry_id']==e))+'</a></li>' for e in members)+'</ul>'+controls(panels)+''.join(h for _,_,h in panels)+evidence(plan,folder)
        (out/name).write_text(_page(title,body),encoding='utf-8');collections.append('<li><a href="'+name+'">'+esc(title)+'</a></li>')
    body='<p class="notice">构建时间 '+esc(build_id)+'。离线快照不会自动跟随工作区变化；新增内容后请重新构建。</p><div class="controls"><input data-search aria-label="搜索文献" placeholder="搜索标题、作者、年份、标签"><select data-filter aria-label="报告类型"><option value="">全部类型</option>'+''.join('<option>'+esc(t)+'</option>' for t in sorted(all_types))+'</select></div>'+''.join(rows)+'<div class="controls"><button data-prev>上一页</button><span data-page></span><button data-next>下一页</button></div><h2>集合报告</h2><ul>'+''.join(collections)+'</ul>'
    (out/'index.html').write_text(_page('研究文献阅读台',body),encoding='utf-8')
    atomic_json(out/'manifest.json',{'build_id':build_id,'entry_ids':list(names),'include_pdf':include_pdf,'source_hashes':inputs,'warnings':warnings,'status':'snapshot_requires_content_review'})
    atomic_json(workspace.path('reader/latest.json'),{'build_id':build_id})
    return {'build_id':build_id,'path':str(out/'index.html'),'entry_count':len(entries),'collection_count':len(collections),'warnings':warnings}

def serve(workspace, build_id=None, port=0):
    workspace=workspace if isinstance(workspace,Workspace) else Workspace(workspace)
    build_id=build_id or _json(workspace.path('reader/latest.json')).get('build_id')
    if not build_id or Path(build_id).name!=build_id:raise ValueError('Invalid reader build ID')
    root=workspace.path('reader/'+build_id)
    if not (root/'index.html').is_file() or not (root/'manifest.json').is_file():raise ValueError('Reader build not found')
    # Reject symlinks even inside a generated directory: SimpleHTTPRequestHandler follows them.
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('Reader build contains symbolic links')
    class Handler(SimpleHTTPRequestHandler):
        def list_directory(self,path):self.send_error(403);return None
        def translate_path(self,path):
            candidate=Path(super().translate_path(path)).resolve()
            return str(candidate) if candidate.is_relative_to(root.resolve()) else str(root/'__denied__')
    server=ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,directory=str(root)))
    print('本地阅读预览：http://127.0.0.1:'+str(server.server_port)+'/index.html （Ctrl+C 停止）',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
