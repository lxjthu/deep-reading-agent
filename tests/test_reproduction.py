import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import reproduce


class ReproductionTest(unittest.TestCase):
    def test_inspect_missing_preserves_source(self):
        if not importlib.util.find_spec('pandas'): self.skipTest('optional pandas unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'data.csv';src.write_text('firm,amount\n1,3\n2,\n',encoding='utf-8')
            before=src.read_bytes();result=reproduce.inspect_data(src)
            self.assertEqual(result['rows'],2)
            self.assertEqual(result['columns'][1]['missing'],1)
            self.assertEqual(src.read_bytes(),before)

    def test_execution_needs_stata_success_marker_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code=root/'example.do';code.write_text('display 1\n')
            def fake(command,**kw):
                (Path(kw['cwd'])/'execution.log').write_text('DRA_REPRODUCTION_RC= 198\n')
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch.object(reproduce.subprocess,'run',side_effect=fake):
                result=reproduce.run_stata(code,sys.executable,root/'run')
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['stata_returncode'],198)
            with self.assertRaises(FileExistsError):reproduce.run_stata(code,sys.executable,root/'run')

    def test_portable_report_escaped_code_and_scoped_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/'report.md';report.write_text('# Results\n\n| N | Result |\n|---|---|\n| 2 | checked |\n',encoding='utf-8')
            code=root/'analysis.do';code.write_text('* <script>alert(1)</script>\ndisplay 2',encoding='utf-8')
            result=reproduce.report(root,report,[code])
            page=Path(result['path']);text=page.read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;',text)
            self.assertIn('data-download64',text)
            self.assertTrue((page.parent/'assets/reader.js').is_file())
            self.assertIn('reproduction.html',(page.parent/'index.html').read_text(encoding='utf-8'))
            outside=root.parent/'not-in-workspace.md'
            with self.assertRaises(ValueError):reproduce.report(root,outside)


if __name__=='__main__':unittest.main()
