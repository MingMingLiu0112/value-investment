import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('monthly',
    Path(__file__).resolve().parents[1] / 'scripts/check_midea_monthly_shares.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

FIRST = 'Midea Group Co., Ltd. For the month ended: 30 September 2025 Date Submitted: 03 October 2025'
HEAD = 'II. Movements in Issued Shares and/or Treasury Shares '


def row(kind, code):
    return (f'Class of shares Ordinary shares Type of shares {kind} Listed on the Exchange (Note 1) Yes '
            f'Stock code (if listed) {code} Description Shares '
            'Number of issued shares (excluding treasury shares) Number of treasury shares Total number of issued shares '
            'Balance at close of preceding month 100 10 110 Increase / decrease (-) -10 10 '
            'Balance at close of the month 90 20 110 ')


def test_distinguish_share_classes_and_treasury():
    result = module.parse_reviewed_table([FIRST, HEAD + row('H', '00300') + row('A', '000333')])
    assert result['H'] == {'issued_excluding_treasury': 90, 'treasury': 20, 'issued_total': 110}
    assert result['A'] == result['H']


@pytest.mark.parametrize('mutation', ['period', 'scope', 'wrong_code', 'arithmetic', 'duplicate'])
def test_reject_wrong_identity_scope_and_amounts(mutation):
    first, table = FIRST, HEAD + row('H', '00300') + row('A', '000333')
    if mutation == 'period': first = first.replace('September', 'August')
    if mutation == 'scope': table = table.replace('(excluding treasury shares)', '(including treasury shares)')
    if mutation == 'wrong_code': table = table.replace('000333', '000334')
    if mutation == 'arithmetic': table = table.replace('90 20 110', '90 20 111')
    if mutation == 'duplicate': table += row('A', '000333')
    with pytest.raises(ValueError): module.parse_reviewed_table([first, table])


def test_missing_h_column_header_cannot_borrow_a_table():
    h = row('H', '00300').replace('Number of issued shares (excluding treasury shares)', 'Missing header')
    with pytest.raises(ValueError):
        module.parse_reviewed_table([FIRST, HEAD + h + row('A', '000333')])


def availability_index():
    return {'News': [{'ID': 7812944, 'formatedDate': '03 October 2025',
        'title': 'Monthly Return of Equity Issuer on Movements in Securities for the month ended 30 September 2025'}],
        'Attachments': [{'prID': 7812944, 'atID': 3926930,
                         'filename': 'HKEX-EPS_20251003_11869418_0.PDF'}]}


def test_availability_is_after_disclosure_not_period_end_and_not_approved():
    result = module.reviewed_availability(availability_index())
    assert result['available_at_candidate'] == '2025-10-04T00:00:00+08:00'
    assert result['availability_bound_verified'] is False
    assert 'available_at' not in result


@pytest.mark.parametrize('mutation', ['date', 'duplicate', 'attachment', 'title'])
def test_availability_rejects_mismatched_index(mutation):
    index = availability_index()
    if mutation == 'date': index['News'][0]['formatedDate'] = '30 September 2025'
    if mutation == 'duplicate': index['News'] *= 2
    if mutation == 'attachment': index['Attachments'][0]['atID'] = 1
    if mutation == 'title': index['News'][0]['title'] = 'Different report'
    with pytest.raises(ValueError):
        module.reviewed_availability(index)
