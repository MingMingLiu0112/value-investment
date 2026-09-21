"""Hash-pinned original-report reconciliation against browser-read issuer IR."""
import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from value_investment_agent.pdf_text import extract_pages


def main():
    path = Path('runtime/historical-filing-index/20260908T041326996681Z/pdfs/000333-1200767542.pdf')
    expected = 'e982cf864c15ca8262d3537fa42b746c70dada2002eecfff559f0a8c46423dd9'
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Original PDF hash mismatch')
    page = extract_pages(path, 91)[90]
    if '合并利润表' not in page or '单位:人民币千元' not in page or '2014年度' not in page:
        raise ValueError('Statement scope, unit or year mismatch')
    patterns = {
        'total_revenue': r'一、营业总收入',
        'operating_revenue': r'其中:营业收入\s+1',
        'interest_income': r'利息收入\s+2',
        'fee_income': r'手续费及佣金收入\s+3',
        'operating_profit': r'三、营业利润（亏损以“-”号填列）',
        'consolidated_net_income': r'五、净利润（净亏损以“-”号填列）',
        'parent_attributable_net_income': r'归属于母公司股东的净利润',
        'minority_income': r'少数股东损益',
    }
    values = {}
    for field, label in patterns.items():
        matches = re.findall(label + r'\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', page)
        if len(matches) != 1:
            raise ValueError('Ambiguous or missing statement row: ' + field)
        values[field] = Decimal(matches[0][0].replace(',', ''))
    revenue_ok = values['total_revenue'] == sum(values[f] for f in ('operating_revenue', 'interest_income', 'fee_income'))
    profit_ok = values['consolidated_net_income'] == values['parent_attributable_net_income'] + values['minority_income']
    # Transcribed from the rendered issuer IR table, not a historical timestamp
    # or an independent financial source. Display precision is millions of CNY.
    ir = {'total_revenue': '142311', 'operating_profit': '13451', 'consolidated_net_income': '11646'}
    comparisons = {field: {'ir_cny_million': display,
                           'pdf_cny_thousand': str(values[field]),
                           'matches_at_display_precision': (values[field] / 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP) == Decimal(display)}
                   for field, display in ir.items()}
    result = {'symbol': '000333', 'period': '2014-12-31', 'pdf_page': 91,
              'pdf_url': 'https://static.cninfo.com.cn/finalpage/2015-03-31/1200767542.PDF',
              'pdf_sha256': expected, 'source_unit': 'CNY thousand',
              'ir_page': 'https://www.midea.com.cn/zh/Investors/Financial_Reports',
              'ir_provider': 'Euroland embedded in issuer IR, browser-read 2026-09-09',
              'values': {k: str(v) for k, v in values.items()},
              'revenue_components_match': revenue_ok, 'profit_components_match': profit_ok,
              'ir_comparison': comparisons,
              'independent_source_verified': False, 'historical_availability_verified': False,
              'backtest_ready': False,
              'limitations': ['IR display is rounded and viewed today, not point-in-time evidence',
                              'Issuer redistribution is not independent financial verification',
                              'Operating revenue and total revenue are distinct fields',
                              'Consolidated net income and parent-attributable income are distinct fields']}
    if not revenue_ok or not profit_ok or not all(r['matches_at_display_precision'] for r in comparisons.values()):
        raise ValueError('Scope reconciliation failed')
    output = Path('runtime/midea-2014-ir-scope-20260909.json')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
