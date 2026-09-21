import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('historical_audit',
    Path(__file__).resolve().parents[1] / 'scripts/audit_historical_candidates.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def packet(rows):
    return {'symbol': '000333', 'report_period_from_title': '2021-12-31',
            'candidates': rows}


def test_changed_value_and_missing_packet_are_reported():
    old = {'field_name': 'net_income', 'value': '10', 'unit': 'CNY', 'page': 9}
    new = dict(old, value='10000')
    result = module.audit({('000333', 'a'): packet([new])},
                          {('000333', 'a'): packet([old]), ('000333', 'b'): packet([old])})
    assert result['changes'][0]['removed'][0][1] == '10'
    assert result['changes'][0]['added'][0][1] == '10000'
    assert result['changes'][1]['packet_missing']
    assert result['companies'][0]['missing_candidate_periods']['eps_ttm'] == ['2021-12-31']
    assert not result['historical_backtest_ready']


def test_duplicate_candidate_loss_is_not_hidden_by_set_comparison():
    row = {'field_name': 'revenue', 'value': '10', 'unit': 'CNY', 'page': 9}
    result = module.audit({('000333', 'a'): packet([row])},
                          {('000333', 'a'): packet([row, row])})
    assert len(result['changes'][0]['removed']) == 1
