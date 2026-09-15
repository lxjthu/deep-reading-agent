"""Explicit, checkpointed prompt workflows. Model prose lives in Markdown resources."""
from __future__ import annotations
import copy
import json
import re
from .workspace import digest
from .quality import locate_quote,translation_checks


def evidence_documents(documents):
    for doc in documents:
        for ev in doc.get('evidence', []):
            ev.update(evidence_id=ev.get('evidence_id', ev.get('id')), quote=ev.get('quote', ev.get('text', '')), entry_id=doc['entry_id'], title=doc['title'], page_number=ev.get('page_number', ev.get('page')), char_start=ev.get('char_start', ev.get('start')), char_end=ev.get('char_end', ev.get('end')))
    return documents


def prepare(task, documents, options, loader):
    flows = json.loads((loader.package / 'assets/workflows.json').read_text(encoding='utf-8'))['workflows']
    if task not in flows:
        raise ValueError('No implemented workflow: ' + task)
    docs = evidence_documents(copy.deepcopy(documents))
    if not docs:
        raise ValueError('At least one source is required')
    if task=='references.format' and not str(options.get('variables',{}).get('rules','')).strip():
        raise ValueError('Reference formatting requires variables.rules; supply an adopted style preset')
    if any(w.get('code')=='multiple_abstracts_review_required' for d in docs for w in d.get('warnings',[]) if isinstance(w,dict)) and not all(d.get('exclusions') for d in docs if any(w.get('code')=='multiple_abstracts_review_required' for w in d.get('warnings',[]) if isinstance(w,dict))):
        raise ValueError('Multiple-article abstract page needs reviewed exclusions before model analysis')
    if task=='translate.abstract':
        for doc in docs:
            abstract=doc.get('metadata',{}).get('abstract','')
            if not abstract: raise ValueError('Abstract translation requires a known abstract; do not use full text as abstract')
            doc['text']=abstract
    if task=='qa':
        terms=re.findall(r'[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}',options.get('question','').lower())
        for doc in docs:
            ranked=sorted(doc.get('evidence',[]),key=lambda ev:sum(t in ev['quote'].lower() for t in terms),reverse=True)
            used=0; chosen=[]
            for ev in ranked:
                if used+len(ev['quote'])<=70000//len(docs): chosen.append(ev); used+=len(ev['quote'])
            doc['evidence']=chosen
    if any(not d.get('text', '').strip() for d in docs) and not task.startswith(('filter.', 'library.','references.format')):
        raise ValueError('Required source text missing; metadata is not full text')
    if task not in ('compare', 'synthesize', 'writing-style.batch','qa','references.format') and not task.startswith('library.') and len(docs) != 1:
        raise ValueError('Single-paper task accepts exactly one paper; use batch')
    if task in ('compare', 'synthesize', 'writing-style.batch') and len(docs) < 2:
        raise ValueError('Comparative workflow needs at least two papers')
    full = '\n\n'.join('[' + d['entry_id'] + '] ' + d['title'] + '\n' + d.get('text', '') for d in docs)
    if len(full) > 150000 and task != 'translate.md-chunks':
        raise ValueError('Input exceeds 150000 characters; split source explicitly; no silent truncation')
    flow = copy.deepcopy(flows[task])
    steps = flow['steps']
    if task=='qa':
        for original in list(steps):
            steps.append({**copy.deepcopy(original),'id':original['id']+'_correction','conditional':'qa_rejected','depends_on':['answer','verify']})
    if task=='writing-style.batch':
        analyzer=steps[0]
        expanded=[{**copy.deepcopy(analyzer),'id':'section_'+str(i+1),'document_index':i,'depends_on':[]} for i in range(len(docs))]
        steps=expanded+steps[1:]
        for i in range(len(expanded),len(steps)): steps[i]['depends_on']=[s['id'] for s in steps[:i]]
    if task=='read.long' and options.get('dimension_set'):
        name=options['dimension_set']
        if not re.fullmatch(r'[\w-]+',name) or not loader.workspace: raise ValueError('Invalid dimension set name')
        definition=json.loads((loader.workspace/'library/dimensions'/ (name+'.json')).read_text(encoding='utf-8'))
        steps=[]
        for row in definition['dimensions']:
            steps.append({'id':row['id'],'system':['code.conversation_engine.system_prompt'],'user':[row['prompt_id'],'reading.evidence'],'depends_on':[s['id'] for s in steps],'output':'markdown','variables':[]})
    if task == 'read.long' and options.get('dimensions'):
        chosen = options['dimensions']
        found = {s['id']: s for s in steps}
        if set(chosen) - found.keys(): raise ValueError('Unknown dimension')
        steps = [found[name] for name in chosen]
        for i, step in enumerate(steps): step['depends_on'] = [s['id'] for s in steps[:i]]
    first = docs[0]
    metadata = first.get('metadata', first)
    variables = {**{k: metadata.get(k, '') for k in ('title','authors','journal','year','abstract')}, 'full_text':full, 'paper_text':full, 'filename':first.get('title',''), 'dois':metadata.get('doi',''), 'n':len(docs), 'metadata':json.dumps({k:v for k,v in metadata.items() if k not in ('text','pages','evidence')}, ensure_ascii=False), 'source_version':first.get('file_sha256',''), 'context_before':'', 'context_after':'', 'user_prompt':options.get('question',''), 'selected_text':options.get('selection',first.get('text','')), 'genre':options.get('genre','依据论文实际内容判断'), 'introduction':first.get('text','')[:12000]}
    for i in range(1,4):
        pages=first.get('pages',[]); variables['page_'+str(i)]=pages[i-1]['text'] if len(pages)>=i else ''
    variables.update(options.get('variables', {}))
    if task=='markdown.clean':
        from .markdown_cleanup import variables_for
        if len(docs)!=1: raise ValueError('Cleanup requires exactly one source')
        variables.update(variables_for(docs[0]))
    if task=='references.format':
        references=variables.get('references',[{**d.get('metadata',{}),'title':d['title'],'order':i+1} for i,d in enumerate(docs)])
        if not isinstance(references,list) or not references or any(not isinstance(r,dict) or not (r.get('title') or r.get('raw_text')) for r in references): raise ValueError('Reference formatting requires structured reference records')
        variables['references']=[{**row,'order':i+1} for i,row in enumerate(references)]
    for name in ('topic','question','dim_label','dimensions','dim_count'):
        if name in options: variables[name]=options[name]
    if task=='compare':
        variables.setdefault('dimensions','研究问题、理论、方法、主要发现与局限'); variables.setdefault('dim_count',5)
    if task=='synthesize': variables.setdefault('dim_label',options.get('topic','主要发现与局限'))
    if task=='synthesize' and variables.get('secondary_references'):
        rows=variables['secondary_references']
        if not isinstance(rows,list) or any(not isinstance(r,dict) or not (r.get('title') or r.get('raw_text')) for r in rows): raise ValueError('secondary_references requires structured references')
        variables['secondary_candidates']='\n'.join('[S'+str(i+1)+'] '+', '.join(r.get('authors',[]))+' ('+str(r.get('year',''))+') — '+str(r.get('title') or r['raw_text'][:80]) for i,r in enumerate(rows))
        variables['synthesis_body']='PENDING'
        steps.append({'id':'secondary_ref_check','system':[],'user':['synthesis.secondary_ref_check'],'depends_on':['synthesis'],'output':'text'})
    if task=='templates.generate': variables.setdefault('dim_count',5)
    if task=='translate.md-chunks':
        chunks=[]
        text=first['text']; limit=int(options.get('chunk_chars',10000))
        if not 1000 <= limit <= 30000: raise ValueError('chunk_chars must be 1000..30000')
        start=0
        while start<len(text):
            end=min(start+limit,len(text))
            if end<len(text):
                split=text.rfind('\n\n',start+limit//2,end)
                if split>start: end=split+2
            chunks.append((start,end,text[start:end])); start=end
        base=steps[1]; steps=steps[:1]
        for i,(start,end,chunk) in enumerate(chunks):
            step=copy.deepcopy(base); step.update(id=f'translation_{i+1}',chunk=chunk,source_range=[start,end]); steps.append(step)
    # Validate every required static template before the first external call.
    snapshot=[]
    for step in steps:
        for slot in step['system']+step['user']:
            values={**variables, 'glossary':'PENDING', 'chunk':step.get('chunk',full)}
            _, provenance=loader.load(slot, values, options.get('prompt_overrides',{}).get(slot))
            snapshot.append(provenance)
    return {'task':task,'documents':docs,'options':options,'steps':steps,'variables':variables,'prompts':snapshot,'fingerprint':digest({'task':task,'docs':docs,'options':options,'prompts':snapshot,'steps':steps})}


def parse_json(content):
    text=re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
    value=json.loads(text)
    if not isinstance(value,(dict,list)): raise ValueError('Expected JSON object or array')
    return value


def validate(task, step, value, documents, variables=None, completed=None):
    variables=variables or {}; completed=completed or {}
    if task=='markdown.clean':
        from .markdown_cleanup import validate_step
        validate_step(step,value,documents[0],completed)
    if task.startswith('filter.'):
        if not isinstance(value,dict) or not isinstance(value.get('score'),(int,float)) or isinstance(value.get('score'),bool) or not 1<=value['score']<=10 or not isinstance(value.get('reason'),str):
            raise ValueError('Filter requires numeric score 1..10 and reason (source prompt scale)')
    if task=='cards.create':
        if not isinstance(value,dict) or any(not isinstance(value.get(k),str) for k in ('title','summary','body_markdown')) or not isinstance(value.get('tags'),list): raise ValueError('Invalid card schema')
    if task=='qa' and step.startswith('answer'):
        ids={ev['evidence_id'] for d in documents for ev in d.get('evidence',[])}
        if not isinstance(value,dict) or not isinstance(value.get('claims'),list): raise ValueError('QA claims missing')
        for claim in value['claims']:
            kind=claim.get('kind'); refs=claim.get('evidence_ids',[])
            if kind not in ('direct','synthesis','explanation','inference') or not isinstance(claim.get('text'),str) or not isinstance(refs,list): raise ValueError('Invalid QA claim schema')
            if set(refs)-ids: raise ValueError('Invented evidence ID')
            if kind in ('direct','synthesis') and not refs: raise ValueError('Factual claim lacks evidence')
            if kind in ('explanation','inference') and refs: raise ValueError('Explanation/inference must be separated from factual evidence')
    if task=='qa' and step.startswith('verify'):
        answer_id='answer_correction' if step.endswith('_correction') else 'answer'
        claims=completed[answer_id]['parsed']['claims']
        checks=value.get('checks') if isinstance(value,dict) else None
        if not isinstance(checks,list) or any(not isinstance(c,dict) or not isinstance(c.get('claim_index'),int) or not isinstance(c.get('supported'),bool) for c in checks) or sorted(c['claim_index'] for c in checks)!=list(range(len(claims))):
            raise ValueError('QA verifier must check each claim exactly once')
    if task.startswith('references.') and step=='references':
        if not isinstance(value,dict) or not isinstance(value.get('references'),list): raise ValueError('Reference extraction requires references array')
        for row in value['references']:
            if not isinstance(row,dict) or not isinstance(row.get('raw_text'),str) or not row['raw_text'].strip(): raise ValueError('Each extracted reference requires raw_text')
            if row.get('ignore') and not row.get('ignore_reason'): raise ValueError('Ignored reference requires a reason')
    if task=='references.trace' and step=='citations':
        if not isinstance(value,dict) or not isinstance(value.get('citation_traces'),list): raise ValueError('citation_traces array required')
        ids={r['reference_order'] for r in completed['references']['parsed']['references'] if not r.get('ignore')}
        seen=set()
        for row in value['citation_traces']:
            rid=row.get('reference_order')
            if rid not in ids or rid in seen or not isinstance(row.get('citations'),list): raise ValueError('Unknown or repeated reference order')
            seen.add(rid)
            for citation in row['citations']:
                confidence=citation.get('confidence')
                if not isinstance(confidence,(int,float)) or not 0<=confidence<=1: raise ValueError('Citation confidence must be 0..1')
                locations=locate_quote(citation.get('quote',''),documents)
                if not locations: raise ValueError('Citation quote not found in source')
                citation['locations']=locations
        if seen!=ids: raise ValueError('Trace output must include every reference, including empty citation lists')
    if task=='references.format':
        rows=value.get('references') if isinstance(value,dict) else None
        if not isinstance(rows,list) or len(rows)!=len(variables['references']): raise ValueError('Formatted reference count mismatch')
        if [r.get('order') for r in rows]!=list(range(1,len(rows)+1)) or any(not isinstance(r.get('formatted'),str) or not r['formatted'].strip() for r in rows): raise ValueError('Invalid formatted reference order or text')
    if task=='references.style-analyze':
        if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or not value[k].strip() for k in ('format_name','rules')): raise ValueError('Style analysis requires format_name and rules')
    if task=='metadata.extract':
        required={'title','authors','year','journal','doi','abstract','language','confidence'}
        if not isinstance(value,dict) or required-value.keys(): raise ValueError('Metadata fields missing')
        if value['authors'] is not None and (not isinstance(value['authors'],list) or any(not isinstance(a,str) for a in value['authors'])): raise ValueError('Metadata authors must be array or null')
        if not isinstance(value['confidence'],(int,float)) or not 0<=value['confidence']<=1: raise ValueError('Metadata confidence must be 0..1')
    if task=='templates.generate':
        rows=value.get('dimensions') if isinstance(value,dict) else None
        if not isinstance(rows,list) or not rows or not isinstance(value.get('template'),dict): raise ValueError('Template and nonempty dimensions required')
        if any(not isinstance(r.get('prompt_content'),str) or not r['prompt_content'].strip() or not r.get('dim_name') for r in rows): raise ValueError('Every dimension requires a name and prompt_content')
    if task=='library.paper_comment_writer':
        ids={d['entry_id'] for d in documents}; rows=value.get('comments') if isinstance(value,dict) else None
        if not isinstance(rows,list) or any(r.get('entry_id') not in ids or not isinstance(r.get('comment'),str) for r in rows): raise ValueError('Invalid library comments or entry IDs')


