import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_runtime
from dra_core.native import NativeClient, advance
from dra_core.pipeline import prepare
from dra_core.jobs import execute
from dra_core.markdown_cleanup import inspect_document, apply_operations
from dra_core.source_versions import import_markdown, resolve_document, adopt, persist_candidate


class CleanupIntegrationTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def fixture(self):
        self.w.update({'entry_id': 'p1', 'title': 'Synthetic boundary fixture', 'sources': []})
        path = self.root / 'source.md'
        path.write_text('The sample has\n\n30 provinces, 2018.\n', encoding='utf-8')
        import_markdown(self.w, path, 'p1')
        doc = resolve_document(self.w, 'p1')
        blocks = [b for b in inspect_document(doc)['blocks'] if b['kind'] == 'paragraph']
        self.answers = [
            {'operations': [{'action': 'join_blocks', 'block_ids': [b['block_id'] for b in blocks],
                             'expected_block_hashes': [b['hash'] for b in blocks], 'separator': 'space',
                             'reason': 'Synthetic split inside one sentence', 'source_support': 'Fixture before injection'}], 'unresolved': []},
            {'operations': [], 'heading_tree': [], 'unresolved': []},
            {'checks': [{'change_id': 'change-1', 'supported': True, 'reason': 'Only the injected whitespace is removed'}], 'unresolved': []}]
        return doc, prepare('markdown.clean', [doc], {}, self.loader)

    def submit(self, state, answer, **extra):
        path = self.root / 'answer.json'
        path.write_text(json.dumps({'request_id': state['native_request']['request_id'], 'content': json.dumps(answer), **extra}), encoding='utf-8')
        return advance(self.w, self.loader, state['run_id'], path)

    def test_native_truncated_retry_resume_and_idempotency(self):
        doc, plan = self.fixture()
        with patch('dra_core.llm.load_config', side_effect=AssertionError('Native must not read keys')):
            state = execute(self.w, plan, NativeClient(), self.loader, 'cleanup-native')
            with self.assertRaises(ValueError):
                self.submit(state, self.answers[0], finish_reason='length')
            state = self.submit(state, self.answers[0])
            pending = state['native_request']['request_id']
            self.assertEqual(advance(self.w, self.loader, state['run_id'])['native_request']['request_id'], pending)
            for answer in self.answers[1:]: state = self.submit(state, answer)
            self.assertEqual(state['status'], 'completed')
            artifact = state['artifacts'][0]
            clean = self.w.path(artifact['clean_path'])
            before = clean.read_bytes()
            execute(self.w, plan, NativeClient(), self.loader, state['run_id'])
            self.assertEqual(clean.read_bytes(), before)
            self.assertEqual(clean.read_text(encoding='utf-8'), 'The sample has 30 provinces, 2018.\n')
            self.assertEqual(resolve_document(self.w, 'p1')['text'], doc['text'])
            adopt(self.w, state['run_id'])
            self.assertEqual(resolve_document(self.w, 'p1')['text'], clean.read_text(encoding='utf-8'))
            self.assertEqual(adopt(self.w, state['run_id'])['status'], 'adopted')
            self.assertEqual(len(list((self.w.root / 'runs/cleanup-native/native/submissions').glob('*.json'))), 4)

    def test_fake_api_and_native_share_finalizer(self):
        _, plan = self.fixture()
        from dra_core import markdown_cleanup
        with patch('dra_core.markdown_cleanup.finalize', wraps=markdown_cleanup.finalize) as finalize:
            api = execute(self.w, plan, test_runtime.Fake([json.dumps(x) for x in self.answers]), self.loader, 'fake-api')
            self.assertEqual(finalize.call_count, 1)
            native = execute(self.w, plan, NativeClient(), self.loader, 'native-finalizer')
            for answer in self.answers: native = self.submit(native, answer)
            self.assertEqual(finalize.call_count, 2)
        a = self.w.path(api['artifacts'][0]['clean_path'])
        b = self.w.path(native['artifacts'][0]['clean_path'])
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(json.loads(a.with_name('source-map.json').read_text()), json.loads(b.with_name('source-map.json').read_text()))

    def test_unreviewed_candidate_rejected(self):
        doc, plan = self.fixture()
        persist_candidate(self.w, plan, {'cleanup': {'text': doc['text'], 'changes': [], 'source_map': [],
            'validation': {'passed': True, 'structural_only': True, 'model_reviewed': False}}}, 'unreviewed')
        with self.assertRaises(ValueError): adopt(self.w, 'unreviewed')

    def join(self, blocks):
        return {'action': 'join_blocks', 'block_ids': [b['block_id'] for b in blocks],
                'expected_block_hashes': [b['hash'] for b in blocks], 'separator': 'empty',
                'reason': 'Adversarial synthetic proposal', 'source_support': 'Synthetic fixture'}

    def test_numeric_merge_rejected(self):
        for text in ('Value 12\n\n34 people\n', 'Value 12\n\n% growth\n', 'Value -\n\n30 percent\n'):
            with self.subTest(text=text):
                doc = {'text': text}
                blocks = [b for b in inspect_document(doc)['blocks'] if b['kind'] == 'paragraph']
                with self.assertRaises(ValueError): apply_operations(doc, [self.join(blocks)])

    def test_duplicate_overlap_unknown_fields_rejected(self):
        doc = {'text': 'One\n\nTwo\n\nThree\n'}
        blocks = [b for b in inspect_document(doc)['blocks'] if b['kind'] == 'paragraph']
        op = self.join(blocks[:2])
        for operations in ([op, op], [op, self.join(blocks[1:])],
                           [{**op, 'replacement': 'Invented text'}],
                           [self.join([blocks[0], blocks[0]])]):
            with self.subTest(operations=operations):
                with self.assertRaises(ValueError): apply_operations(doc, operations)

    def test_multiline_html_regions_protected(self):
        for text in ('<table>\n<tr><td>\n## Value 30\n</td></tr>\n</table>\n',
                     '<div class="equation">\n## Value 30\n</div>\n',
                     '<!--\n## archival metadata\n-->\n'):
            with self.subTest(text=text):
                profile = inspect_document({'text': text})
                self.assertEqual(profile['headings'], [], 'HTML region interior must not become editable Markdown heading')

    def test_body_number_not_page_label(self):
        text = 'Opening\n30\nClosing\n'
        doc = {'text': text, 'pages': [{'page': 1, 'start': 0, 'end': len(text)}]}
        number = next(b for b in inspect_document(doc)['blocks'] if b['text'].strip() == '30')
        self.assertEqual(number['kind'], 'paragraph')
        with self.assertRaises(ValueError):
            apply_operations(doc, [{'action': 'remove_layout_block', 'block_id': number['block_id'],
                'expected_block_hash': number['hash'], 'reason': 'Fake page label', 'source_support': 'No layout proof'}])

    def test_repeated_body_sentence_not_header_evidence(self):
        first = 'Repeated research claim.\nOther text.\n'
        second = 'Page two opening.\nRepeated research claim.\nClosing.\n'
        doc = {'text': first + second, 'pages': [{'page': 1, 'start': 0, 'end': len(first)},
            {'page': 2, 'start': len(first), 'end': len(first + second)}]}
        block = inspect_document(doc)['blocks'][0]
        self.assertEqual(block['kind'], 'paragraph', 'Interior recurrence is not repeated page-header evidence')


if __name__ == '__main__': unittest.main()
