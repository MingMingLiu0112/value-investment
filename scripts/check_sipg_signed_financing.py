"""Pinned cross-page evidence capture; no blank-to-zero or debt approval."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pdfplumber


def main():
    path = Path('runtime/candidate-financing-batch-20260909-03/600018-0100d2e99a61.pdf')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != '0100d2e99a61ea2d9d7022259f724b00530f1058c3a93163106630f0ffdcbfe7':
        raise ValueError('Unexpected PDF')
    with pdfplumber.open(path) as document:
        prior = ''.join(document.pages[240].extract_text().split())
        if not prior.endswith('筹资活动产生的各项负债变动情况√适用□不适用241/325'):
            raise ValueError('Heading continuation not established')
        page = document.pages[241]
        table = page.find_tables()[0]
        context = ''.join(page.crop((0, 0, page.width, table.bbox[1])).extract_text().split())
        if not context.endswith('单位：元币种：人民币'):
            raise ValueError('Continuation unit not explicit')
        cells = table.extract()
    expected_labels = ['短期借款', '长期借款(含一年内到期)', '租赁负债(含一年内到期)', '应付债券', '合计']
    if [row[0] for row in cells[2:]] != expected_labels or any(len(row) != 7 for row in cells):
        raise ValueError('Table layout changed')
    rows = []
    for row in cells[2:]:
        amounts = [Decimal(v.replace(',', '')) if v else None for v in row[1:]]
        if any(v is not None and not v.is_finite() for v in amounts):
            raise ValueError('Nonfinite amount')
        if amounts[3] is None or amounts[3] >= 0:
            raise ValueError('Expected explicit signed decrease')
        rows.append({'label': row[0], 'raw_cells': row,
                     'amounts': [str(v) if v is not None else None for v in amounts]})
    sums = {name: sum(Decimal(row['amounts'][index]) for row in rows[:-1]) == Decimal(rows[-1]['amounts'][index])
            for name, index in [('opening', 0), ('closing', 5)]}
    if not all(sums.values()):
        raise ValueError('Component balances do not reconcile')
    result = {'symbol': '600018', 'sha256': digest, 'title_page': 241, 'table_page': 242,
              'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-01/1225065811.PDF',
              'unit': 'CNY', 'column_order': ['opening', 'cash_increase', 'noncash_increase',
                                             'signed_cash_decrease', 'signed_noncash_decrease', 'closing'],
              'rows': rows, 'component_balance_checks': sums,
              'full_movements_verified': False, 'complete_debt_verified': False,
              'limitations': ['Blank movements retained as null', 'Negative decreases must not be subtracted again',
                              'Same-document evidence; independent scope review remains required']}
    output = Path('runtime/sipg-signed-financing-20260909.json')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'output': str(output), 'checks': sums, 'components': len(rows)-1}))


if __name__ == '__main__':
    main()