def messages_for(plan, step, completed, loader):
    variables={**plan['variables'], 'chunk':step.get('chunk',plan['variables']['full_text'])}
    if plan['task']=='markdown.clean':
        from .markdown_cleanup import variables_for
        variables.update(variables_for(plan['documents'][0],completed))
    if step['id']=='secondary_ref_check': variables['synthesis_body']=completed['synthesis']['content']
    if 'glossary' in completed: variables['glossary']=completed['glossary']['content']
    provenance=[]; messages=[]
    for slot in step['system']:
        body, meta=loader.load(slot,variables,plan['options'].get('prompt_overrides',{}).get(slot)); messages.append({'role':'system','content':body}); provenance.append(meta)
    task=plan['task']
    if task=='qa':
        data={'question':plan['options'].get('question',''), 'evidence':[ev for d in plan['documents'] for ev in d.get('evidence',[])], 'scope':[{'entry_id':d['entry_id'],'title':d['title']} for d in plan['documents']]}
        if step['id'].startswith('verify'): data['draft']=completed['answer_correction' if step['id'].endswith('_correction') else 'answer']['parsed']['claims']
        if step['id']=='answer_correction':
            data['previous_draft']=completed['answer']['parsed']
            data['correction_required']=[c.get('reason','Unsupported claim '+str(c['claim_index'])) for c in completed['verify']['parsed']['checks'] if not c['supported']]
        if plan['options'].get('history'): data['history']=plan['options']['history']
        messages.append({'role':'user','content':json.dumps(data,ensure_ascii=False)})
    elif task.startswith('writing-style.'):
        papers=[{'metadata':{**d.get('metadata',{}),'entry_id':d['entry_id'],'title':d['title']},'source_mode':'full_markdown','full_markdown':d['text']} for d in plan['documents']]
        if step['id'].startswith('section_') or step['id']=='single_fulltext_analyzer':
            data=papers[step.get('document_index',0)]
        else:
            data={'papers':[{k:v for k,v in p.items() if k!='full_markdown'} for p in papers], 'section_analyses':[v['content'] for k,v in completed.items() if k.startswith('section_') or k=='single_fulltext_analyzer']}
            if step['id'].endswith('report_writer'):
                data.update(imitation_advice=next((v['content'] for k,v in completed.items() if k.endswith('imitation_advisor')),''),comparative=next((v['content'] for k,v in completed.items() if k.endswith('comparative_synthesizer')),None),skipped=[])
        messages.append({'role':'user','content':json.dumps(data,ensure_ascii=False)})
    elif task=='references.trace' and step['id']=='citations':
        messages.append({'role':'user','content':json.dumps({'body_text':plan['variables']['full_text'],'references':completed['references']['parsed']['references']},ensure_ascii=False)})
    elif task=='references.format':
        messages.append({'role':'user','content':json.dumps({'rules':variables['rules'],'references':variables['references']},ensure_ascii=False)})
    elif task!='markdown.clean' and not task.startswith('translate.'):
        messages.append({'role':'user','content':json.dumps({'documents':[{k:d.get(k) for k in ('entry_id','title','text','metadata')} for d in plan['documents']], 'request':plan['options'].get('question',''), 'parameters':plan['options'].get('variables',{})},ensure_ascii=False)})
    for dependency in step.get('depends_on',[]):
        if dependency in completed and task!='qa' and not task.startswith('writing-style.'):
            previous=completed[dependency]
            messages.extend([{'role':'user','content':previous.get('instruction',dependency)}, {'role':'assistant','content':previous['content']}])
    instruction=[]
    for slot in step['user']:
        body,meta=loader.load(slot,variables,plan['options'].get('prompt_overrides',{}).get(slot)); instruction.append(body); provenance.append(meta)
    if instruction: messages.append({'role':'user','content':'\n\n'.join(instruction)})
    expected={(p['id'],p['sha256']) for p in plan['prompts']}
    if any((p['id'],p['sha256']) not in expected for p in provenance): raise ValueError('Prompt changed during run; re-prepare explicitly')
    return messages,provenance,'\n\n'.join(instruction)


