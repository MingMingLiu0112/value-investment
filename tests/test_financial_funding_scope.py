"""Candidate-only funding rows; synthetic layouts and opt-in real originals."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.financial_funding_scope import (
    FUNDING_LABELS, extract_financial_funding_observations as extract, extract_funding_cash_context,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages


def table(rows, period='2026-06-30', unit='\u5143'):
    year, month, day = map(int, period.split('-'))
    return (f'\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n{year}\u5e74{month}\u6708{day}\u65e5\n'
        f'\u5355\u4f4d\uff1a{unit} \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'
        f'\u9879\u76ee \u9644\u6ce8 {year}\u5e74{month}\u6708{day}\u65e5 {year-1}\u5e7412\u670831\u65e5\n'
        '\u6d41\u52a8\u8d44\u4ea7\uff1a\n'+rows)


@pytest.mark.parametrize('period', ['2025-12-31', '2026-06-30'])
@pytest.mark.parametrize('unit,multiplier', [('\u5143', 1), ('\u5343\u5143', 1000), ('\u4e07\u5143', 10000)])
def test_four_exact_labels_two_columns_and_units(period, unit, multiplier):
    pages = [table('\n'.join(label+' 28 123.00 100.00' for label in FUNDING_LABELS.values()), period, unit)]
    before = deepcopy(pages)
    rows = extract(pages, period)
    assert len(rows) == 4 and pages == before
    for row in rows:
        assert row['value'] == str(123*multiplier)+'.00'
        assert row['prior_value'] == str(100*multiplier)+'.00'
        assert row['period_label'] == period
        assert row['prior_period_label'] == str(int(period[:4])-1)+'-12-31'
        assert row['source_unit'] == unit and row['unit'] == row['currency'] == 'CNY'
        assert row['statement_scope'] == 'consolidated'
        assert row['status'] == 'candidate_funding_scope_unverified'
        assert row['page'] == row['unit_evidence_page'] == 1
        assert row['excerpt'] in pages[0] and 'symbol' not in row


def test_blanks_not_applicability_but_explicit_zero_is_observed():
    label = FUNDING_LABELS['financial_deposits_and_interbank']
    for suffix in ('', ' -- --', ' - -'):
        assert extract([table(label+suffix)], '2026-06-30') == []
    rows = extract([table(label+' 0.00 0.00')], '2026-06-30')
    assert rows[0]['value'] == rows[0]['prior_value'] == '0.00'


@pytest.mark.parametrize('cell', ['100', '28', '\u4e03\uff0830\uff09'])
def test_lone_integer_or_note_is_unknown_not_absent_funding(cell):
    rows = extract([table(FUNDING_LABELS['financial_deposits_and_interbank']+' '+cell)], '2026-06-30')
    assert len(rows) == 1
    assert rows[0]['value'] is rows[0]['prior_value'] is None
    assert rows[0]['reason'] == 'SINGLE_PRINTED_AMOUNT_COLUMN_UNRESOLVED'
    assert rows[0]['status'] == 'candidate_funding_scope_unverified'


@pytest.mark.parametrize('cells', ['1,234.50', '28 1,234.50', '28 - 1,234.50',
    '1.00 2.00 3.00', '1.00 --', '100 200', '1,23.00 2.00'])
def test_ambiguous_cells_never_guess_column_or_zero(cells):
    rows = extract([table(FUNDING_LABELS['interbank_borrowings']+' '+cells)], '2026-06-30')
    assert len(rows) == 1
    assert rows[0]['value'] is rows[0]['prior_value'] is None
    assert 'UNRESOLVED' in rows[0]['reason'] or 'UNSUPPORTED' in rows[0]['reason']


@pytest.mark.parametrize('change', ['reversed', 'wrong_period', 'parent', 'mixed_parent', 'three', 'adjust_before',
    'adjust_after', 'missing_unit', 'wrong_currency', 'unsupported_unit'])
def test_unproven_table_rejected(change):
    page = table(FUNDING_LABELS['repurchase_financing']+' 123.00 100.00')
    if change == 'reversed': page = page.replace('\u9879\u76ee \u9644\u6ce8 2026\u5e746\u670830\u65e5 2025\u5e7412\u670831\u65e5', '\u9879\u76ee 2025\u5e7412\u670831\u65e5 2026\u5e746\u670830\u65e5')
    elif change == 'wrong_period': page = page.replace('2026\u5e746\u670830\u65e5', '2026\u5e7412\u670831\u65e5')
    elif change == 'parent': page = page.replace('\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868', '\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868')
    elif change == 'mixed_parent': page = page.replace('\u9879\u76ee \u9644\u6ce8', '\u9879\u76ee \u9644\u6ce8 \u5408\u5e76 \u6bcd\u516c\u53f8')
    elif change == 'three': page = page.replace('\u6d41\u52a8\u8d44\u4ea7', '2024\u5e7412\u670831\u65e5\n\u6d41\u52a8\u8d44\u4ea7')
    elif change == 'adjust_before': page += '\n\u8c03\u6574\u524d'
    elif change == 'adjust_after': page += '\n\u8c03\u6574\u540e'
    elif change == 'missing_unit': page = page.replace('\u5355\u4f4d\uff1a\u5143', '')
    elif change == 'wrong_currency': page = page.replace('\u4eba\u6c11\u5e01', '\u7f8e\u5143')
    elif change == 'unsupported_unit': page = page.replace('\u5355\u4f4d\uff1a\u5143', '\u5355\u4f4d\uff1a\u4ebf\u5143')
    assert extract([page], '2026-06-30') == []


def test_continuation_ends_at_parent_or_statement_total():
    label = FUNDING_LABELS['financial_deposits_and_interbank']
    header = table('')
    continuation = label+' 10.00 9.00\n\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868\n'+label+' 99.00 88.00'
    rows = extract([header, continuation], '2026-06-30')
    assert len(rows) == 1 and rows[0]['page'] == 2 and rows[0]['unit_evidence_page'] == 1
    assert rows[0]['value'] == '10.00'
    end = '\u8d1f\u503a\u548c\u6240\u6709\u8005\u6743\u76ca\u603b\u8ba1 100.00 90.00'
    assert extract([header+end, label+' 99.00 88.00'], '2026-06-30') == []
    assert extract([header, '\u5355\u4f4d\uff1a\u5343\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'+label+' 99.00 88.00'], '2026-06-30') == []


def test_no_label_prefix_or_derivative_extension():
    label = FUNDING_LABELS['interbank_borrowings']
    assert extract([table(label+'\u884d\u751f\u54c1 10.00 9.00')], '2026-06-30') == []


@pytest.mark.parametrize('period', ['2025-12-31', '2026-06-30'])
@pytest.mark.parametrize('declaration', [
    '\u9879\u76ee \u9644\u6ce8 2024\u5e7412\u670831\u65e5 2023\u5e7412\u670831\u65e5',
    '\u5e01\u79cd\uff1a\u7f8e\u5143',
])
def test_conflicting_continuation_stops_inherited_period_or_currency(period, declaration):
    label = FUNDING_LABELS['financial_deposits_and_interbank']
    initial = table(label+' 10.00 9.00', period)
    rows = extract([initial, declaration+'\n'+label+' 99.00 88.00',
                    label+' 77.00 66.00'], period)
    assert len(rows) == 1 and rows[0]['value'] == '10.00'
    assert rows[0]['page'] == 1


@pytest.mark.parametrize('period', ['2025-12-31', '2026-06-30'])
def test_matching_continuation_columns_and_currency_retain_original_unit(period):
    year, month, day = map(int, period.split('-'))
    label = FUNDING_LABELS['financial_deposits_and_interbank']
    continuation = (f'\u9879\u76ee \u9644\u6ce8\n{year}\u5e74{month}\u6708{day}\u65e5 {year-1}\u5e7412\u670831\u65e5\n'
                    '\u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'+label+' 10.00 9.00')
    rows = extract([table('', period, '\u5343\u5143'), continuation], period)
    assert len(rows) == 1 and rows[0]['value'] == '10000.00'
    assert rows[0]['page'] == 2 and rows[0]['unit_evidence_page'] == 1


@pytest.mark.parametrize('period', ['2026-03-31', '2026', '2026-6-30', '0000-12-31'])
def test_invalid_period_fails_closed(period):
    with pytest.raises(ValueError):
        extract([], period)


def context_pages(period='2025-12-31'):
    year = int(period[:4])
    closing = f'{year}\u5e7412\u670831\u65e5' if period.endswith('12-31') else f'{year}\u5e746\u670830\u65e5'
    columns = (f'{year}\u5e74\u5ea6 {year-1}\u5e74\u5ea6' if period.endswith('12-31') else
               f'{year}\u5e74\u534a\u5e74\u5ea6 {year-1}\u5e74\u534a\u5e74\u5ea6')
    unit = '\u5355\u4f4d\uff1a\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01'
    party = 'TEST\u63a7\u80a1\u96c6\u56e2\u516c\u53f8'
    return [table(FUNDING_LABELS['financial_deposits_and_interbank']+' 100.00 90.00', period),
        f'\u5b58\u6b3e\u4e1a\u52a1\n{unit}\n\u5173\u8054\u65b9 \u5173\u8054\u5173\u7cfb \u671f\u672b\u4f59\u989d\n{party} \u6bcd\u516c\u53f8 30.00 20.00 10.00 40.00',
        f'\u5176\u4ed6\u5173\u8054\u4ea4\u6613\n\u5b58\u6b3e\u4f59\u989d\u53ca\u5e94\u8ba1\u5229\u606f\n{unit}\n\u5173\u8054\u65b9 {closing}\n{party} 40.00',
        f'\u5408\u5e76\u73b0\u91d1\u6d41\u91cf\u8868\n{unit}\n\u9879\u76ee {columns}\n\u516d\u3001\u671f\u672b\u73b0\u91d1\u53ca\u73b0\u91d1\u7b49\u4ef7\u7269\u4f59\u989d 1000.00 900.00',
        f'\u6bcd\u516c\u53f8\u73b0\u91d1\u6d41\u91cf\u8868\n{unit}\n\u9879\u76ee {columns}\n\u516d\u3001\u671f\u672b\u73b0\u91d1\u53ca\u73b0\u91d1\u7b49\u4ef7\u7269\u4f59\u989d 300.00 250.00']


@pytest.mark.parametrize('period', ['2025-12-31', '2026-06-30'])
def test_context_separates_controlling_group_and_issuer_parent_cash(period):
    pages = context_pages(period)
    before = deepcopy(pages)
    rows = extract_funding_cash_context(pages, period)
    by_field = {r['field_name']: r for r in rows}
    assert len(rows) == 4 and pages == before
    assert by_field['controlling_group_deposits']['value'] == '40.00'
    assert by_field['controlling_group_deposits']['relationship'] == 'CONTROLLING_GROUP_NOT_ISSUER_PARENT'
    assert by_field['controlling_group_deposits']['relationship_evidence']['page'] == 2
    assert by_field['consolidated_cash_and_equivalents']['value'] == '1000.00'
    assert by_field['issuer_parent_cash_and_equivalents']['value'] == '300.00'
    assert by_field['issuer_parent_cash_and_equivalents']['statement_scope'] == 'issuer_parent'
    for row in rows:
        assert row['period_label'] == period and row['page'] > 0
        assert row['excerpt'] in pages[row['page']-1]


@pytest.mark.parametrize('fault', ['role', 'date', 'invalid_date', 'two_dates', 'note_unit', 'note_currency', 'duplicate', 'flow', 'cross_table'])
def test_context_ambiguous_or_unbound_controlling_depositor_is_not_guessed(fault):
    pages = context_pages()
    if fault == 'role': pages[1] = pages[1].replace('\u6bcd\u516c\u53f8 ', '\u6bcd\u516c\u53f8\u7684\u5168\u8d44\u5b50\u516c\u53f8 ')
    elif fault == 'date': pages[2] = pages[2].replace('2025\u5e7412\u670831\u65e5', '2024\u5e7412\u670831\u65e5')
    elif fault == 'invalid_date': pages[2] = pages[2].replace('2025\u5e7412\u670831\u65e5', '2025\u5e7413\u670831\u65e5')
    elif fault == 'two_dates': pages[2] = pages[2].replace('2025\u5e7412\u670831\u65e5', '2025\u5e7412\u670831\u65e5 2024\u5e7412\u670831\u65e5')
    elif fault == 'note_unit': pages[2] = pages[2].replace('\u5355\u4f4d\uff1a\u5143', '\u5355\u4f4d\uff1a\u4e07\u5143')
    elif fault == 'note_currency': pages[2] = pages[2].replace('\u4eba\u6c11\u5e01', '\u7f8e\u5143')
    elif fault == 'duplicate': pages.append(pages[2])
    elif fault == 'cross_table': pages[2] = pages[2].replace('40.00', '41.00')
    else: pages[1] = pages[1].replace('10.00 40.00', '11.00 40.00')
    assert 'controlling_group_deposits' not in {r['field_name'] for r in extract_funding_cash_context(pages, '2025-12-31')}


@pytest.mark.parametrize('fault', ['reversed', 'wrong_year', 'unit', 'currency', 'blank', 'duplicate', 'mixed_scope'])
def test_cash_context_requires_explicit_statement_period_unit_and_unique_current_column(fault):
    pages = context_pages()
    if fault == 'reversed': pages[4] = pages[4].replace('2025\u5e74\u5ea6 2024\u5e74\u5ea6', '2024\u5e74\u5ea6 2025\u5e74\u5ea6')
    elif fault == 'wrong_year': pages[4] = pages[4].replace('2025\u5e74\u5ea6 2024\u5e74\u5ea6', '2024\u5e74\u5ea6 2023\u5e74\u5ea6')
    elif fault == 'unit': pages[4] = pages[4].replace('\u5355\u4f4d\uff1a\u5143', '\u5355\u4f4d\uff1a\u4e07\u5143')
    elif fault == 'currency': pages[4] = pages[4].replace('\u4eba\u6c11\u5e01', '\u7f8e\u5143')
    elif fault == 'blank': pages[4] = pages[4].replace('300.00 250.00', '-- 250.00')
    elif fault == 'duplicate': pages.append(pages[4])
    else: pages[4] = pages[4].replace('\u6bcd\u516c\u53f8\u73b0\u91d1\u6d41\u91cf\u8868', '\u5408\u5e76\u73b0\u91d1\u6d41\u91cf\u8868')
    rows = extract_funding_cash_context(pages, '2025-12-31')
    assert 'issuer_parent_cash_and_equivalents' not in {r['field_name'] for r in rows}


def test_cash_context_continuation_preserves_header_not_business_unit_word():
    pages = context_pages()
    heading, balance = pages[4].rsplit('\n', 1)
    pages[4:] = [heading, '\u5904\u7f6e\u5b50\u516c\u53f8\u53ca\u5176\u4ed6\u8425\u4e1a\u5355\u4f4d\n'+balance]
    row = next(r for r in extract_funding_cash_context(pages, '2025-12-31')
               if r['field_name'] == 'issuer_parent_cash_and_equivalents')
    assert row['page'] == 6 and row['statement_header_page'] == row['unit_evidence_page'] == 5
    pages[5] = '\u5355\u4f4d\uff1a\u4e07\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'+balance
    assert 'issuer_parent_cash_and_equivalents' not in {r['field_name'] for r in extract_funding_cash_context(pages, '2025-12-31')}


def test_real_maotai_fy_h1_originals_and_unchanged_income_implementations():
    source = os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    if not source:
        pytest.skip('Explicit public original root required; no network/source discovery')
    root = Path(source).resolve()
    hash_file = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    candidate_path = root/'runtime/source-native-pending/3bb7bfe05c3f4c7d9a52d34b07588087/candidate.json'
    assert hash_file(candidate_path) == 'bfba1fb08f316cd4791e2f8d36490a86345e969d1f2c97663fb7a1e42aa912d8'
    candidate = json.loads(candidate_path.read_bytes())
    package_binding = candidate['source_package_binding']
    assert hash_file(root/package_binding['path']) == package_binding['sha256']
    package = json.loads((root/package_binding['path']).read_bytes())
    preserved = ['src/value_investment_agent/infrastructure/screening/value_evidence_enrichment_v1.py',
                 'src/value_investment_agent/filing_extract.py',
                 'src/value_investment_agent/infrastructure/filings/financial_funding_scope.py',
                 'src/value_investment_agent/financing_table.py',
                 'src/value_investment_agent/financing_rollforward.py',
                 'src/value_investment_agent/infrastructure/filings/pdf_text.py',
                 'src/value_investment_agent/infrastructure/filings/pdfium_runtime.py']
    code_root = Path(__file__).resolve().parents[1]
    assert Path(extract.__code__.co_filename).resolve() == (code_root/preserved[2]).resolve()
    # The retained-data checkout need not share the execution checkout's EOLs.
    # Bind the actual executing implementations separately, never normalize IDs.
    executing_before = {name: hash_file(code_root/name) for name in preserved}
    before = {name: hash_file(root/name) for name in preserved}
    reports = []
    for source_id, period, expected, prior in [
        ('cninfo:1225114741', '2025-12-31', '18038383776.30', '23102858820.97'),
        ('cninfo:1225475868', '2026-06-30', '25426316668.17', '18038383776.30')]:
        row = next(item for item in package['sources'] if item['id'] == source_id)
        path = root/row['local_path']
        assert hash_file(path) == row['sha256']
        before[row['local_path']] = row['sha256']
        pages = extract_pages(path)
        observations = extract(pages, period)
        assert len(observations) == 1
        observation = observations[0]
        assert observation['field_name'] == 'financial_deposits_and_interbank'
        assert observation['value'] == expected and observation['prior_value'] == prior
        assert observation['page'] == (58 if period == '2025-12-31' else 27)
        context = extract_funding_cash_context(pages, period)
        by_field = {item['field_name']: item for item in context}
        expected_context = ({
            'controlling_group_deposits': ('8330698318.34', 131),
            'consolidated_cash_and_equivalents': ('126425609447.72', 66),
            'issuer_parent_cash_and_equivalents': ('84730758118.65', 67),
        } if period == '2025-12-31' else {
            'controlling_group_deposits': ('15158632454.02', 97),
            'consolidated_cash_and_equivalents': ('184811095482.62', 35),
            'issuer_parent_cash_and_equivalents': ('61255736577.13', 36),
        })
        assert len(context) == 4
        for field, (value, page) in expected_context.items():
            assert (by_field[field]['value'], by_field[field]['page']) == (value, page)
            assert by_field[field]['excerpt'] in pages[page-1]
            assert by_field[field]['period_label'] == period
        # Arch's two counterexamples on in-memory copies of the actual A58/H27.
        # No original bytes, amounts or source dates are modified on disk.
        for declaration in (
            '\u9879\u76ee \u9644\u6ce8 2024\u5e7412\u670831\u65e5 2023\u5e7412\u670831\u65e5',
            '\u5e01\u79cd\uff1a\u7f8e\u5143',
        ):
            altered = list(pages)
            index = observation['page']-1
            altered[index] = declaration+'\n'+altered[index]
            assert extract(altered, period) == []
        reports.append(dict(source_id=source_id, source_url=row['location'], path=row['local_path'],
            sha256=row['sha256'], observations=observations, research_observations=context))
    assert {name: hash_file(root/name) for name in before} == before
    assert {name: hash_file(code_root/name) for name in executing_before} == executing_before
    output = os.environ.get('FUNDING_SCOPE_RECEIPT_DIR')
    if output:
        from datetime import datetime, timezone
        directory = Path(output).resolve()
        assert directory.is_relative_to(root/'.tmp')
        directory.mkdir(parents=True, exist_ok=False)
        receipt = dict(status='PASS', scope='ACTUAL_RETAINED_PUBLIC_ORIGINALS_COLD_EXTRACTION_NOT_FACT_ADMISSION',
            observed_at=datetime.now(timezone.utc).isoformat(), action='no_order',
            candidate_binding=dict(path=candidate_path.relative_to(root).as_posix(), sha256=hash_file(candidate_path)),
            package_binding=package_binding, reports=reports, source_hashes_before=before,
            source_hashes_after={name: hash_file(root/name) for name in before},
            executing_implementations_before=executing_before,
            executing_implementations_after={name: hash_file(code_root/name) for name in executing_before},
            verification_created=False, formal_eligibility=False,
            source_adapter_created=False, income_implementations_unchanged=True,
            raw_pages_authenticate_identity=False,
            limitations=['Caller must verify security identity, original hash, availability and source closure.',
                        'Printed consolidated funding rows do not classify industrial debt, applicability or completeness.',
                        'No fact registration, financial admission, Quality/G3 approval or investment recommendation.'])
        with (directory/'receipt.json').open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
