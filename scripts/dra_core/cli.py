from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from .workspace import Workspace,atomic_json,digest
from .prompt_loader import PromptLoader,PACKAGE
from .llm import Client,ConfigurationError,RemoteError
from .io_services import extract_document,parse_bibliography,match_bibliography
from .pipeline import prepare
from .jobs import execute


def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def ingest(workspace,path,exclusions=None,refresh=False,tessdata=None,ocr_language='eng'):
    path=Path(path).resolve()
    if path.name.endswith('.source.md'): return {'status':'skipped','path':str(path),'reason':'source_description_not_paper'}
    sha=digest(path.read_bytes())
    existing=None
    for entry in workspace.entries():
        if any(s.get('sha256')==sha for s in entry.get('sources',[])):
            if not refresh: return {'status':'duplicate','entry_id':entry['entry_id']}
            existing=entry
    if path.suffix.lower()=='.txt':
        parsed=parse_bibliography(path); added=[]
        for record in parsed['records']:
            eid='bib-'+digest({k:record[k] for k in ('title','authors','year','doi')})[:20]
            if any(e['entry_id']==eid for e in workspace.entries()): continue
            workspace.update({'entry_id':eid,'title':record['title'],'metadata':record,'sources':[],'tags':[]})
            added.append(eid)
        target=workspace.path('sources/bibliography-'+sha+path.suffix)
        if not target.exists(): shutil.copy2(path,target)
        return {'status':'completed','records':len(parsed['records']),'added':len(added),'warnings':parsed['warnings']}
    document=extract_document(path,exclusions=exclusions,tessdata=tessdata,ocr_language=ocr_language)
    entry_id='paper-'+sha[:20]
    candidates=match_bibliography(document,[{**e.get('metadata',{}),'title':e['title']} for e in workspace.entries()])
    certain=[c for c in candidates if c['score']==1 and c['basis']=='title_in_source']
    matched=existing
    if not existing and len(certain)==1:
        matched=workspace.entries()[certain[0]['record_index']]; entry_id=matched['entry_id']
    if existing: entry_id=existing['entry_id']
    folder=workspace.path('sources/'+entry_id); folder.mkdir(parents=True,exist_ok=True)
    target=folder/(sha+path.suffix.lower())
    if not target.exists(): shutil.copy2(path,target)
    document.update(entry_id=entry_id,title=matched['title'] if matched else document['title'])
    extraction_id=sha+'-'+digest(document['pages'])[:12]+'-'+digest(document.get('exclusions',[]))[:8]
    atomic_json(folder/(extraction_id+'.json'),document)
    md=folder/(extraction_id+'.md')
    if not md.exists(): md.write_text(document['text'],encoding='utf-8')
    entry=matched or {'entry_id':entry_id,'title':document['title'],'metadata':{},'sources':[],'tags':[]}
    entry['sources'].append({'path':str(target.relative_to(workspace.root)),'extracted':str((folder/(extraction_id+'.json')).relative_to(workspace.root)),'markdown':str(md.relative_to(workspace.root)),'sha256':sha,'extraction_id':extraction_id})
    workspace.update(entry)
    return {'status':'completed','entry_id':entry_id,'warnings':document['warnings'],'association':'exact_unique_title' if matched else 'new_entry','candidates':candidates}


def documents(workspace,args):
    ids=list(args.entry_id or [])
    for path in args.input or []:
        result=ingest(workspace,path,read_json(args.exclusions) if args.exclusions else None)
        if result.get('entry_id'): ids.append(result['entry_id'])
    result=[]
    for eid in dict.fromkeys(ids):
        entry=workspace.get(eid)
        if entry.get('sources'):
            from .source_versions import resolve_document
            doc=resolve_document(workspace,entry)
            doc.update(metadata=entry.get('metadata',{}),entry_id=eid,title=entry['title'])
        else: doc={**entry,'text':entry.get('metadata',{}).get('abstract',''),'evidence':[]}
        result.append(doc)
    return result


