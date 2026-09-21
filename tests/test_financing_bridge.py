from copy import deepcopy

import pytest

from value_investment_agent.financing_bridge import bridge_financing_rows


def fixture():
    table = {'rows': [{'label': '短期借款', 'amounts': {'closing': '100.00'}}],
             'total': {'unit': 'CNY'}}
    fact = {'symbol': '001386', 'field_name': 'short_term_borrowings',
            'period_label': '2025-12-31', 'value': '100', 'unit': 'CNY',
            'data_point_id': 'fact', 'source_id': 'official', 'sha256': 'a' * 64,
            'source_url': 'https://example.test/report.pdf', 'validation_status': 'verified',
            'metadata': {'automatic_cross_source_verification': True,
                         'official_file_sha256': 'a' * 64, 'secondary_source_id': 'secondary',
                         'secondary_data_point_id': 'other-fact',
                         'secondary_source_url': 'https://example.test/secondary'}}
    return table, fact


def run(table, points):
    return bridge_financing_rows(table, points, '001386', '2025-12-31', 'a' * 64,
                                 'https://example.test/report.pdf')


def test_exact_match_retains_evidence_without_complete_debt_approval():
    table, fact = fixture()
    result = run(table, [fact, deepcopy(fact)])
    assert result['matched_rows'] == 1
    assert result['rows'][0]['balance_fact'] == fact
    assert result['rows'][0]['difference_cny'] == '0.00'
    assert not result['complete_debt_verified']


@pytest.mark.parametrize('value,unit', [('0.01', 'CNY 10K'), ('0.000001', 'CNY 100M')])
def test_only_explicit_compatible_units_normalize(value, unit):
    table, fact = fixture()
    fact.update(value=value, unit=unit)
    assert run(table, [fact])['matched_rows'] == 1


@pytest.mark.parametrize('change', [
    {'symbol': '600519'}, {'period_label': '2024-12-31'}, {'sha256': 'b' * 64},
    {'source_url': 'https://example.test/revision.pdf'}, {'source_id': ''},
    {'data_point_id': ''}, {'validation_status': 'pending'}, {'unit': 'USD'},
    {'value': None}, {'value': 'NaN'}, {'value': '-100'}, {'value': '100.01'},
])
def test_conflicts_missing_identity_and_other_period_never_match(change):
    table, fact = fixture()
    fact.update(change)
    assert run(table, [fact])['matched_rows'] == 0


@pytest.mark.parametrize('change', [
    {'automatic_cross_source_verification': 'true'}, {'evidence_quarantine': True},
    {'superseded_by_parser': 'new-version'},
    {'secondary_source_id': ''}, {'secondary_data_point_id': ''},
    {'secondary_source_url': ''}, {'official_file_sha256': 'b' * 64},
    {'secondary_source_id': 'official'}, {'secondary_data_point_id': 'fact'},
])
def test_retained_independent_evidence_is_required(change):
    table, fact = fixture()
    fact['metadata'].update(change)
    assert run(table, [fact])['matched_rows'] == 0


def test_different_candidate_is_not_discarded_even_if_old_fact_matches():
    table, fact = fixture()
    other = {**fact, 'data_point_id': 'new', 'validation_status': 'pending', 'value': '101'}
    result = run(table, [fact, other])
    assert result['rows'][0]['status'] == 'ambiguous_balance_facts'
    assert result['matched_rows'] == 0


def test_blank_financing_value_cannot_match_zero_balance():
    table, fact = fixture()
    table['rows'][0]['amounts']['closing'] = None
    fact['value'] = '0'
    result = run(table, [fact])
    assert result['matched_rows'] == 0
    assert result['rows'][0]['status'] == 'financing_closing_unknown_or_invalid'
    assert run(table, [])['rows'][0]['status'] == 'financing_closing_unknown_or_invalid'


def test_current_inclusive_labels_cannot_map_to_noncurrent_or_aggregate_balances():
    table, fact = fixture()
    for label in ('银行借款(含一年内到期)', '租赁负债(含一年内到期)', '其他流动负债'):
        table['rows'][0]['label'] = label
        result = run(table, [fact])
        assert result['rows'][0]['status'] == 'requires_note_classification'
        assert result['rows'][0]['field_name'] is None


def test_missing_report_hash_rejects_before_comparison():
    table, fact = fixture()
    with pytest.raises(ValueError, match='identity'):
        bridge_financing_rows(table, [fact], '001386', '2025-12-31', '', fact['source_url'])


def test_audit_rehashes_original_and_rejects_ambiguous_replay(tmp_path):
    import hashlib
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location('balance_bridge_audit',
        Path(__file__).resolve().parents[1] / 'scripts' / 'audit_financing_balance_bridge.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = tmp_path / 'identity-fixture.pdf'
    original.write_bytes(b'identity fixture, not a real PDF')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    table, fact = fixture()
    fact['sha256'] = fact['metadata']['official_file_sha256'] = digest
    manifest = {'reports': [{'symbol': '001386', 'report_period': '2025-12-31',
        'sha256': digest, 'source_url': fact['source_url'], 'archive_hash_matched': True}]}
    replay = [{'sha256': digest, 'path': str(original),
               'hits': [{'physical_page': 203, 'parsed': table}]}]
    result = module.audit({'annual_points': [fact]}, manifest, replay)
    assert result['reports'][0]['matched_rows'] == 1
    assert result['reports'][0]['physical_pages'] == [203]
    with pytest.raises(ValueError, match='ambiguous'):
        module.audit({'annual_points': [fact]}, manifest, replay * 2)
    original.write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        module.audit({'annual_points': [fact]}, manifest, replay)
