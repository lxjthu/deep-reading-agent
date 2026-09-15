import json
import sys
import uuid
import shutil
from contextlib import contextmanager

@contextmanager
def fixture():
    root=Path(__file__).resolve().parent / ("reader-fixture-"+uuid.uuid4().hex)
    root.mkdir()
    try:yield str(root)
    finally:shutil.rmtree(root)

import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dra_core.workspace import Workspace, atomic_json
from dra_core.reader import build
from dra_core.reader_render import render


class ReaderTests(unittest.TestCase):
    def test_markdown_and_untrusted_html(self):
        source='---\ntitle: test\n---\n\nHeading\n=======\n\n## Nested\n\n- One\n- Two\n\n> Quote\n\n```python\nprint(1)\n```\n\n| X | Y |\n|---|---|\n| 1 | 2 |\n\nFoot[^a]\n\n[^a]: note\n\n$x^2$\n\n<table><tr><td rowspan="2">30</td></tr></table>\n<script>alert(1)</script><iframe src="https://evil.test"></iframe><img src="https://evil.test/x" onerror="boom()">\n[bad](javascript:alert(1))\n'
        result=render(source)
        for fragment in ('<h1','<h2','<li>','<blockquote>','<code','rowspan="2"','data-tex="x^2"','footnote'):
            self.assertIn(fragment,result['html'])
        for fragment in ('<script','<iframe','onerror','javascript:','src="https:'):
            self.assertNotIn(fragment,result['html'])
        self.assertNotIn('title: test',result['toc'])

    def test_images_bounded_and_copied(self):
        with fixture() as temp:
            root=Path(temp);src=root/'source';src.mkdir();out=root/'out';out.mkdir()
            (src/'x.png').write_bytes(b'png');(root/'secret.png').write_bytes(b'secret')
            result=render('![ok](x.png) ![bad](../secret.png)',src/'a.md',out)
            self.assertEqual(len(list((out/'media').iterdir())),1)
            self.assertIn('media/',result['html']);self.assertNotIn('secret.png',result['html'])

    def test_build_selection_collection_and_immutable_snapshots(self):
        with fixture() as temp:
            ws=Workspace(temp)
            for eid in ('a','b'):
                folder=ws.path('sources/'+eid);folder.mkdir()
                (folder/'raw.md').write_text('# Body '+eid,encoding='utf-8')
                ws.update({'entry_id':eid,'title':'Title '+eid,'metadata':{'authors':['Author'],'year':'2026'},'sources':[{'markdown':'sources/'+eid+'/raw.md'}]})
            artifact=ws.artifact('collection','compare','# Collection')
            atomic_json(ws.path('runs/r/state.json'),{'status':'completed','task':'compare','artifacts':[artifact]})
            atomic_json(ws.path('runs/r/plan.json'),{'documents':[{'entry_id':'a'},{'entry_id':'b'}]})
            one=build(ws,['a']);self.assertEqual(one['collection_count'],0)
            first=Path(one['path']);self.assertNotIn('Title b',first.read_text(encoding='utf-8'))
            first.write_text('User edited snapshot',encoding='utf-8')
            two=build(ws);self.assertEqual(two['collection_count'],1)
            self.assertEqual(first.read_text(encoding='utf-8'),'User edited snapshot')
            snapshot=Path(two['path']).parent
            self.assertFalse(list(snapshot.rglob('.env')))
            self.assertFalse(list(snapshot.rglob('plan.json')))
            self.assertTrue((snapshot/'assets/katex/katex.min.js').is_file())

    def test_clean_artifact_parent_comparison_and_unique_anchors(self):
        import re
        with fixture() as temp:
            ws=Workspace(temp)
            folder=ws.path('sources/a/versions/raw-1');folder.mkdir(parents=True)
            (folder/'raw.md').write_text('# Shared\n\nOriginal',encoding='utf-8')
            atomic_json(folder/'manifest.json',{'version_id':'raw-1','markdown_path':'raw.md'})
            clean=ws.path('sources/a/versions/clean-1');clean.mkdir()
            (clean/'clean.md').write_text('# Shared\n\nCleaned',encoding='utf-8')
            atomic_json(clean/'manifest.json',{'version_id':'clean-1','markdown_path':'clean.md','parent_version_id':'raw-1','parent_markdown':'sources/a/versions/raw-1/raw.md'})
            ws.update({'entry_id':'a','title':'A','sources':[{'markdown':'sources/a/versions/raw-1/raw.md'}]})
            atomic_json(ws.path('runs/r/state.json'),{'artifacts':[{'clean_path':'sources/a/versions/clean-1/clean.md'}]})
            atomic_json(ws.path('runs/r/plan.json'),{'documents':[{'entry_id':'a'}]})
            result=build(ws)
            html=next(Path(result['path']).parent.glob('entry-*.html')).read_text(encoding='utf-8')
            ids=re.findall(r' id="([^"]+)"',html)
            self.assertEqual(len(ids),len(set(ids)))
            for anchor in re.findall(r'href="#([^"]+)"',html):self.assertIn(anchor,ids)
            self.assertIn('data-comparison',html)
            self.assertIn('Original',html);self.assertIn('Cleaned',html)

    def test_manifest_images_and_raw_svg(self):
        with fixture() as temp:
            root=Path(temp);src=root/'source';src.mkdir();out=root/'out';out.mkdir()
            (src/'original').mkdir();(src/'original/x.png').write_bytes(b'png')
            result=render('![ok](x.png)\n<svg><script>evil()</script><text>secret</text></svg>',src/'raw.md',out,src,image_map={'x.png':src/'original/x.png'})
            self.assertIn('media/',result['html'])
            self.assertNotIn('<svg',result['html']);self.assertNotIn('secret',result['html'])

    def test_symlink_image_rejected(self):
        from unittest.mock import patch
        with fixture() as temp:
            root=Path(temp);image=root/'x.png';image.write_bytes(b'png')
            actual=Path.is_symlink
            with patch.object(Path,'is_symlink',lambda p: p == image or actual(p)):
                result=render('![x](x.png)',root/'raw.md',root)
            self.assertNotIn('media/',result['html'])
            self.assertTrue(result['warnings'])

    def test_invalid_selection_and_paths(self):
        with fixture() as temp:
            ws=Workspace(temp)
            with self.assertRaises(ValueError):build(ws,['missing'])
            ws.update({'entry_id':'a','title':'A','sources':[{'markdown':'../outside.md'}]})
            with self.assertRaises(ValueError):build(ws)

if __name__=='__main__':unittest.main()
