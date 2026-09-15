"""Read-only material audit and isolated acceptance preparation. No implicit API calls."""
import argparse
import json
import re
import unicodedata
from pathlib import Path
from dra_core.workspace import Workspace,atomic_json,digest
from dra_core.cli import ingest
from dra_core.io_services import extract_document,parse_bibliography
from dra_core.prompt_loader import PromptLoader
from dra_core.pipeline import prepare


def audit(materials,workspace):
    root=Path(materials).resolve(); w=Workspace(workspace); manifest=[]; results=[]; documents=[]
    for path in sorted(root.rglob('*')):
        if not path.is_file(): continue
        row={'sample_id':'sample-'+digest(path.read_bytes())[:12],'file':str(path.relative_to(root)),'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size}
        if path.name.endswith('.source.md'): row['kind']='source-description'; manifest.append(row); continue
        if path.suffix.lower()=='.txt':
            parsed=parse_bibliography(path); row.update(kind=parsed['format'],records=len(parsed['records']),warnings=parsed['warnings']); results.append(ingest(w,path))
        elif path.suffix.lower() in ('.pdf','.md'):
            doc=extract_document(path); exclusions=[]
            if '含绿量' in path.name and path.suffix.lower()=='.pdf':
                raw=doc['pages'][-1]['text']
                # Full-width Latin font: normalize only for identifying review boundaries;
                # preserve offsets and original page text for evidence.
                canonical=''; positions=[]
                for index,char in enumerate(raw):
                    part=unicodedata.normalize('NFKC',char); canonical+=part; positions.extend([index]*len(part))
                start=canonical.find('How"GreenContent"'); end=canonical.find('TheMechanismsandPathwaysofDigital-',start)
                if start<0 or end<0: raise ValueError('Known multi-abstract sample changed; manual boundary review required')
                a,b=positions[start],positions[end]
                exclusions=[{'page':len(doc['pages']),'start':0,'end':a,'reason':'Other articles preceding the target ecological-product abstract'}, {'page':len(doc['pages']),'start':b,'end':len(raw),'reason':'Following digital ecological security article and page footer'}]
                atomic_json(w.root/'reviewed-abstract-exclusions.json',{'source_sha256':row['sha256'],'exclusions':exclusions,'retained_text':raw[a:b],'review':'boundaries identified from article titles; inspect alongside physical PDF page 15'})
                doc=extract_document(path,exclusions)
            result=ingest(w,path,exclusions); results.append(result)
            row.update(kind='paper',pages=len(doc['pages']),chars=len(doc['text']),warnings=doc['warnings'],entry_id=result.get('entry_id'))
            if result.get('entry_id'):
                entry=w.get(result['entry_id']); doc.update(entry_id=entry['entry_id'],title=entry['title'],metadata=entry.get('metadata',{})); documents.append(doc)
        manifest.append(row)
    loader=PromptLoader(w.root); flows=json.loads((loader.package/'assets/workflows.json').read_text(encoding='utf-8'))['workflows']; checks=[]
    representative=next(d for d in documents if '组态' in d['title'])
    for task in flows:
        selected=documents[:3] if task in ('compare','synthesize','writing-style.batch') else [representative]
        opts={'topic':'生态产品价值实现','question':'论文研究对象与样本范围是什么？','variables':{}}
        if task=='references.format': opts['variables']['rules']='Synthetic author-title-year rule for offline preparation only.'
        if task=='translate.abstract': selected=[{**representative,'metadata':{'abstract':'Synthetic abstract for preparation only.'}}]
        try:
            plan=prepare(task,selected,opts,loader)
            checks.append({'task':task,'status':'prepared_not_executed','steps':len(plan['steps']),'fingerprint':plan['fingerprint']})
        except Exception as exc: checks.append({'task':task,'status':'failed','error':str(exc)})
    facts=[]
    for doc in documents:
        for evidence in doc['evidence']:
            if re.search(r'30|双重差分|1896|样本|201[0-9]',evidence['text']):
                facts.append({'entry_id':doc['entry_id'],'title':doc['title'],**evidence,'review_status':'source_excerpt_for_blind_human_check'})
                if sum(f['entry_id']==doc['entry_id'] for f in facts)>=4: break
    atomic_json(w.root/'material-manifest.json',manifest); atomic_json(w.root/'preflight.json',checks); atomic_json(w.root/'fact-check-excerpts.json',facts)
    summary={'status':'prepared','files':len(manifest),'papers':len(documents),'bibliography_records':sum(r.get('records',0) for r in manifest),'workflow_preflight':len(checks),'preflight_failures':[r for r in checks if r['status']=='failed'],'network_called':False}
    atomic_json(w.root/'acceptance-summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--materials',required=True); parser.add_argument('--workspace',required=True)
    args=parser.parse_args(); print(json.dumps(audit(args.materials,args.workspace),ensure_ascii=False,indent=2))
