"""Explicit adoption of user-supplied dimension instructions into workspace MD slots."""
import json
import re
import shutil
import uuid
from .workspace import atomic_json,digest
from .prompt_loader import VARIABLE


def adopt(workspace,name,data):
    rows=data.get('dimensions',[]) if isinstance(data,dict) else data
    if not isinstance(rows,list) or not rows: raise ValueError('Dimensions must be a nonempty list')
    if not re.fullmatch(r'[\w-]+',name): raise ValueError('Invalid dimension set name')
    prompts=[]; dimensions=[]
    for i,row in enumerate(rows):
        body=row.get('prompt_content',row.get('instruction',row.get('prompt')))
        if not isinstance(body,str) or not body.strip(): raise ValueError('Each dimension requires prompt_content/instruction/prompt')
        slot='custom.'+name+'.'+str(i+1)
        question=row.get('default_question','')
        if question: body+='\n\n'+question
        prompts.append({'id':slot,'path':slot+'.md','variables':sorted(set(VARIABLE.findall(body))),'source':'workspace-dimension-import','version':digest(body)[:12],'body':body})
        dimensions.append({'id':'dimension_'+str(i+1),'name':row.get('dim_name',row.get('name',str(i+1))),'prompt_id':slot})
    catalog=workspace.path('prompts/catalog.json'); existing=json.loads(catalog.read_text(encoding='utf-8'))['prompts'] if catalog.exists() else []
    for meta in prompts:
        path=workspace.path('prompts/'+meta['id']+'.md')
        if path.exists(): shutil.copy2(path,path.with_suffix('.'+uuid.uuid4().hex[:8]+'.bak'))
        path.write_text(meta.pop('body'),encoding='utf-8')
    ids={m['id'] for m in prompts}; atomic_json(catalog,{'prompts':[r for r in existing if r['id'] not in ids]+prompts})
    target=workspace.path('library/dimensions/'+name+'.json')
    if target.exists(): shutil.copy2(target,target.with_suffix('.'+uuid.uuid4().hex[:8]+'.bak'))
    atomic_json(target,{'name':name,'dimensions':dimensions,'source_definition':data})
    return {'status':'adopted','name':name,'dimensions':len(dimensions),'path':str(target)}
