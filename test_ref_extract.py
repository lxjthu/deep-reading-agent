import sys, os, traceback, glob
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
from dotenv import load_dotenv
load_dotenv()

pdfs = glob.glob('_uploads/**/*.pdf', recursive=True)
pdf_path = max(pdfs, key=os.path.getmtime)
print('Testing:', pdf_path)

try:
    from routers.references import write_trace_outputs, persist_trace_success
    from services.deepseek_refs import extract_references_deepseek, trace_citations_deepseek

    refs = extract_references_deepseek(pdf_path, api_key=None)
    print(f'Step 1: {len(refs)} refs extracted')
    if not refs:
        print('No refs, abort')
        sys.exit(0)

    refs = trace_citations_deepseek(pdf_path, refs, api_key=None)
    print('Step 2: citation tracing done')

    from db.utils import compute_dedup_key
    for ref in refs:
        ref['dedup_key'] = compute_dedup_key(
            ref.get('doi'), ref.get('title') or ref.get('raw_text', '')[:80],
            ref.get('authors', []), ref.get('year'))
        ref.setdefault('citations', [])

    print('Step 3: dedup keys computed')
    artifacts = write_trace_outputs(1, 'test-task-id', 'test-title', refs)
    print(f'Step 4: write_trace_outputs -> {len(artifacts)} artifacts')
    for a in artifacts:
        print(f'  {a["artifact_type"]}: {a["absolute_path"]}')

    import asyncio
    asyncio.run(persist_trace_success('test-ref-task', 1, 'test-bib-id', refs, artifacts))
    print('Step 5: persist_trace_success done')

except Exception as e:
    traceback.print_exc()
