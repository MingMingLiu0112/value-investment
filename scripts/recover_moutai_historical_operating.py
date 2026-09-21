"""Recover dated consolidated operating lines without asserting segment EBIT."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
import re
from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import _page_sections, _number_after_label
from replay_moutai_distributions import digest, write_json, ANNUAL_DIR, ANNUAL_HASH

ROOT=Path(__file__).resolve().parents[1]
FIELDS={
    'revenue':['营业收入'], 'cost':['营业成本'],
    'surcharges':['税金及附加','营业税金及附加'],
    'selling':['销售费用'], 'admin':['管理费用'], 'research':['研发费用'],
    'financial_expense':['财务费用'], 'total_revenue':['营业总收入'],
    'total_cost':['营业总成本'], 'finance_interest_revenue':['利息收入'],
    'finance_interest_expense':['利息支出'], 'finance_commission_expense':['手续费及佣金支出'],
    'asset_impairment_loss':['资产减值损失'],
}


def statement(pages, kind='利润表'):
    active=False
    result=[]
    for page,text in enumerate(pages,1):
        collected=[]
        for line in text.splitlines():
            compact=re.sub(r'\s+','',line)
            title=re.fullmatch(r'(?:[0-9一二三四五六七八九十、.．（）()]*)?((?:合并|母公司|公司)(?:现金流量表|资产负债表|利润表))',compact)
            if title:
                if active:
                    if collected:result.append((page,'\n'.join(collected)))
                    return result
                active=title.group(1)=='合并'+kind
            if active:collected.append(line)
        if collected:result.append((page,'\n'.join(collected)))
    return result


def main():
    registry=ROOT/ANNUAL_DIR/'annual-inputs.json'
    if digest(registry)!=ANNUAL_HASH:
        raise ValueError('Annual original-vintage registry changed')
    out=ROOT/'runtime/strategy-validation'/('moutai-historical-operating-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    rows=[]
    for vintage in json.loads(registry.read_text(encoding='utf-8')):
        path=(ROOT/vintage['source_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=vintage['raw_file_hash']:
            raise ValueError('Original changed')
        sections=statement(extract_pages(path))
        reader=PdfReader(path)
        second=statement([p.extract_text() for p in reader.pages])
        block='\n'.join(t for _,t in sections)
        other='\n'.join(t for _,t in second)
        compact=re.sub(r'\s+','',block)
        header_ok=bool(re.search(r'单位[：:]元',compact) and (
            re.search(str(vintage['report_year'])+r'年(?:度)?.{0,30}?'+str(vintage['report_year']-1)+r'年',compact)
            or (str(vintage['report_year'])+'年1' in compact and re.search(r'本期(?:金额|发生额)上期(?:金额|发生额)',compact))))
        facts={}
        for field,labels in FIELDS.items():
            found=[]
            for label in labels:
                first=_number_after_label(block,label,monetary=True,wrapped_label=True)
                check=_number_after_label(other,label,monetary=True,wrapped_label=True)
                if first and check and D(first[0])==D(check[0]):
                    found.append({'value':first[0],'label':label,'excerpt':first[1]})
            # The short tax label must not silently select a different row.
            distinct={r['value'] for r in found}
            facts[field]=found[0] if len(distinct)==1 and header_ok else None
        required=('revenue','cost','surcharges','selling','admin','research')
        legacy_cost_keys=('cost','surcharges','selling','admin','financial_expense','finance_interest_expense','finance_commission_expense','asset_impairment_loss')
        legacy_cost_residual=None
        legacy_presentation=False
        if facts['research'] is None and '研发费用' not in compact and all(facts[k] is not None for k in (*legacy_cost_keys,'total_cost')):
            legacy_cost_residual=D(facts['total_cost']['value'])-sum((D(facts[k]['value']) for k in legacy_cost_keys),D(0))
            legacy_presentation=legacy_cost_residual==0
        used=required[:-1] if legacy_presentation else required
        proxy=None
        if all(facts[k] is not None for k in used):
            value=D(facts['revenue']['value'])-sum((D(facts[k]['value']) for k in used[1:]),D(0))
            exact=Fraction(facts['revenue']['value'])-sum((Fraction(facts[k]['value']) for k in used[1:]),Fraction(0))
            assert Fraction(value)==exact
            proxy=str(value)
        row={k:vintage[k] for k in ('report_year','source_id','source_path','source_url','available_at','period_label')}
        row.update(source_sha256=vintage['raw_file_hash'],statement_pages=sorted({p for p,_ in sections}),
            current_column_unit_checked=header_ok,header_excerpt=compact[:450],facts=facts,
            operating_subtotal_before_financial_and_other_items=proxy,
            missing_required=[k for k in used if facts[k] is None],industrial_ebit_approved=False,
            legacy_total_cost_residual=str(legacy_cost_residual) if legacy_cost_residual is not None else None,
            research_presentation='not_separately_presented_total_cost_reconciled_no_extra_deduction' if legacy_presentation else 'separate_line_or_unresolved',
            subtotal_deducted_fields=list(used[1:]),
            historical_valuation_approved=False)
        rows.append(row)
        print(json.dumps({'year':row['report_year'],'header':header_ok,'missing':row['missing_required'],'proxy':proxy}),flush=True)
    write_json(out/'evidence.json',{'symbol':'600519','rows':rows,
        'scope':'Original current-year consolidated statement lines. Shared costs not allocated; financial and other gains excluded from conditional subtotal. Missing R&D is not zero; historical expense presentation may embed it in administration.',
        'verification':'Same issuer original via PDFium/pypdf; not independent sources.', 'historical_valuation_approved':False})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'evidence_sha256':digest(out/'evidence.json'),
        'parser_sha256':digest(ROOT/'src/value_investment_agent/filing_extract.py')})
    print(json.dumps({'output':str(out)}))


if __name__=='__main__':main()
