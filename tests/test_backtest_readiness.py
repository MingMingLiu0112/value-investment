import importlib.util
import pytest
from pathlib import Path

spec = importlib.util.spec_from_file_location('readiness',
    Path(__file__).resolve().parents[1] / 'scripts/audit_backtest_readiness.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_export_inventory_never_approves_strategy_or_double_counts():
    point = {'symbol': '600519', 'source_id': 's', 'field_name': 'fair_value',
             'period_label': '2025-12-31', 'published_at': '2026-04-01',
             'validation_status': 'verified',
             'metadata': {'automatic_cross_source_verification': True}}
    result = module.audit({'points': [point], 'annual_points': [point]})
    row = result['companies'][0]
    assert row['unique_evidence_rows'] == 1 and row['verified_fair_values'] == 1
    assert not row['historical_backtest_ready']
    point['metadata']['evidence_quarantine'] = {'reason': 'bad scope'}
    assert module.audit({'points': [point]})['companies'][0]['verified_fair_values'] == 0
    assert result['companies'][1]['unique_evidence_rows'] == 0


@pytest.mark.parametrize('flag', [False, None, 'false', 'true', 0, 1, {}, []])
def test_inventory_rejects_non_boolean_verification(flag):
    point = {'symbol': '600519', 'source_id': 's', 'field_name': 'fair_value',
             'period_label': '2025-12-31', 'validation_status': 'verified',
             'metadata': {'automatic_cross_source_verification': flag}}
    row = module.audit({'points': [point]})['companies'][0]
    assert row['verified_fair_values'] == 0
    assert row['historical_backtest_ready'] is False
