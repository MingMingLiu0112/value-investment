import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import runpy
import sys

import pytest

from test_workbook_publication import registration, write_bound
from test_product_workbench_read_model import _payload
from test_pending_review_response import signed
from value_investment_agent.application.product.user_research_workflow import read_published_research, selected_review_candidate, verify_user_update_registry
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.presentation.user_research_workflow import render_published_research
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


@pytest.mark.parametrize('option', [
    '--candidate', '--candidate-sha256', '--pending-review-candidate',
    '--pending-review-candidate-sha256', '--case-registry', '--symbol',
])
def test_unified_entry_rejects_candidate_override_before_reading_assets(monkeypatch, option):
    script = Path(__file__).resolve().parents[1]/'scripts/current/use_trade_assistant.py'
    entry = runpy.run_path(str(script))['main']
    monkeypatch.setattr(sys, 'argv', [str(script), '--mode', 'review', '--symbol',
                                    '600519', '--', option + '=replacement'])
    with pytest.raises(SystemExit) as failure:
        entry()
    assert failure.value.code == 2


def published_fixture(root):
    pointer = registration(root)
    workbook = root/'canonical.xlsx'
    workbook.write_bytes(b'synthetic canonical workbook')
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    pub = pointer['current_publication']
    native_path = root/pub['wps_receipt']
    native = json.loads(native_path.read_text())
    native['workbook_sha256'] = digest
    pub['wps_receipt_sha256'] = write_bound(root, pub['wps_receipt'], native)['sha256']
    receipt = json.loads((root/pub['receipt']).read_text())
    sources = json.loads((root/receipt['source_bindings_path']).read_text())
    sources['workbook_sha256'] = digest
    receipt['source_bindings_sha256'] = write_bound(root, receipt['source_bindings_path'], sources)['sha256']
    receipt['after_sha256'] = receipt['candidate_sha256'] = digest
    pub['receipt_sha256'] = write_bound(root, pub['receipt'], receipt)['sha256']
    pointer.update(canonical_workbook_sha256=digest, workbook_source='WORKBOOK_PATH')
    write_bound(root, 'config/current-trial-workbook.json', pointer)
    return workbook


def test_view_reads_published_bytes_without_writing_or_private_input(tmp_path):
    workbook = published_fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = read_published_research(root=tmp_path, workbook=workbook)
    assert result['quote_observation_as_of'] == '2026-09-07'
    assert result['canonical_written'] is False and result['position_guidance'] is None
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize('fault', ['canonical', 'source', 'publication'])
def test_view_rejects_tampered_real_dependency_without_regeneration(tmp_path, fault):
    workbook = published_fixture(tmp_path)
    target = {'canonical':workbook, 'source':tmp_path/'runtime/quote.json',
              'publication':tmp_path/'runtime/publication-input.json'}[fault]
    target.write_bytes(b'changed')
    with pytest.raises(ValueError):
        read_published_research(root=tmp_path, workbook=workbook)
    assert target.read_bytes() == b'changed'


def test_review_selector_never_chooses_an_unpublished_candidate(tmp_path):
    write_bound(tmp_path, 'config/user-research-workflow-v1.json', {
        'schema_version':'user-research-workflow-v1', 'action':'no_order',
        'review_candidates':{'600519':{'path':'runtime/new-candidate.json','sha256':'a'*64}}})
    with pytest.raises(ValueError, match='not bound to current publication'):
        selected_review_candidate(root=tmp_path, published={'source_bindings':[]}, symbol='600519')


def test_compact_view_distinguishes_pending_candidate_from_baseline_without_prices():
    snapshot = json.loads(json.dumps(asdict(product_workbench_from_payload(_payload())),
                                    default=lambda value: value.isoformat()))
    candidate = dict(selected_choice='SYNTHETIC_PENDING', candidate_research_as_of='2026-09-26',
                     candidate_valuation={'bear_value':'8', 'base_value':'10','bull_value':'12'})
    symbol = snapshot['companies'][0]['symbol']
    result = dict(snapshot=snapshot, quote_observation_as_of='2026-09-25',
                  pending_candidates={symbol:candidate})
    before = copy.deepcopy(result)
    text = render_published_research(result, [symbol])
    assert '8.00 / 10.00 / 12.00' in text and '未批准' in text
    assert 'position_guidance=null' in text
    assert result == before
    with pytest.raises(ValueError, match='unknown or duplicate'):
        render_published_research(result, ['UNKNOWN'])


def test_update_uses_exact_selected_candidate_package_and_rejects_other_version(signed):
    root, candidate_path = signed['root'], signed['path']
    symbol = signed['candidate']['symbol']
    binding = dict(path=candidate_path.relative_to(root).as_posix(), sha256=sha256_file(candidate_path))
    write_bound(root, 'config/user-research-workflow-v1.json', {
        'schema_version':'user-research-workflow-v1', 'action':'no_order',
        'review_candidates':{symbol:binding}})
    package = candidate_path.parent/'package.json'
    registry = dict(schema_version='daily-trade-assistant-cases-v1', action='no_order',
                    cases={symbol:dict(package=package.relative_to(root).as_posix(), package_sha256=sha256_file(package))})
    path = write_bound(root, 'config/user-daily-trade-assistant-v1.json', registry)['path']
    published = {'source_bindings':[binding]}
    assert verify_user_update_registry(root=root, published=published, symbols=[symbol]) == root/path
    registry['cases'][symbol]['package_sha256'] = '0'*64
    write_bound(root, path, registry)
    with pytest.raises(ValueError, match='differs from selected candidate'):
        verify_user_update_registry(root=root, published=published, symbols=[symbol])
