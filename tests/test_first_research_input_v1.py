"""TEST_ONLY first compilation: no old package/candidate and no real acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.research import first_research_input_v1 as mod
from value_investment_agent.domain.valuation.joint_capital_cash_path_v4 import SCOPE

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
STAMP = NOW.isoformat()


def test_real_source_environment_acceptance(monkeypatch):
    """Opt in with E2_REAL_SOURCE_ROOT; missing/corrupt opted-in data must fail."""
    import os
    from pathlib import Path
    from value_investment_agent.infrastructure.filings.first_research_fact_replay_v1 import replay_first_research_facts
    from value_investment_agent.application.product.first_research_input_view_v1 import read_first_research_input
    from value_investment_agent.valuation_models.residual_income_path_v4 import ResidualIncomePathValuationModel

    configured = os.environ.get('E2_REAL_SOURCE_ROOT')
    if configured is None:
        pytest.skip('Real-source acceptance NOT RUN; set E2_REAL_SOURCE_ROOT explicitly')
    assert configured.strip(), 'Opted-in source root must not be empty'
    root = Path(configured).resolve(strict=True)
    now = datetime.now(timezone.utc)
    registry = json.loads((root / 'config/current-first-research-inputs-v1.json').read_bytes())
    ref = registry['cases']['000568']['receipt']
    receipt_bytes = (root / ref['path']).read_bytes()
    assert hashlib.sha256(receipt_bytes).hexdigest() == ref['sha256']
    receipt = json.loads(receipt_bytes)
    spec_bytes = (root / receipt['spec_binding']['path']).read_bytes()
    assert hashlib.sha256(spec_bytes).hexdigest() == receipt['spec_binding']['sha256']
    spec = json.loads(spec_bytes)
    native = replay_first_research_facts(root=root, binding=spec['native_facts_binding'], now=now)
    assert native['symbol'] == '000568' and len(native['facts']) == 84
    assert all(row['source_id'] and row['physical_page'] >= 1 for row in native['facts'])
    executions = []
    original = ResidualIncomePathValuationModel.value

    def consumed(self, *args, **kwargs):
        executions.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ResidualIncomePathValuationModel, 'value', consumed)
    cold = mod.replay_first_research_input(root=root, receipt_binding=ref, now=now)
    assert executions and cold['issuer_identity_status'] == 'VERIFIED'
    assert cold['valuation_status'] == 'conditional_research_only'
    assert all(cold['valuation'][key] is not None for key in ('bear_value', 'base_value', 'bull_value'))
    assert cold['main_range_adopted'] is False and cold['main_valuation_range'] is None
    assert cold['approval_changed'] is False and cold['formal_eligibility'] is False
    public = read_first_research_input(root=root, symbol='000568', now=now)
    assert public['status'] == 'SOURCE_BOUND_FIRST_INPUT_COMPILED'
    assert public['native_fact_count'] == 84
    assert public['main_range_adopted'] is False and public['main_valuation_range'] is None
    assert public['current_price'] is None and public['condition_price'] is None


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mod.encode_json_bytes(value))
    return dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def first(tmp_path):
    root = tmp_path
    # Existing identity only; every financial/forecast value below is invented
    # TEST_ONLY data, not this issuer's research or a transplanted research package.
    symbol = '600887'
    raw = root / 'runtime/TEST_ONLY-original.json'
    raw.parent.mkdir(parents=True)
    values = dict(start_book_equity='100', ordinary_shares='10', revenue='100', cost='80',
        surcharges='0', selling='0', admin='0', research='0', pre_tax_profit='20', tax='0',
        parent_profit='20', ex_parent_profit='20', depreciation='0', amortization='0', parent_cash='20')
    raw.write_text(json.dumps(values), encoding='utf-8')
    raw_binding = dict(path=raw.relative_to(root).as_posix(), sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    source = dict(id='TEST_ONLY-official', kind='official_issuer_filing',
        location='https://static.cninfo.com.cn/TEST_ONLY.pdf', local_path=raw_binding['path'],
        sha256=raw_binding['sha256'], source_available_at=STAMP, retrieved_at=STAMP,
        published_at='2026-08-01T00:00:00+00:00', parser_version='TEST_ONLY',
        availability_basis='TEST_ONLY_CURRENT_RECONSTRUCTION_NOT_HISTORICAL_PIT',
        issuer_identity=dict(venue='CNINFO', security_code=symbol,
            issuer_name='伊利股份', organization_id='gssh0600887'))
    records = []
    for field, value in values.items():
        scope = ('consolidated_parent_equity' if field == 'start_book_equity' else
                 'issued_ordinary_shares' if field == 'ordinary_shares' else
                 'consolidated_parent' if field in {'parent_profit', 'ex_parent_profit'} else
                 'parent' if field == 'parent_cash' else 'consolidated')
        records.append(dict(id=field, field=field, period_end='2026-06-30', value=value,
            unit='shares' if field == 'ordinary_shares' else 'CNY', scope=scope,
            source_id=source['id'], physical_page=1, label=field,
            excerpt='TEST_ONLY explicit row ' + field + '=' + value, column='TEST_ONLY closing'))
    manifest = dict(schema_version='TEST_ONLY-native-facts-v1', symbol=symbol, generated_at=STAMP,
        financial_basis='2026-06-30', sources=[source], facts=records)
    manifest_binding = put(root, 'runtime/TEST_ONLY-facts.json', manifest)
    rationale_binding = put(root, 'runtime/TEST_ONLY-D2-rationale.json',
        dict(statement='TEST_ONLY explicitly unsupported as real economics'))
    historical = {k: dict(operation='DIRECT', fact_ids=[k]) for k in values
        if k not in {'start_book_equity', 'ordinary_shares', 'ex_parent_profit', 'depreciation', 'amortization', 'parent_cash'}}
    historical['nonrecurring'] = dict(operation='DIFFERENCE', fact_ids=['parent_profit', 'ex_parent_profit'])
    historical['da'] = dict(operation='SUM', fact_ids=['depreciation', 'amortization'])
    for field, value in [('cash_floor', '10'), ('opening_distribution_capacity', '100'), ('opening_cash', '20')]:
        historical[field] = dict(assumption=dict(value=value, unit='CNY', scope=SCOPE,
            rationale='TEST_ONLY owner-equivalent cash hypothesis; not an official fact',
            source_bindings=[rationale_binding]))
    drivers = dict(operating_allocation='0', new_operating_return='0', new_liquidity_return='0',
        years=[dict(year=i, revenue_growth='0', cost_ratio='0.8', target_payout_ratio='0.85',
            accessible_profit_ratio='0.95', net_maintenance_cash_cny='2', operating_wc_cash_cny='1',
            commitment_cash_cny='0', reserve_ratio='0.1') for i in range(1, 11)])
    terminal = dict(net_maintenance_cash_cny='2', operating_wc_cash_cny='1', commitment_cash_cny='0',
        accessible_profit_ratio='0.95', target_payout_ratio='0.85', reserve_ratio='0.1',
        profit_scale='1', rationale='TEST_ONLY supported steady-state terminal mechanism',
        terminal_mechanism='recursive_capital_use_and_owner_distribution_v2', terminal_start_year=11,
        first_distribution_timing='end_of_terminal_year_1', legacy_profit_dynamics='constant_after_profit_scale_transition',
        commitment_occurrences=0, restricted_cash_release_cny='0', restricted_cash_release_year=None,
        convergence_tolerance_cny='0.01', max_tail_years=2000)
    assumptions = dict(schema_version=mod.ASSUMPTIONS_SCHEMA, action='no_order', symbol=symbol,
        financial_basis='2026-06-30', generated_at=STAMP,
        assumption_scope='RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST', source_bindings=[rationale_binding],
        choice=dict(id='TEST_ONLY-first', rationale='TEST_ONLY finite input hypothesis',
                    countercase='TEST_ONLY owner cash may be inaccessible'),
        historical_bindings=historical, scenarios={name: dict(drivers=deepcopy(drivers),
            terminal_policy=deepcopy(terminal), cost_of_equity=cost)
            for name, cost in [('bear', '0.10'), ('base', '0.09'), ('bull', '0.08')]})
    ab = put(root, 'runtime/TEST_ONLY-assumptions.json', assumptions)
    spec = dict(schema_version=mod.SCHEMA, action='no_order', symbol=symbol, name='TEST_ONLY first issuer',
        profile_id='quality_compounder', run_id='TEST_ONLY-first-without-predecessor',
        point_in_time=dict(report_period='2026-06-30', research_as_of='2026-10-31',
            valuation_date='2026-06-30', available_at=STAMP, computed_at=STAMP),
        native_facts_binding=manifest_binding, assumption_binding=ab,
        capital_bindings=dict(start_book_equity='start_book_equity', ordinary_shares='ordinary_shares'),
        share_basis='issued_ordinary_shares', research_case=dict(industry='TEST_ONLY',
            investment_path='TEST_ONLY research only', thesis='TEST_ONLY operating hypothesis',
            return_driver='TEST_ONLY own cash', mispricing_hypothesis='TEST_ONLY unassessed', positives=[],
            counter_evidence=[dict(kind='hypothesis', text='TEST_ONLY cash may not reach owners', evidence_refs=[])],
            thesis_breakers=[], next_events=[]))
    calls = []

    def cold(*, root, binding, now):
        calls.append(binding)
        data = json.loads(mod._read(root, binding, []))
        official = data['sources'][0]
        actual = json.loads(mod._read(root, dict(path=official['local_path'], sha256=official['sha256']), []))
        # Independent TEST_ONLY transport decoder verifies values against raw
        # rows, not `verified=True` or saved manifest PASS.
        for row in data['facts']:
            if row['value'] != actual[row['field']]:
                raise ValueError('TEST_ONLY original row differs from claimed fact')
        return dict(data, action='no_order', issuer_name='TEST_ONLY',
            input_fingerprint=hashlib.sha256(mod.encode_json_bytes(data)).hexdigest(), strict_historical_pit=False)

    def save():
        spec['native_facts_binding'] = put(root, 'runtime/TEST_ONLY-facts.json', manifest)
        spec['assumption_binding'] = put(root, 'runtime/TEST_ONLY-assumptions.json', assumptions)
        return put(root, 'runtime/TEST_ONLY-spec.json', spec)

    return root, spec, manifest, assumptions, cold, calls, save


def run(first):
    root, _, _, _, cold, _, save = first
    return mod.build_first_research_input(root=root, spec_binding=save(),
        output_dir=root / 'runtime/compiled', now=NOW, fact_replay=cold)


@pytest.mark.parametrize('key', [
    'value_investment_agent.infrastructure.filings.first_research_fact_replay_v1',
    'value_investment_agent.domain.research.issuer_identity_registry.json',
])
def test_native_helper_and_identity_registry_fingerprints_invalidate_receipt(first, monkeypatch, key):
    from importlib.resources import files
    from pathlib import Path
    from value_investment_agent.infrastructure.filings import first_research_fact_replay_v1

    root, _, _, _, cold, calls, _ = first
    result = run(first)
    fingerprints = mod._implementations()
    expected = (files('value_investment_agent.domain.research')
                .joinpath('issuer_identity_registry.json').read_bytes()
                if key.endswith('.json') else Path(first_research_fact_replay_v1.__file__).read_bytes())
    assert fingerprints[key] == hashlib.sha256(expected).hexdigest()
    fingerprints[key] = '0' * 64
    monkeypatch.setattr(mod, '_implementations', lambda: fingerprints)
    before = len(calls)
    with pytest.raises(ValueError, match='implementation changed'):
        mod.replay_first_research_input(root=root, receipt_binding=result['receipt_binding'],
                                       now=NOW, fact_replay=cold)
    assert len(calls) == before


def test_first_payload_compiles_and_cold_replays_without_predecessor(first, monkeypatch):
    from value_investment_agent.valuation_models.residual_income_path_v4 import ResidualIncomePathValuationModel
    executions = []
    original_value = ResidualIncomePathValuationModel.value

    def counted_value(self, *args, **kwargs):
        executions.append(True)
        return original_value(self, *args, **kwargs)

    monkeypatch.setattr(ResidualIncomePathValuationModel, 'value', counted_value)
    root, _, _, _, _, calls, _ = first
    assert not (root / 'config').exists()
    result = run(first)
    assert len(calls) == 2
    assert result['predecessor_package'] is None and result['approvals_created'] == 0
    cold = result['cold_recompile']
    assert cold['status'] == 'COLD_RECOMPILED' and cold['issuer_identity_status'] == 'VERIFIED'
    assert cold['valuation_status'] == 'conditional_research_only'
    assert executions, 'Cold replay must execute the existing v4 valuation model'
    assert all(cold['valuation'][key] is not None for key in ('bear_value', 'base_value', 'bull_value'))
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert result['external_acceptance_required'] is True
    assert result['compilation_scope'] == 'condition_scenarios_not_adopted_main_range'
    assert result['main_range_adopted'] is False and cold['main_valuation_range'] is None
    assert result['input_fingerprint'] and result['artifact_bundle']['artifacts']
    assert result['research_result']['human_research_approval'] is None
    package = json.loads((root / 'runtime/compiled/package.json').read_bytes())
    assert package['assumptions']['blockers'] == []
    assert package['research_case']['blockers'] == ['ECONOMIC_RESEARCH_NOT_APPROVED']
    assert cold['approval_changed'] is False and cold['formal_eligibility'] is False
    assert len(result['annual_ledgers']['base']['rows']) == 10
    assert not (root / 'config').exists()
    assert {p.name for p in (root / 'runtime/compiled').iterdir()} == {
        'proposal.json', 'package.json', 'receipt.json', 'cold-recompile.json'}


@pytest.mark.parametrize('damage', ['predecessor', 'profile', 'future', 'scope', 'period',
    'shares_fraction', 'false_original_value', 'unbound_history', 'missing_wc', 'issuer'])
def test_invalid_first_inputs_fail_before_valuation(first, damage):
    root, spec, manifest, assumptions, _, _, _ = first
    if damage == 'predecessor': spec['old_package'] = {'path': 'old.json', 'sha256': 'a'*64}
    elif damage == 'profile': spec['profile_id'] = 'mature_manufacturing'
    elif damage == 'future': manifest['sources'][0]['retrieved_at'] = '2099-01-01T00:00:00+00:00'
    elif damage == 'scope': manifest['facts'][0]['scope'] = 'consolidated'
    elif damage == 'period': manifest['facts'][0]['period_end'] = '2025-12-31'
    elif damage == 'shares_fraction':
        manifest['facts'][1]['value'] = '10.5'
    elif damage == 'false_original_value': manifest['facts'][0]['value'] = '999'
    elif damage == 'unbound_history': assumptions['historical_bindings']['revenue'] = '100'
    elif damage == 'missing_wc': del assumptions['scenarios']['base']['drivers']['years'][0]['operating_wc_cash_cny']
    elif damage == 'issuer': manifest['sources'][0]['issuer_identity']['security_code'] = '000568'
    with pytest.raises((ValueError, TypeError)):
        run(first)
    assert not (root / 'runtime/compiled/package.json').exists()


def test_missing_cold_capital_is_precise_without_fake_success(first):
    root, _, manifest, _, _, _, _ = first
    manifest['facts'] = [row for row in manifest['facts'] if row['field'] != 'ordinary_shares']
    result = run(first)
    assert result['status'] == 'MISSING_INPUTS' and result['missing_inputs'] == ['ordinary_shares']
    assert not (root / 'runtime/compiled').exists()


def test_raw_hash_change_and_cold_package_tamper_are_rejected(first):
    root, _, _, _, cold, _, _ = first
    result = run(first)
    package = root / result['package_binding']['path']
    data = json.loads(package.read_bytes())
    data['facts']['operating_inputs']['ordinary_shares'] = '999'
    changed = put(root, 'runtime/compiled/package.json', data)
    receipt = deepcopy(result)
    receipt['package_binding'] = changed
    rb = put(root, 'runtime/tampered-receipt.json', receipt)
    with pytest.raises(ValueError, match='Cold package differs'):
        mod.replay_first_research_input(root=root, receipt_binding=rb, now=NOW, fact_replay=cold)
    (root / 'runtime/TEST_ONLY-original.json').write_bytes(b'TEST_ONLY corrupted source')
    with pytest.raises(ValueError, match='hash mismatch'):
        mod.replay_first_research_input(root=root, receipt_binding=result['receipt_binding'], now=NOW, fact_replay=cold)


def test_existing_output_is_never_overwritten(first):
    root, _, _, _, _, _, _ = first
    run(first)
    before = {p.name: p.read_bytes() for p in (root / 'runtime/compiled').iterdir()}
    with pytest.raises(FileExistsError):
        run(first)
    assert before == {p.name: p.read_bytes() for p in (root / 'runtime/compiled').iterdir()}


def test_root_native_source_shape_and_ttm_are_supported(first):
    root, _, manifest, assumptions, _, _, _ = first
    source = manifest['sources'][0]
    manifest['sources'] = [dict(id=source['id'], path=source['local_path'], sha256=source['sha256'],
        symbol='600887', issuer_name='伊利股份', source_url=source['location'],
        available_at=STAMP, published_date='2026-08-01', report_period='2026-06-30',
        report_title='TEST_ONLY', organization_id='gssh0600887')]
    # Three raw revenue rows, with actual values decoded by the TEST_ONLY replay.
    original = root / source['local_path']
    values = json.loads(original.read_bytes())
    for ident, amount in [('prior_fy_revenue', '100'), ('current_h1_revenue', '50'), ('prior_h1_revenue', '50')]:
        values[ident] = amount
    original.write_text(json.dumps(values), encoding='utf-8')
    manifest['sources'][0]['sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
    template = next(row for row in manifest['facts'] if row['field'] == 'revenue')
    for ident, period in [('prior_fy_revenue', '2025-12-31'), ('current_h1_revenue', '2026-06-30'),
                          ('prior_h1_revenue', '2025-06-30')]:
        # TEST_ONLY decoder uses row.field as a native lookup; normalize the
        # semantic field after decoding, just as Root's locator parser does.
        manifest['facts'].append(dict(template, id=ident, field=ident, value=values[ident], period_end=period))
    # Root source shape differs from legacy package-source shape.
    # Adapt only this TEST_ONLY decoder's raw-transport access.
    def native_cold(*, root, binding, now):
        first[5].append(binding)
        data = json.loads(mod._read(root, binding, []))
        s = data['sources'][0]
        actual = json.loads(mod._read(root, {'path':s['path'], 'sha256':s['sha256']}, []))
        for row in data['facts']:
            if row['value'] != actual[row['field']]:
                raise ValueError('TEST_ONLY original differs')
            if row['id'].endswith('_revenue'):
                row['field'] = 'revenue'
        return dict(data, action='no_order', issuer_name='伊利股份', strict_historical_pit=False)
    assumptions['historical_bindings']['revenue'] = dict(operation='TTM',
        fact_ids=['prior_fy_revenue', 'current_h1_revenue', 'prior_h1_revenue'])
    result = mod.build_first_research_input(root=root, spec_binding=first[6](),
        output_dir=root/'runtime/native-shape', now=NOW, fact_replay=native_cold)
    assert result['cold_recompile']['valuation_status'] == 'conditional_research_only'
    proposal = json.loads((root/result['proposal_binding']['path']).read_bytes())
    assert proposal['historical_derivations']['revenue']['value'] == '100'


@pytest.mark.parametrize('damage', ['cash_as_fact', 'sum_double_count', 'nonrecurring_reversed',
                                  'manifest_future', 'source_rationale_future', 'unknown_operation',
                                  'financial_as_hypothesis', 'publication_after_availability'])
def test_only_explicit_bounded_source_derivations_are_allowed(first, damage):
    root, _, manifest, assumptions, _, _, _ = first
    if damage == 'cash_as_fact':
        assumptions['historical_bindings']['opening_cash'] = dict(operation='DIRECT', fact_ids=['parent_cash'])
    elif damage == 'sum_double_count':
        assumptions['historical_bindings']['da'] = dict(operation='SUM', fact_ids=['depreciation', 'depreciation'])
    elif damage == 'nonrecurring_reversed':
        assumptions['historical_bindings']['nonrecurring']['fact_ids'].reverse()
    elif damage == 'manifest_future':
        manifest['generated_at'] = '2099-01-01T00:00:00+00:00'
    elif damage == 'source_rationale_future':
        binding = put(root, 'runtime/future-rationale.json', dict(generated_at='2099-01-01T00:00:00+00:00'))
        assumptions['source_bindings'].append(binding)
    elif damage == 'financial_as_hypothesis':
        assumptions['historical_bindings']['revenue'] = deepcopy(assumptions['historical_bindings']['cash_floor'])
        assumptions['historical_bindings']['revenue']['assumption']['scope'] = 'consolidated'
    elif damage == 'publication_after_availability':
        manifest['sources'][0].pop('published_at')
        manifest['sources'][0]['published_date'] = '2099-01-01'
    else:
        assumptions['historical_bindings']['revenue'] = dict(operation='DEFAULT', fact_ids=['revenue'])
    with pytest.raises(ValueError):
        run(first)


def test_unregistered_real_identity_is_not_reported_as_verified_success(first):
    root, spec, manifest, assumptions, cold, _, save = first
    # Use an actually unregistered issuer; 000568 now has official identity data.
    spec['symbol'] = manifest['symbol'] = assumptions['symbol'] = '999999'
    manifest['sources'][0]['issuer_identity']['security_code'] = '999999'
    result = mod.build_first_research_input(root=root, spec_binding=save(),
        output_dir=root/'runtime/unregistered', now=NOW, fact_replay=cold)
    assert result['cold_recompile']['issuer_identity_status'] != 'VERIFIED'
    assert result['cold_recompile']['valuation_status'] != 'conditional_research_only'
    assert result['external_acceptance_required'] is True
    assert result['cold_recompile']['blockers']


def test_default_entry_calls_root_cold_helper_twice_and_never_e1(first, monkeypatch):
    from value_investment_agent.infrastructure.filings import first_research_fact_replay_v1 as native
    from value_investment_agent.application.product import neutral_valuation_proposal
    root, _, _, _, cold, calls, save = first
    monkeypatch.setattr(native, 'replay_first_research_facts', cold)
    def forbidden(**kwargs):
        raise AssertionError('A first compilation cannot call an old-package proposal builder')
    monkeypatch.setattr(neutral_valuation_proposal, 'build_neutral_valuation_proposal', forbidden)
    result = mod.build_first_research_input(root=root, spec_binding=save(),
        output_dir=root/'runtime/default-helper', now=NOW)
    assert len(calls) == 2 and result['cold_recompile']['valuation_status'] == 'conditional_research_only'


def test_cold_replay_is_read_only_and_preserves_input_identity(first):
    root, _, _, _, cold, _, _ = first
    result = run(first)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    replay = mod.replay_first_research_input(root=root, receipt_binding=result['receipt_binding'],
        now=NOW, fact_replay=cold)
    assert replay['input_fingerprint'] == result['input_fingerprint']
    assert replay['input_descriptor_sha256'] == result['input_descriptor_sha256']
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_missing_base_is_a_gap_not_an_invented_main_valuation(first):
    root, _, _, assumptions, _, _, _ = first
    del assumptions['scenarios']['base']
    result = run(first)
    assert result['status'] == 'MISSING_INPUTS'
    assert result['missing_inputs'] == ['scenarios.base']
    assert result['main_range_adopted'] is False
    assert not (root/'runtime/compiled').exists()
