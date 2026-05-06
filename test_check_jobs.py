import sys, os, traceback, glob
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
from dotenv import load_dotenv
load_dotenv()

from upload_storage import lookup_path_by_file_id
import sqlite3

db_path = os.path.join(os.getcwd(), 'backend', 'db', 'app.sqlite')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Find recent reading jobs
rows = conn.execute("""
    SELECT j.id, j.job_type, j.status, j.input_file_id, f.original_name, f.storage_path
    FROM jobs j
    LEFT JOIN files f ON f.id = j.input_file_id
    ORDER BY j.created_at DESC
    LIMIT 10
""").fetchall()

for r in rows:
    path = lookup_path_by_file_id(r['input_file_id']) if r['input_file_id'] else None
    ext = os.path.splitext(str(path))[1] if path else '?'
    print(f"  job={r['id'][:8]}... type={r['job_type']} status={r['status']} "
          f"file={r['original_name']} ext={ext} path={path}")

conn.close()
