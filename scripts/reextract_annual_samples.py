"""Audited sample migration; promoted candidates are never overwritten."""
import argparse
import hashlib
import json
import uuid
from pathlib import Path
from filing_extract import ANNUAL_BACKFILL_PARSER_VERSION, extract_candidates_from_pages
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings
from value_investment_agent.candidate_migration import plan_candidate_supersession, supersede_unpromoted

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--supersede-obsolete', action='store_true')
parser.add_argument('--symbols', nargs='+', default=['000333','600036','600519'])
args = parser.parse_args()
if len(args.symbols) > 20 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbols):
    parser.error('Provide at most 20 six-digit symbols')
version = ANNUAL_BACKFILL_PARSER_VERSION
with connect(get_settings().database_url) as db:
    reports = db.execute("""SELECT DISTINCT ON (symbol) * FROM official_disclosures
        WHERE symbol=ANY(%s) AND report_kind='annual'
        ORDER BY symbol,report_period DESC,published_at DESC""",(args.symbols,)).fetchall()
for report in reports:
    path = Path(report['local_path'])
    with path.open('rb') as handle:
        assert hashlib.file_digest(handle,'sha256').hexdigest() == report['sha256']
    candidates = extract_candidates_from_pages(extract_pages(path))
    with connect(get_settings().database_url) as db:
        db.execute("SET lock_timeout='5s'")
        db.execute("SET statement_timeout='30s'")
        db.execute('LOCK TABLE filing_candidates, data_points IN SHARE ROW EXCLUSIVE MODE')
        run = begin_run(db,'annual-parser-migration')
        existing = db.execute('SELECT * FROM filing_candidates WHERE disclosure_id=%s',
                              (report['disclosure_id'],)).fetchall()
        fact_refs = db.execute("""SELECT DISTINCT p.metadata->>'candidate_id' AS candidate_id
            FROM data_points p JOIN filing_candidates c
              ON p.metadata->>'candidate_id'=c.candidate_id::text
            WHERE c.disclosure_id=%s""", (report['disclosure_id'],)).fetchall()
        supersession_plan = plan_candidate_supersession(existing, candidates,
            [row['candidate_id'] for row in fact_refs])
        before = []
        changed = skipped = 0
        for c in candidates:
            old = db.execute("""SELECT * FROM filing_candidates WHERE disclosure_id=%s
                AND field_name=%s AND page_number=%s AND source_label=%s""",
                (report['disclosure_id'],c['field_name'],c['page'],c['source_label'])).fetchone()
            if old:
                promoted = db.execute("SELECT 1 FROM data_points WHERE metadata->>'candidate_id'=%s LIMIT 1",
                                      (str(old['candidate_id']),)).fetchone()
                if promoted or old['parser_version'] == version:
                    skipped += 1
                    continue
                before.append(json.loads(json.dumps(old,default=str)))
                db.execute("""UPDATE filing_candidates SET value=%s,unit=%s,excerpt=%s,
                    parser_version=%s,status=%s WHERE candidate_id=%s""",
                    (c['value'],c['unit'],c['excerpt'][:1000],version,c['status'],old['candidate_id']))
            else:
                db.execute("""INSERT INTO filing_candidates(candidate_id,disclosure_id,field_name,value,
                    unit,page_number,source_label,excerpt,parser_version,status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (uuid.uuid4(),report['disclosure_id'],c['field_name'],c['value'],c['unit'],c['page'],
                     c['source_label'],c['excerpt'][:1000],version,c['status']))
            changed += 1
        superseded = 0
        if args.supersede_obsolete:
            obsolete_ids = {str(value) for value in supersession_plan['unpromoted_obsolete']}
            before.extend(json.loads(json.dumps(row, default=str)) for row in existing
                          if str(row['candidate_id']) in obsolete_ids)
            if obsolete_ids:
                superseded = supersede_unpromoted(db, obsolete_ids)
        details = {'symbol':report['symbol'],'report_period':report['report_period'],
            'official_sha256':report['sha256'],'official_url':report['source_url'],
            'parser_version':version,'changed':changed,'skipped':skipped,'previous_candidates':before,
            'supersession_plan': supersession_plan, 'superseded': superseded,
            'supersession_applied': bool(args.apply and args.supersede_obsolete)}
        end_run(db,run,'succeeded',details)
        if not args.apply:
            db.rollback()
    print(json.dumps({'symbol':report['symbol'],'changed':changed,'skipped':skipped,
                      'applied':args.apply, 'supersession_plan':supersession_plan,
                      'superseded':superseded,
                      'supersession_applied':bool(args.apply and args.supersede_obsolete)}),flush=True)
