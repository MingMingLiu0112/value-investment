"""Synthetic availability contracts, not verified historical trading dates."""
import pytest

from value_investment_agent.historical_asof import select_asof
from value_investment_agent.historical_asof import publication_date_upper_bound


def fact(**changes):
    return dict(dict(symbol='601088', field_name='bvps', period_label='2014-12-31',
                     value='14.67', unit='CNY/share', source_id='original',
                     raw_file_hash='test-fixture-only', validation_status='verified',
                     availability_verified=True, timestamp_precision='timestamp',
                     published_at='2015-03-21T08:00:00+08:00',
                     available_at='2015-03-21T08:00:00+08:00'), **changes)


def choose(points, at='2015-04-01T00:00:00+08:00'):
    return select_asof(points, symbol='601088', field_name='bvps',
                       period_label='2014-12-31', decision_at=at)


def test_later_restatement_does_not_leak_backwards():
    original = fact()
    revised = fact(value='14.84', source_id='revision',
                   published_at='2016-03-01T08:00:00+08:00',
                   available_at='2016-03-01T08:00:00+08:00')
    assert choose([revised, original]) == [original]
    assert choose([original, revised], '2016-04-01T00:00:00+08:00') == [revised]
    assert choose([original], '2015-03-20T00:00:00+08:00') == []


@pytest.mark.parametrize('changes', [dict(timestamp_precision='date_only_until_verified'),
    dict(availability_verified=False), dict(validation_status='candidate'),
    dict(raw_file_hash=''), dict(metadata={'evidence_quarantine': True}),
    dict(period_label='2015-12-31')])
def test_unusable_evidence_is_not_selected(changes):
    assert choose([fact(**changes)]) == []


def test_conflicts_do_not_depend_on_input_order():
    with pytest.raises(ValueError, match='Conflicting'):
        choose([fact(), fact(value='17.88')])


def test_timezone_and_chronology_are_enforced():
    with pytest.raises(ValueError, match='Timezone'):
        choose([fact()], '2015-04-01T00:00:00')
    with pytest.raises(ValueError, match='precedes'):
        choose([fact(available_at='2015-03-20T00:00:00+08:00')])


def test_ingestion_delay_controls_visibility():
    assert choose([fact(available_at='2015-05-01T00:00:00+08:00')]) == []


def test_late_ingestion_of_old_document_does_not_replace_revision():
    original = fact(available_at='2016-05-01T00:00:00+08:00')
    revision = fact(value='14.84', source_id='revision',
                    published_at='2016-03-01T00:00:00+08:00',
                    available_at='2016-03-02T00:00:00+08:00')
    assert choose([revision, original], '2016-06-01T00:00:00+08:00') == [revision]


def dated_fact(**changes):
    return fact(timestamp_precision='date', published_date='2015-03-21',
                publication_date_verified=True, availability_bound_verified=True,
                availability_method='china_publication_date_upper_bound',
                available_at='2015-03-22T00:00:00+08:00', **changes)


def test_date_only_never_enters_during_publication_day():
    point = dated_fact()
    assert choose([point], '2015-03-21T23:59:59+08:00') == []
    assert choose([point], '2015-03-22T00:00:00+08:00') == [point]
    assert publication_date_upper_bound('2024-02-29').isoformat() == '2024-03-01T00:00:00+08:00'


def test_date_upper_bound_cannot_be_claimed_as_same_day_visibility():
    point = dated_fact()
    point['available_at'] = '2015-03-21T15:00:00+08:00'
    with pytest.raises(ValueError, match='precedes'):
        choose([point])


@pytest.mark.parametrize('field', ['publication_date_verified', 'availability_bound_verified', 'availability_method'])
def test_unverified_date_bound_stays_blocked(field):
    point = dated_fact()
    point.pop(field)
    assert choose([point]) == []


@pytest.mark.parametrize('reverse', [False, True])
def test_exact_and_date_only_same_day_conflict_cannot_guess_revision_order(reverse):
    points = [dated_fact(), fact(value='15', published_at='2015-03-21T18:00:00+08:00',
                                available_at='2015-03-21T18:00:00+08:00')]
    with pytest.raises(ValueError, match='Conflicting'):
        choose(points[::-1] if reverse else points)


def test_exact_next_midnight_is_certainly_later_than_previous_day():
    newer = fact(value='15', published_at='2015-03-22T00:00:00+08:00',
                 available_at='2015-03-22T00:00:00+08:00')
    assert choose([dated_fact(), newer]) == [newer]
