"""Offline adapter for the online DimNavigation / AnswerCard comparison view."""
from html import escape as esc
from pathlib import Path
import json
import re
from .workspace import Workspace, digest
from .reader_render import render


def mode_label(mode):
    return {'read-quant':'定量七步','read-qual':'定性四步','read-long':'长文本精读'}.get(mode,mode)


def reading_files(workspace, eid):
    result=[]
    for path in sorted(workspace.path('artifacts/'+eid).glob('*.md')):
        meta_path=path.with_suffix('.md.json')
        meta=json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.is_file() else {}
        kind=meta.get('kind','')
        if kind.startswith(('read-', 'read.', 'reading_')):
            result.append((path,meta))
    return result


def find(workspace, query):
    workspace=workspace if isinstance(workspace,Workspace) else Workspace(workspace)
    terms=query.casefold().split()
    matches=[]
    for entry in workspace.entries():
        fields=json.dumps([entry.get('title',''),entry.get('metadata',{}),entry.get('tags',[])],ensure_ascii=False).casefold()
        if terms and not all(t in fields for t in terms):continue
        reports=reading_files(workspace,entry['entry_id'])
        matches.append({'entry_id':entry['entry_id'],'title':entry.get('metadata',{}).get('title') or entry.get('title'), 'reading_reports':len(reports)})
    return {'query':query,'matches':matches,'count':len(matches),'match_scope':'title_metadata_tags; all query terms required'}


def sections(text):
    # Keep modes separate in the UI. Match literal second-level headings only;
    # step_1 in a quantitative report is not equated with a qualitative step_1.
    lines=text.splitlines(keepends=True); starts=[]; fence=None
    for n,line in enumerate(lines):
        f=re.match(r'^\s{0,3}(`{3,}|~{3,})',line)
        if f:
            token=f[1]
            if fence is None:fence=token
            elif token[0]==fence[0] and len(token)>=len(fence):fence=None
            continue
        if fence:continue
        m=re.match(r'^##\s+(.+?)\s*#*\s*$',line)
        if m:starts.append((n,m[1]))
    result={}
    for i,(n,label) in enumerate(starts):
        result.setdefault(label,[]).append(''.join(lines[n:starts[i+1][0] if i+1<len(starts) else len(lines)]))
    return {k:'\n\n'.join(v) for k,v in result.items()}


def comparison(workspace, entries, names, out, load, warnings):
    records=[]; modes={}; selectors=[]; missing=[]
    for entry in entries:
        eid=entry['entry_id']; reports=reading_files(workspace,eid)
        if not reports:
            missing.append('<li><a href="'+names[eid]+'">'+esc(entry.get('title') or eid)+'</a> · 尚无精读报告</li>')
            continue
        title=entry.get('title') or eid
        selectors.append('<label class="paper-card selected"><input type="checkbox" data-paper value="'+esc(eid,quote=True)+'" checked> <span class="paper-card-title">'+esc(title)+'</span><span class="paper-card-dims">'+str(len(reports))+' 份精读版本</span></label>')
        for path,meta in reports:
            text=load(path.relative_to(workspace.root));mode=meta['kind'];parts=sections(text)
            modes.setdefault(mode,[])
            for label in parts:
                if label not in modes[mode]:modes[mode].append(label)
            records.append((eid,title,path,meta,text,parts))
    nav='<button class="dim-pill active" data-dimension="all">完整报告</button>'
    blocks=[]
    for mode,labels in modes.items():
        for label in ['all']+labels:
            key='all' if label=='all' else digest(mode+label)[:16]
            if label!='all':nav+='<button class="dim-pill" data-dimension="'+key+'">'+esc(mode_label(mode)+' · '+label)+'</button>'
            cards=[]
            for eid,title,path,meta,text,parts in records:
                if meta['kind']!=mode:continue
                content=text if label=='all' else parts.get(label)
                if content:
                    rendered=render(content,path,out,path.parent,namespace='cmp-'+digest(str(path)+key)[:16]);warnings.extend(rendered['warnings']);html=rendered['html']
                else:html='<p class="answer-card-empty">本版本没有此标题，未推断等价维度。</p>'
                panel='panel-'+digest(str(path)+('人工稿' if meta.get('origin')=='user' else 'AI 候选，内容待验收')+' · '+mode+'reading')[:16]
                cards.append('<article class="answer-card" data-answer-paper="'+esc(eid,quote=True)+'"><header class="answer-card-header"><a class="answer-card-title" href="'+names[eid]+'#'+panel+'">'+esc(title)+'</a><div class="answer-card-meta">'+esc(mode+' · '+path.stem)+'<br>'+('人工稿' if meta.get('origin')=='user' else 'AI 候选，内容待验收')+'</div></header><div class="answer-card-content">'+html+'</div></article>')
            blocks.append('<section data-dimension-panel="'+key+'"'+(' hidden' if label!='all' else '')+'><h2>'+esc(mode_label(mode)+' · '+('完整报告' if label=='all' else label))+'</h2><div class="answer-cards-scroll">'+''.join(cards)+'</div></section>')
    return '<section class="compare-root"><div class="page-wrapper"><div class="page-header"><p class="page-subtitle">按精读模式分组，横向查看各论文的同名章节。保留已有报告的各个版本。</p></div><div class="paper-bar"><div class="paper-bar-label">选择参与展示的论文</div><div class="paper-cards">'+(''.join(selectors) or '<p>暂无精读报告。请先在代理中为选定论文执行精读，再构建页面。</p>')+'</div></div><nav class="dim-nav">'+nav+'</nav><p data-compare-empty hidden>请至少选择一篇论文。</p>'+''.join(blocks)+('<details'+('' if records else ' open')+'><summary>尚无精读报告（'+str(len(missing))+'）</summary><ul>'+''.join(missing)+'</ul></details>' if missing else '')+'</div></section>'
