import sys
import tempfile
import os
import uuid
import shutil
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from dra_core.workspace import Workspace
from dra_core.source_versions import import_markdown, resolve_document, persist_candidate, adopt
from dra_core.portability import export_workspace, import_archive


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ.get('DRA_TEST_TMP',tempfile.gettempdir())).resolve()/('dra-test-'+uuid.uuid4().hex); self.root.mkdir(parents=True)
        self.w = Workspace(self.root/'workspace')
        self.w.update({'entry_id':'paper-test','title':'Test paper','sources':[]})
        self.input = self.root/'paper.md'; self.input.write_text('# Title\n\n## Child\n\nValue 123.', encoding='utf-8')
    def tearDown(self):
        if self.root.name.startswith('dra-test-'): shutil.rmtree(self.root)
    def candidate(self, run='test-run'):
        import_markdown(self.w,self.input,'paper-test')
        doc=resolve_document(self.w,'paper-test')
        return persist_candidate(self.w,{'documents':[doc]}, {'cleanup':{'text':doc['text'].replace('## Child','### Child'), 'changes':[], 'source_map':[], 'validation':{'passed':True,'structural_only':True,'model_reviewed':True}}},run)
    def test_original_unknown_and_adoption(self):
        candidate=self.candidate(); original=resolve_document(self.w,'paper-test')
        self.assertIsNone(original['pages'][0]['page'])
        self.assertIn('## Child',original['text'])
        adopt(self.w,'test-run'); self.assertIn('### Child',resolve_document(self.w,'paper-test')['text'])
        self.assertEqual(adopt(self.w,'test-run')['status'],'adopted')
        self.assertEqual(self.input.read_text(encoding='utf-8'),'# Title\n\n## Child\n\nValue 123.')
    def test_stale_parent_and_edited_candidate(self):
        self.candidate(); doc=resolve_document(self.w,'paper-test')
        self.w.path(doc['source_markdown']).write_text('Human edit',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Parent source changed'): adopt(self.w,'test-run')
    def test_natural_order_missing_duplicate(self):
        folder=self.root/'pages'; folder.mkdir()
        for n in (10,1,2): (folder/f'page_{n}.md').write_text(f'Page {n}',encoding='utf-8')
        imported=import_markdown(self.w,folder,'paper-test'); doc=resolve_document(self.w,'paper-test')
        self.assertEqual([p['page'] for p in doc['pages']],[1,2,10])
        self.assertEqual(imported['warnings'][0]['code'],'missing_pages')
        self.assertEqual(import_markdown(self.w,folder,'paper-test')['status'],'duplicate')
    def test_ambiguous_and_traversal_images(self):
        folder=self.root/'pages'; folder.mkdir()
        for name in ('first','last'): (folder/f'{name}.md').write_text(name,encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Ambiguous'): import_markdown(self.w,folder,'paper-test')
        self.input.write_text('![x](../outside.png)',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'escapes'): import_markdown(self.w,self.input,'paper-test')
    def test_manual_edit_refreshes_evidence_without_rewriting_snapshot(self):
        self.candidate()
        doc = resolve_document(self.w, 'paper-test')
        frozen = self.w.path(self.w.get('paper-test')['sources'][-1]['extracted'])
        before = frozen.read_bytes()
        self.w.path(doc['source_markdown']).write_text('Entirely new paragraph.', encoding='utf-8')
        edited = resolve_document(self.w, 'paper-test')
        self.assertEqual(edited['pages'][0]['text'], 'Entirely new paragraph.')
        self.assertEqual(edited['evidence'][0]['text'], 'Entirely new paragraph.')
        self.assertEqual(edited['source_map'], [])
        self.assertEqual(edited['page_mapping_status'], 'invalidated_by_manual_edit')
        self.assertEqual(frozen.read_bytes(), before)

    def test_cleaned_quote_has_both_source_ranges(self):
        from dra_core.quality import locate_quote
        import_markdown(self.w, self.input, 'paper-test')
        doc = resolve_document(self.w, 'paper-test')
        text = doc['text'].replace('## Child', '### Child')
        mapping = [{'clean_start': 0, 'clean_end': len(text), 'source_ranges': [
            {'source_file': doc['source_markdown'], 'source_version_id': doc['source_version_id'],
             'start': 0, 'end': len(doc['text']), 'match_method': 'structural_edit'}]}]
        persist_candidate(self.w, {'documents':[doc]}, {'cleanup': {'text':text, 'changes':[],
            'source_map':mapping, 'validation':{'passed':True,'model_reviewed':True}}}, 'mapped')
        adopt(self.w, 'mapped')
        clean = resolve_document(self.w, 'paper-test')
        self.assertTrue(clean['pages'])
        self.assertEqual(len(clean['evidence'][0]['source_ranges']), 2)
        match = locate_quote('### Child', [clean])[0]
        self.assertFalse(match['pdf_verbatim'])
        self.assertEqual(match['original_source_ranges'], mapping[0]['source_ranges'])

    def test_roundtrip_versions(self):
        self.candidate(); adopt(self.w,'test-run')
        archive=self.root/'snapshot.dra'; export_workspace(self.w.root,archive)
        dest=self.root/'restored'; import_archive(archive,dest)
        restored=Workspace(dest)
        self.assertEqual(resolve_document(restored,'paper-test'),resolve_document(self.w,'paper-test'))
        self.assertTrue(restored.path('sources/paper-test/versions/clean-test-run/source-map.json').is_file())

if __name__=='__main__': unittest.main()


