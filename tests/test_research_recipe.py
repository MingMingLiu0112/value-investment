import hashlib
import json
import pytest
from value_investment_agent.application.product.research_recipe import load_research_recipe


def test_excel_research_gap_explanations_preserve_unverified_outcome():
    from value_investment_agent.presentation.excel.product_workbench import _user_text
    question = 'yili_scp010_011_maturity_outcome'
    condition = 'A later eligible official settlement/refinancing or cash/debt disclosure establishes the CNY 20bn maturity outcome and liquidity bridge.'
    displayed = _user_text(question + ': ' + condition)
    assert question not in displayed
    assert '200 亿元' in displayed and '尚未核实' in displayed
    assert '后续合格' in displayed
    assert condition.startswith('A later eligible')


def recipe(tmp_path):
    base = tmp_path / 'base.json'
    workbench = tmp_path / 'workbench.json'
    base.write_text('{}', encoding='utf-8')
    workbench.write_text('{"symbol":"600887"}', encoding='utf-8')
    payload = dict(schema_version='shared-research-recipe-v1', action='no_order',
        scope='READ_ONLY_RESEARCH_EXPLANATION', symbol='600887', presentation_as_of='2026-10-01',
        base=dict(path=base.name, sha256=hashlib.sha256(base.read_bytes()).hexdigest()),
        workbench=dict(path=workbench.name, sha256=hashlib.sha256(workbench.read_bytes()).hexdigest()))
    return payload


def load(tmp_path, value):
    path = tmp_path / 'recipe.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return load_research_recipe(root=tmp_path, path=path,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_recipe_is_pinned_and_does_not_grant_publication(tmp_path):
    value = recipe(tmp_path)
    assert load(tmp_path, value) == value
    (tmp_path / 'base.json').write_text('{"changed":true}', encoding='utf-8')
    with pytest.raises(ValueError, match='source hash'): load(tmp_path, value)


def test_recipe_pins_historical_closure_and_rejects_wrong_company(tmp_path):
    value = recipe(tmp_path)
    closure = tmp_path / 'closure.json'
    closure.write_text('{"symbol":"600887"}', encoding='utf-8')
    value['historical_closure'] = {
        'path': closure.name,
        'sha256': hashlib.sha256(closure.read_bytes()).hexdigest(),
    }
    assert load(tmp_path, value) == value

    closure.write_text('{"symbol":"600519"}', encoding='utf-8')
    value['historical_closure']['sha256'] = hashlib.sha256(closure.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='historical closure symbol mismatch'):
        load(tmp_path, value)


