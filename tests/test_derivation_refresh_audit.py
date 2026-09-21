from types import SimpleNamespace

from scripts.audit_derivation_refresh import input_changes


def test_changed_input_retains_document_and_output_timeline():
    previous = {'source_id': 'doc', 'value': '10', 'data_point_id': 'old'}
    current = {'source_id': 'doc', 'value': '11', 'data_point_id': 'new'}
    old = {'created_at': '2026-09-08', 'metadata': {'input_facts': {'revenue': previous}}}
    record = SimpleNamespace(point_metadata={'input_facts': {'revenue': current}})
    points = {'revenue': {'created_at': '2026-09-07', 'source_url': 'https://example.org/report.pdf',
                          'sha256': 'abc', 'metadata': {'page_number': 83}}}
    result = input_changes(old, record, points)
    assert len(result) == 1
    assert result[0]['previous_input'] == previous
    assert result[0]['current_input'] == current
    assert result[0]['same_document'] is True
    assert result[0]['current_created_at'] < result[0]['old_output_created_at']
    assert result[0]['page_number'] == 83


def test_unchanged_inputs_are_not_reported():
    fact = {'source_id': 'doc', 'value': '10'}
    old = {'metadata': {'input_facts': {'revenue': fact}}}
    record = SimpleNamespace(point_metadata={'input_facts': {'revenue': fact}})
    assert input_changes(old, record, {}) == []


def test_missing_previous_provenance_is_not_same_document():
    record = SimpleNamespace(point_metadata={'input_facts': {'revenue': {'value': '10'}}})
    result = input_changes(None, record, {'revenue': {}})
    assert result[0]['previous_input'] is None
    assert result[0]['same_document'] is False
