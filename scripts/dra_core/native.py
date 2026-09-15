"""File handoff to the host Agent; never calls an API or reads credentials."""
import json
import os
import time
import uuid
from pathlib import Path
from .workspace import atomic_json, digest


class AwaitingNative(Exception):
    def __init__(self, request): self.request=request


class NativeClient:
    def public(self): return {'provider':'native','model':None,'execution':'host_agent','model_verification':'host_reported_only'}
    def bind(self, folder): self.folder=folder
    def set_step(self, step): self.step=step
    def complete(self, messages):
        request_id=digest({'step':self.step['id'],'messages':messages})
        request_path=self.folder/'native/requests'/(request_id+'.json')
        if not request_path.exists():
            atomic_json(request_path,{'request_id':request_id,'run_id':self.folder.name,'step_id':self.step['id'],'output_format':self.step['output'],'messages':messages,'created_at':time.time(),'model_policy':'Use actual host model; do not infer Luna from configuration.'})
        saved=json.loads(request_path.read_text(encoding='utf-8'))
        if digest({'step':saved['step_id'],'messages':saved['messages']})!=request_id or saved['run_id']!=self.folder.name:
            raise ValueError('Native request file was changed; restore the original request before continuing')
        pending={'request_id':request_id,'step_id':self.step['id'],'request_path':str(request_path)}
        atomic_json(self.folder/'native/pending.json',pending)
        response_path=self.folder/'native/responses'/(request_id+'.json')
        if not response_path.exists(): raise AwaitingNative(pending)
        response=json.loads(response_path.read_text(encoding='utf-8'))
        if response.get('request_id')!=request_id: raise ValueError('Native response request mismatch')
        return {'content':response['content'],'provider':'native','model':response.get('reported_model'),'model_verification':'host_reported_only' if response.get('reported_model') else 'unavailable','model_evidence':response.get('model_evidence'),'usage':None,'elapsed_seconds':None,'handoff_elapsed_seconds':max(0,response['submitted_at']-json.loads(request_path.read_text(encoding='utf-8'))['created_at']),'finish_reason':response.get('finish_reason','stop'),'truncated':response.get('finish_reason')=='length','attempts':[]}


def advance(workspace, loader, run_id, response_path=None):
    from .jobs import execute
    folder=workspace.path('runs/'+run_id)
    lock=folder/'native.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY); os.close(fd)
    try:
        state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
        if state['model'].get('provider')!='native': raise ValueError('This is not a native run')
        if (folder/'cancel.request').exists(): raise ValueError('Run cancelled; use jobs resume explicitly')
        if response_path:
            if state['status']=='completed': raise ValueError('Run completed; no further response accepted')
            pending=json.loads((folder/'native/pending.json').read_text(encoding='utf-8'))
            response=json.loads(Path(response_path).read_text(encoding='utf-8-sig'))
            if not isinstance(response,dict) or response.get('request_id')!=pending['request_id']: raise ValueError('Stale or missing native request_id')
            if not isinstance(response.get('content'),str) or not response['content'].strip(): raise ValueError('Native response requires nonempty content string')
            if response.get('finish_reason','stop') not in ('stop','length'): raise ValueError('Invalid finish_reason')
            for key in ('reported_model','model_evidence'):
                if response.get(key) is not None and not isinstance(response[key],str): raise ValueError(key+' must be string or null')
            response={k:response[k] for k in ('request_id','content','reported_model','model_evidence','finish_reason') if k in response}
            response['submitted_at']=time.time()
            atomic_json(folder/'native/submissions'/(uuid.uuid4().hex+'.json'),response)
            atomic_json(folder/'native/responses'/(pending['request_id']+'.json'),response)
        plan=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
        return execute(workspace,plan,NativeClient(),loader,run_id)
    finally: lock.unlink(missing_ok=True)
