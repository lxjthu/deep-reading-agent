"""Prepare source-based review forms; never rank candidates by model self-scores."""
import argparse
import json
import random
from pathlib import Path
from dra_core.workspace import atomic_json,digest


def build(runs,output,native=None):
    target=Path(output).resolve()
    if target.exists(): raise FileExistsError('Use a new blind-review directory')
    target.mkdir(parents=True); candidates=[]; performance=[]
    for folder in runs:
        folder=Path(folder); state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
        if state['status']!='completed': performance.append({'run_id':folder.name,'status':state['status'],'error':state.get('error'),'usage':None}); continue
        result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        plan=json.loads((folder/'plan.json').read_text(encoding='utf-8'))
        steps=list(result['steps'].values())
        content=json.dumps(steps[0]['parsed'],ensure_ascii=False,indent=2) if result['task']=='qa' else result['content']
        candidates.append({'content':content,'identity':{'run_id':folder.name,**state['model']},'input_fingerprint':plan['fingerprint']})
        performance.append({'run_id':folder.name,'status':state['status'],'elapsed_seconds':sum(s.get('elapsed_seconds') or 0 for s in steps) if all(s.get('elapsed_seconds') is not None for s in steps) else None,'steps':len(steps),'attempts':[s.get('attempts') for s in steps],'usage':[s.get('usage') for s in steps],'models':[s.get('model') for s in steps],'truncated':any(s.get('truncated',False) for s in steps)})
        atomic_json(target/'source-evidence.json',[{'entry_id':d['entry_id'],'title':d['title'],'evidence':d.get('evidence',[])} for d in plan['documents']])
    if native:
        path=Path(native)
        candidates.append({'content':path.read_text(encoding='utf-8'),'identity':{'provider':'codex_native','model':None,'model_verification':'external platform receipt required','usage':None},'input_fingerprint':None})
        performance.append({'provider':'codex_native','elapsed_seconds':None,'usage':None,'cost':None,'timing_comparable_to_api':False})
    random.SystemRandom().shuffle(candidates); mapping={}; rubric=[]
    for i,candidate in enumerate(candidates):
        label='candidate-'+chr(65+i); (target/(label+'.md')).write_text(candidate['content'],encoding='utf-8')
        mapping[label]={**candidate['identity'],'output_sha256':digest(candidate['content'].encode()),'input_fingerprint':candidate['input_fingerprint']}
        rubric.append({'candidate':label,'facts_numbers_evidence':None,'completion_translation_terminology':None,'format_usability':None,'critical_errors':[],'source_locations':[],'human_reviewed':False})
    atomic_json(target/'identity-map.json',mapping); atomic_json(target/'performance.json',performance); atomic_json(target/'review-form.json',rubric)
    return {'status':'prepared','directory':str(target),'candidates':len(candidates),'ranking':None,'warning':'Keep identity-map.json separate during human review; initial answer and API verified output are distinct.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--runs',nargs='+',required=True); p.add_argument('--output',required=True); p.add_argument('--native'); args=p.parse_args()
    print(json.dumps(build(args.runs,args.output,args.native),ensure_ascii=False))
