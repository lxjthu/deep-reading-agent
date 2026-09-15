"""Conservative structural edits: models propose IDs; Python owns text and offsets."""
from __future__ import annotations
import json
import re
from .workspace import digest


def sha(text):
    return digest(text.encode('utf-8'))


def inspect_document(document):
    text = document['text']
    lines = text.splitlines(keepends=True)
    blocks = []; offset = 0; i = 0
    warnings = list(document.get('warnings', []))
    while i < len(lines):
        start = offset; first = i; line = lines[i]; stripped = line.strip()
        kind = 'paragraph'; level = None; stop = i + 1
        if not stripped: kind = 'whitespace'
        elif i == 0 and stripped == '---':
            kind = 'protected'
            while stop < len(lines) and lines[stop].strip() not in ('---', '...'): stop += 1
            stop = min(stop + 1, len(lines))
        elif re.match(r'^\s*(`{3,}|~{3,})', line):
            kind = 'protected'; fence = re.match(r'^\s*(`{3,}|~{3,})', line)[1]
            while stop < len(lines) and not re.match(r'^\s*' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*$', lines[stop]): stop += 1
            if stop == len(lines): warnings.append('unclosed_fence')
            stop = min(stop + 1, len(lines))
        elif stripped.startswith('<') or stripped.startswith(('$$', '\\[', '\\begin{')):
            kind = 'protected'
            if stripped.startswith('<'):
                tag = re.match(r'<([A-Za-z][\w-]*)\b', stripped)
                if stripped.startswith('<!--'): close_html = '-->'
                elif tag and tag[1].lower() not in ('img','br','hr','input','meta','link','wbr','source') and not stripped.endswith('/>'):
                    close_html = '</' + tag[1].lower() + '>'
                else: close_html = None
                if close_html:
                    while stop < len(lines) and close_html not in ''.join(lines[i:stop]).lower(): stop += 1
                    if close_html not in ''.join(lines[i:stop]).lower(): warnings.append('unclosed_html')
            elif stripped.startswith(('$$', '\\[', '\\begin{')):
                close = '$$' if stripped.startswith('$$') else '\\]' if stripped.startswith('\\[') else '\\end{'
                if close not in stripped[len(close):]:
                    while stop < len(lines) and close not in lines[stop]: stop += 1
                    stop = min(stop + 1, len(lines))
        elif re.match(r'^\s*#{1,6}\s+', line):
            kind = 'heading'; level = len(re.match(r'^\s*(#+)', line)[1])
        elif stop < len(lines) and stripped and re.fullmatch(r'\s*(?:=+|-+)\s*', lines[stop]):
            kind = 'heading'; level = 1 if '=' in lines[stop] else 2; stop += 1
        elif len(stripped) <= 100 and re.match(r'^(?:[一二三四五六七八九十]+[、．.]|[（(][一二三四五六七八九十]+[）)])\s*\S', stripped):
            kind = 'heading_candidate'; level = 0
        elif (re.match(r'^\s*(?:\||\[\^|!\[|\d+[.)]\s|[-*+]\s|>)', line)
              or '$' in line or re.match(r'^ {4}\S', line)):
            kind = 'protected'
            while stop < len(lines) and lines[stop].strip(): stop += 1
        elif re.match(r'^\s*(?:图|表|Figure|Table)\s*[\d一二三四五六七八九十]', line, re.I): kind = 'protected'
        elif re.fullmatch(r'\s*(?:第\s*)?\d+\s*(?:页)?\s*', line): kind = 'layout_candidate'
        body = ''.join(lines[i:stop]); offset += len(body)
        block = {'block_id': 'b-' + sha(text)[:12] + '-' + str(start), 'hash': sha(body),
                 'start': start, 'end': offset, 'line_start': first+1, 'line_end': stop,
                 'kind': kind, 'text': body, 'level': level, 'physical_page': None, 'printed_page': None}
        for page in document.get('pages', []):
            ps = page.get('char_start', page.get('start'))
            pe = page.get('char_end', page.get('end'))
            if ps is not None and pe is not None and ps <= start < pe:
                block['physical_page'] = page.get('physical_page', page.get('page'))
                block['printed_page'] = page.get('printed_page'); break
        blocks.append(block); i = stop
    # A standalone number in the body is not sufficient evidence of a page label.
    page_blocks = {}
    for b in blocks:
        if b['physical_page'] is not None and b['text'].strip(): page_blocks.setdefault(b['physical_page'], []).append(b)
    for b in blocks:
        if b['kind'] == 'layout_candidate':
            same_page = page_blocks.get(b['physical_page'], [])
            number = re.search(r'\d+', b['text'])[0]
            if not same_page or b not in (same_page[0], same_page[-1]) or number not in (str(b['physical_page']), str(b['printed_page'])):
                b['kind'] = 'paragraph'
    # Repeated short text is only a candidate at an explicitly known page edge.
    counts = {}
    for page, items in page_blocks.items():
        for b in (items[0], items[-1]): counts.setdefault(b['text'].strip(), set()).add(page)
    for n, b in enumerate(blocks):
        same_page = page_blocks.get(b['physical_page'], [])
        edge = same_page and b in (same_page[0], same_page[-1])
        if b['kind'] == 'paragraph' and edge and len(b['text'].strip()) < 100 and len(counts.get(b['text'].strip(), [])) >= 2: b['kind'] = 'layout_candidate'
    return {'source_sha256': sha(text), 'blocks': blocks, 'headings': [b for b in blocks if b['kind'] in ('heading','heading_candidate')],
            'warnings': warnings, 'page_mapping_status': document.get('page_mapping_status', 'unknown'),
            'protected_count': sum(b['kind']=='protected' for b in blocks)}


def _heading_text(block):
    lines = block['text'].splitlines()
    return re.sub(r'^\s*#{1,6}\s+', '', lines[0]) if re.match(r'^\s*#', lines[0]) else lines[0]


def apply_operations(document, operations):
    profile = inspect_document(document); blocks = profile['blocks']; by_id = {b['block_id']: b for b in blocks}
    edits = []; used = set()
    if not isinstance(operations, list): raise ValueError('operations must be an array')
    for op in operations:
        if not isinstance(op, dict) or not isinstance(op.get('reason'), str) or not op['reason'].strip() or not op.get('source_support'): raise ValueError('Each operation requires reason and source_support')
        if set(op) - {'action','block_ids','block_id','expected_block_hashes','expected_block_hash','reason','source_support','separator','level'}: raise ValueError('Unknown cleanup operation fields; arbitrary replacement is forbidden')
        action = op.get('action'); ids = op.get('block_ids', [op.get('block_id')])
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or any(k not in by_id for k in ids): raise ValueError('Unknown or duplicate block ID')
        selected = [by_id[k] for k in ids]
        if used.intersection(ids): raise ValueError('Overlapping operations')
        hashes = op.get('expected_block_hashes', [op.get('expected_block_hash')])
        if hashes != [b['hash'] for b in selected]: raise ValueError('Stale block hash')
        if any(b['kind']=='protected' for b in selected): raise ValueError('Protected region cannot be edited')
        start = selected[0]['start']; end = selected[-1]['end']; old = document['text'][start:end]
        if action in ('set_heading_level', 'normalize_heading_whitespace'):
            if len(selected)!=1 or selected[0]['kind'] not in ('heading','heading_candidate'): raise ValueError('Only indexed headings may be changed')
            level = op.get('level', selected[0]['level'])
            if isinstance(level, bool) or not isinstance(level,int) or not 0<=level<=6: raise ValueError('Invalid heading level')
            title = _heading_text(selected[0]); ending = '\n' if old.endswith('\n') else ''
            if action=='normalize_heading_whitespace':
                title = re.sub(r'\s+', ' ', title).strip()
                title = re.sub(r'(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])', '', title)
                level = selected[0]['level']
            new = ('#'*level+' ' if level else '') + title + ending
        elif action in ('join_blocks','normalize_boundary_whitespace'):
            if len(selected)<2 or any(b['kind']!='paragraph' for b in selected): raise ValueError('Only adjacent prose boundaries may be joined')
            if selected != sorted(selected,key=lambda b:b['start']): raise ValueError('Block order mismatch')
            for a,b in zip(selected,selected[1:]):
                if document['text'][a['end']:b['start']].strip(): raise ValueError('Cannot skip source content')
            separator = {'empty':'','space':' ','newline':'\n'}.get(op.get('separator'))
            if separator is None: raise ValueError('Invalid separator')
            new = separator.join(b['text'].strip() for b in selected) + ('\n' if old.endswith('\n') else '')
            if re.sub(r'\s','',old)!=re.sub(r'\s','',new): raise ValueError('Boundary edit changed source characters')
            numbers = lambda s: re.findall(r'[+-]?\d+(?:[.,]\d+)*(?:%|％)?', s)
            if numbers(old) != numbers(new): raise ValueError('Boundary edit changed numeric tokens')
        elif action=='remove_layout_block':
            if len(selected)!=1 or selected[0]['kind']!='layout_candidate': raise ValueError('Not an indexed layout candidate')
            if selected[0]['physical_page'] is None: raise ValueError('Layout removal needs explicit page provenance')
            new = ''
        else: raise ValueError('Unsupported cleanup action')
        if any(not (end<=e['start'] or start>=e['end']) for e in edits): raise ValueError('Overlapping source ranges')
        used.update(ids)
        edits.append({'change_id':'change-'+str(len(edits)+1),'action':action,'start':start,'end':end,'before':old,'after':new,
                      'block_ids':ids,'reason':op['reason'],'source_support':op['source_support']})
    edits.sort(key=lambda e:e['start']); parts=[]; mapping=[]; pos=0; clean_pos=0
    def append(text,start,end,method):
        nonlocal clean_pos
        if not text: return
        ranges=[]
        for b in blocks:
            a=max(start,b['start']); z=min(end,b['end'])
            if a<z: ranges.append({'source_file':document.get('source_markdown'), 'source_version_id':document.get('source_version_id'),
                                  'start':a,'end':z,'block_hash':b['hash'],'physical_page':b['physical_page'], 'printed_page':b['printed_page'],'match_method':method})
        parts.append(text); mapping.append({'clean_start':clean_pos,'clean_end':clean_pos+len(text),'source_ranges':ranges}); clean_pos+=len(text)
    for e in edits:
        append(document['text'][pos:e['start']],pos,e['start'],'unchanged')
        append(e['after'],e['start'],e['end'],'structural_edit'); pos=e['end']
    append(document['text'][pos:],pos,len(document['text']),'unchanged')
    clean=''.join(parts)
    return {'text':clean,'changes':edits,'source_map':mapping,'validation':{'passed':True,'structural_only':True,'protected_blocks_unchanged':True,
            'source_sha256':sha(document['text']),'clean_sha256':sha(clean),'warnings':profile['warnings'],'model_reviewed':False}}


def proposal_operations(completed):
    return [op for key in ('boundaries','headings') if key in completed for op in completed[key]['parsed']['operations']]


def variables_for(document, completed=None):
    completed=completed or {}; profile=inspect_document(document)
    boundaries=[]; blocks=profile['blocks']
    for i,b in enumerate(blocks):
        if b['kind'] in ('paragraph','layout_candidate'):
            boundaries.append({'block':b,'next':blocks[i+1:i+3]})
    applied=apply_operations(document,proposal_operations(completed))
    values={'document_profile_json':{k:v for k,v in profile.items() if k not in ('blocks','headings')},
            'boundary_context_json':boundaries,'protected_blocks_json':[{'block_id':b['block_id'],'kind':b['kind'],'hash':b['hash']} for b in blocks if b['kind']=='protected'],
            'heading_candidates_json':profile['headings'],'heading_context_json':profile['headings'],
            'structure_constraints_json':{'protected_count':profile['protected_count'],'source_sha256':profile['source_sha256']},
            'changes_with_context_json':applied['changes'],'deterministic_checks_json':applied['validation'],
            'source_mapping_summary_json':applied['source_map']}
    return {k:json.dumps(v,ensure_ascii=False) for k,v in values.items()}


def validate_step(step,value,document,completed):
    if not isinstance(value,dict) or not isinstance(value.get('unresolved'),list): raise ValueError('Cleanup response requires unresolved array')
    if step=='verify':
        changes=apply_operations(document,proposal_operations(completed))['changes']; checks=value.get('checks')
        if not isinstance(checks,list) or any(not isinstance(c,dict) or not isinstance(c.get('supported'),bool) or not c.get('reason') for c in checks): raise ValueError('Invalid cleanup checks')
        if sorted(c.get('change_id','') for c in checks)!=sorted(c['change_id'] for c in changes): raise ValueError('Verifier must check every change exactly once')
    else:
        permitted={'boundaries':{'join_blocks','remove_layout_block','normalize_boundary_whitespace'},'headings':{'set_heading_level','normalize_heading_whitespace'}}[step]
        if not isinstance(value.get('operations'),list) or any(op.get('action') not in permitted for op in value['operations']): raise ValueError('Invalid operations for this cleanup step')
        apply_operations(document,proposal_operations(completed)+value['operations'])
        if step=='headings':
            headings=inspect_document(document)['headings']; tree=value.get('heading_tree')
            if not isinstance(tree,list) or [x.get('block_id') for x in tree]!=[b['block_id'] for b in headings]: raise ValueError('Heading tree must cover original headings in order')
            levels={b['block_id']:b['level'] for b in headings}
            for op in value['operations']:
                if op['action']=='set_heading_level': levels[op['block_id']]=op['level']
            stack=[]
            for row in tree:
                level=row.get('level')
                if level!=levels[row['block_id']]: raise ValueError('Heading tree differs from proposed edits')
                while stack and stack[-1]['level']>=level: stack.pop()
                parent=stack[-1]['block_id'] if stack and level else None
                if row.get('parent_block_id')!=parent: raise ValueError('Incorrect heading parent')
                if level: stack.append(row)


def finalize(document,completed):
    result=apply_operations(document,proposal_operations(completed))
    unresolved=[x for row in completed.values() for x in row.get('parsed',{}).get('unresolved',[])]
    checks=completed['verify']['parsed']['checks']
    blocking = [w for w in result['validation']['warnings'] if (w.get('code') if isinstance(w,dict) else w) in
                ('unclosed_fence','unclosed_html','missing_pages','duplicate_page_content','missing_image','multiple_abstracts_review_required')]
    result['validation'].update(model_reviewed=True,model_checks=checks,unresolved=unresolved,blocking_warnings=blocking,
        passed=not unresolved and not blocking and all(c['supported'] for c in checks))
    return result
