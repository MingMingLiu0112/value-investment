"""Pinned original-filing arithmetic, not complete interest-bearing debt approval."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from pypdf import PdfReader

from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.financing_table import extract_financing_components
from value_investment_agent.financing_rollforward import AMOUNTS

SHA256 = '14a4aee14a23967837438f10c04c2244616f537402e1456325fcf1409c9e4f8f'
END_BALANCES = ['2923896082.50', '5012787.50', '234152189.81',
                '245795331.64', '603799232.90']
TOTALS = ['2845794781.76', '7676503207.85', '358737056.69',
          '6675219938.53', '193159483.42', '4012655624.35']


def reconcile(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError('Unreviewed source file')
    pages = extract_pages(path, 177)
    page = pages[176]
    layout = PdfReader(path).pages[176].extract_text(extraction_mode='layout')
    parsed = extract_financing_components(layout)
    if parsed is None or not parsed['balances_reconcile']:
        raise ValueError('General financing parser failed balance reconciliation')
    if [parsed['total']['amounts'][field] for field in AMOUNTS] != TOTALS:
        raise ValueError('Parsed totals differ from reviewed table')
    if [row['amounts']['closing'] for row in parsed['rows']] != END_BALANCES:
        raise ValueError('Parsed closing components differ from reviewed table')
    # Only normalize whitespace within this hash-pinned, previously read table.
    text = re.sub(r'\s+', '', page)
    for value in END_BALANCES + TOTALS:
        if format(Decimal(value), ',.2f') not in text:
            raise ValueError('Reviewed amount absent from physical page 177: ' + value)
    opening, cash_in, noncash_in, cash_out, noncash_out, closing = map(Decimal, TOTALS)
    row_sum = sum(map(Decimal, END_BALANCES))
    rollforward = opening + cash_in + noncash_in - cash_out - noncash_out
    if row_sum != closing or rollforward != closing:
        raise ValueError('Financing table does not reconcile')
    bond_text = re.sub(r'\s+', '', pages[163])
    bond_values = ['392349537.41', '7413249.53', '12038392.04',
                   '6093187.50', '171555801.67', '234152189.81',
                   '175656700.00', '4100898.33']
    for value in bond_values:
        if format(Decimal(value), ',.2f') not in bond_text:
            raise ValueError('Reviewed bond amount absent from page 164: ' + value)
    begin, interest, amortization, paid, conversion, end, face, adjustment = map(Decimal, bond_values)
    if begin + interest + amortization - paid - conversion != end:
        raise ValueError('Bond carrying value rollforward mismatch')
    if face - adjustment != conversion:
        raise ValueError('Conversion face/carrying value mismatch')
    return {'symbol': '000411', 'period': '2025-12-31', 'unit': 'CNY',
            'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-23/1225143841.PDF',
            'sha256': SHA256, 'physical_page': 177,
            'component_sum': str(row_sum), 'rollforward_end': str(rollforward),
            'reported_end': str(closing), 'table_arithmetic_verified': True,
            'general_parser_result': parsed,
            'bond_note_page': 164, 'bond_rollforward_verified': True,
            'annual_conversion_face': str(face), 'conversion_interest_adjustment': str(adjustment),
            'annual_conversion_carrying_reduction': str(conversion),
            'complete_interest_bearing_debt_verified': False,
            'independent_source_verified': False,
            'limitations': ['Pinned one-document check, not a general table parser',
                           'Other-payable financing scope remains unresolved',
                           'Current portions already included; do not add twice']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = reconcile(args.pdf)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))