def test_recipe_includes_current_stops_without_research_or_publication(tmp_path):
    from pathlib import Path
    from value_investment_agent.application.product.workbench import build_current_workbench_for_symbol
    value = recipe(tmp_path)
    config = tmp_path / 'config'
    config.mkdir()
    ledger = Path(__file__).resolve().parents[1] / 'config/research-evidence-stop-ledger-v1.json'
    (config / ledger.name).write_bytes(ledger.read_bytes())
    target = tmp_path / 'runtime/readiness.json'
    build_current_workbench_for_symbol(root=tmp_path, symbol=value['symbol'], output_path=target)
    value['research_readiness'] = dict(path='runtime/readiness.json', sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    assert load(tmp_path, value) == value
    other = tmp_path / 'runtime/other-readiness.json'
    build_current_workbench_for_symbol(root=tmp_path, symbol='000333', output_path=other)
    other_value = dict(value, research_readiness=dict(path='runtime/other-readiness.json',
                       sha256=hashlib.sha256(other.read_bytes()).hexdigest()))
    with pytest.raises(ValueError, match='readiness symbol mismatch'):
        load(tmp_path, other_value)
    (config / ledger.name).write_bytes(ledger.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='ledger hash mismatch'):
        load(tmp_path, value)


def test_recipe_pins_historical_execution_replay_and_rejects_wrong_company(tmp_path):
    value = recipe(tmp_path)
    replay = tmp_path / 'execution-replay.json'
    replay.write_text('{"symbol":"600887"}', encoding='utf-8')
    value['historical_execution_replay'] = {
        'path': replay.name,
        'sha256': hashlib.sha256(replay.read_bytes()).hexdigest(),
    }
    assert load(tmp_path, value) == value

    replay.write_text('{"symbol":"600519"}', encoding='utf-8')
    value['historical_execution_replay']['sha256'] = hashlib.sha256(replay.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='historical execution replay symbol mismatch'):
        load(tmp_path, value)


@pytest.mark.parametrize('case', ['publication', 'symbol', 'duplicate', 'recovery', 'cash'])
def test_recipe_rejects_scope_expansion_and_ambiguous_inputs(tmp_path, case):
    value = recipe(tmp_path)
    if case == 'publication': value['publish'] = True
    if case == 'symbol': value['symbol'] = '000333'
    if case == 'duplicate': value['metrics'] = [value['base'], value['base']]
    if case == 'recovery': value['recovered_event_originals'] = [dict(id='x', path='base.json')]
    if case == 'cash': value['cash_change_periods'] = ['2025', '2025']
    with pytest.raises(ValueError): load(tmp_path, value)


@pytest.mark.parametrize('case', ['pass', 'drift', 'conflict', 'scope', 'escape'])
def test_research_publication_handoff_checks_transitive_originals(tmp_path, case):
    from value_investment_agent.application.product.research_publication_input import prepare_research_publication_input
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    original = tmp_path / 'original.txt'
    original.write_text('sealed source', encoding='utf-8')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    inner = tmp_path / 'inner.json'
    inner.write_text(json.dumps({'source_bindings': [dict(path=original.name, sha256=digest)]}), encoding='utf-8')
    envelope = dict(schema_version='historical-company-read-model-preview-v1', action='no_order',
                    canonical_written=False, historical_preview=True,
                    snapshot=dict(action='no_order', companies=[], audit_evidence=[
                        dict(path=inner.name, sha256=hashlib.sha256(inner.read_bytes()).hexdigest())]))
    if case == 'scope': envelope['canonical_written'] = True
    if case == 'conflict': envelope['snapshot']['audit_evidence'].append(dict(path=original.name, sha256='a'*64))
    if case == 'escape': envelope['snapshot']['audit_evidence'].append(dict(path='../outside.txt', sha256='a'*64))
    source = runtime / 'read-model.json'
    source.write_text(json.dumps(envelope), encoding='utf-8')
    if case == 'drift': original.write_text('changed source', encoding='utf-8')
    output = runtime / 'handoff.json'
    args = dict(root=tmp_path, read_model_path=source,
                expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), output_path=output)
    if case != 'pass':
        with pytest.raises(ValueError): prepare_research_publication_input(**args)
        assert not output.exists()
        return
    result = prepare_research_publication_input(**args)
    assert result['snapshot'] == envelope['snapshot']
    assert len(result['source_bindings']) == 3
    assert result['action'] == 'no_order'
    assert not result['canonical_written'] and not result['publication_approved']
    assert not result['strict_pit_admitted'] and not result['current_price_admitted']
    if case == 'pass':
        from scripts.current.publish_product_workbench_to_canonical import _verify_reviewed_research_source_bindings
        candidate = runtime / 'preview.xlsx'
        candidate.write_bytes(b'contract fixture, not a real workbook')
        proof = runtime / 'proof.json'
        proof.write_text('{}', encoding='utf-8')
        sidecar = runtime / 'bindings.json'
        receipt = dict(schema_version='existing-workbench-preview-bindings-v1',
                       integrated_canonical=True, historical_preview=True, canonical_written=False,
                       action='no_order', workbook_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                       output_manifest_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),
                       publication_input_binding=dict(path=output.relative_to(tmp_path).as_posix(),
                           sha256=hashlib.sha256(output.read_bytes()).hexdigest()),
                       source_bindings=result['source_bindings'])
        sidecar.write_text(json.dumps(receipt), encoding='utf-8')
        assert _verify_reviewed_research_source_bindings(tmp_path, candidate, proof, sidecar)['verified_source_count'] == 4
        receipt['source_bindings'] = receipt['source_bindings'][:-1]
        sidecar.write_text(json.dumps(receipt), encoding='utf-8')
        with pytest.raises(ValueError, match='source bindings differ'):
            _verify_reviewed_research_source_bindings(tmp_path, candidate, proof, sidecar)
    from value_investment_agent.application.product.research_publication_input import load_research_publication_input
    handoff_digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert load_research_publication_input(root=tmp_path, path=output, expected_sha256=handoff_digest) == result
    with pytest.raises(FileExistsError): prepare_research_publication_input(**args)
    original.write_text('later drift', encoding='utf-8')
    with pytest.raises(ValueError, match='original hash mismatch'):
        load_research_publication_input(root=tmp_path, path=output, expected_sha256=handoff_digest)


@pytest.mark.parametrize('case', ['snapshot', 'sources', 'approval'])
def test_publication_handoff_cannot_replace_original_research(tmp_path, case):
    from value_investment_agent.application.product.research_publication_input import prepare_research_publication_input, load_research_publication_input
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    original = tmp_path / 'source.txt'
    original.write_text('sealed', encoding='utf-8')
    envelope = dict(schema_version='historical-company-read-model-preview-v1', action='no_order',
                    canonical_written=False, historical_preview=True, snapshot=dict(action='no_order',
                        audit_evidence=[dict(path=original.name, sha256=hashlib.sha256(original.read_bytes()).hexdigest())]))
    source = runtime / 'research.json'
    source.write_text(json.dumps(envelope), encoding='utf-8')
    output = runtime / 'handoff.json'
    result = prepare_research_publication_input(root=tmp_path, read_model_path=source,
        expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), output_path=output)
    if case == 'snapshot': result['snapshot']['invented_valuation'] = '999'
    if case == 'sources': result['source_bindings'] = []
    if case == 'approval': result['publication_approved'] = True
    output.write_text(json.dumps(result), encoding='utf-8')
    with pytest.raises(ValueError, match='differs from reverified'):
        load_research_publication_input(root=tmp_path, path=output,
            expected_sha256=hashlib.sha256(output.read_bytes()).hexdigest())


def test_pending_quote_and_margin_survive_public_snapshot_roundtrip():
    from dataclasses import asdict
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
    from value_investment_agent.presentation.read_models.existing_research_report import public_workbench_payload_from_snapshot
    from test_product_workbench_read_model import _payload
    value = _payload()
    for key in ('price', 'margin_of_safety'):
        assessment = value['companies'][0][key]
        assessment.update(status='PENDING_EXTERNAL_DATA', available=False, value_text=None,
                          unavailable_reason='No verified quote', needed_evidence='Verified PriceBridge')
    model = product_workbench_from_payload(value)
    snapshot = json.loads(json.dumps(asdict(model), default=lambda item: item.isoformat()))
    restored = product_workbench_from_payload(public_workbench_payload_from_snapshot(snapshot))
    assert restored.companies == model.companies
    value['companies'][0]['price'].update(available=True, value_text='99', unavailable_reason=None, needed_evidence=None)
    with pytest.raises(ValueError, match='pending external data'):
        product_workbench_from_payload(value)
