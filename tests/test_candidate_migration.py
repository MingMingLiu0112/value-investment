from value_investment_agent.candidate_migration import plan_candidate_supersession


def row(identifier='a', **changes):
    return dict(candidate_id=identifier, field_name='cash', page_number=1, source_label='cash',
                value='10.00', unit='CNY', status='candidate_pending_automated_verification', **changes)


def test_identical_numeric_format_preserves_candidate():
    revised = dict(field_name='cash', page=1, source_label='cash', value='10', unit='CNY')
    assert plan_candidate_supersession([row()], [revised], [])['reproduced'] == ['a']


def test_missing_unpromoted_candidate_is_only_planned_not_mutated():
    original = row()
    assert plan_candidate_supersession([original], [], [])['unpromoted_obsolete'] == ['a']
    assert original['status'] == 'candidate_pending_automated_verification'


def test_any_fact_reference_requires_audit_even_if_candidate_pending():
    assert plan_candidate_supersession([row()], [], ['a'])['fact_backed_requires_audit'] == ['a']


def test_verified_status_is_protected_without_fact_reference():
    original = row()
    original['status'] = 'automatically_verified'
    assert plan_candidate_supersession([original], [], [])['fact_backed_requires_audit'] == ['a']


def test_unit_or_page_change_is_not_exact_reproduction():
    original = row()
    for field, value in [('unit', 'CNY 10K'), ('page_number', 2), ('value', '11')]:
        revised = {**original, field: value}
        assert plan_candidate_supersession([original], [revised], [])['unpromoted_obsolete'] == ['a']


def test_changed_amount_in_same_unique_slot_requires_explicit_migration():
    revised = {**row(), 'value': '11'}
    plan = plan_candidate_supersession([row()], [revised], [])
    assert plan['unique_key_collisions'] == ['a']
    assert plan['unpromoted_obsolete'] == ['a']


def test_numeric_format_only_is_not_a_collision():
    assert plan_candidate_supersession([row()], [{**row(), 'value': '10'}], [])['unique_key_collisions'] == []


def test_conflicting_revised_values_are_not_hidden_by_one_matching_value():
    plan = plan_candidate_supersession([row()], [row(), {**row(), 'value': '11'}], [])
    assert plan['reproduced'] == ['a']
    assert plan['unique_key_collisions'] == ['a']


def test_different_page_does_not_hit_same_database_unique_slot():
    revised = {**row(), 'page_number': 2, 'value': '11'}
    assert plan_candidate_supersession([row()], [revised], [])['unique_key_collisions'] == []


def test_retired_candidate_is_not_planned_for_reactivation():
    retired = {**row(), 'status': 'superseded_by_parser'}
    plan = plan_candidate_supersession([retired], [row()], ['a'])
    assert plan['already_superseded'] == ['a']
    assert plan['reproduced'] == []
    assert plan['fact_backed_requires_audit'] == []


def test_retired_slot_still_blocks_changed_value_insert():
    retired = {**row(), 'status': 'superseded_by_parser'}
    plan = plan_candidate_supersession([retired], [{**row(), 'value': '11'}], [])
    assert plan['already_superseded'] == ['a']
    assert plan['unique_key_collisions'] == ['a']