def run(plan,llm,loader,checkpoint=None,resume=None):
    completed=dict(resume or {})
    for step in plan['steps']:
        if step.get('conditional')=='qa_rejected' and all(c['supported'] for c in completed['verify']['parsed']['checks']): continue
        messages,provenance,instruction=messages_for(plan,step,completed,loader)
        request_hash=digest(messages)
        if step['id'] in completed:
            if completed[step['id']].get('request_hash') != request_hash: raise ValueError('Checkpoint input or prompt changed; start a new run')
            continue
        if hasattr(llm,'set_step'): llm.set_step(step)
        response=llm.complete(messages)
        result={**response,'messages':messages,'prompts':provenance,'instruction':instruction,'request_hash':request_hash,'step_id':step['id']}
        if plan['task'].startswith('read.'):
            marker=re.search(r'<!--SOURCE_EVIDENCE_JSON\s*(.*?)\s*SOURCE_EVIDENCE_JSON-->',response['content'],re.S)
            located=[]
            if marker:
                items=json.loads(marker[1]).get('items',[])
                for item in items:
                    quote=item.get('quote',''); matches=locate_quote(quote,plan['documents'])
                    located.append({**item,'locations':matches,'quote_verified':bool(matches)})
            result['source_evidence']=located
            result['evidence_status']='located' if located and all(x['quote_verified'] for x in located) else 'missing_or_unverified'
        if response.get('truncated') or response.get('finish_reason')=='length':
            if checkpoint: checkpoint(step['id']+'.truncated',result)
            raise ValueError('Model output truncated; checkpoint retained, step not completed')
        if step['id']=='secondary_ref_check':
            text=response['content'].strip()
            if text!='无' and not re.fullmatch(r'S\d+(?:\s*[,，]\s*S\d+)*',text): raise ValueError('Invalid secondary citation check format')
            ids=sorted({int(n) for n in re.findall(r'S(\d+)',text)})
            if any(n<1 or n>len(plan['variables']['secondary_references']) for n in ids): raise ValueError('Invented secondary reference identifier')
            result['cited_secondary_references']=[plan['variables']['secondary_references'][i-1] for i in ids]
        if step['output']=='json':
            try:
                result['parsed']=parse_json(response['content']); validate(plan['task'],step['id'],result['parsed'],plan['documents'],plan['variables'],completed)
                if step['id']=='references':
                    order=0
                    for row in result['parsed']['references']:
                        if not row.get('ignore'): order+=1; row['reference_order']=order
            except ValueError:
                if checkpoint: checkpoint(step['id']+'.invalid',{**result,'step_id':step['id']+'.invalid'})
                raise
        completed[step['id']]=result
        if checkpoint: checkpoint(step['id'],result)
    warnings=[]
    if plan['task']=='markdown.clean':
        from .markdown_cleanup import finalize
        cleanup=finalize(plan['documents'][0],completed)
        return {'status':'completed','task':plan['task'],'steps':completed,'content':cleanup['text'],'cleanup':cleanup,'warnings':cleanup['validation']['unresolved'],'quality_status':'validated_candidate' if cleanup['validation']['passed'] else 'needs_review'}
    if plan['task'].startswith('read.') and any(s.get('evidence_status')!='located' for s in completed.values()):
        warnings.append('Some reading evidence is missing or not located in source; review required')
    if plan['task']=='qa':
        claims=completed.get('answer_correction',completed['answer'])['parsed']['claims']; checks=completed.get('verify_correction',completed['verify'])['parsed'].get('checks',[])
        if sorted(c.get('claim_index',-1) for c in checks)!=list(range(len(claims))) or any(not isinstance(c.get('supported'),bool) for c in checks): raise ValueError('QA verifier must check each claim exactly once')
        accepted=[claims[c['claim_index']] for c in checks if c['supported']]
        if len(accepted)<len(claims): warnings.append('Unsupported claims withheld; inspect draft and verifier separately')
        labels={'direct':'原文摘述','synthesis':'原文综合','explanation':'知识拓展','inference':'有条件推断'}
        output='\n\n'.join('### '+labels[c['kind']]+'\n\n'+c['text']+('\n\n证据：'+', '.join(c['evidence_ids']) if c['evidence_ids'] else '') for c in accepted)
        if not output: output='本轮未得到通过核验的回答。请查阅原文证据与核验记录。'
    elif plan['task'].startswith('translate.'):
        output='\n\n'.join(completed[s['id']]['content'] for s in plan['steps'] if s['id'].startswith('translation'))
    else:
        output='\n\n'.join('## '+s['id']+'\n\n'+completed[s['id']]['content'] for s in plan['steps'])
    checks=translation_checks(plan['documents'][0]['text'],output) if plan['task'].startswith('translate.') else None
    return {'status':'completed','task':plan['task'],'steps':completed,'content':output,'warnings':warnings,'quality_checks':checks,'quality_status':'requires_source_and_user_review'}
