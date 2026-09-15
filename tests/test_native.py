import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_runtime
from dra_core.native import NativeClient,advance
from dra_core.pipeline import prepare
from dra_core.jobs import execute


class NativeTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown
    # Reuse only the isolated fixture, not the inherited regression methods.
    def submit(self,state,content,**metadata):
        file=self.root/'response.json'
        file.write_text(json.dumps({'request_id':state['native_request']['request_id'],'content':content,**metadata}),encoding='utf-8')
        return advance(self.w,self.loader,state['run_id'],file)

    def test_native_multiturn_and_no_credentials(self):
        with patch('dra_core.llm.load_config',side_effect=AssertionError('must not read credentials')):
            plan=prepare('read.qual',[self.doc],{},self.loader)
            state=execute(self.w,plan,NativeClient(),self.loader,'native-qual')
            first=state['native_request']['request_id']
            self.assertEqual(advance(self.w,self.loader,'native-qual')['native_request']['request_id'],first)
            for i in range(4):
                request=json.loads(Path(state['native_request']['request_path']).read_text(encoding='utf-8'))
                self.assertEqual(sum(m['role']=='assistant' for m in request['messages']),i)
                state=self.submit(state,'Synthetic native answer '+str(i),reported_model='host-test')
            self.assertEqual(state['status'],'completed')
            with self.assertRaises(ValueError): advance(self.w,self.loader,'native-qual',self.root/'response.json')

    def test_invalid_retry_preserves_submissions(self):
        plan=prepare('filter.explorer',[self.doc],{'topic':'test'},self.loader)
        state=execute(self.w,plan,NativeClient(),self.loader,'native-filter')
        with self.assertRaises(ValueError): self.submit(state,'{}')
        result=self.submit(state,'{"score":7,"reason":"Synthetic test"}')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(list((self.w.root/'runs/native-filter/native/submissions').glob('*.json'))),2)

    def test_stale_response_and_prompt_edit_rejected(self):
        plan=prepare('read.qual',[self.doc],{},self.loader)
        state=execute(self.w,plan,NativeClient(),self.loader,'native-stale')
        next_state=self.submit(state,'first answer')
        with self.assertRaises(ValueError): self.submit(state,'outdated answer')
        (self.w.root/'prompts/qual.L1.md').write_text('Changed prompt',encoding='utf-8')
        with self.assertRaises(ValueError): self.submit(next_state,'second answer')

    def test_truncated_response_is_not_resumed_as_completed(self):
        plan=prepare('translate.abstract',[self.doc],{},self.loader)
        state=execute(self.w,plan,NativeClient(),self.loader,'native-truncated')
        with self.assertRaises(ValueError): self.submit(state,'incomplete translation',finish_reason='length')
        result=self.submit(state,'完整的合成测试译文')
        self.assertEqual(result['status'],'completed')
        saved=json.loads((self.w.root/'runs/native-truncated/result.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['content'],'完整的合成测试译文')

    def test_native_batch_resume(self):
        from dra_core.batch import run_batch
        plans=[prepare('translate.abstract',[self.doc],{},self.loader),prepare('translate.abstract',[{**self.doc,'entry_id':'p2'}],{},self.loader)]
        state=run_batch(self.w,plans,NativeClient(),self.loader,'native-batch')
        self.assertEqual(state['status'],'waiting_for_native')
        for item in state['results']: self.submit(item,'合成摘要译文')
        self.assertEqual(run_batch(self.w,[],NativeClient(),self.loader,'native-batch',resume=True)['status'],'completed')

    def test_native_cancel_resume_does_not_read_keys(self):
        from dra_core.cli import parser,dispatch
        state=execute(self.w,prepare('translate.abstract',[self.doc],{},self.loader),NativeClient(),self.loader,'native-cancel')
        (self.w.root/'runs/native-cancel/cancel.request').touch()
        with self.assertRaises(ValueError): self.submit(state,'回答')
        with patch('dra_core.llm.load_config',side_effect=AssertionError('must not read credentials')):
            result=dispatch(parser().parse_args(['jobs','resume','--workspace',str(self.w.root),'--run-id','native-cancel']))
        self.assertEqual(result['status'],'waiting_for_native')


