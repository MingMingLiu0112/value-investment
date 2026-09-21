"""Separate corporate income tax balances using the original reconciled tax note."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
import re
from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import _number_after_label
from recover_moutai_historical_capital import layout_current_value
from replay_moutai_distributions import digest,write_json

ROOT=Path(__file__).resolve().parents[1]
CAPITAL='runtime/strategy-validation/moutai-historical-capital-20260909T153535637673Z/evidence.json'
EXPECTED='9e1e49492b4877f47627c6a4575a77abe306d659880536bc213f3198a17923c8'


def tax_table(text):
    income=re.search(r'企\s*业\s*所\s*得\s*税',text)
    if not income:return None
    headings=list(re.finditer(r'应\s*交\s*税\s*费',text[:income.start()]))
    if not headings:return None
    start=headings[-1].start()
    total=re.search(r'合\s*计[^\n]*',text[income.end():])
    if not total:return None
    return text[start:income.end()+total.end()]


def main():
    if digest(ROOT/CAPITAL)!=EXPECTED:raise ValueError('Capital basis changed')
    out=ROOT/'runtime/strategy-validation'/('moutai-historical-tax-balances-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    rows=[]
    for vintage in json.loads((ROOT/CAPITAL).read_text(encoding='utf-8'))['rows']:
        path=(ROOT/vintage['source_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=vintage['source_sha256']:raise ValueError('Original changed')
        pages=extract_pages(path)
        reader=PdfReader(path)
        candidates=[]
        total_expected=vintage['facts']['taxes_payable']['value_cny']
        for i,text in enumerate(pages):
            if not re.search(r'应\s*交\s*税\s*费',text):continue
            table=tax_table(text+'\n'+(pages[i+1] if i+1<len(pages) else ''))
            if not table:continue
            income=_number_after_label(table,'企业所得税',monetary=True,wrapped_label=True)
            total=_number_after_label(table,'合计',monetary=True,wrapped_label=True)
            if not income or not total or total_expected is None or D(total[0])!=D(total_expected):continue
            indices=range(i,min(i+2,len(pages)))
            other=tax_table('\n'.join(reader.pages[j].extract_text() for j in indices))
            layout=tax_table('\n'.join(reader.pages[j].extract_text(extraction_mode='layout') for j in indices))
            income2=_number_after_label(other,'企业所得税',monetary=True,wrapped_label=True) if other else None
            total2=_number_after_label(other,'合计',monetary=True,wrapped_label=True) if other else None
            located=layout_current_value(layout,'企业所得税') if layout else (None,'layout_table_missing',None)
            header=re.sub(r'\s+','',table[:table.find('企业')])
            ordered=bool(re.search(r'期末(?:余额|数)(?:期初|年初)(?:余额|数)',header))
            verified=bool(income2 and total2 and D(income2[0])==D(income[0]) and D(total2[0])==D(total[0])
                and located[0] is not None and D(located[0])==D(income[0]) and ordered)
            candidates.append({'page':i+1,'corporate_income_tax_candidate':income[0],
                'physical_page_window':[i+1,min(i+2,len(pages))],
                'tax_total':total[0],'table_excerpt':table,'layout_income_row':located,
                'current_column_checked':ordered,'verified':verified,
                'unit_anchor':'Tax note total equals separately position-checked consolidated CNY taxes payable'})
        accepted=[c for c in candidates if c['verified']]
        row={k:vintage[k] for k in ('report_year','source_id','source_path','source_url','available_at','period_label','source_sha256')}
        row.update(candidates=candidates,corporate_income_tax_payable_cny=None,other_taxes_payable_cny=None,
            cash_income_tax_paid_cny=None,industrial_tax_allocation_approved=False,status='unresolved')
        if len(accepted)==1:
            selected=accepted[0]
            rest=D(selected['tax_total'])-D(selected['corporate_income_tax_candidate'])
            assert Fraction(rest)==Fraction(selected['tax_total'])-Fraction(selected['corporate_income_tax_candidate'])
            row.update(corporate_income_tax_payable_cny=selected['corporate_income_tax_candidate'],other_taxes_payable_cny=str(rest),
                selected=selected,status='original_tax_note_and_balance_reconciled')
        rows.append(row)
        print(json.dumps({'year':row['report_year'],'status':row['status'],'income_tax':row['corporate_income_tax_payable_cny']}),flush=True)
    write_json(out/'evidence.json',{'symbol':'600519','rows':rows,
        'scope':'Consolidated closing corporate income tax liability separated from other taxes; not cash tax payments, not industrial tax allocation. Prepaid taxes not yet reconciled.',
        'capital_basis':CAPITAL,'capital_basis_sha256':EXPECTED,'historical_valuation_approved':False})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'evidence_sha256':digest(out/'evidence.json')})
    print(json.dumps({'output':str(out),'checked':sum(r['status']!='unresolved' for r in rows)}))


if __name__=='__main__':main()
