import unittest
from pathlib import Path
from test_reader import fixture
from dra_core.workspace import Workspace
from dra_core.reader import build
from dra_core.reader_compare import find, sections

class ReaderCompareTests(unittest.TestCase):
    def test_selection_missing_and_sanitization(self):
        with fixture() as temp:
            w=Workspace(temp)
            for eid,title in [('a','碳汇甲'),('b','碳汇乙'),('c','其他论文')]:
                w.update({'entry_id':eid,'title':title,'sources':[]})
            w.artifact('a','read-quant','## step_1\n\n甲<script>alert(1)</script>\n\n## step_2\n结论')
            w.artifact('c','read-quant','## step_1\nSECRET_UNSELECTED')
            matches=find(w,'碳汇')['matches']
            self.assertEqual([m['reading_reports'] for m in matches],[1,0])
            self.assertEqual(find(w,'missing')['matches'],[])
            result=build(w,['a','b']);page=Path(result['comparison_path']).read_text(encoding='utf-8')
            self.assertIn('尚无精读报告',page);self.assertIn('碳汇乙',page)
            self.assertNotIn('SECRET_UNSELECTED',page);self.assertNotIn('<script>alert',page)
            self.assertIn('data-dimension=',page)
    def test_code_headings_are_not_dimensions(self):
        self.assertEqual(list(sections('## Real\ntext\n```md\n## Fake\n```\n## Next\nend')),['Real','Next'])
