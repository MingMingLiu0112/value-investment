"""Read-only real annual-PDF regression for delimited statement note references."""
import hashlib
import json
import uuid
import argparse
from pathlib import Path
from filing_extract import extract_candidates_from_pages as revised
from value_investment_agent.filing_extract import extract_candidates_from_pages as live
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages

expected_hash = 'aa0cdb92e3aad81b1e6454594a64cacbcfeb9013b10dd31f47a93a94e7a70f91'
arguments = argparse.ArgumentParser()
arguments.add_argument('--apply', action='store_true')
args = arguments.parse_args()
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='20s'")
    report = db.execute("""SELECT disclosure_id,local_path,sha256,source_url FROM official_disclosures
        WHERE symbol='600900' AND sha256=%s LIMIT 1""", (expected_hash,)).fetchone()
    assert report, 'Expected archived official report missing'
    db.rollback()
path = Path(report['local_path'])
assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
pages = extract_pages(path)
result = {'symbol':'600900', 'sha256':expected_hash, 'source_url':report['source_url']}
for name, parser in [('production', live), ('revised', revised)]:
    result[name] = [r for r in parser(pages) if r['field_name']=='long_term_borrowings']
assert any(r['page']==81 and r['value']=='172310624303.31' for r in result['revised'])
from value_investment_agent.candidate_review import automatically_verified_candidates
from filing_extract import ANNUAL_BACKFILL_PARSER_VERSION
with connect(get_settings().database_url) as db:
    db.execute("SET statement_timeout='30s'")
    db.execute("SET lock_timeout='3s'")
    db.execute('CREATE TEMP TABLE filing_candidates (LIKE public.filing_candidates INCLUDING ALL)')
    row = next(r for r in result['revised'] if r['page']==81)
    candidate_id = uuid.uuid4()
    db.execute("""INSERT INTO filing_candidates
        (candidate_id,disclosure_id,field_name,value,unit,page_number,source_label,excerpt,parser_version,status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (candidate_id,report['disclosure_id'],row['field_name'],row['value'],row['unit'],row['page'],
         row['source_label'],row['excerpt'][:1000],ANNUAL_BACKFILL_PARSER_VERSION,row['status']))
    verified = list(automatically_verified_candidates(db, 1))
    result['automatic_cross_check'] = [dict(candidate_id=identity,value=str(record.value),
        metadata=record.point_metadata) for identity,record in verified]
    assert len(verified)==1, 'Latest independent source did not validate the exact official fact'
    assert str(verified[0][1].value)=='172310624303.31'
    if args.apply:
        from value_investment_agent.db import store_record, begin_run, end_run
        run_id = begin_run(db, 'repair-long-borrowing-note-v14')
        db.execute('INSERT INTO public.filing_candidates SELECT * FROM filing_candidates WHERE candidate_id=%s', (candidate_id,))
        point_id = store_record(db, verified[0][1], validation_status='verified')
        db.execute("UPDATE public.filing_candidates SET status='automatically_verified' WHERE candidate_id=%s", (candidate_id,))
        stored = db.execute('SELECT value,metadata FROM data_points WHERE data_point_id=%s', (point_id,)).fetchone()
        assert str(stored['metadata']['candidate_id']) == str(candidate_id)
        assert stored['value'] == verified[0][1].value
        result['data_point_id'] = str(point_id)
        end_run(db, run_id, 'succeeded', {'symbol':'600900','field':'long_term_borrowings',
            'candidate_id':str(candidate_id),'data_point_id':str(point_id),'official_sha256':expected_hash})
        db.commit()
    else:
        db.rollback()
result['production_writes'] = args.apply
print(json.dumps(result))
