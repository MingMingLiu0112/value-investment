from value_investment_agent.financial_quality import _accepted, evaluate_financial_quality, GENERAL_FIELDS
import pytest


PROXY = 'short_term_borrowings + current_portion_long_term_debt + long_term_borrowings + bonds_payable'


def point(field):
    return dict(symbol='000338', field_name=field, value='20', unit='CNY' if field in
                ('cash', 'interest_bearing_debt') else 'percent', period_label='2025-12-31',
                validation_status='verified', metadata={'automatic_cross_source_verification': True})


def test_verified_old_debt_proxy_is_not_complete_debt():
    debt = point('interest_bearing_debt')
    debt['metadata']['derivation_formula'] = PROXY
    assert not _accepted(debt)
    assert debt['validation_status'] == 'verified'


def test_missing_complete_scope_flag_is_not_implicit_approval():
    debt = point('interest_bearing_debt')
    assert not _accepted(debt)
    debt['metadata']['complete_debt_verified'] = True
    assert _accepted(debt)


def test_proxy_cannot_produce_total_score_or_cash_coverage_score():
    points = [point(field) for field in GENERAL_FIELDS]
    for row in points:
        if row['field_name'] == 'interest_bearing_debt':
            row['metadata']['derivation_formula'] = PROXY
    result = evaluate_financial_quality('000338', None, None, points)
    assert result.total_score is None
    assert result.cash_flow_score is None
    assert 'interest_bearing_debt' not in result.calculation_details['accepted_fields']
    assert len(result.calculation_details['accepted_fields']) == 8


def test_scope_gate_does_not_discard_other_verified_ratios():
    ratio = point('debt_ratio')
    ratio['metadata']['derivation_formula'] = 'total_liabilities / total_assets * 100'
    assert _accepted(ratio)


@pytest.mark.parametrize('scope', [False, None, 'false', 'true', 0, 1])
def test_explicit_unverified_or_malformed_scope_cannot_be_overridden_by_crosscheck(scope):
    debt = point('interest_bearing_debt')
    debt['metadata']['complete_debt_verified'] = scope
    assert not _accepted(debt)


def test_scope_flag_does_not_replace_evidence_or_approve_old_proxy():
    debt = point('interest_bearing_debt')
    debt['metadata']['complete_debt_verified'] = True
    debt['metadata']['automatic_cross_source_verification'] = False
    assert not _accepted(debt)
    debt['metadata']['automatic_cross_source_verification'] = True
    debt['metadata']['derivation_formula'] = PROXY
    assert not _accepted(debt)


def test_explicit_incomplete_debt_blocks_score_without_affecting_other_fields():
    points = [point(field) for field in GENERAL_FIELDS]
    for row in points:
        if row['field_name'] == 'interest_bearing_debt':
            row['metadata']['complete_debt_verified'] = False
    result = evaluate_financial_quality('000338', None, None, points)
    assert result.total_score is None
    assert len(result.calculation_details['accepted_fields']) == 8
