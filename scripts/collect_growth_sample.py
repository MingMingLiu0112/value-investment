"""Retain exact-period growth inputs and official candidates without promoting facts."""
import hashlib
import importlib.util
import json
import uuid
import argparse
from pathlib import Path
from value_investment_agent.db import connect,begin_run,end_run,store_record
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
from filing_extract import extract_annual_growth
growth_spec = importlib.util.spec_from_file_location('value_investment_agent.growth_probe',
                                                    Path(__file__).with_name('growth_evidence.py'))
growth_module = importlib.util.module_from_spec(growth_spec)
growth_spec.loader.exec_module(growth_module)
build_growth_evidence = growth_module.build_growth_evidence

spec = importlib.util.spec_from_file_location('value_investment_agent.growth_adapter',
                                            Path(__file__).with_name('adapters.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
parser = argparse.ArgumentParser()
parser.add_argument('--symbol',default='000333')
args = parser.parse_args()
symbol = args.symbol
if len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit():
    parser.error('symbol must contain six digits')
with connect(get_settings().database_url) as db:
    report = db.execute("""SELECT * FROM official_disclosures WHERE symbol=%s
        AND report_kind='annual' ORDER BY report_period DESC,published_at DESC LIMIT 1""",(symbol,)).fetchone()
if not report:
    raise RuntimeError('No retained annual report for '+symbol)
current_period = report['report_period']
previous_period = f'{int(current_period[:4])-1}-12-31'
path = Path(report['local_path'])
with path.open('rb') as handle:
    if hashlib.file_digest(handle,'sha256').hexdigest() != report['sha256']:
        raise ValueError('Official archive hash mismatch')
candidates = []
for index,page in enumerate(extract_pages(path),1):
    if '\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807' in page:
        candidates.extend(extract_annual_growth(page,index))
with connect(get_settings().database_url) as db:
    done = db.execute("""SELECT c.field_name,c.page_number,c.source_label FROM filing_candidates c
        JOIN data_points p ON p.metadata->>'candidate_id'=c.candidate_id::text
        WHERE c.disclosure_id=%s AND p.validation_status='verified'
          AND p.metadata->>'automatic_cross_source_verification'='true'
          AND NOT (p.metadata ? 'evidence_quarantine')""",(report['disclosure_id'],)).fetchall()
    completed = {(r['field_name'],r['page_number'],r['source_label']) for r in done}
candidates = [c for c in candidates if (c['field_name'],c['page'],c['source_label']) not in completed]
if not candidates:
    print(json.dumps({'symbol':symbol,'status':'no_unverified_unambiguous_growth_candidates'}))
    raise SystemExit(0)
records = {}
for period in [current_period,previous_period]:
    values = module.SinaFinancialStatementsAdapter().fetch([symbol],report_period=period)
    values += module.AkshareFinancialAbstractAdapter().fetch([symbol],report_period=period)
    records[period] = {r.field_name:r for r in values if r.field_name in ['revenue','net_income']}
with connect(get_settings().database_url) as db:
    db.execute("SET lock_timeout='5s'")
    run = begin_run(db,'collect-growth-sample')
    stored = []
    for field in sorted({c['field_name'].removesuffix('_yoy') for c in candidates}):
        current,previous = records[current_period][field],records[previous_period][field]
        current_id = store_record(db,current,'pending')
        previous_id = store_record(db,previous,'pending')
        growth = build_growth_evidence(current,previous,str(current_id),str(previous_id))
        point_id = store_record(db,growth,'pending')
        stored.append({'field':growth.field_name,'value':str(growth.value),'data_point_id':str(point_id)})
    for c in candidates:
        db.execute("""INSERT INTO filing_candidates(candidate_id,disclosure_id,field_name,value,unit,
            page_number,source_label,excerpt,parser_version,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (disclosure_id,field_name,page_number,source_label) DO NOTHING""",
            (uuid.uuid4(),report['disclosure_id'],c['field_name'],c['value'],c['unit'],c['page'],
             c['source_label'],c['excerpt'][:1000],'filing-growth-v1-explicit-annual',c['status']))
    result = {'symbol':symbol,'growth_points':stored,'official_candidates':len(candidates),
              'official_sha256':report['sha256'],'all_records_pending':True}
    end_run(db,run,'succeeded',result)
print(json.dumps(result))
