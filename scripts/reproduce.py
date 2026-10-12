#!/usr/bin/env python3
"""Portable data inspection, trusted Stata execution, and offline reports."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from html import escape


def inspect_data(path, sheet=None):
    import pandas as pd
    path=Path(path).resolve()
    labels={}
    if path.suffix.lower()=='.dta':
        with pd.io.stata.StataReader(path) as reader: labels=reader.variable_labels()
        frame=pd.read_stata(path,convert_categoricals=False)
    elif path.suffix.lower() in ('.xlsx','.xlsm'):
        frame=pd.read_excel(path,sheet_name=sheet or 0)
    elif path.suffix.lower()=='.csv': frame=pd.read_csv(path)
    else: raise ValueError('Supported inputs: .dta, .xlsx, .xlsm, .csv')
    return {'rows':len(frame),'columns':[{'name':str(c),'label':labels.get(c,''),
        'dtype':str(frame[c].dtype),'missing':int(frame[c].isna().sum())} for c in frame.columns]}


def stata_path(value):
    value=str(Path(value).resolve()).replace('\\','/')
    if any(c in value for c in ['"','\n','\r','`','$']):
        raise ValueError('Stata paths cannot contain quotes, newlines or macro characters')
    return value


def run_stata(code, binary, output, inputs=(), timeout=3600):
    code=Path(code).resolve();binary=shutil.which(binary) or str(Path(binary).resolve())
    if not code.is_file() or not Path(binary).is_file(): raise ValueError('Code or Stata executable missing')
    out=Path(output).resolve()
    if out.exists(): raise FileExistsError('Use a new run directory; existing results are retained')
    sources=[code,*[Path(x).resolve() for x in inputs]]
    if any(not x.is_file() for x in sources): raise ValueError('An input file is missing')
    names=['analysis.do',*[x.name for x in sources[1:]]]
    if len({x.casefold() for x in names})!=len(names) or any(x in {'run-wrapper.do','execution.json','execution.log'} for x in names):
        raise ValueError('Input filenames collide with execution files')
    # Validate paths before creating a run; code is supplied/reviewed by the Agent.
    directory=stata_path(out)
    out.mkdir(parents=True)
    for src,name in zip(sources,names): shutil.copy2(src,out/name)
    wrapper=out/'run-wrapper.do'
    wrapper.write_text('clear all\nset more off\ncd "'+directory+'"\n'
        'log using "execution.log", text replace\ncapture noisily do "analysis.do"\n'
        'local dra_rc=_rc\ndisplay "DRA_REPRODUCTION_RC=" `dra_rc\'\n'
        'log close\nexit `dra_rc\', clear\n',encoding='utf-8')
    command=[binary,'/e','do',str(wrapper)] if os.name=='nt' else [binary,'-b','do',str(wrapper)]
    startup=None
    if os.name=='nt':
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow=0
    manifest={'status':'running','sources':[{'name':n,'sha256':hashlib.sha256(s.read_bytes()).hexdigest()}
        for s,n in zip(sources,names)]}
    try:
        completed=subprocess.run(command,cwd=out,timeout=timeout,startupinfo=startup,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        text=(out/'execution.log').read_text(encoding='utf-8',errors='replace') if (out/'execution.log').exists() else ''
        matches=re.findall(r'^DRA_REPRODUCTION_RC=\s*(\d+)\s*$',text,re.M)
        manifest.update(status='completed' if completed.returncode==0 and matches and matches[-1]=='0' else 'failed',
            process_returncode=completed.returncode,stata_returncode=int(matches[-1]) if matches else None)
    except subprocess.TimeoutExpired:
        manifest.update(status='failed',reason='timeout; process stopped; inspect partial outputs')
    (out/'execution.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {**manifest,'directory':str(out)}


def report(workspace, markdown, codes=(), results=(), evidence=()):
    from dra_core.reader import build, _page
    from dra_core.reader_render import render
    from dra_core.workspace import Workspace
    w=Workspace(workspace)
    supplied=[Path(markdown).resolve(),*[Path(x).resolve() for x in codes],*[Path(x).resolve() for x in results]]
    for p in supplied:
        if not p.is_file() or not p.is_relative_to(w.root): raise ValueError('Reports/code/results must be files inside this workspace')
    # Preserve the library/source/report navigation in a fresh reader snapshot.
    info=build(w);out=Path(info['path']).parent
    text=supplied[0].read_text(encoding='utf-8-sig')
    rendered=render(text,namespace='reproduction')
    downloads=[];code_blocks=[]
    for i,p in enumerate(supplied):
        if i==0: continue
        name=f'attachment-{i}'+p.suffix.lower();shutil.copy2(p,out/name)
        data=p.read_bytes()
        if len(data)<=2*1024*1024:
            downloads.append('<a class="download-button" download="'+escape(p.name,quote=True)+'" data-download64="'+base64.b64encode(data).decode()+'" href="'+name+'">下载 '+escape(p.name)+'</a>')
        else: downloads.append('<a target="_blank" rel="noopener noreferrer" href="'+name+'">打开结果文件 '+escape(p.name)+'</a>')
        if i<=len(codes):
            code_blocks.append('<h2>'+escape(p.name)+'</h2><pre><code>'+escape(data.decode('utf-8-sig'))+'</code></pre>')
    links=[]
    for i,item in enumerate(evidence):
        source=w.path(item['path'])
        if not source.is_file() or source.suffix.lower() not in {'.pdf','.html','.png','.jpg'}:
            raise ValueError('Evidence must be a local PDF, HTML or page image')
        if source.suffix.lower()=='.html':
            # Source HTML must be a generated reader page, including its relative assets.
            raise ValueError('Use original PDF/page images as evidence; HTML evidence requires a reader route')
        target=f'evidence-{i}'+source.suffix.lower();shutil.copy2(source,out/target)
        fragment=str(item.get('fragment',''))
        if fragment and not re.fullmatch(r'page=\d+',fragment): raise ValueError('Only PDF page fragments are supported')
        label=escape(item.get('label',source.name))
        if source.suffix.lower()=='.pdf':
            import fitz
            number=int(fragment.split('=')[1]) if fragment else 1
            with fitz.open(source) as doc:
                if not 1<=number<=len(doc): raise ValueError('Evidence physical PDF page outside document')
                image=f'evidence-{i}-page-{number}.png'
                doc[number-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(out/image)
            viewer=f'evidence-{i}.html'
            original='<article class="reading-paper" id="page-'+str(number)+'"><h2>'+label+'</h2><p>PDF 物理页 '+str(number)+'</p><p><a target="_blank" rel="noopener noreferrer" href="'+target+'#page='+str(number)+'">打开原 PDF 对应页</a></p><img style="max-width:100%;height:auto" src="'+image+'" alt="原文第'+str(number)+'页"></article>'
            (out/viewer).write_text(_page('原文证据',original),encoding='utf-8')
            destination=viewer+'#page-'+str(number)
        else: destination=target
        links.append('<a target="_blank" rel="noopener noreferrer" href="'+destination+'">'+label+'</a>')
    body='<div class="reading-layout"><aside class="reading-sidebar"><nav>'+rendered['toc']+'</nav><h2>代码与结果</h2>'+''.join('<p>'+x+'</p>' for x in downloads)+'<h2>原文证据</h2>'+''.join('<p>'+x+'</p>' for x in links)+'</aside><article class="reading-paper">'+rendered['html']+''.join(code_blocks)+'</article></div>'
    (out/'reproduction.html').write_text(_page('数据复现报告与代码',body),encoding='utf-8')
    for page in out.glob('*.html'):
        text=page.read_text(encoding='utf-8')
        text=text.replace('<div class="app-nav">','<div class="app-nav"><a class="nav-item" href="reproduction.html">数据复现</a>',1)
        page.write_text(text,encoding='utf-8')
    return {'status':'completed','path':str(out/'reproduction.html'),'build_id':info['build_id']}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    i=sub.add_parser('inspect');i.add_argument('--input',required=True);i.add_argument('--sheet');i.add_argument('--output',required=True)
    s=sub.add_parser('run-stata');s.add_argument('--code',required=True);s.add_argument('--stata',default=os.getenv('STATA_BIN','stata-mp'));s.add_argument('--output',required=True);s.add_argument('--input',action='append',default=[]);s.add_argument('--timeout',type=int,default=3600)
    r=sub.add_parser('report');r.add_argument('--workspace',required=True);r.add_argument('--markdown',required=True);r.add_argument('--code',action='append',default=[]);r.add_argument('--result',action='append',default=[]);r.add_argument('--evidence')
    args=p.parse_args()
    try:
        if args.action=='inspect':
            out=Path(args.output)
            if out.exists(): raise FileExistsError(out)
            result=inspect_data(args.input,args.sheet);out.parent.mkdir(parents=True,exist_ok=True)
            out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        elif args.action=='run-stata': result=run_stata(args.code,args.stata,args.output,args.input,args.timeout)
        else: result=report(args.workspace,args.markdown,args.code,args.result,json.loads(Path(args.evidence).read_text(encoding='utf-8-sig')) if args.evidence else [])
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('status','completed')=='completed' else 6
    except (ValueError,OSError) as exc: print(json.dumps({'status':'failed','error':str(exc)},ensure_ascii=False));return 2


if __name__=='__main__': raise SystemExit(main())
