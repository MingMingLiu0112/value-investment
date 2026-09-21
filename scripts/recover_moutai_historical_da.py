"""Original-vintage noncash adjustment evidence for historical valuation research."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
import re
from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.filing_extract import extract_candidates_from_pages, _number_after_label
from replay_moutai_distributions import digest, write_json, ANNUAL_DIR, ANNUAL_HASH

ROOT=Path(__file__).resolve().parents[1]
LABELS={
    'depreciation':['固定资产折旧、油气资产折耗、生产性生物资产折旧','固定资产折旧、油气资产折耗、生产性生物资产折旧：'],
    'intangible_amortization':['无形资产摊销'],
    'deferred_expense_amortization':['长期待摊费用摊销'],
    'rou_amortization':['使用权资产摊销','使用权资产折旧'],
}


def main():
    registry=ROOT/ANNUAL_DIR/'annual-inputs.json'
    if digest(registry)!=ANNUAL_HASH:
        raise ValueError('Annual original-vintage registry changed')
    out=ROOT/'runtime/strategy-validation'/('moutai-historical-da-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    rows=[]
    for vintage in json.loads(registry.read_text(encoding='utf-8')):
        path=(ROOT/vintage['source_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=vintage['raw_file_hash']:
            raise ValueError('Annual original changed')
        pages=extract_pages(path)
        cfo_values={r['value'] for r in extract_candidates_from_pages(pages) if r['field_name']=='operating_cash_flow'}
        matches=[]
        for i,text in enumerate(pages):
            # Cash-flow notes may continue on the next page; preserve both as evidence.
            block=text+'\n'+(pages[i+1] if i+1<len(pages) else '')
            compact=re.sub(r'\s+','',text)
            if not ('固定资产折旧' in compact and '无形资产摊销' in re.sub(r'\s+','',block)):
                continue
            values={}
            for field,labels in LABELS.items():
                found=[]
                for label in labels:
                    result=_number_after_label(block,label,monetary=True,wrapped_label=True)
                    if result:
                        found.append((label,result))
                if found:
                    label,(value,excerpt)=found[0]
                    values[field]={'label':label,'value':value,'excerpt':excerpt}
            cfo=_number_after_label(block,'经营活动产生的现金流量净额',monetary=True,wrapped_label=True)
            matches.append({'page':i+1,'values':values,'cfo':cfo[0] if cfo else None,
                'cfo_matches_reported_consolidated':bool(cfo and cfo[0] in cfo_values),
                'header_excerpt':re.sub(r'\s+','',block)[:500]})
        row={k:vintage[k] for k in ('report_year','source_id','source_path','source_url','available_at','period_label')}
        row.update(source_sha256=vintage['raw_file_hash'],candidates=matches,da_excluding_rou_cny=None,
            industrial_allocation_approved=False,fcff_approved=False,status='candidate_scope_pending')
        chosen=[m for m in matches if m['cfo_matches_reported_consolidated']]
        if len(chosen)==1:
            selected=chosen[0]
            page=selected['page']
            reader=PdfReader(path)
            original='\n'.join(reader.pages[j].extract_text() for j in range(page-1,min(page+1,len(reader.pages))))
            required=('depreciation','intangible_amortization','deferred_expense_amortization')
            agreement=all(field in selected['values'] for field in required)
            for field,item in selected['values'].items():
                other=_number_after_label(original,item['label'],monetary=True,wrapped_label=True)
                agreement=agreement and bool(other and D(other[0])==D(item['value']))
            selected['dual_decoder_agreement']=agreement
            header_context=re.sub(r'\s+','', '\n'.join(pages[max(0,page-2):page+1]))
            heading=header_context.rfind('现金流量表补充资料',0,header_context.find('生产性生物资产折旧'))
            heading_text=header_context[heading:] if heading>=0 else ''
            ordered_columns=bool(re.search(r'补充资料本期(?:金额|发生额)上期(?:金额|发生额)',heading_text))
            original_cfo=_number_after_label(original,'经营活动产生的现金流量净额',monetary=True,wrapped_label=True)
            unit_anchor=bool(original_cfo and original_cfo[0]==selected['cfo'] and selected['cfo'] in cfo_values)
            selected.update(original_current_column_header=ordered_columns,
                unit_anchor='Supplement CFO equals consolidated CNY CFO; same table amount columns' if unit_anchor else None,
                supplement_heading_excerpt=heading_text[:450])
            if agreement and ordered_columns and unit_anchor:
                total=sum((D(selected['values'][field]['value']) for field in required),D(0))
                assert Fraction(total)==sum((Fraction(selected['values'][field]['value']) for field in required),Fraction(0))
                row.update(da_excluding_rou_cny=str(total),status='original_row_decoder_header_and_cfo_scope_checked',selected=selected)
        rows.append(row)
        print(json.dumps({'year':row['report_year'],'candidates':len(matches),'status':row['status'],'value':row['da_excluding_rou_cny']},ensure_ascii=False),flush=True)
    write_json(out/'evidence.json',{'symbol':'600519','rows':rows,'historical_valuation_approved':False,
        'scope':'Consolidated noncash D&A; ROU separate; no missing-field zero imputation. Supplement current column required; CNY scale anchored by exact same-table CFO reconciliation to consolidated CNY amount. Two decoders are one source.'})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'evidence_sha256':digest(out/'evidence.json')})
    print(json.dumps({'output':str(out)}))


if __name__=='__main__':main()
