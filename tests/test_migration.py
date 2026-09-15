import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dra_core.portability import import_archive
from dra_core.workspace import Workspace


class MigrationTest(unittest.TestCase):
    def test_website_relations_and_raw_preservation(self):
        base=Path(os.environ.get('DRA_TEST_TMP',tempfile.gettempdir())).resolve(); root=base/('dra-migration-'+uuid.uuid4().hex); root.mkdir(parents=True)
        try:
            archive=root/'sample.dra'
            tables={'bib_entries':[{'id':'b1','owner_user_id':2,'title':'Paper','authors_json':'[]','user_tags_json':'[]','source_file_id':'f1','unknown_field':'keep'}],'files':[{'id':'f1','owner_user_id':2,'original_name':'paper.md','file_type':'markdown'}],'reading_items':[{'id':7,'owner_user_id':2,'bib_entry_id':'b1','file_id':'f1'}]}
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('manifest.json',json.dumps({'format_version':1,'schema_version':'027','errors':[],'missing_files':[]}))
                for name,rows in tables.items(): z.writestr('data/'+name+'.json',json.dumps(rows))
                z.writestr('files/f1.md','# Paper\n\nSample content.')
            result=import_archive(archive,root/'restored'); w=Workspace(root/'restored')
            entry=w.entries()[0]; self.assertNotEqual(entry['entry_id'],'b1'); self.assertEqual(entry['metadata']['unknown_field'],'keep'); self.assertTrue(entry['sources'])
            raw=json.loads((w.root/'imports/website/data/bib_entries.json').read_text())
            self.assertEqual(raw,tables['bib_entries'])
            rows=json.loads((w.root/'imports/mapped/reading_items.json').read_text())
            self.assertEqual(rows[0]['bib_entry_id'],entry['entry_id'])
            mapped_entries=json.loads((w.root/'imports/mapped/bib_entries.json').read_text())
            self.assertNotEqual(mapped_entries[0]['source_file_id'],'f1')
            self.assertEqual(rows[0]['file_id'],'f1')  # Unknown fields are preserved, not guessed as FKs.
        finally:
            if root.resolve().parent==base and root.name.startswith('dra-migration-'): shutil.rmtree(root)


if __name__=='__main__': unittest.main()
