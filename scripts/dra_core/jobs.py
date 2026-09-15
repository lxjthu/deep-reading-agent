from __future__ import annotations
import json
import time
import uuid
import os
from .workspace import atomic_json,digest
from . import pipeline


def execute(workspace,plan,client,loader,run_id=None):
    run_id=run_id or time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    folder=workspace.path('runs/'+run_id); folder.mkdir(parents=True,exist_ok=True)
    if hasattr(client,'bind'): client.bind(folder)
    lock=folder/'execution.lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.write(fd,str(os.getpid()).encode()); os.close(fd)
    except FileExistsError:
        raise ValueError('Run already active or stale execution.lock; inspect its process before resuming') from None
    try: return _execute(workspace,plan,client,loader,run_id)
    finally: lock.unlink(missing_ok=True)


def _execute(workspace,plan,client,loader,run_id=None):
    run_id=run_id or time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    folder=workspace.path('runs/'+run_id); folder.mkdir(parents=True,exist_ok=True)
    state_path=folder/'state.json'
    configuration=client.public()
    fingerprint=digest({'plan':plan['fingerprint'],'client':configuration})
    completed={}
    if state_path.exists():
        old=json.loads(state_path.read_text(encoding='utf-8'))
        if old['fingerprint']!=fingerprint: raise ValueError('Inputs, prompts or provider changed; cannot resume this run')
        if old['status']=='completed': return old
        for path in folder.glob('step-*.json'):
            row=json.loads(path.read_text(encoding='utf-8'))
            if row['step_id'] in {s['id'] for s in plan['steps']} and path.name=='step-'+row['step_id']+'.json': completed[row['step_id']]=row
    state={'run_id':run_id,'status':'running','task':plan['task'],'fingerprint':fingerprint,'model':configuration,'artifacts':[],'warnings':[]}
    atomic_json(folder/'plan.json',plan); atomic_json(state_path,state)
    def checkpoint(step_id,result):
        atomic_json(folder/('step-'+step_id+'.json'),result)
        completed[step_id]=result
        state['completed_steps']=[k for k in completed if k in {s['id'] for s in plan['steps']}]; atomic_json(state_path,state)
        if (folder/'cancel.request').exists(): raise InterruptedError('Cancellation requested; current response safely checkpointed')
    try:
        if (folder/'cancel.request').exists(): raise InterruptedError('Cancellation requested')
        result=pipeline.run(plan,client,loader,checkpoint=checkpoint,resume=completed)
        entry_id=plan['documents'][0]['entry_id'] if len(plan['documents'])==1 else 'collection'
        content='---\n'+ 'run_id: '+run_id+'\ntask: '+plan['task']+'\norigin: ai\n---\n\n'+result['content']
        if plan['task']=='markdown.clean':
            from .source_versions import persist_candidate
            artifact=persist_candidate(workspace,plan,result,run_id)
        else:
            artifact=workspace.artifact(entry_id,plan['task'].replace('.','-'),content)
        atomic_json(folder/'result.json',result)
        state.update(status='completed',artifacts=[artifact],warnings=result['warnings'],quality_status=result['quality_status'])
    except Exception as exc:
        from .native import AwaitingNative
        if isinstance(exc,AwaitingNative):
            state.update(status='waiting_for_native',native_request=exc.request)
            atomic_json(state_path,state)
            return state
        state.update(status='cancelled' if isinstance(exc,InterruptedError) else 'failed',error=str(exc))
        atomic_json(state_path,state)
        raise
    atomic_json(state_path,state)
    return state
