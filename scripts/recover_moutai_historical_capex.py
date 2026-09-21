"""Recover archived original-vintage capital spending, never equate it to FCFF."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import re
from pypdf import PdfReader
from value_investment_agent.filing_extract import extract_candidates_from_pages, _number_after_label, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.pdf_text import extract_pages
from replay_moutai_distributions import digest, write_json, ANNUAL_DIR, ANNUAL_HASH

ROOT = Path(__file__).resolve().parents[1]


def main():
    annual_path = ROOT / ANNUAL_DIR / 'annual-inputs.json'
    if digest(annual_path) != ANNUAL_HASH:
        raise ValueError('Original-vintage registry changed')
    annual = json.loads(annual_path.read_text(encoding='utf-8'))
    out = ROOT / 'runtime/strategy-validation' / ('moutai-historical-capex-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    results = []
    for vintage in annual:
        path = (ROOT / vintage['source_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != vintage['raw_file_hash']:
            raise ValueError('Historical original changed')
        pages = extract_pages(path)
        candidates = [r for r in extract_candidates_from_pages(pages) if r['field_name'] == 'capital_expenditure']
        record = {'report_year': vintage['report_year'], 'period': vintage['period_label'],
            'source_id': vintage['source_id'], 'source_path': vintage['source_path'],
            'source_url': vintage.get('source_url'), 'source_sha256': vintage['raw_file_hash'],
            'available_at': vintage['available_at'], 'parser_version': ANNUAL_BACKFILL_PARSER_VERSION,
            'candidates': candidates, 'value_cny': None, 'status': 'missing_or_ambiguous',
            'industrial_capex_approved': False, 'fcff_approved': False, 'trade_input_approved': False}
        if len(candidates) == 1:
            candidate = candidates[0]
            page_index = candidate['page'] - 1
            original = PdfReader(path).pages[page_index].extract_text()
            matched = _number_after_label(original, candidate['source_label'], monetary=True, wrapped_label=True)
            # Require CNY declaration and explicit original-year header in this statement.
            start = None
            for i in range(page_index, -1, -1):
                compact = re.sub(r'\s+', '', pages[i])
                if i == page_index:
                    label_at = compact.find(candidate['source_label'])
                    if label_at < 0:
                        raise ValueError('Candidate label missing from original page')
                    compact = compact[:label_at]
                parent_at = compact.rfind('母公司现金流量表')
                consolidated_at = compact.rfind('合并现金流量表')
                if parent_at > consolidated_at:
                    break
                if consolidated_at >= 0:
                    start = i
                    header = compact[consolidated_at:]
                    break
            if start is None:
                header = ''
            else:
                for i in range(start + 1, page_index + 1):
                    continuation = re.sub(r'\s+', '', pages[i])
                    if i == page_index:
                        continuation = continuation[:continuation.index(candidate['source_label'])]
                    header += continuation
            current_year = str(vintage['report_year'])
            prior_year = str(vintage['report_year'] - 1)
            unit = bool(re.search(r'单位[：:]元(?:币种[：:]人民币)?', header))
            ordered_years = bool(re.search(current_year + r'年(?:度)?' + r'.{0,20}?' + prior_year + r'年', header))
            dated_current_period = bool(re.search(current_year + r'年1[—－-]12月', header)
                and re.search(r'本期(?:发生额|金额)上期(?:发生额|金额)', header))
            ordered_years = ordered_years or dated_current_period
            agreement = bool(matched and Decimal(matched[0]) == Decimal(candidate['value']))
            record.update(dual_decoder_agreement=agreement, unit_cny_in_statement=unit,
                original_current_column_header=ordered_years, statement_header_page=start + 1 if start is not None else None,
                statement_header_excerpt=header[:550], pypdf_excerpt=matched[1] if matched else None)
            if agreement and unit and ordered_years:
                record.update(value_cny=candidate['value'], status='original_row_decoder_and_header_checked')
            else:
                record['status'] = 'candidate_requires_scope_review'
        results.append(record)
        print(json.dumps({'year':record['report_year'],'status':record['status'],'value':record['value_cny']},ensure_ascii=False),flush=True)
    write_json(out / 'evidence.json', {'symbol':'600519','rows':results,
        'scope':'Consolidated gross cash purchases of long-lived assets. Not maintenance capex, industrial allocation, net reinvestment, FCFF or a strategy valuation.',
        'verification':'Two decoders of the same issuer original, not independent external sources. Original column and unit gates; unresolved rows remain null.',
        'annual_registry_sha256':ANNUAL_HASH,'historical_valuation_approved':False})
    write_json(out / 'manifest.json', {'script_sha256':digest(Path(__file__)),
        'parser_sha256':digest(ROOT/'src/value_investment_agent/filing_extract.py'),
        'evidence_sha256':digest(out/'evidence.json')})
    print(json.dumps({'output':str(out),'checked':sum(r['value_cny'] is not None for r in results),'total':len(results)}))


if __name__ == '__main__':
    main()
