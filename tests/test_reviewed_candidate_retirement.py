import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'retirement', Path(__file__).parents[1] / 'scripts/build_reviewed_candidate_retirement.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def setup_files(tmp_path):
    candidate = dict(candidate_id='c', disclosure_id='d', field_name='cash', page_number=1,
                     value='2026', status='candidate_pending_automated_verification')
    report = dict(disclosure_id='d', symbol='000001', report_period='2026-06-30',
                  sha256='pdf-hash', source_url='https://example.org/report')
    paths = [tmp_path / name for name in ('review.json', 'triage.csv', 'evidence.json', 'inventory.json')]
    review, triage, evidence, inventory = paths
    triage.write_text('symbol,field_name,page,reason\n000001,cash,1,year_parsed_as_amount\n', encoding='utf-8')
    write_json(evidence, dict(review_group='unpromoted_obsolete', reviews=[dict(
        original_candidate=candidate, symbol='000001', report_period='2026-06-30',
        sha256='pdf-hash', source_url=report['source_url'])]))
    write_json(review, dict(decision='reject_existing_field_mapping', expected_count=1,
                           triage_sha256=module.digest(triage), evidence_sha256=module.digest(evidence)))
    write_json(inventory, dict(candidates=[candidate], reports=[report], facts=[]))
    return paths


def test_valid_review_preserves_original_without_applying(tmp_path):
    paths = setup_files(tmp_path)
    result = module.build(*paths)
    assert result['records'][0]['candidate']['value'] == '2026'
    assert result['records'][0]['reason'] == 'year_parsed_as_amount'
    assert result['production_updated'] is False


@pytest.mark.parametrize('change', ['value', 'reference', 'disclosure', 'status'])
def test_changed_or_protected_production_record_rejected(tmp_path, change):
    paths = setup_files(tmp_path)
    inventory = json.loads(paths[3].read_text(encoding='utf-8'))
    if change == 'reference':
        inventory['facts'] = [{'metadata': {'candidate_id': 'c'}}]
    elif change == 'disclosure':
        inventory['reports'][0]['sha256'] = 'different'
    else:
        inventory['candidates'][0][change] = 'changed'
    write_json(paths[3], inventory)
    with pytest.raises(ValueError):
        module.build(*paths)


def test_changed_review_evidence_rejected(tmp_path):
    paths = setup_files(tmp_path)
    paths[2].write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        module.build(*paths)
