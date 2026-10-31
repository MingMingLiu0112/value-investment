"""No fabricated cash or disclosure classification in public economic steps."""
from copy import deepcopy

from value_investment_agent.application.product.consumed_economic_path import _economic_path


def test_missing_cash_is_not_zero_and_input_is_not_mutated():
    review = dict(basis_at='2026-06-30', valuation_at='2026-06-30',
        candidate_binding={'path': 'TEST_ONLY/candidate', 'sha256': 'a' * 64},
        policy_binding={'path': 'TEST_ONLY/policy', 'sha256': 'b' * 64},
        scenarios=[dict(scenario='base', ledger={'rows': [dict(year=1, revenue='123', cost='0')]})])
    before = deepcopy(review)
    actual = _economic_path(review)
    steps = actual['scenarios'][0]['years'][0]['steps']
    assert steps[0]['status'] == 'available'
    cash = next(step for step in steps if step['id'] == 'access')
    assert cash['status'] == 'missing'
    assert cash['values']['accessible_profit'] is None
    assert 'accessible_profit' in cash['missing_fields']
    assert actual['action'] == 'no_order'
    assert actual['scope'] == 'ordinary_owner_equivalent_cash_mapping'
    assert review == before