def options(args):
    out={'question':args.question or '', 'variables':read_json(args.variables) if args.variables else {}}
    if args.topic: out['topic']=args.topic
    if args.dimensions: out['dimensions']=args.dimensions.split(',')
    if args.dimension_set: out['dimension_set']=args.dimension_set
    if args.selection: out['selection']=Path(args.selection).read_text(encoding='utf-8')
    if args.prompt_overrides: out['prompt_overrides']=read_json(args.prompt_overrides)
    return out


def make_client(args):
    if args.provider=='native':
        from .native import NativeClient
        return NativeClient()
    return Client(args.provider,env_path=args.env)


def parser():
    p=argparse.ArgumentParser(description='Independent Deep Reading Agent research workspace')
    p.add_argument('command',choices=['doctor','ingest','extract','read','filter','translate','references','metadata','qa','cards','compare','synthesize','writing-style','research','library','dimensions','templates','prompts','jobs','batch','artifacts','data','search','online','plan','benchmark','native','package','reader','markdown','ocr'])
    p.add_argument('action',nargs='?',default='')
    p.add_argument('--workspace'); p.add_argument('--input',action='append'); p.add_argument('--entry-id',action='append')
    p.add_argument('--mode'); p.add_argument('--provider',choices=['mimo','deepseek','native'],default='deepseek'); p.add_argument('--env')
    p.add_argument('--dimension-set')
    p.add_argument('--include-pdf',action='store_true'); p.add_argument('--build-id'); p.add_argument('--source-url')
    p.add_argument('--tessdata'); p.add_argument('--ocr-language',default='eng')
    p.add_argument('--continue-run')
    p.add_argument('--output'); p.add_argument('--run-id'); p.add_argument('--question'); p.add_argument('--topic'); p.add_argument('--dimensions')
    p.add_argument('--variables'); p.add_argument('--selection'); p.add_argument('--exclusions'); p.add_argument('--prompt-overrides')
    p.add_argument('--dry-run',action='store_true'); p.add_argument('--task'); p.add_argument('--name'); p.add_argument('--text'); p.add_argument('--limit',type=int,default=1)
    p.add_argument('--base-url'); p.add_argument('--endpoint'); p.add_argument('--method',default='GET'); p.add_argument('--allow-write',action='store_true')
    return p


def task_name(args):
    defaults={'read':'quant','filter':'explorer','translate':'md-chunks','references':'extract','metadata':'extract','cards':'create','writing-style':'single','templates':'generate'}
    if args.command=='library': return {'ask':'library.query_parser','report':'library.report_writer','comment':'library.paper_comment_writer'}[args.action]
    return args.command+'.'+(args.mode or args.action or defaults[args.command]) if args.command in defaults else args.command


