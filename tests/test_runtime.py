import json
import sys
import tempfile
import os
import shutil
import uuid
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dra_core.prompt_loader import PromptLoader,PACKAGE
from dra_core.workspace import Workspace,atomic_json
from dra_core.pipeline import prepare,run,messages_for
from dra_core.jobs import execute
from dra_core.io_services import extract_document,parse_bibliography
from dra_core.portability import export_workspace,import_archive,inspect_archive
from dra_core.cli import ingest
from dra_core.llm import Client,RemoteError
from dra_core.dimensions import adopt
from unittest.mock import patch


class Fake:
    def __init__(self,outputs=None,fail_at=None): self.outputs=outputs or []; self.calls=[]; self.fail_at=fail_at
    def public(self): return {'provider':'mock','model':'test-only'}
    def complete(self,messages):
        self.calls.append(messages)
        if len(self.calls)==self.fail_at: raise RuntimeError('simulated interruption')
        value=self.outputs.pop(0) if self.outputs else 'Synthetic analysis; not a research result.'
        return {'content':value,'provider':'mock','model':'test-only','usage':None,'finish_reason':'stop'}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        base=Path(os.environ.get('DRA_TEST_TMP',tempfile.gettempdir())).resolve()
        self.root=base/('dra-test-'+uuid.uuid4().hex); self.root.mkdir(parents=True)
        self.w=Workspace(self.root/'workspace'); self.loader=PromptLoader(self.w.root)
        self.doc={'entry_id':'p1','title':'Synthetic policy study','text':'# Paper\n\nThe sample has 30 provinces.\n\nEvidence only.', 'metadata':{'title':'Synthetic policy study','abstract':'A synthetic test only'},'evidence':[{'id':'ev1','text':'The sample has 30 provinces.','page':1,'start':0,'end':28}]}
    def tearDown(self):
        if self.root.name.startswith('dra-test-') and self.root.parent == Path(os.environ.get('DRA_TEST_TMP',tempfile.gettempdir())).resolve(): shutil.rmtree(self.root)
    def test_catalog_all_valid(self): self.assertEqual(self.loader.check()['errors'],[])
    def test_missing_variable(self):
        with self.assertRaises(ValueError): self.loader.load('filter.explorer')
    def test_json_braces_preserved(self):
        body,_=self.loader.load('card_note.atomic_card_writer'); self.assertIn('"title"',body)
    def test_override_and_missing_resource(self):
        path=self.w.root/'prompts/quant.step_1.md'; path.write_text('USER OVERRIDE',encoding='utf-8')
        self.assertEqual(self.loader.load('quant.step_1')[0],'USER OVERRIDE')
        with self.assertRaises(FileNotFoundError): self.loader.load('quant.step_1',override=self.root/'absent.md')
    def test_unknown_override_variable(self):
        (self.w.root/'prompts/quant.step_1.md').write_text('{unknown}',encoding='utf-8')
        with self.assertRaises(ValueError): self.loader.load('quant.step_1')
    def test_read_steps_and_history(self):
        plan=prepare('read.quant',[self.doc],{},self.loader); fake=Fake(); result=run(plan,fake,self.loader)
        self.assertEqual(len(result['steps']),7); self.assertEqual(len(fake.calls),7)
        self.assertEqual(sum(m['role']=='assistant' for m in fake.calls[-1]),6)
    def test_qual_and_long(self):
        self.assertEqual(len(prepare('read.qual',[self.doc],{},self.loader)['steps']),4)
        self.assertEqual(len(prepare('read.long',[self.doc],{'dimensions':['overview','results']},self.loader)['steps']),2)
    def test_resume_no_duplicate_calls(self):
        plan=prepare('read.quant',[self.doc],{},self.loader)
        with self.assertRaises(RuntimeError): execute(self.w,plan,Fake(fail_at=3),self.loader,'resume')
        fake=Fake(); result=execute(self.w,plan,fake,self.loader,'resume')
        self.assertEqual(result['status'],'completed'); self.assertEqual(len(fake.calls),5)
    def test_batch_resume_skips_completed_and_partial_steps(self):
        from dra_core.batch import run_batch
        plans=[prepare('read.qual',[self.doc],{},self.loader),prepare('read.qual',[{**self.doc,'entry_id':'p2'}],{},self.loader)]
        initial=run_batch(self.w,plans,Fake(fail_at=6),self.loader,'batch-test')
        self.assertEqual(initial['status'],'partial')
        resumed=Fake(); result=run_batch(self.w,[],resumed,self.loader,'batch-test',resume=True)
        self.assertEqual(result['status'],'completed'); self.assertEqual(len(resumed.calls),3)
    def test_resume_prompt_change_rejected(self):
        plan=prepare('read.quant',[self.doc],{},self.loader)
        with self.assertRaises(RuntimeError): execute(self.w,plan,Fake(fail_at=2),self.loader,'change')
        (self.w.root/'prompts/quant.step_1.md').write_text('Different prompt',encoding='utf-8')
        changed=prepare('read.quant',[self.doc],{},self.loader)
        with self.assertRaises(ValueError): execute(self.w,changed,Fake(),self.loader,'change')
    def test_user_artifact_protected(self):
        a=self.w.artifact('p1','card','Human edits',origin='user'); b=self.w.artifact('p1','card','AI replacement')
        self.assertNotEqual(a['path'],b['path']); self.assertEqual(self.w.path(a['path']).read_text(),'Human edits')
    def test_path_traversal(self):
        with self.assertRaises(ValueError): self.w.path('../outside')
    def test_empty_and_source_sidecar(self):
        file=self.root/'note.source.md'; file.write_text('Not paper')
        with self.assertRaises(ValueError): extract_document(file)
        with self.assertRaises(ValueError): prepare('read.quant',[{**self.doc,'text':''}],{},self.loader)
    def test_md_evidence_offsets_and_dedup(self):
        file=self.root/'中文 空格.md'; file.write_text(self.doc['text'],encoding='utf-8'); doc=extract_document(file)
        for ev in doc['evidence']: self.assertEqual(doc['pages'][0]['text'][ev['start']:ev['end']].strip(),ev['text'])
        ingest(self.w,file); self.assertEqual(ingest(self.w,file)['status'],'duplicate')
    def test_translation_chunk_coverage(self):
        text=('Paragraph test. '*200+'\n\n')*8
        plan=prepare('translate.md-chunks',[{**self.doc,'text':text}],{'chunk_chars':1000},self.loader)
        self.assertEqual(''.join(s['chunk'] for s in plan['steps'][1:]),text)
        result=run(plan,Fake(),self.loader); self.assertEqual(len(result['steps']),len(plan['steps']))
    def test_translation_resume_order_above_nine(self):
        plan=prepare('translate.md-chunks',[{**self.doc,'text':'a'*12000}],{'chunk_chars':1000},self.loader)
        values=['glossary']+[f'PART-{i:02}' for i in range(1,13)]
        with self.assertRaises(RuntimeError): execute(self.w,plan,Fake(values.copy(),fail_at=12),self.loader,'order')
        result=execute(self.w,plan,Fake(['PART-11','PART-12']),self.loader,'order')
        data=json.loads((self.w.root/'runs/order/result.json').read_text(encoding='utf-8'))
        self.assertEqual(data['content'],'\n\n'.join(values[1:]))
    def test_cancel_then_explicit_resume(self):
        from dra_core.cli import parser,dispatch
        plan=prepare('read.quant',[self.doc],{},self.loader)
        folder=self.w.root/'runs/cancel'; folder.mkdir(); (folder/'cancel.request').touch()
        with self.assertRaises(InterruptedError): execute(self.w,plan,Fake(),self.loader,'cancel')
        args=parser().parse_args(['jobs','resume','--run-id','cancel','--workspace',str(self.w.root)])
        with patch('dra_core.cli.Client',return_value=Fake()): self.assertEqual(dispatch(args)['status'],'completed')
    def test_custom_dimension_adoption_and_run(self):
        adopt(self.w,'local',[{'dim_name':'Source method','prompt_content':'Analyze the method using source evidence.'}])
        loader=PromptLoader(self.w.root); plan=prepare('read.long',[self.doc],{'dimension_set':'local'},loader)
        self.assertEqual(len(plan['steps']),1); self.assertIn('custom.local.1',plan['steps'][0]['user']); run(plan,Fake(),loader)
    def test_template_legacy_braces_rendered(self):
        body,_=self.loader.load('ai_template.meta_prompt',{'paper_text':'raw {example}','dim_count':4})
        self.assertNotIn('{{',body); self.assertIn('raw {example}',body)
    def test_refs_missing_rules_fails_before_model(self):
        with self.assertRaises(ValueError): prepare('references.format',[self.doc],{},self.loader)
    def test_trace_rejects_fabricated_reference_or_quote(self):
        plan=prepare('references.trace',[self.doc],{},self.loader)
        refs=json.dumps({'references':[{'raw_text':'A real reference','ignore':False}]})
        for trace in ({'reference_order':999,'citations':[]},{'reference_order':1,'citations':[{'quote':'NOT IN SOURCE','confidence':.9}]}):
            with self.assertRaises(ValueError): run(plan,Fake([refs,json.dumps({'citation_traces':[trace]})]),self.loader)
    def test_required_json_schemas_reject_empty(self):
        for task in ('metadata.extract','templates.generate','references.style-analyze','references.format'):
            opts={'variables':{'rules':'Author. Title. Year.'}} if task=='references.format' else {}
            plan=prepare(task,[self.doc],opts,self.loader)
            with self.assertRaises(ValueError): run(plan,Fake(['{}']),self.loader)
    def test_overlimit(self):
        with self.assertRaises(ValueError): prepare('read.quant',[{**self.doc,'text':'a'*150001}],{},self.loader)
    def test_two_column_reading_order_and_image_only(self):
        import pymupdf as fitz
        doc=fitz.open(); page=doc.new_page(width=600,height=800)
        for i in range(10):
            page.insert_text((40,150+i*20),f'LEFT paragraph {i} continuous text and evidence')
            page.insert_text((320,150+i*20),f'RIGHT paragraph {i} continuous text and evidence')
        path=self.root/'columns.pdf'; doc.save(path)
        extracted=extract_document(path)
        self.assertEqual(extracted['pages'][0]['layout'],'two-column-bands')
        self.assertLess(extracted['text'].index('LEFT paragraph 9'),extracted['text'].index('RIGHT paragraph 0'))
        image=page.get_pixmap().tobytes('png'); scan=fitz.open(); scanned=scan.new_page(width=600,height=800); scanned.insert_image(scanned.rect,stream=image)
        pure=self.root/'derived-image-only.pdf'; scan.save(pure); result=extract_document(pure)
        self.assertFalse(result['ocr_executed']); self.assertTrue(any(w['code']=='ocr_required' for w in result['warnings']))
    def test_qa_invented_id_rejected(self):
        plan=prepare('qa',[self.doc],{'question':'Sample?'},self.loader)
        with self.assertRaises(ValueError): run(plan,Fake([json.dumps({'claims':[{'text':'30','kind':'direct','evidence_ids':['fake']} ]})]),self.loader)
    def test_qa_verification_withholds(self):
        plan=prepare('qa',[self.doc],{'question':'Sample?'},self.loader)
        answer={'claims':[{'text':'30 provinces','kind':'direct','evidence_ids':['ev1']}]}
        replies=[json.dumps(answer),json.dumps({'checks':[{'claim_index':0,'supported':False,'reason':'test'}]})]
        fake=Fake(replies*2); result=run(plan,fake,self.loader)
        self.assertEqual(len(fake.calls),4)
        self.assertIn('correction_required',fake.calls[2][-1]['content'])
        self.assertNotIn('30 provinces',result['content']); self.assertTrue(result['warnings'])
    def test_qa_accepted_skips_correction(self):
        plan=prepare('qa',[self.doc],{'question':'Sample?'},self.loader)
        fake=Fake([json.dumps({'claims':[{'text':'30 provinces','kind':'direct','evidence_ids':['ev1']}]}),json.dumps({'checks':[{'claim_index':0,'supported':True}]})])
        result=run(plan,fake,self.loader)
        self.assertEqual(len(fake.calls),2); self.assertIn('30 provinces',result['content'])
    def test_batch_style_individual_inputs(self):
        second={**self.doc,'entry_id':'p2','text':'SECOND PAPER ONLY'}
        plan=prepare('writing-style.batch',[self.doc,second],{},self.loader); fake=Fake()
        run(plan,fake,self.loader)
        self.assertEqual(len(fake.calls),5)
        self.assertNotIn('SECOND PAPER ONLY',json.dumps(fake.calls[0])); self.assertIn('SECOND PAPER ONLY',json.dumps(fake.calls[1]))
        self.assertEqual(len(json.loads(fake.calls[2][-1]['content'])['section_analyses']),2)
    def test_card_from_qa_uses_new_run(self):
        from dra_core.cli import parser,dispatch
        source=self.root/'source.md'; source.write_text('Original source for card.',encoding='utf-8')
        eid=ingest(self.w,source)['entry_id']
        original={'task':'qa','content':'Verified source answer'}
        atomic_json(self.w.root/'runs/source-qa/result.json',original)
        args=parser().parse_args(['cards','from-qa','--workspace',str(self.w.root),'--entry-id',eid,'--run-id','source-qa'])
        with patch('dra_core.cli.Client',return_value=Fake([json.dumps({'title':'Card','summary':'Summary','body_markdown':'Body','tags':[]})])):
            result=dispatch(args)
        self.assertNotEqual(result['run_id'],'source-qa')
        self.assertEqual(json.loads((self.w.root/'runs/source-qa/result.json').read_text()),original)
    def test_secondary_references_check(self):
        plan=prepare('synthesize',[self.doc,{**self.doc,'entry_id':'p2'}],{'variables':{'secondary_references':[{'title':'Synthetic source','authors':['A'],'year':2020}]}},self.loader)
        result=run(plan,Fake(['Synthetic review','S1']),self.loader)
        self.assertEqual(result['steps']['secondary_ref_check']['cited_secondary_references'][0]['year'],2020)
    def test_filter_schema(self):
        plan=prepare('filter.explorer',[self.doc],{'topic':'policy'},self.loader)
        with self.assertRaises(ValueError): run(plan,Fake(['{"score":99,"reason":"wrong scale"}']),self.loader)
    def test_local_migration_roundtrip(self):
        self.w.artifact('p1','card','keep this',origin='user'); archive=self.root/'backup.zip'
        export_workspace(self.w.root,archive); target=self.root/'restored'; import_archive(archive,target)
        self.assertEqual(sorted(p.read_bytes() for p in target.glob('artifacts/**/*.md')), [b'keep this'])
        with self.assertRaises(ValueError): import_archive(archive,target)
    def test_archive_zip_slip(self):
        path=self.root/'evil.zip'
        with zipfile.ZipFile(path,'w') as z: z.writestr('../escape','bad'); z.writestr('manifest.json','{}')
        with self.assertRaises(ValueError): inspect_archive(path)
    def test_http_retry_and_secret_safety(self):
        import httpx
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(429 if len(calls)==1 else 200,json={} if len(calls)==1 else {'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],'usage':{'total_tokens':3}})
        config={'DEEPSEEK_API_KEY':'sk-'+('s'*30),'DEEPSEEK_BASE_URL':'https://api.deepseek.com','DEEPSEEK_MODEL':'test','DRA_COMPARE_API_MAX_RETRIES':'1'}
        client=Client('deepseek',config=config,transport=httpx.MockTransport(handler)); result=client.complete([{'role':'user','content':'test'}])
        self.assertEqual(len(calls),2); self.assertNotIn(config['DEEPSEEK_API_KEY'],json.dumps(result)+json.dumps(client.public()))


if __name__=='__main__': unittest.main()
