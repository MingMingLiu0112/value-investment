"""Recover missing official archives only when downloaded bytes match stored hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.disclosures import _download
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
settings = get_settings()
if args.apply and settings.evidence_directory != Path('/app/evidence'):
    raise ValueError('Recovery requires the explicitly mounted /app/evidence directory')
with connect(settings.database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    rows = db.execute('SELECT disclosure_id,symbol,sha256,source_url,local_path FROM official_disclosures').fetchall()
missing = [r for r in rows if not Path(r['local_path']).is_file()]
print(json.dumps({'registered': len(rows), 'missing': len(missing),
                  'symbols': sorted({r['symbol'] for r in missing})}), flush=True)
if args.apply:
    with connect(settings.database_url) as db:
        run = begin_run(db, 'repair-missing-official-files')
    repaired, failures = [], []
    for row in missing:
        try:
            url = urlparse(row['source_url'])
            if (url.scheme != 'https' or url.hostname != 'static.cninfo.com.cn'
                or not re.fullmatch(r'\d{6}', row['symbol'])
                or not re.fullmatch(r'[a-fA-F0-9]{64}', row['sha256'])):
                raise ValueError('Unsupported recovery identity or source')
            target = settings.evidence_directory / row['symbol'] / f"recovered-{row['sha256']}.pdf"
            digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else _download(row['source_url'], target)
            if digest.lower() != row['sha256'].lower():
                raise ValueError('Recovered bytes differ from archived SHA-256; record unchanged')
            with connect(settings.database_url) as db:
                db.execute('UPDATE official_disclosures SET local_path=%s WHERE disclosure_id=%s AND sha256=%s',
                           (str(target), row['disclosure_id'], row['sha256']))
            repaired.append({'disclosure_id': str(row['disclosure_id']), 'symbol': row['symbol'],
                'sha256': digest, 'previous_path': row['local_path'], 'new_path': str(target)})
        except Exception as error:
            failures.append({'disclosure_id': str(row['disclosure_id']), 'error': str(error)})
    with connect(settings.database_url) as db:
        end_run(db, run, 'failed' if failures else 'succeeded', {'repaired': repaired, 'failures': failures})
    print(json.dumps({'repaired': len(repaired), 'failures': failures}), flush=True)
    if failures:
        raise SystemExit(1)