def dispatch(args):
    if args.command=='package':
        if not args.output: raise ValueError('--output required')
        target=Path(args.output).resolve()
        if target.exists(): raise ValueError('Package destination must not exist')
        target.mkdir(parents=True)
        for name in ('SKILL.md','README.md','THIRD_PARTY.md','.env.example','.gitignore','requirements.txt','requirements-reproduction.txt','scripts','prompts','assets','references','agents','tests'):
            src=PACKAGE/name
            if src.is_dir(): shutil.copytree(src,target/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','build_prompt_resources.py','tmp*','*.local.md'))
            elif src.is_file(): shutil.copy2(src,target/name)
        return {'status':'completed','package':str(target),'excludes':['.env','test','user workspaces','source migration builder','*.local.md']}
    if args.command=='data' and args.action in ('import','inspect'):
        from .portability import import_archive,inspect_archive
        return import_archive(args.input[0],args.workspace) if args.action=='import' else inspect_archive(args.input[0])
    if args.command=='doctor':
        loader=PromptLoader(); check=loader.check()
        import importlib.util
        dependencies = {m:bool(importlib.util.find_spec(m)) for m in ('fitz','httpx','openpyxl','markdown','nh3','mdx_math')}
        return {'status':'failed' if check['errors'] or not all(dependencies.values()) else 'completed','prompts':check,'dependencies':dependencies,'network_called':False,'python':sys.version.split()[0]}
    if args.command=='search':
        from .connectors import search_links
        return search_links(args.question or args.topic or '',args.action or 'cnki')
    if args.command=='online':
        from .connectors import request_online
        if not args.base_url or not args.endpoint: raise ValueError('--base-url and --endpoint required; no production default')
        return request_online(args.base_url,args.endpoint,args.method,os.environ.get('DRA_ONLINE_TOKEN'),read_json(args.input[0]) if args.input else None,args.allow_write)
    if not args.workspace: raise ValueError('--workspace required')
    workspace=Workspace(args.workspace); loader=PromptLoader(workspace.root)
    if args.command=='reader':
        from .reader import build,serve,find
        if args.action=='find': return find(workspace,args.topic or args.question or '')
        if args.action=='compare':
            ids=args.entry_id
            matches=find(workspace,args.topic or args.question or '') if not ids else None
            if not ids and not (args.topic or args.question): raise ValueError('reader compare requires --entry-id or --topic')
            if matches is not None:
                ids=[m['entry_id'] for m in matches['matches']]
                if not ids:return {'status':'no_matches',**matches}
            result=build(workspace,ids,args.include_pdf)
            result['path']=result['comparison_path']
            if matches is not None:result['selection']=matches
            return result
        if args.action=='build': return build(workspace,args.entry_id,args.include_pdf)
        if args.action=='serve': return serve(workspace,args.build_id)
        raise ValueError('Use reader find/build/compare/serve')
    if args.command=='ocr':
        from .ocr_guidance import guide
        if args.action!='guide' or not args.input: raise ValueError('Use ocr guide --input PDF')
        return guide(args.input[0],args.tessdata,args.ocr_language)
    if args.command=='markdown':
        from .source_versions import import_markdown,adopt,resolve_document,inspect_markdown
        from .markdown_cleanup import inspect_document
        if args.action=='import':
            if not args.input or not args.entry_id or len(args.entry_id)!=1: raise ValueError('Markdown import requires one --entry-id and --input')
            return import_markdown(workspace,args.input[0],args.entry_id[0],args.source_url)
        if args.action=='adopt':
            if not args.run_id: raise ValueError('--run-id required')
            return adopt(workspace,args.run_id)
        docs=documents(workspace,args)
        if len(docs)!=1: raise ValueError('Select exactly one document')
        if args.action=='inspect': return inspect_markdown(workspace,docs[0]['entry_id'])
        if args.action=='clean':
            plan=prepare('markdown.clean',docs,options(args),loader)
            if args.dry_run: return {'status':'planned','plan':plan}
            return execute(workspace,plan,make_client(args),loader,args.run_id)
        raise ValueError('Use markdown import/inspect/clean/adopt')
    if args.command in ('ingest','extract'):
        results=[]
        for path in args.input or []:
            paths=sorted(Path(path).rglob('*')) if Path(path).is_dir() else [Path(path)]
            for file in paths:
                if not file.is_file() or file.suffix.lower() not in ('.pdf','.md','.txt','.markdown'): continue
                try: results.append(ingest(workspace,file,read_json(args.exclusions) if args.exclusions else None,refresh=args.command=='extract',tessdata=args.tessdata,ocr_language=args.ocr_language))
                except Exception as exc: results.append({'status':'failed','file':str(file),'error':str(exc)})
        return {'status':'partial' if any(r['status']=='failed' for r in results) else 'completed','results':results}
    if args.command=='prompts':
        if args.action=='export-online':
            from .connectors import request_online
            if not args.base_url: raise ValueError('--base-url required; token from DRA_ONLINE_TOKEN')
            exported=[]
            for slot,meta in loader.catalog.items():
                if meta['source'].split('#')[0].startswith(('prompts/','backend/prompts/')) and not slot.startswith('unregistered.'):
                    category,key=slot.split('.',1)
                    response=request_online(args.base_url,'/api/prompts/item',token=os.environ.get('DRA_ONLINE_TOKEN'),params={'type':category,'key':key})
                    exported.append(response['data'])
            target=workspace.path('imports/online-prompts-'+uuid.uuid4().hex+'.json'); atomic_json(target,{'server':args.base_url,'prompts':exported,'adopted':False})
            return {'status':'completed','path':str(target),'slots':len(exported),'local_overrides_changed':False}
        if args.action in ('','list'): return {'prompts':list(loader.catalog)}
        if args.action=='check': return loader.check()
        if args.action=='show':
            body,meta=loader.load(args.name,read_json(args.variables) if args.variables else {}); return {'body':body,'provenance':meta}
        if args.action=='set':
            if args.name not in loader.catalog: raise ValueError('Unknown prompt slot')
            target=workspace.path('prompts/'+args.name+'.md')
            if target.exists(): shutil.copy2(target,target.with_suffix('.'+uuid.uuid4().hex[:8]+'.bak'))
            shutil.copy2(args.input[0],target); return {'path':str(target),'check':loader.check()}
    if args.command=='library' and args.action not in ('ask','report','comment'):
        entries=workspace.entries()
        if args.action in ('','list'): return {'entries':entries,'count':len(entries)}
        if args.action=='search': return {'entries':[e for e in entries if (args.question or '').casefold() in json.dumps(e,ensure_ascii=False).casefold()]}
        entry=workspace.get(args.entry_id[0])
        if args.action in ('show','attachments'): return entry
        if args.action in ('edit','tags','delete'):
            if args.action=='edit':
                patch=read_json(args.input[0]); allowed={'title','metadata','notes'}
                if set(patch)-allowed: raise ValueError('Editable fields: title, metadata, notes')
                workspace.artifact(entry['entry_id'],'record-before-edit',json.dumps(entry,ensure_ascii=False),'.json','user-history'); entry.update(patch)
            elif args.action=='tags': entry['tags']=(args.text or '').split(',')
            else: entry['deleted']=True
            return workspace.update(entry)
    if args.command=='metadata' and args.action in ('match','apply'):
        if args.action=='match':
            docs=documents(workspace,args)
            return {'suggestions':match_bibliography(docs[0],[{**e.get('metadata',{}),'title':e['title']} for e in workspace.entries()])}
        entry=workspace.get(args.entry_id[0]); patch=read_json(args.input[0]); workspace.artifact(entry['entry_id'],'metadata-before',json.dumps(entry,ensure_ascii=False),'.json','user-history'); entry['metadata'].update(patch); return workspace.update(entry)
    if args.command in ('dimensions','templates') and args.action!='generate':
        directory=workspace.path('library/'+args.command); directory.mkdir(exist_ok=True)
        if args.action in ('','list'): return {'builtin':read_json(PACKAGE/'assets/dimensions/default.json'),'custom':[p.stem for p in directory.glob('*.json')]}
        name=args.name or 'custom'
        if not re.fullmatch(r'[\w-]+',name): raise ValueError('Invalid resource name')
        target=directory/(name+'.json')
        if args.action in ('import','save'):
            value=read_json(args.input[0])
            if args.command=='dimensions':
                from .dimensions import adopt
                return adopt(workspace,name,value)
            if not isinstance(value,(list,dict)): raise ValueError('Expected structured dimensions/template')
            if target.exists(): shutil.copy2(target,target.with_suffix('.'+uuid.uuid4().hex[:8]+'.bak'))
            atomic_json(target,value); return {'path':str(target)}
        if args.action=='export': shutil.copy2(target,args.output); return {'path':args.output}
    if args.command=='references' and args.action=='presets':
        directory=workspace.path('library/ref-presets'); directory.mkdir(exist_ok=True)
        if not args.input: return {'presets':[read_json(p) for p in directory.glob('*.json')]}
        preset=read_json(args.input[0])
        if not isinstance(preset.get('rules'),str) or not preset['rules'].strip(): raise ValueError('Reference preset needs nonempty rules')
        target=directory/(uuid.uuid4().hex+'.json'); atomic_json(target,preset); return {'path':str(target)}
    if args.command=='data' and args.action=='export':
        from .portability import export_workspace
        with workspace.lock(): return export_workspace(workspace.root,args.output)
    if args.command=='artifacts' or (args.command=='cards' and args.action in ('list','edit','export')):
        if args.command=='artifacts' and args.action=='export':
            from openpyxl import Workbook
            if not args.output: raise ValueError('--output required')
            target=Path(args.output)
            if target.exists(): raise FileExistsError(target)
            wb=Workbook(); sheet=wb.active; sheet.title='Results'; sheet.append(['run_id','task','step','field','value'])
            for path in workspace.root.glob('runs/*/result.json'):
                result=read_json(path)
                for step,row in result.get('steps',{}).items():
                    value=row.get('parsed')
                    if value is not None:
                        for field,item in (value.items() if isinstance(value,dict) else [('items',value)]):
                            text=json.dumps(item,ensure_ascii=False) if isinstance(item,(dict,list)) else str(item)
                            if text.startswith(('=','+','-','@')): text="'"+text
                            sheet.append([path.parent.name,result['task'],step,field,text])
            target.parent.mkdir(parents=True,exist_ok=True); wb.save(target); return {'path':str(target),'rows':sheet.max_row-1}
        files=list(workspace.root.glob('artifacts/**/*.md'))
        if args.command=='artifacts' or args.action=='list': return {'artifacts':[str(p) for p in files]}
        if args.action=='edit': return workspace.artifact(args.entry_id[0],'card-edited',Path(args.input[0]).read_text(encoding='utf-8'),origin='user')
        if args.action=='export':
            target=Path(args.output); target.mkdir(parents=True,exist_ok=True)
            for path in files:
                if 'card' in path.name:
                    out=target/(path.parent.name+'-'+path.name)
                    if out.exists(): raise FileExistsError(out)
                    shutil.copy2(path,out)
            return {'path':str(target)}
    if args.command=='native':
        from .native import advance
        if args.action not in ('next','submit') or not args.run_id: raise ValueError('Use native next/submit --run-id ...')
        if args.action=='submit' and not args.input: raise ValueError('Native submit requires --input response.json')
        return advance(workspace,loader,args.run_id,args.input[0] if args.action=='submit' else None)
    if args.command=='jobs':
        if args.action in ('','list'): return {'jobs':[read_json(p) for p in workspace.root.glob('runs/*/state.json')]}
        folder=workspace.path('runs/'+args.run_id)
        if args.action=='status': return read_json(folder/'state.json')
        if args.action=='cancel': (folder/'cancel.request').touch(); return {'status':'cancel_requested','run_id':args.run_id}
        if args.action=='resume':
            if (folder/'cancel.request').exists(): (folder/'cancel.request').rename(folder/('cancel-consumed-'+uuid.uuid4().hex+'.record'))
            plan=read_json(folder/'plan.json'); refreshed=prepare(plan['task'],plan['documents'],plan['options'],loader)
            if read_json(folder/'state.json')['model'].get('provider')=='native': args.provider='native'
            return execute(workspace,refreshed,make_client(args),loader,args.run_id)
    if args.command=='batch':
        from .batch import run_batch
        if args.action=='resume':
            if not args.run_id: raise ValueError('Batch resume requires --run-id <batch_id>')
            return run_batch(workspace,[],make_client(args),loader,args.run_id,resume=True)
        docs=documents(workspace,args)
        if not 1<=args.limit<=len(docs): raise ValueError('--limit must be within selected input count')
        if not args.dry_run:
            plans=[prepare(args.task or 'read.quant',[doc],options(args),loader) for doc in docs[:args.limit]]
            return run_batch(workspace,plans,make_client(args),loader,args.run_id)
        outcomes=[]; client=None if args.dry_run else make_client(args)
        for doc in docs[:args.limit]:
            try:
                plan=prepare(args.task or 'read.quant',[doc],options(args),loader)
                outcomes.append({'entry_id':doc['entry_id'],'plan':plan['fingerprint'],'steps':len(plan['steps'])} if args.dry_run else execute(workspace,plan,client,loader))
            except Exception as exc: outcomes.append({'entry_id':doc['entry_id'],'status':'failed','error':str(exc)})
        return {'status':'partial' if any(o.get('status')=='failed' for o in outcomes) else 'completed','results':outcomes,'selected':len(docs),'executed':min(args.limit,len(docs))}
    if args.continue_run and not args.entry_id and not args.input:
        previous=read_json(workspace.path('runs/'+args.continue_run+'/plan.json')); args.entry_id=[d['entry_id'] for d in previous['documents']]
    docs=documents(workspace,args)
    if args.command=='research':
        from .research import research
        result=research(args.action,docs,args.topic or args.question or '')
        if args.action=='session':
            target=workspace.path('library/sessions/'+uuid.uuid4().hex+'.json'); atomic_json(target,{'result':result,'input_entry_ids':[d['entry_id'] for d in docs],'topic':args.topic or args.question,'status':'evidence_ready','proposals':[]}); result['session_path']=str(target)
        return result
    task=args.task if args.command in ('plan','benchmark') else task_name(args)
    task_options=options(args)
    if args.continue_run:
        previous=read_json(workspace.path('runs/'+args.continue_run+'/plan.json')); result=read_json(workspace.path('runs/'+args.continue_run+'/result.json'))
        if task!='qa' or result.get('task')!='qa': raise ValueError('--continue-run requires an earlier QA run')
        task_options['history']=previous['options'].get('history',[])+[{'question':previous['options'].get('question'),'answer':result['content']}]
    if args.command=='cards' and args.action=='from-qa':
        if not args.run_id: raise ValueError('--run-id of a completed QA required')
        qa=read_json(workspace.path('runs/'+args.run_id+'/result.json'))
        if qa.get('task')!='qa': raise ValueError('Source run is not QA')
        task='cards.create'; task_options['selection']=qa['content']; task_options['variables']['source_version']='qa:'+args.run_id
        args.run_id=None
    plan=prepare(task,docs,task_options,loader)
    if args.dry_run or args.command in ('plan','benchmark'):
        target=Path(args.output) if args.output else workspace.path('runs/prepared-'+uuid.uuid4().hex[:10]+'.json')
        atomic_json(target,plan)
        return {'status':'prepared','path':str(target),'fingerprint':plan['fingerprint'],'steps':len(plan['steps']),'network_called':False,'native_model':'must_be_verified_by_platform'}
    return execute(workspace,plan,make_client(args),loader,args.run_id)


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        result=dispatch(args)
        if result is None: raise ValueError('Unsupported action; check --help and workflows reference')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 6 if result.get('status')=='partial' else 1 if result.get('status')=='failed' else 0
    except ConfigurationError as exc: code=3; error=str(exc)
    except RemoteError as exc: code=4; error=str(exc)
    except (ValueError,KeyError,OSError,StopIteration,TypeError) as exc: code=2; error=str(exc) or type(exc).__name__
    print(json.dumps({'status':'failed','error':error,'exit_code':code},ensure_ascii=False),file=sys.stderr)
    return code
