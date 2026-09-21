"""Review dated latest issuer rows; no valuation or historical promotion."""
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import json

from pypdf import PdfReader
import pypdfium2 as pdfium
from build_moutai_business_evidence import ROOT, compact


FOLDER = 'runtime/historical-filing-index/20260909T033444358365Z/pdfs/'
REPORTS = [
    ('1225114741', '474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288', '2025-12-31', 'FY', 6,
     [('revenue', '营业收入', ['168,838,102,514.79', '170,899,152,276.34']),
      ('parent_profit', '归属于上市公司股东的净利润', ['82,320,067,101.68', '86,228,146,421.62']),
      ('cfo', '经营活动产生的现金流量净额', ['61,522,204,989.35', '92,463,692,168.43'])]),
    ('1225475868', '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6', '2026-06-30', 'YTD', 5,
     [('revenue', '营业收入', ['90,703,260,964.48', '89,389,354,416.84']),
      ('parent_profit', '归属于上市公司股东的净利润', ['44,516,880,421.86', '45,402,962,298.10']),
      ('cfo', '经营活动产生的现金流量净额', ['70,690,750,119.06', '13,119,061,031.33'])]),
    ('1224462930', 'c80fb7180169469053c396e65315414368bcfa9f1f1d4e3bf793c8fb327e6b0c', '2025-06-30', 'YTD', 5,
     [('revenue', '营业收入', ['89,389,354,416.84', '81,930,977,667.75']),
      ('parent_profit', '归属于上市公司股东的净利润', ['45,402,962,298.10', '41,695,610,983.37']),
      ('cfo', '经营活动产生的现金流量净额', ['13,119,061,031.33', '36,621,833,812.63'])]),
]


def main():
    rows = []
    for ident, digest, period, basis, page_number, fields in REPORTS:
        folder = ('runtime/historical-filing-index/20260909T033820132471Z/pdfs/'
                  if ident == '1224462930' else FOLDER)
        path = ROOT / folder / ('600519-' + ident + '.pdf')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Source PDF changed')
        reader = PdfReader(path)
        text1 = compact(reader.pages[page_number - 1].extract_text())
        with pdfium.PdfDocument(path) as doc:
            page = doc[page_number - 1]
            textpage = page.get_textpage()
            try:
                text2 = compact(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
        for field, label, cells in fields:
            snippet = compact(label + ''.join(cells))
            if snippet not in text1 or snippet not in text2:
                raise ValueError('Reviewed row mismatch: ' + field)
            current, comparative = (D(value.replace(',', '')) for value in cells)
            rows.append({'field': field, 'period_end': period, 'period_basis': basis,
                         'current': str(current), 'comparative_from_current_report': str(comparative),
                         'unit': 'CNY', 'yoy_recomputed': str(current / comparative - 1),
                         'path': str(path.relative_to(ROOT)), 'sha256': digest,
                         'physical_page': page_number, 'reviewed_row': label, 'cells': cells})
    annual = next(row for row in rows if row['field'] == 'parent_profit' and row['period_basis'] == 'FY')
    interim = next(row for row in rows if row['field'] == 'parent_profit' and row['period_basis'] == 'YTD')
    comparisons = {}
    for field in ('revenue', 'parent_profit', 'cfo'):
        current = next(row for row in rows if row['field'] == field and row['period_end'] == '2026-06-30')
        prior = next(row for row in rows if row['field'] == field and row['period_end'] == '2025-06-30')
        comparisons[field] = current['comparative_from_current_report'] == prior['current']
    if not all(comparisons.values()):
        raise ValueError('Prior original differs from current comparative')
    result = {'symbol': '600519', 'generated_at': datetime.now(timezone.utc).isoformat(),
              'rows': rows,
              'ttm_profit_arithmetic_candidate': str(D(annual['current']) + D(interim['current']) - D(interim['comparative_from_current_report'])),
              'prior_original_comparisons': comparisons,
              'ttm_status': 'prior_original_values_match_full_accounting_comparability_pending',
              'per_share_value': None, 'current_valuation_approved': False,
              'historical_inputs_approved': False,
              'validation_scope': 'Two decoders of issuer original rows; no independent financial source',
              'gaps': ['Accounting policy and consolidation comparability', 'Current ordinary shares and treasury scope',
                       'Industrial/finance cash flow split', 'Scenario and discount-rate evidence']}
    target = ROOT / 'runtime/company-research' / ('600519-latest-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    target.mkdir(parents=True, exist_ok=False)
    (target / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(target / 'evidence.json'), 'verified_original_rows': len(rows),
                      'ttm_profit_candidate': result['ttm_profit_arithmetic_candidate'], 'approved': False}))


if __name__ == '__main__':
    main()
