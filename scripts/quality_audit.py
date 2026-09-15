import argparse
import json
from pathlib import Path
from dra_core.quality import locate_quote,translation_checks
from dra_core.workspace import atomic_json


def audit(workspace):
    root=Path(workspace); report=[]
    for file in root.glob('runs/*/result.json'):
        result=json.loads(file.read_text(encoding='utf-8')); plan=json.loads((file.parent/'plan.json').read_text(encoding='utf-8')); rows=[]
        for step in result['steps'].values():
            for item in step.get('source_evidence',[]):
                rows.append({'claim':item.get('claim'),'quote':item['quote'],'locations':locate_quote(item['quote'],plan['documents'])})
        report.append({'run_id':file.parent.name,'task':result['task'],'source_evidence_count':len(rows),'located_exact':sum(any(l['match']=='exact' for l in r['locations']) for r in rows),'located_whitespace_only':sum(bool(r['locations']) and not any(l['match']=='exact' for l in r['locations']) for r in rows),'unlocated':sum(not r['locations'] for r in rows),'evidence':rows,'translation':translation_checks(plan['documents'][0]['text'],result['content']) if result['task'].startswith('translate.') else None,'quality_accepted':False})
    atomic_json(root/'quality-audit.json',report)
    return [{k:v for k,v in row.items() if k not in ('evidence',)} for row in report]


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--workspace',required=True); args=p.parse_args(); print(json.dumps(audit(args.workspace),ensure_ascii=False,indent=2))
