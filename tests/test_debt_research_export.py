import hashlib
import json

import pytest

from value_investment_agent.debt_research_export import load_debt_research


def fixture(tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    original = runtime / 'original.pdf'
    original.write_bytes(b'original identity fixture')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    source = {'symbol': '600001', 'sha256': digest, 'source_url': 'https://example.test/report.pdf',
              'report_period': '2025-12-31', 'source_id': 'official'}
    row = {'label': '合计', 'amounts': {'closing': '10000'}, 'raw_cells': ['合计', '10', '20']}
    audit = {'payload_sha256': 'snapshot', 'reports': [{**source,
        'financing': {'path': str(original)}, 'notes': [{'rows': [], 'total': row, 'physical_page': 5,
            'context': '单位：千元', 'parser': 'fixture', 'normalization_multiplier': '1000'}],
        'reconciliation': {'aggregate_bridge': {'matched_rows': 1}}}]}
    path = runtime / 'audit.json'
    path.write_text(json.dumps(audit), encoding='utf-8')
    config = {'audit_path': 'runtime/audit.json', 'audit_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (tmp_path / 'debt-research.json').write_text(json.dumps(config), encoding='utf-8')
    return {'disclosures': [source]}, original, path


def test_research_is_unapproved_and_displays_original_unit_not_normalized_as_original(tmp_path):
    payload, _, _ = fixture(tmp_path)
    result = load_debt_research(tmp_path, payload, 'snapshot')
    row = result['evidence']['600001'][0]
    assert row['value'] == '10'
    assert row['unit'] == 'CNY thousand'
    assert row['status'] == '研究提取，非已验证指标'
    assert row['field_name'].startswith('research_')
    assert '完整有息负债未验证' in result['companies']['600001']


def verified_point(payload):
    source = payload['disclosures'][0]
    return {**source, 'field_name': 'current_portion_long_term_debt', 'period_label': source['report_period'],
            'value': '10000', 'unit': 'CNY', 'data_point_id': 'current-fact', 'validation_status': 'verified',
            'metadata': {'automatic_cross_source_verification': True, 'official_file_sha256': source['sha256'],
                         'secondary_data_point_id': 'secondary-fact', 'secondary_source_id': 'secondary',
                         'secondary_source_url': 'https://example.test/secondary'}}


def test_cached_match_never_replaces_missing_current_fact_even_on_same_snapshot(tmp_path):
    payload, _, _ = fixture(tmp_path)
    result = load_debt_research(tmp_path, payload, 'snapshot')
    assert '当前导出缺少对应本期指标' in result['companies']['600001']


def test_new_snapshot_rechecks_actual_current_fact_and_retains_lineage(tmp_path):
    payload, _, _ = fixture(tmp_path)
    payload['annual_points'] = [verified_point(payload)]
    result = load_debt_research(tmp_path, payload, 'new-snapshot')
    assert '与当前导出金额一致' in result['companies']['600001']
    row = result['evidence']['600001'][0]
    assert row['status'] == '研究提取，非已验证指标'
    check = json.loads(row['excerpt'])['current_export_recheck']
    assert check['payload_sha256'] == 'new-snapshot'
    assert check['data_point_id'] == 'current-fact'
    assert check['secondary_data_point_id'] == 'secondary-fact'
    assert check['difference_cny'] == '0'
    assert len(check['recheck_id']) == 64
    assert result == load_debt_research(tmp_path, payload, 'new-snapshot')


@pytest.mark.parametrize('change,expected', [({'value': '10001'}, '金额冲突'),
    ({'validation_status': 'pending'}, '证据尚未通过校验'),
    ({'unit': 'USD'}, '单位不兼容')])
def test_changed_current_fact_does_not_inherit_cached_match(tmp_path, change, expected):
    payload, _, _ = fixture(tmp_path)
    payload['annual_points'] = [{**verified_point(payload), **change}]
    result = load_debt_research(tmp_path, payload, 'snapshot')
    assert expected in result['companies']['600001']
    assert '金额一致' not in result['companies']['600001']


def test_duplicate_candidate_never_silently_uses_matching_fact(tmp_path):
    payload, _, _ = fixture(tmp_path)
    point = verified_point(payload)
    payload['annual_points'] = [point, {**point, 'data_point_id': 'new-fact', 'value': '10001'}]
    result = load_debt_research(tmp_path, payload, 'snapshot')
    assert '候选不唯一' in result['companies']['600001']


def test_changed_original_or_missing_export_source_disables_numeric_display(tmp_path):
    payload, original, _ = fixture(tmp_path)
    assert not load_debt_research(tmp_path, {}, 'snapshot')['evidence']
    original.write_bytes(b'changed original')
    result = load_debt_research(tmp_path, payload, 'snapshot')
    assert not result['evidence']
    assert '停用' in result['companies']['600001']


def test_changed_audit_aborts_before_workbook_publication(tmp_path):
    payload, _, audit = fixture(tmp_path)
    audit.write_bytes(b'{}')
    with pytest.raises(ValueError, match='audit changed'):
        load_debt_research(tmp_path, payload, 'snapshot')


def test_unconfigured_project_has_no_research_inputs(tmp_path):
    assert load_debt_research(tmp_path, {}, '') == {'companies': {}, 'evidence': {}}
