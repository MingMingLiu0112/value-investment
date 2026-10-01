import hashlib
import json
import pytest
from value_investment_agent.application.product.research_recipe import load_research_recipe


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
    with pytest.raises(FileExistsError): prepare_research_publication_input(**args)
