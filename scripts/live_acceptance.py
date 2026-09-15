"""Explicit one-sample-per-task live acceptance. Provider concurrency is one."""
import argparse
import json
from pathlib import Path
from dra_core.workspace import Workspace,atomic_json
from dra_core.prompt_loader import PromptLoader
from dra_core.llm import Client,RemoteError
from dra_core.pipeline import prepare
from dra_core.jobs import execute


def main():
    p=argparse.ArgumentParser(); p.add_argument('--workspace',required=True); p.add_argument('--provider',required=True,choices=['deepseek','mimo']); p.add_argument('--tasks',required=True); p.add_argument('--env')
    args=p.parse_args(); w=Workspace(args.workspace); loader=PromptLoader(w.root); docs=[]
    for entry in w.entries():
        if entry.get('sources'):
            source=entry['sources'][-1]; d=json.loads(w.path(source['extracted']).read_text(encoding='utf-8')); d.update(entry_id=entry['entry_id'],metadata=entry.get('metadata',{})); docs.append(d)
    quant=next(d for d in docs if '返乡创业' in d['title']); qual=next(d for d in docs if '两化' in d['title']); fsqca=next(d for d in docs if '组态' in d['title']); english=next(d for d in docs if 'JSTOR' in d['title'])
    ecological=[d for d in docs if any(word in d['title'] for word in ('两化','含绿量','组态'))]
    cases={'read.quant':([quant],{}),'read.qual':([qual],{}),'read.long':([fsqca],{'dimensions':['overview','methodology']}),'translate.md-chunks':([english],{}),'cards.create':([fsqca],{'selection':fsqca['text'][:1800]}),'writing-style.single':([fsqca],{}),'synthesize':(ecological,{'topic':'生态产品价值实现的条件组合与实现机制'})}
    client=Client(args.provider,env_path=args.env); results=[]
    cases.update({'filter.explorer':([fsqca],{'topic':'生态产品价值实现的条件组合与实现机制'}),'references.extract':([fsqca],{}),'writing-style.batch':([fsqca,qual],{})})
    for task in args.tasks.split(','):
        documents,options=cases[task]; run_id='accept-'+args.provider+'-'+task.replace('.','-')
        try:
            plan=prepare(task,documents,options,loader); result=execute(w,plan,client,loader,run_id)
            results.append({'task':task,**result})
        except Exception as exc:
            results.append({'task':task,'run_id':run_id,'status':'failed','error':str(exc)})
            if isinstance(exc,RemoteError) and ('401' in str(exc) or '403' in str(exc)): break
        atomic_json(w.root/('live-'+args.provider+'.json'),results)
        print(json.dumps({'task':task,'status':results[-1]['status'],'run_id':run_id},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
