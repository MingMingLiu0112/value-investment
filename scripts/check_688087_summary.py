"""Compare retained summary facts against hash-verified official PDF text."""
import hashlib
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
from filing_extract import extract_candidates_from_pages

digest = 'd5ea80d0a678586b178bb95bdedcabd00459fd23c98ea5601d772ec55adfaa9a'
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    report = db.execute('SELECT * FROM official_disclosures WHERE symbol=%s AND sha256=%s', ('688087',digest)).fetchone()
    assert report
    old = db.execute("""SELECT candidate_id,field_name,value,unit,page_number,status FROM filing_candidates
        WHERE disclosure_id=%s AND page_number=14
        AND field_name IN ('revenue','net_income','operating_cash_flow')""", (report['disclosure_id'],)).fetchall()
path = Path(report['local_path'])
assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
pages = extract_pages(path)
rows = [r for r in extract_candidates_from_pages(pages)
        if r['field_name'] in ('revenue','net_income','operating_cash_flow')]
assert any(r['field_name']=='net_income' and r['page']==125 and r['value']=='285734507.57'
           and r['unit']=='CNY' for r in rows)
assert not any(r['field_name']=='net_income' and r['page']==127 for r in rows)
assert any(r['field_name']=='revenue' and r['page']==14 and r['value']=='3546216993.66' for r in rows)
print(json.dumps({'sha256':digest,'source_url':report['source_url'],'retained':old,
    'reparsed':[{'field':r['field_name'],'page':r['page'],'value':r['value'],'unit':r['unit']} for r in rows],
    'consolidated_income_verified':True,'parent_company_excluded':True},default=str,ensure_ascii=False))
