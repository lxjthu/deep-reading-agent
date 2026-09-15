"""Durable serial batches; resume uses the original input snapshots."""
import json
import uuid
from .workspace import atomic_json
from .jobs import execute


def run_batch(workspace, plans, client, loader, batch_id=None, resume=False):
    batch_id=batch_id or 'batch-'+uuid.uuid4().hex[:12]
    path=workspace.path('batches/'+batch_id+'.json')
    if resume:
        state=json.loads(path.read_text(encoding='utf-8'))
    else:
        if path.exists(): raise FileExistsError('Batch exists; explicitly resume it')
        state={'batch_id':batch_id,'status':'running','items':[{'run_id':batch_id+'-'+str(i+1),'plan':p,'status':'pending'} for i,p in enumerate(plans)]}
        atomic_json(path,state)
    for item in state['items']:
        if item['status']=='completed': continue
        try:
            result=execute(workspace,item['plan'],client,loader,item['run_id'])
            item.update(status=result['status'],artifacts=result.get('artifacts',[])); item.pop('error',None)
            if result.get('native_request'): item['native_request']=result['native_request']
            else: item.pop('native_request',None)
        except Exception as exc: item.update(status='failed',error=str(exc))
        atomic_json(path,state)
    state['status']='completed' if all(i['status']=='completed' for i in state['items']) else 'partial' if any(i['status']=='failed' for i in state['items']) else 'waiting_for_native'
    atomic_json(path,state)
    return {'batch_id':batch_id,'status':state['status'],'manifest':str(path),'results':[{k:v for k,v in i.items() if k!='plan'} for i in state['items']]}
