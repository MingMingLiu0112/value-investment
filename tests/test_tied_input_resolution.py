from copy import deepcopy

import pytest

from scripts.tied_input_resolution import CASES, plan_resolution


def rows():
    return [dict(data_point_id=c[p+'_id'], symbol=c['symbol'], field_name=c['field'],
                 period_label='2025-12-31', unit='CNY', value=c[p+'_value'], sha256=c['sha256'],
                 source_id=c['symbol'], validation_status='verified', human_reviewed=False,
                 metadata={'page_number': c[p+'_page'], 'automatic_cross_source_verification': True})
            for c in CASES for p in ('old', 'new')]


def test_exact_reviewed_records_produce_three_non_mutating_replacements():
    inputs = rows()
    original = deepcopy(inputs)
    changes = plan_resolution(inputs)
    assert len(changes) == 3
    assert all(c['replacement_data_point_id'] == c['new_id'] for c in changes)
    assert inputs == original


@pytest.mark.parametrize('field,value', [('value', '0'), ('sha256', 'changed'),
                                        ('source_id', 'other'), ('human_reviewed', True),
                                        ('period_label', '2024-12-31')])
def test_changed_preconditions_block_entire_plan(field, value):
    inputs = rows()
    inputs[0][field] = value
    with pytest.raises(ValueError):
        plan_resolution(inputs)


def test_quarantined_replacement_cannot_be_used():
    inputs = rows()
    inputs[1]['metadata']['evidence_quarantine'] = 'unresolved'
    with pytest.raises(ValueError):
        plan_resolution(inputs)
