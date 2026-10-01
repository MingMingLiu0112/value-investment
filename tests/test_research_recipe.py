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
