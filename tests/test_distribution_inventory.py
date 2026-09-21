from copy import deepcopy

import pytest

from scripts.audit_reviewed_distributions import reconcile_inventory


def fixture():
    event = {'symbol': '000333', 'superseded_document_id': 'old',
             'evidence': [{'url': 'https://example.test/new', 'sha256': 'newhash'}]}
    reports = [
        {'symbol': '000333', 'announcement_id': 'new', 'url': 'https://example.test/new',
         'sha256': 'newhash', 'title': 'updated'},
        {'symbol': '000333', 'announcement_id': 'old', 'url': 'https://example.test/old',
         'sha256': 'oldhash', 'title': 'cancelled'},
    ]
    return [event], reports


def test_revisions_are_not_additional_cash_events():
    events, reports = fixture()
    result = reconcile_inventory(events, reports + deepcopy(reports))
    assert result['documents'] == 2
    assert result['events'] == 1
    assert result['unreviewed_documents'] == 0
    assert not result['historical_coverage_certified']


def test_unknown_document_remains_unreviewed():
    events, reports = fixture()
    reports.append({**reports[0], 'announcement_id': 'extra',
                    'url': 'https://example.test/extra'})
    assert reconcile_inventory(events, reports)['unreviewed_documents'] == 1


@pytest.mark.parametrize('field', ['sha256', 'url', 'title'])
def test_conflicting_archive_versions_fail(field):
    events, reports = fixture()
    reports.append({**reports[0], field: 'different'})
    with pytest.raises(ValueError, match='Conflicting archive'):
        reconcile_inventory(events, reports)


def test_missing_replacement_or_original_evidence_fails():
    events, reports = fixture()
    for partial in (reports[:1], reports[1:]):
        with pytest.raises(ValueError):
            reconcile_inventory(events, partial)
