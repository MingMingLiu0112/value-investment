"""Fresh-container audit of persisted official archives and latest IPO evidence."""
import hashlib
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    rows = db.execute('SELECT local_path,sha256 FROM official_disclosures').fetchall()
    ipo = db.execute("""SELECT DISTINCT ON (details->>'symbol') details FROM task_runs
        WHERE task_name='archive-ipo-evidence' AND status='succeeded'
        ORDER BY details->>'symbol',started_at DESC""").fetchall()
    ipo_documents = [doc for row in ipo for doc in row['details']['documents']]
failures = []
for row in [*rows, *ipo_documents]:
    path = Path(row['local_path'])
    if not path.is_file():
        failures.append({'path': str(path), 'error': 'missing'})
        continue
    with path.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != row['sha256']:
            failures.append({'path': str(path), 'error': 'sha256_mismatch'})
print(json.dumps({'official_files_checked': len(rows), 'ipo_files_checked': len(ipo_documents),
                  'failures': failures}), flush=True)
if failures:
    raise SystemExit(1)
