"""Original balance-sheet ingredients, with unresolved classifications explicit."""
from datetime import datetime,timezone
from pathlib import Path
from decimal import Decimal as D
import json
import re
from statistics import median
from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import _number_after_label
from recover_moutai_historical_operating import statement
from replay_moutai_distributions import digest,write_json,ANNUAL_DIR,ANNUAL_HASH

ROOT=Path(__file__).resolve().parents[1]
FIELDS={
 'inventory':'存货','accounts_receivable':'应收账款','notes_receivable':'应收票据',
 'combined_notes_accounts_receivable':'应收票据及应收账款','receivables_financing':'应收款项融资',
 'prepayments':'预付款项','contract_assets':'合同资产','other_receivables':'其他应收款',
 'other_current_assets':'其他流动资产','accounts_payable':'应付账款','notes_payable':'应付票据',
 'combined_notes_accounts_payable':'应付票据及应付账款','advance_receipts':'预收款项',
 'contract_liabilities':'合同负债','payroll_payable':'应付职工薪酬','taxes_payable':'应交税费',
 'other_payables':'其他应付款','other_current_liabilities':'其他流动负债',
 'cash':'货币资金','financial_deposits':'吸收存款及同业存放','loans':'发放贷款及垫款',
 'deferred_tax_assets':'递延所得税资产','deferred_tax_liabilities':'递延所得税负债',
 'fixed_assets':'固定资产','construction':'在建工程','intangibles':'无形资产',
 'rou_assets':'使用权资产','lease_liabilities':'租赁负债',
}


def layout_current_value(text,label):
    money=re.compile(r'(?<![\d.])-?\d[\d,]*\.\d{2}(?!\d)')
    lines=text.splitlines()
    pairs=[list(money.finditer(line)) for line in lines]
    pairs=[p for p in pairs if len(p)==2]
    if len(pairs)<3:
        return None,'insufficient_column_anchors',None
    current=median(p[0].end() for p in pairs)
    prior=median(p[1].end() for p in pairs)
    if prior-current<12:
        return None,'ambiguous_column_positions',None
    match=re.search(r'\s*'.join(re.escape(c) for c in label),text)
    if match is None:
        return None,'label_not_present',None
    first=text[:match.start()].count('\n')
    last=text[:match.end()].count('\n')
    observed=[]
    for line in lines[first:last+1]:
        observed.extend(m.group().replace(',','') for m in money.finditer(line) if abs(m.end()-current)<=4)
    excerpt='\n'.join(lines[first:last+1])
    if len(observed)==1:
        return observed[0],'current_column_amount',excerpt
    if not observed:
        return None,'current_column_blank_or_wrapped_amount',excerpt
    return None,'multiple_current_amounts',excerpt


def main():
    registry=ROOT/ANNUAL_DIR/'annual-inputs.json'
    if digest(registry)!=ANNUAL_HASH:raise ValueError('Annual original registry changed')
    out=ROOT/'runtime/strategy-validation'/('moutai-historical-capital-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    rows=[]
    for vintage in json.loads(registry.read_text(encoding='utf-8')):
        path=(ROOT/vintage['source_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=vintage['raw_file_hash']:raise ValueError('Original changed')
        pages=extract_pages(path)
        primary=statement(pages,'资产负债表')
        reader=PdfReader(path)
        # Reuse the physical-page selection; parse headings again within those pages.
        selected={p for p,_ in primary}
        secondary_pages=[reader.pages[i].extract_text() if i+1 in selected else '' for i in range(len(reader.pages))]
        secondary=statement(secondary_pages,'资产负债表')
        layout_pages=[reader.pages[i].extract_text(extraction_mode='layout') if i+1 in selected else '' for i in range(len(reader.pages))]
        layout_sections=statement(layout_pages,'资产负债表')
        block='\n'.join(t for _,t in primary)
        other='\n'.join(t for _,t in secondary)
        compact=re.sub(r'\s+','',block)
        year=str(vintage['report_year'])
        ordered=bool(re.search(year+r'年12月31日.{0,25}?'+str(vintage['report_year']-1)+r'年12月31日',compact)
            or (year+'年12月31日' in compact and re.search(r'期末(?:余额|数)(?:期初|年初)(?:余额|数)',compact)))
        unit=bool(re.search(r'单位[：:]元',compact))
        facts={}
        for field,label in FIELDS.items():
            first=_number_after_label(block,label,monetary=True,wrapped_label=True)
            second=_number_after_label(other,label,monetary=True,wrapped_label=True)
            matches=bool(first and second and D(first[0])==D(second[0]))
            positions=[(p,layout_current_value(t,label)) for p,t in layout_sections if label in re.sub(r'\s+','',t)]
            layout_value=None
            if len(positions)==1:
                layout_value=positions[0][1][0]
            checked=bool(matches and ordered and unit and layout_value is not None and D(layout_value)==D(first[0]))
            facts[field]={'value_cny':first[0] if checked else None,
                'label':label,'status':'original_row_decoder_header_and_position_checked' if checked else 'blank_absent_or_unresolved',
                'layout_evidence':positions,
                'excerpt':first[1] if first else None}
        row={k:vintage[k] for k in ('report_year','source_id','source_path','source_url','available_at','period_label')}
        row.update(source_sha256=vintage['raw_file_hash'],statement_pages=sorted(selected),
            current_column_checked=ordered,unit_cny_checked=unit,header_excerpt=compact[:650],facts=facts,
            operating_nwc_cny=None,industrial_invested_capital_approved=False,
            classification_blockers=['Income tax embedded in tax balances; financial and operating balances require note allocation.',
                'Combined and component receivables/payables are alternative presentations; never sum both.',
                'Advance receipts and contract liabilities/VAT changed presentation; compare policies before differencing.',
                'Blank or absent is unknown, not zero. No automatic current minus prior-original difference.'])
        rows.append(row)
        print(json.dumps({'year':row['report_year'],'column':ordered,'unit':unit,'numeric_fields':sum(v['value_cny'] is not None for v in facts.values())}),flush=True)
    write_json(out/'evidence.json',{'symbol':'600519','rows':rows,'scope':'Consolidated closing balance ingredients; not classified industrial NWC or investable capital. Original current-year column only.', 'historical_valuation_approved':False})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'evidence_sha256':digest(out/'evidence.json'),
        'statement_helper_sha256':digest(ROOT/'scripts/recover_moutai_historical_operating.py'),
        'parser_sha256':digest(ROOT/'src/value_investment_agent/filing_extract.py')})
    print(json.dumps({'output':str(out)}))


if __name__=='__main__':main()
