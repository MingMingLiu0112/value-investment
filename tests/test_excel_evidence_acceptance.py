from value_investment_agent.excel_report import accepted, point_status, choose_points
from value_investment_agent.quality import accepted_verification


def point():
    return {'symbol': '000411', 'field_name': 'cash', 'period_label': '2025-12-31',
            'validation_status': 'verified', 'metadata': {'automatic_cross_source_verification': True}}


def test_quarantined_verified_evidence_is_not_displayed_as_accepted():
    row = point()
    row['metadata']['evidence_quarantine'] = {'reason': 'wrong_scope'}
    assert not accepted(row)
    assert point_status(row) == '\u8bc1\u636e\u5df2\u9694\u79bb\uff0c\u4e0d\u53c2\u4e0e\u51b3\u7b56'


def test_old_debt_proxy_is_not_complete_but_named_subtotal_is_valid():
    row = point()
    row['field_name'] = 'interest_bearing_debt'
    row['metadata']['derivation_formula'] = 'short_term_borrowings + current_portion_long_term_debt + long_term_borrowings + bonds_payable'
    assert not accepted(row)
    assert '\u5b8c\u6574\u53e3\u5f84\u672a\u9a8c\u8bc1' in point_status(row)
    row['field_name'] = 'borrowings_bonds_subtotal'
    assert accepted(row)


def test_quarantined_evidence_loses_same_period_verified_preference():
    bad = point()
    bad['metadata']['evidence_quarantine'] = {'reason': 'wrong_scope'}
    bad['created_at'] = '2026-09-08'
    good = point()
    good['created_at'] = '2026-09-07'
    assert choose_points([good, bad])[('000411', 'cash')] is good


def test_incomplete_debt_is_rejected_by_excel_and_decision_gate():
    row = point()
    row['field_name'] = 'interest_bearing_debt'
    row['metadata']['complete_debt_verified'] = False
    assert not accepted(row)
    assert not accepted_verification(row)
    assert point_status(row) == '完整债务口径未验证，不参与决策'


def test_legacy_proxy_is_rejected_by_decision_gate_too():
    row = point()
    row['field_name'] = 'interest_bearing_debt'
    row['metadata']['derivation_formula'] = 'short_term_borrowings + current_portion_long_term_debt + long_term_borrowings + bonds_payable'
    assert not accepted_verification(row)
    row['field_name'] = 'borrowings_bonds_subtotal'
    assert accepted_verification(row)
