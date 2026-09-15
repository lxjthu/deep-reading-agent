import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dra_core.markdown_cleanup import inspect_document,apply_operations,validate_step


class CleanupTests(unittest.TestCase):
    def test_heading_and_protection(self):
        doc={'text':'# 标题\n\n## （一）方法\n\n<table><tr><td>2018</td></tr></table>\n\n$$x^2=30$$\n'}
        profile=inspect_document(doc); b=profile['headings'][1]
        op={'action':'set_heading_level','block_id':b['block_id'],'expected_block_hash':b['hash'],'level':3,'reason':'子节','source_support':'原文编号'}
        result=apply_operations(doc,[op])
        self.assertIn('### （一）方法',result['text']); self.assertIn('<td>2018</td>',result['text'])
        self.assertEqual(result['text'].replace('###','##'),doc['text'])
        self.assertTrue(all(m['source_ranges'] for m in result['source_map']))
        for protected in (x for x in profile['blocks'] if x['kind']=='protected'):
            with self.assertRaises(ValueError): apply_operations(doc,[{**op,'block_id':protected['block_id'],'expected_block_hash':protected['hash']}])

    def test_boundary_and_hash(self):
        doc={'text':'跨页段落前半\n\n后半内容，2018 年。\n'}
        bs=[b for b in inspect_document(doc)['blocks'] if b['kind']=='paragraph']
        op={'action':'join_blocks','block_ids':[b['block_id'] for b in bs],'expected_block_hashes':[b['hash'] for b in bs],'separator':'empty','reason':'跨页','source_support':'两侧正文'}
        self.assertEqual(apply_operations(doc,[op])['text'],'跨页段落前半后半内容，2018 年。\n')
        with self.assertRaises(ValueError): apply_operations(doc,[{**op,'expected_block_hashes':['bad']*2}])
        with self.assertRaises(ValueError): apply_operations(doc,[op,op])

    def test_unknown_pages_cannot_delete(self):
        doc={'text':'123\n正文\n'}; b=inspect_document(doc)['blocks'][0]
        with self.assertRaises(ValueError): apply_operations(doc,[{'action':'remove_layout_block','block_id':b['block_id'],'expected_block_hash':b['hash'],'reason':'页码','source_support':'猜测'}])

    def test_fence_setext_and_empty_verify(self):
        profile=inspect_document({'text':'标题\n====\n\n```python\n# code\n```\n'})
        self.assertEqual(len(profile['headings']),1)
        self.assertEqual(profile['headings'][0]['level'],1)
        validate_step('verify',{'checks':[],'unresolved':[]},{'text':'正文'}, {})
        with self.assertRaises(ValueError): validate_step('verify',{'checks':[{'change_id':'invented','supported':True,'reason':'ok'}],'unresolved':[]},{'text':'正文'}, {})


if __name__=='__main__': unittest.main()
