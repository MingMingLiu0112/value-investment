import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('insertion', Path(__file__).parents[1] / 'scripts/insert_reviewed_parser_candidates.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(**changes):
    return dict(field_name='cash', source_label='cash', page=1, value='10', unit='CNY',
                status='candidate_pending_automated_verification', **changes)


def test_only_missing_slots_added():
    new = {**row(), 'page': 2}
    assert module.missing_candidates([row()], [row(), new]) == [new]


def test_retired_slot_never_reactivated():
    with pytest.raises(ValueError, match='retired'):
        module.missing_candidates([{**row(), 'status': 'superseded_by_parser'}], [row()])


def test_changed_amount_rejected():
    with pytest.raises(ValueError, match='differs'):
        module.missing_candidates([row()], [{**row(), 'value': '11'}])


def test_duplicate_slots_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        module.missing_candidates([], [row(), row()])
