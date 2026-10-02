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
    sensitivity = '来源docs/current/review.json；SHA-256 ' + 'a' * 64
    display = _user_text(sensitivity)
    assert 'SHA-256' not in display and 'docs/' not in display
    assert 'a' * 64 not in display


def test_composed_handoff_reverifies_parent_and_array_originals(tmp_path):
    from value_investment_agent.application.product.research_publication_input import prepare_research_publication_input, load_research_publication_input
    from value_investment_agent.application.product.common import sha256_file
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    original = runtime / 'original.txt'
    original.write_text('sealed evidence', encoding='utf-8')
    array = runtime / 'quotes.json'
    array.write_text(json.dumps([dict(path='runtime/original.txt', sha256=sha256_file(original))]), encoding='utf-8')
    envelope = dict(schema_version='historical-company-read-model-preview-v1',
                    action='no_order', canonical_written=False, historical_preview=True,
                    snapshot=dict(action='no_order', audit_evidence=[dict(path='runtime/quotes.json', sha256=sha256_file(array))]))
    source = runtime / 'parent-model.json'
    source.write_text(json.dumps(envelope), encoding='utf-8')
    parent = runtime / 'parent.json'
    prepare_research_publication_input(root=tmp_path, read_model_path=source,
                                      expected_sha256=sha256_file(source), output_path=parent)
    envelope['publication_input_binding'] = dict(path='runtime/parent.json', sha256=sha256_file(parent))
    child_source = runtime / 'child-model.json'
    child_source.write_text(json.dumps(envelope), encoding='utf-8')
    child = runtime / 'child.json'
    result = prepare_research_publication_input(root=tmp_path, read_model_path=child_source,
                                               expected_sha256=sha256_file(child_source), output_path=child)
    assert result['strict_pit_admitted'] is False
    assert {entry['path'] for entry in result['source_bindings']} == {
        'runtime/original.txt', 'runtime/quotes.json', 'runtime/parent-model.json',
        'runtime/parent.json', 'runtime/child-model.json'}
    digest = sha256_file(child)
    assert load_research_publication_input(root=tmp_path, path=child, expected_sha256=digest) == result
    original.write_text('changed original', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_research_publication_input(root=tmp_path, path=child, expected_sha256=digest)


def _retained_fixture(tmp_path):
    from test_product_workbench_read_model import _payload
    from value_investment_agent.application.product.common import sha256_file
    payload = _payload()
    payload.update(as_of='2026-10-02', generated_at='2026-10-02T01:00:00+00:00')
    payload['companies'][0].update(symbol='600887', company_name='伊利股份')
    payload['opportunities'][0].update(symbol='600887', company_name='伊利股份')
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    original = runtime / 'fact.pdf'
    original.write_bytes(b'synthetic report for contract tests only')
    cards = []
    for symbol, name, profile in [('000333', '美的集团', 'mature_manufacturing'),
                                  ('600887', '伊利股份', 'quality_compounder'),
                                  ('601088', '中国神华', 'cyclical_cash_return')]:
        cards.append(dict(case_id=f'prospective-{symbol}-20260927-v2', symbol=symbol, company=name,
            profile=profile, action='no_order', valuation_status='VALUATION_NOT_READY',
            research_status='BASELINE_PARTIAL', unadmitted_fact_ids=[],
            business_quality='封存业务解释', financial_quality='封存财务解释', capital_allocation='尚待核验',
            dividend_sustainability='尚待核验', model_applicability='模型口径缺失', strongest_counterevidence='已登记反证',
            return_drivers='已登记回报驱动', unknowns=['口径缺项'],
            next_evidence_trigger='next official financial filing with cash-flow, capital-allocation and share disclosures',
            known_facts=[dict(fact_id=f'{symbol}-revenue', fact_type='revenue', value='10', unit='CNY',
                report_period='2025FY', source_path='runtime/fact.pdf', source_sha256=sha256_file(original),
                source_url='https://static.cninfo.com.cn/synthetic.pdf',
                available_at='2026-04-01T00:00:00+08:00')]))
    snapshot = dict(schema_version='prospective-baseline-snapshot-v2', action='no_order',
        built_at='2026-09-27T09:00:00+08:00', registration_time_assurance='PROCESS_CLOCK_ONLY_UNATTESTED',
        strict_pit_admissible=False, registration_receipt_sha256='a' * 64,
        baseline_input_sha256='b' * 64, cards=cards)
    source = runtime / 'retained.json'
    source.write_text(json.dumps(snapshot), encoding='utf-8')
    digest = sha256_file(source)
    pin = tmp_path / 'config/prospective-baseline-publication-v7.json'
    pin.parent.mkdir()
    pin.write_text(json.dumps(dict(schema_version='prospective-baseline-publication-v7', action='no_order',
        snapshot_path='runtime/retained.json', snapshot_sha256=digest,
        registration_receipt_sha256='a' * 64, baseline_input_sha256='b' * 64)), encoding='utf-8')
    return payload, source, digest, original


def test_retained_cases_append_without_overwriting_primary_research(tmp_path, monkeypatch):
    from copy import deepcopy
    from value_investment_agent.application.product import retained_research
    from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
    payload, source, digest, _ = _retained_fixture(tmp_path)
    frozen = deepcopy(payload)
    calls = []
    monkeypatch.setattr(retained_research, '_verify_fact_text', lambda raw, fact, binding: calls.append(fact['fact_id']))
    result = retained_research.extend_retained_research_payload(root=tmp_path, payload=payload,
        snapshot_path=source, snapshot_sha256=digest)
    model = product_workbench_from_payload(result)
    assert payload == frozen
    assert result['companies'][0] == frozen['companies'][0]
    assert result['opportunities'][0] == frozen['opportunities'][0]
    assert result['portfolio'] == frozen['portfolio']
    assert result['stages'] == frozen['stages']
    assert {card.symbol for card in model.companies} == {'600887', '000333', '601088'}
    assert set(calls) == {'000333-revenue', '601088-revenue'}
    assert next(item for item in result['audit']['evidence'] if item['evidence_id'] == 'prospective-000333-fact-1')['source_url'] == 'https://static.cninfo.com.cn/synthetic.pdf'
    assert all(not card.valuation.available and not card.price.available for card in model.companies[1:])
    assert all(step.status == 'BLOCKED' for card in model.companies[1:] for step in card.decision_process)
    assert '不年化' in dict(model.companies[1].decision_review)['事实解释边界']


@pytest.mark.parametrize('case', ['drift', 'future', 'identity', 'pin', 'semantic'])
def test_retained_cases_fail_closed_on_unverified_sources(tmp_path, monkeypatch, case):
    from value_investment_agent.application.product import retained_research
    payload, source, digest, original = _retained_fixture(tmp_path)
    monkeypatch.setattr(retained_research, '_verify_fact_text', lambda *args: None)
    if case == 'drift': original.write_bytes(b'changed')
    elif case == 'future': payload['as_of'] = '2026-09-25'
    elif case == 'identity': payload['companies'][0]['company_name'] = 'wrong issuer'
    elif case == 'pin': (tmp_path / 'config/prospective-baseline-publication-v7.json').unlink()
    elif case == 'semantic':
        def reject(*args): raise ValueError('wrong report column')
        monkeypatch.setattr(retained_research, '_verify_fact_text', reject)
    with pytest.raises(ValueError):
        retained_research.extend_retained_research_payload(root=tmp_path, payload=payload,
            snapshot_path=source, snapshot_sha256=digest)


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
