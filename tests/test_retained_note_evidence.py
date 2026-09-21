import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'retained_note_evidence', Path(__file__).parents[1] / 'scripts/build_retained_note_evidence.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_files(tmp_path):
    pdf = tmp_path / '000001.pdf'
    pdf.write_bytes(b'original')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    old = dict(candidate_id='c', disclosure_id='d', field_name='cash', value='10.00',
               unit='CNY', page_number=3)
    report = dict(disclosure_id='d', symbol='000001', report_period='2026-06-30',
                  sha256=digest, source_url='https://example.org/report.pdf')
    inventory = tmp_path / 'inventory.json'
    inventory.write_text(json.dumps(dict(candidates=[old], reports=[report])), encoding='utf-8')
    revised = dict(field_name='cash', value='10', unit='CNY', page=2, unit_evidence_page=1)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(dict(
        inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
        results=[dict(disclosure_id='d', plan=dict(fact_backed_requires_audit=['c']),
                      revised_candidates=[revised])])), encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(results=[dict(
        symbol='000001', period='2026-06-30', official_sha256=digest)])), encoding='utf-8')
    return inventory, plan, manifest, pdf


def test_matches_remain_unapproved_and_preserve_context(tmp_path, monkeypatch):
    inventory, plan, manifest, _ = fixture_files(tmp_path)
    monkeypatch.setattr(module, 'extract_pages', lambda _: ['unit', 'statement', 'note'])
    packet = module.build_packet(inventory, plan, [manifest])
    review = packet['reviews'][0]
    assert len(review['same_value_candidates']) == 1
    assert review['pages'] == {'1': 'unit', '2': 'statement', '3': 'note'}
    assert review['decision'] == 'scope_review_required'
    assert review['independent_source_verification'] is False
    assert packet['production_updated'] is False


def test_changed_inventory_rejected(tmp_path):
    inventory, plan, manifest, _ = fixture_files(tmp_path)
    inventory.write_text(inventory.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    with pytest.raises(ValueError, match='Inventory'):
        module.build_packet(inventory, plan, [manifest])


def test_changed_original_rejected_before_decode(tmp_path):
    inventory, plan, manifest, pdf = fixture_files(tmp_path)
    pdf.write_bytes(b'changed')
    with pytest.raises(ValueError, match='PDF hash'):
        module.build_packet(inventory, plan, [manifest])


def test_unpromoted_group_does_not_mix_protected_candidates(tmp_path, monkeypatch):
    inventory, plan, manifest, _ = fixture_files(tmp_path)
    data = json.loads(plan.read_text(encoding='utf-8'))
    data['results'][0]['plan']['unpromoted_obsolete'] = ['c']
    data['results'][0]['plan']['fact_backed_requires_audit'] = ['missing-protected']
    plan.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setattr(module, 'extract_pages', lambda _: ['unit', 'statement', 'note'])
    packet = module.build_packet(inventory, plan, [manifest], 'unpromoted_obsolete')
    assert packet['review_group'] == 'unpromoted_obsolete'
    assert [row['candidate_id'] for row in packet['reviews']] == ['c']
    assert packet['reviews'][0]['decision'] == 'scope_review_required'


def test_unknown_group_rejected(tmp_path):
    with pytest.raises(ValueError, match='Unsupported review group'):
        module.build_packet(tmp_path / 'missing', tmp_path / 'missing', [], 'reproduced')
