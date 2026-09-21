from decimal import Decimal

from value_investment_agent.candidate_review import latest_consistent_secondary


def point(value, source='provider-a', unit='percent'):
    return dict(value=value, source_name=source, unit=unit)


def test_new_conflict_cannot_be_bypassed_by_old_match():
    assert latest_consistent_secondary([point('12'), point('8')], Decimal('8'), 'percent') is None


def test_new_correction_supersedes_old_conflict():
    current = point('8')
    assert latest_consistent_secondary([current, point('12')], Decimal('8'), 'percent') is current


def test_conflicting_other_provider_blocks_promotion():
    assert latest_consistent_secondary(
        [point('8'), point('12', 'provider-b')], Decimal('8'), 'percent'
    ) is None


def test_latest_unit_conflict_cannot_be_bypassed():
    assert latest_consistent_secondary(
        [point('8', unit='CNY'), point('8')], Decimal('8'), 'percent'
    ) is None


def test_empty_and_agreeing_sources():
    assert latest_consistent_secondary([], Decimal('8'), 'percent') is None
    current = point('8')
    assert latest_consistent_secondary(
        [current, point('8.01', 'provider-b')], Decimal('8'), 'percent'
    ) is current
