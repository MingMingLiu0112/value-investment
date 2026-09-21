"""Authenticate reported TTM flow comparability, not normalized earnings or FCFF."""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT/'runtime/company-research/600519-latest-20260909T034033235112Z/evidence.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text):
    return re.sub(r'\s+', '', text)


def texts(path, page_number):
    first = PdfReader(path).pages[page_number-1].extract_text()
    with pdfium.PdfDocument(path) as document:
        page = document[page_number-1]
        textpage = page.get_textpage()
        second = textpage.get_text_range()
        textpage.close()
        page.close()
    return [compact(first), compact(second)]


def main():
    rows = json.loads(PACK.read_text(encoding='utf-8'))['rows']
    original_files = {}
    for row in rows:
        path = ROOT/row['path']
        if sha(path) != row['sha256']:
            raise ValueError('Original changed')
        phrase = compact(row['reviewed_row'] + ''.join(row['cells']))
        if any(phrase not in text for text in texts(path, row['physical_page'])):
            raise ValueError('Reported numeric row mismatch')
        if Decimal(row['cells'][0].replace(',', '')) != Decimal(row['current']):
            raise ValueError('Normalized current value differs from original')
        if Decimal(row['cells'][1].replace(',', '')) != Decimal(row['comparative_from_current_report']):
            raise ValueError('Normalized comparative value differs from original')
        original_files[str(path)] = sha(path)
    current = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    scope = {
        52: ['财会〔2025〕32号）无0', '财会〔2026〕7号）无0',
             '(2)重要会计估计变更□适用√不适用'],
        85: ['1、非同一控制下企业合并□适用√不适用',
             '2、同一控制下企业合并□适用√不适用'],
        86: ['本期是否存在丧失子公司控制权的交易或事项□适用√不适用',
             '公司出资6亿元成立全资子公司贵州爱茅台数字科技有限公司',
             '截至报告披露日已出资2亿元'],
    }
    for page, phrases in scope.items():
        candidates = texts(current, page)
        for phrase in phrases:
            if any(phrase not in text for text in candidates):
                raise ValueError(f'Scope mismatch page {page}: {phrase}')
    result = {}
    for field in ('revenue', 'parent_profit', 'cfo'):
        found = {(r['period_end'], r['period_basis']): r for r in rows if r['field'] == field}
        fy = found[('2025-12-31', 'FY')]
        cy = found[('2026-06-30', 'YTD')]
        py = found[('2025-06-30', 'YTD')]
        if Decimal(cy['comparative_from_current_report']) != Decimal(py['current']):
            raise ValueError('Comparative restatement needs separate bridge')
        value = Decimal(fy['current']) + Decimal(cy['current']) - Decimal(py['current'])
        independent = Fraction(fy['current']) + Fraction(cy['current']) - Fraction(py['current'])
        if Fraction(value) != independent:
            raise ValueError('Independent recomputation failed')
        result[field] = {'value': str(value), 'unit': 'CNY',
                         'formula': 'FY2025 + H1_2026 - H1_2025',
                         'input_rows': [fy, cy, py], 'comparative_matches_original': True}
    out = ROOT/'runtime/company-research'/('600519-ttm-scope-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    payload = {'symbol': '600519', 'period_start': '2025-07-01', 'period_end': '2026-06-30',
        'reported_flow_research_supported': True, 'normalized_earnings_approved': False,
        'fcff_approved': False, 'current_eps_approved': False, 'trade_value_approved': False,
        'scope_checks': scope, 'ttm': result,
        'limitations': ['Issuer disclosed zero effects; not an independent audit opinion',
            'Organic subsidiary formation does not mean unchanged economic operations',
            'Consolidated CFO includes finance subsidiary flows; not distributable cash',
            'No September share count, industrial/financial split or scenario valuation approval']}
    (out/'evidence.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {'original_files': original_files, 'input_pack_sha256': sha(PACK),
                'script_sha256': sha(Path(__file__)), 'evidence_sha256': sha(out/'evidence.json')}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'ttm': {k:v['value'] for k,v in result.items()},
                      'reported_flow_research_supported': True}))


if __name__ == '__main__':
    main()
