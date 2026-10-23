"""Synthetic economic drivers; source hashes and arithmetic are not approvals."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import shutil
import os
import ast
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from test_neutral_valuation_proposal import proposal_inputs, run
from test_pending_research_candidate import candidate_inputs, run as run_pending
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.neutral_valuation_proposal import JOINT_SCHEMA
from value_investment_agent.application.product.pending_research_candidate import verify_pending_research_candidate
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.domain.valuation.joint_capital_path import compile_joint_capital_path
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.application.product.research_reviews import build_research_review_model_context
from value_investment_agent.application.product.workbench import build_current_workbench_for_symbol
from value_investment_agent.application.product.research_review_packet import project_research_review_packet


def policy_inputs(root, package_path, policy_path):
    package = json.loads(package_path.read_text(encoding='utf-8'))
    anchor = D(package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'])
    values = dict(revenue=anchor * 2, cost=anchor / 2, surcharges=anchor / 20,
        selling=anchor / 20, admin=anchor / 20, research=anchor / 20,
        pre_tax_profit=anchor * D('1.25'), tax=anchor / 4, parent_profit=anchor,
        nonrecurring=D(0), da=anchor / 50, cash=anchor / 2)
    declared = {key: dict(value=str(value), unit='CNY', scope=(
        'consolidated_parent' if key in ('parent_profit', 'nonrecurring') else
        'parent_cash_lookthrough_proxy' if key == 'cash' else 'consolidated')) for key, value in values.items()}
    evidence = root / 'runtime/TEST_ONLY-capital-observations.json'
    evidence.write_text(json.dumps(declared), encoding='utf-8')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy.update(schema_version=JOINT_SCHEMA, generated_at='2026-10-10T00:00:00+08:00',
        assumption_scope='RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST',
        joint_historical={key: dict(**item, source_id='TEST_ONLY-capital', field_path=[key],
            rationale='Synthetic aggregate bridge, not issuer research.') for key, item in declared.items()})
    policy.pop('income_growth')
    policy['rationale_bindings'].append(dict(id='TEST_ONLY-capital',
        path=evidence.relative_to(root).as_posix(), sha256=sha256_file(evidence)))
    drivers = {}
    for name, delta in [('bear', '-.01'), ('base', '0'), ('bull', '.01')]:
        drivers[name] = dict(years=[dict(year=i, revenue_growth=delta,
            cost_ratio=str(D('.25') - D(delta) * D(i) / 5)) for i in range(1, 6)],
            retention='.10', operating_allocation='.90', new_operating_return='.10',
            new_liquidity_return='.01', parent_cash_conversion='1', terminal_growth='.01',
            terminal_profit_scale='1')
    policy['choices'] = [dict(id='continuity', rationale='Explicit synthetic joint assumptions.',
        countercase='Capital efficiency and cash conversion can fail.', joint_drivers=drivers,
        cost_of_equity={name: '.08' for name in drivers})]
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    # Production candidate Hash checks remain real; synthetic roots get exact implementation bytes.
    repo = Path(__file__).resolve().parents[1]
    for relative in ('src/value_investment_agent/domain/valuation/joint_capital_path.py',
            'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
            'src/value_investment_agent/application/product/pending_research_candidate.py',
            'src/value_investment_agent/valuation_models/residual_income.py'):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / relative, destination)
    return values, drivers, policy


def test_joint_drivers_really_reach_same_model_without_quote(tmp_path):
    package, policy = proposal_inputs(tmp_path)
    values, drivers, _ = policy_inputs(tmp_path, package, policy)
    result = run(tmp_path, package, policy)
    row = result['choices'][0]
    assert result['input_mode'] == JOINT_SCHEMA
    assert result['normalized_profit'] is None
    assert result['g3_approved'] is result['price_admitted'] is False
    assert row['valuation']['status'] == 'conditional_research_only'
    assert row['valuation']['confidence'] == '低'
    assert len(row['actual_calculation_inputs']['scenarios']['base']['forecast_roe']) == 5
    for name, ledger in row['joint_capital_ledgers'].items():
        actual = row['actual_calculation_inputs']['scenarios'][name]
        assert actual['forecast_roe'] == ledger['forecast_roe']
        assert actual['terminal_roe'] == ledger['terminal_roe']
        arithmetic = row['annual_arithmetic'][name]
        assert abs(D(arithmetic['dividend_crosscheck_difference_cny'])) < D('.01')
        for year, consumed in zip(ledger['rows'], arithmetic['forecast_years']):
            assert abs(D(year['profit']) - D(consumed['net_income_assumption_cny'])) < D('.01')
            assert abs(D(year['closing_book']) - D(consumed['closing_book_equity_cny'])) < D('.01')
    text = (tmp_path / 'runtime/proposal.md').read_text(encoding='utf-8')
    assert '五年联结资本路径' in text
    assert '年全资本衰减' not in text


def test_ke_only_stress_cannot_change_business_profit_or_book(tmp_path):
    package, path = proposal_inputs(tmp_path)
    _, _, policy = policy_inputs(tmp_path, package, path)
    first = run(tmp_path, package, path)['choices'][0]
    policy['choices'][0]['cost_of_equity'] = dict(bear='.12', base='.12', bull='.12')
    path.write_text(json.dumps(policy), encoding='utf-8')
    from value_investment_agent.application.product.neutral_valuation_proposal import build_neutral_valuation_proposal
    second = build_neutral_valuation_proposal(root=tmp_path, package_path=package,
        package_sha256=sha256_file(package), policy_path=path, policy_sha256=sha256_file(path),
        output_path=tmp_path / 'runtime/ke-only.json')['choices'][0]
    assert first['joint_capital_ledgers'] == second['joint_capital_ledgers']
    assert D(first['valuation']['base_value']) > D(second['valuation']['base_value'])


def test_cash_stress_fail_is_retained_not_replaced_by_zero(tmp_path):
    package, path = proposal_inputs(tmp_path)
    _, _, policy = policy_inputs(tmp_path, package, path)
    for drivers in policy['choices'][0]['joint_drivers'].values():
        drivers['parent_cash_conversion'] = '0'
    path.write_text(json.dumps(policy), encoding='utf-8')
    result = run(tmp_path, package, path)
    assert all(row['cash_funding_status'] == 'FAIL'
               for row in result['choices'][0]['joint_capital_ledgers'].values())
    assert result['g3_approved'] is False
    assert result['cash_funding_status'] == 'FAIL'


@pytest.mark.parametrize('fault', ['nan', 'float', 'missing', 'year_order', 'year_count',
    'extra_roe', 'scope', 'unit', 'source', 'value', 'hash', 'future', 'assumption_scope'])
def test_joint_input_contract_rejects_invalid_or_unbound_values(tmp_path, fault):
    package, path = proposal_inputs(tmp_path)
    _, _, policy = policy_inputs(tmp_path, package, path)
    driver = policy['choices'][0]['joint_drivers']['base']
    if fault == 'nan':
        driver['new_operating_return'] = 'NaN'
    elif fault == 'float':
        driver['retention'] = 0.1
    elif fault == 'missing':
        driver.pop('new_liquidity_return')
    elif fault == 'year_order':
        driver['years'][0]['year'] = 2
    elif fault == 'year_count':
        driver['years'].pop()
    elif fault == 'extra_roe':
        driver['forecast_roe'] = ['.3'] * 5
    elif fault in ('scope', 'unit', 'source', 'value'):
        field, value = dict(scope=('scope', 'parent'), unit=('unit', 'USD'),
            source=('source_id', 'missing'), value=('value', '1'))[fault]
        policy['joint_historical']['revenue'][field] = value
    elif fault == 'hash':
        (tmp_path / 'runtime/TEST_ONLY-capital-observations.json').write_text('{}', encoding='utf-8')
    elif fault == 'future':
        policy['generated_at'] = '2099-01-01T00:00:00Z'
    else:
        policy['assumption_scope'] = 'OFFICIAL_FACTS'
    path.write_text(json.dumps(policy), encoding='utf-8')
    with pytest.raises((ValueError, KeyError)):
        run(tmp_path, package, path)
    assert not (tmp_path / 'runtime/proposal.json').exists()


def test_pending_consumes_joint_facts_assumptions_and_packet_same_version(tmp_path, synthetic_pending_candidate_clock):
    package, path, request = candidate_inputs(tmp_path)
    policy_inputs(tmp_path, package, path)
    result = run_pending(tmp_path, package, path, request)
    folder = tmp_path / 'runtime/pending'
    candidate = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
    work = json.loads((folder / 'workbench.json').read_text(encoding='utf-8'))
    dependency_objects = verify_current_decision_workbench(work).dependency_objects
    consumed = artifact_payload(dependency_objects['financial_facts'])[1]
    assert consumed['scenario_inputs'] == candidate['facts']['scenario_inputs']
    consumed_assumptions = artifact_payload(dependency_objects['valuation_assumptions'])[1]
    assert consumed_assumptions == artifact_payload(build_descriptor(candidate, root=tmp_path).assumptions)[1]
    assert len(candidate['assumption_bindings']) == 9 * 3
    assert candidate['quote'] is None
    assert candidate['research_case']['financial_summary']['normalized_parent_profit_cny'] is None
    assert candidate['research_case']['financial_summary']['pending_joint_capital_research']['scope'] == 'RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS'
    assert work['valuation']['status'] == 'conditional_research_only'
    assert work['suggested_state'] == 'NO_ACTION'
    assert (folder / 'consumed-review.json').is_file()
    verified = verify_pending_research_candidate(root=tmp_path, path=folder / 'candidate.json',
        expected_sha256=sha256_file(folder / 'candidate.json'))
    assert verified['model_context'] == result['model_context']
    assert verified['review_packet_binding']['sha256'] == sha256_file(folder / 'consumed-review.json')
    assert any('joint_capital_path.py' in row['path'] for row in verified['implementation_bindings'])
    assert result['approval_changed'] is result['price_admitted'] is False
    original_packet = (folder / 'consumed-review.json').read_bytes()
    packet = json.loads(original_packet)
    packet['symbol'] = '000333'
    (folder / 'consumed-review.json').write_text(json.dumps(packet), encoding='utf-8')
    resealed = deepcopy(verified)
    packet_binding = resealed['review_packet_binding']
    packet_binding['sha256'] = sha256_file(folder / 'consumed-review.json')
    for binding in resealed['source_bindings']:
        if binding['path'] == packet_binding['path']:
            binding['sha256'] = packet_binding['sha256']
    (folder / 'candidate.json').write_text(json.dumps(resealed), encoding='utf-8')
    with pytest.raises(ValueError, match='packet differs'):
        verify_pending_research_candidate(root=tmp_path, path=folder / 'candidate.json',
            expected_sha256=sha256_file(folder / 'candidate.json'))
    (folder / 'consumed-review.json').write_bytes(original_packet)
    (folder / 'candidate.json').write_text(json.dumps(verified), encoding='utf-8')
    domain_copy = tmp_path / 'src/value_investment_agent/domain/valuation/joint_capital_path.py'
    domain_copy.write_bytes(domain_copy.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='drift'):
        verify_pending_research_candidate(root=tmp_path, path=folder / 'candidate.json',
            expected_sha256=sha256_file(folder / 'candidate.json'))


def test_manual_mapping_cannot_silently_skip_value_verification(tmp_path):
    package, path = proposal_inputs(tmp_path)
    _, _, policy = policy_inputs(tmp_path, package, path)
    policy['joint_historical']['revenue'].pop('field_path')
    path.write_text(json.dumps(policy), encoding='utf-8')
    with pytest.raises(ValueError, match='explicit independent review'):
        run(tmp_path, package, path)


def test_joint_domain_requires_decimal_and_capital_scope_without_mutating_input(tmp_path):
    package, path = proposal_inputs(tmp_path)
    historical, scenarios, _ = policy_inputs(tmp_path, package, path)
    inputs = dict(start_book=str(historical['parent_profit'] * 5), profit_anchor=str(historical['parent_profit']),
                  historical=historical, drivers=scenarios['base'])
    original = deepcopy(inputs)
    ledger = compile_joint_capital_path(**inputs)
    assert inputs == original
    with localcontext() as ctx:
        ctx.prec = 48
        for row in ledger['rows']:
            assert row['closing_book'] == row['opening_book'] + row['retained']
            assert abs(row['profit'] - row['dividend'] - row['retained']) < D('.000001')
        assert abs(ledger['terminal_growth'] * ledger['terminal_book']
                   - ledger['terminal_retention'] * ledger['terminal_profit']) < D('.000001')


def test_joint_operative_narrative_does_not_inherit_predecessor_stress_label(
        tmp_path, synthetic_pending_candidate_clock):
    source, policy_path, request = candidate_inputs(tmp_path)
    package = json.loads(source.read_text(encoding='utf-8'))
    package['package_version'] = 'TEST_ONLY-stress-predecessor'
    old = package['research_case']
    old['thesis'] = 'LEGACY STRESS_ONLY: 后五年全资本机械衰减。'
    old['mispricing_hypothesis'] = '旧全资本强衰减可能高估侵蚀。'
    old['blockers'].append('本候选优势期和全资本衰减未获主模型批准')
    old['counter_evidence'].append(dict(kind='hypothesis', text='旧十年全资本衰减压力路径不能作为主估值。',
                                       evidence_refs=['facts']))
    old['financial_summary']['profit_adjustment_research'] = dict(open_questions=['capital-return fade assumptions'])
    package['assumptions'].setdefault('blockers', []).append('Selected finite model assumptions remain pending economic approval.')
    source.write_text(json.dumps(package), encoding='utf-8')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['source_package_sha256'] = sha256_file(source)
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    policy_inputs(tmp_path, source, policy_path)
    run_pending(tmp_path, source, policy_path, request)
    folder = tmp_path / 'runtime/pending'
    current = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
    case = current['research_case']
    assert 'STRESS_ONLY' not in case['thesis']
    assert '本候选以历史归母盈利与权益为锚点' in case['thesis']
    assert '全资本' not in case['mispricing_hypothesis']
    assert not any('全资本' in blocker for blocker in case['blockers'])
    historical = case['financial_summary']['predecessor_research_narrative']
    assert historical['statements']['thesis'] == old['thesis']
    assert historical['package_binding']['sha256'] == sha256_file(source)
    assert historical['research_version'] == package['package_version']
    assert case['counter_evidence'][-2]['text'].startswith('历史版本 ' + package['package_version'])
    assert case['financial_summary']['profit_adjustment_research']['scope'] == 'PREDECESSOR_RESEARCH_NOT_CURRENT_JOINT_MODEL'
    assert not any('finite model' in item for item in current['assumptions']['blockers'])
    proposal = json.loads((folder / 'valuation-proposal.json').read_text(encoding='utf-8'))
    assert proposal['baseline_scope'] == 'PREDECESSOR_MODEL_COMPARISON_NOT_CURRENT_JOINT_PATH'
    verify_pending_research_candidate(root=tmp_path, path=folder / 'candidate.json',
        expected_sha256=sha256_file(folder / 'candidate.json'))


@pytest.mark.parametrize('fault', ['missing_generator', 'missing_neutral', 'missing_helper', 'duplicate', 'unknown'])
def test_joint_verifier_requires_exact_implementation_set(tmp_path, synthetic_pending_candidate_clock, fault):
    package, path, request = candidate_inputs(tmp_path)
    policy_inputs(tmp_path, package, path)
    result = run_pending(tmp_path, package, path, request)
    bindings = result['implementation_bindings']
    if fault.startswith('missing_'):
        marker = dict(missing_generator='pending_research_candidate.py',
                      missing_neutral='neutral_valuation_proposal.py', missing_helper='joint_capital_path.py')[fault]
        result['implementation_bindings'] = [row for row in bindings if not row['path'].endswith(marker)]
    elif fault == 'duplicate':
        bindings.append(deepcopy(bindings[0]))
    else:
        bindings[0] = dict(path='src/value_investment_agent/valuation_models/residual_income.py',
            sha256=sha256_file(tmp_path / 'src/value_investment_agent/valuation_models/residual_income.py'))
    candidate_path = tmp_path / 'runtime/pending/candidate.json'
    candidate_path.write_text(json.dumps(result), encoding='utf-8')
    with pytest.raises(ValueError, match='exact generator/neutral/helper'):
        verify_pending_research_candidate(root=tmp_path, path=candidate_path,
            expected_sha256=sha256_file(candidate_path))


@pytest.mark.parametrize('fault', ['roe', 'ledger', 'policy_driver', 'source_value', 'proposal_ledger',
                                  'policy_symbol', 'policy_action', 'proposal_driver_copy'])
def test_recomputed_package_workbench_and_receipt_cannot_divorce_joint_policy(
        tmp_path, synthetic_pending_candidate_clock, monkeypatch, fault):
    source, policy_path, request = candidate_inputs(tmp_path)
    policy_inputs(tmp_path, source, policy_path)
    receipt = run_pending(tmp_path, source, policy_path, request)
    folder = tmp_path / 'runtime/pending'
    package_path = folder / 'package.json'
    package = json.loads(package_path.read_text(encoding='utf-8'))
    if fault == 'roe':
        value = str(D(package['facts']['scenario_inputs']['base']['forecast_roes'][0]) + D('.001'))
        package['facts']['scenario_inputs']['base']['forecast_roes'][0] = value
        for assumption in package['assumptions']['assumptions']:
            if assumption['name'] == 'forecast_roes_0':
                assumption['base'] = value
        for binding in package['assumption_bindings']:
            if binding['assumption_name'] == 'forecast_roes_0' and binding['scenario'] == 'base':
                binding['expected_value'] = value
    elif fault == 'ledger':
        package['research_case']['financial_summary']['pending_joint_capital_research']['ledgers']['base']['rows'][0]['profit'] = '1'
    elif fault in ('proposal_ledger', 'proposal_driver_copy'):
        proposal_path = folder / 'valuation-proposal.json'
        proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
        if fault == 'proposal_ledger':
            proposal['choices'][0]['joint_capital_ledgers']['base']['rows'][0]['profit'] = '1'
        else:
            proposal['choices'][0]['joint_drivers']['base']['new_operating_return'] = '.99'
        proposal_path.write_text(json.dumps(proposal), encoding='utf-8')
        for source_row in package['sources']:
            if source_row['local_path'] == proposal_path.relative_to(tmp_path).as_posix():
                source_row['sha256'] = sha256_file(proposal_path)
        # Keep reference hashes consistent too, not merely the outer source list.
        def refresh(value):
            if isinstance(value, dict):
                if value.get('path') == proposal_path.relative_to(tmp_path).as_posix():
                    value['sha256'] = sha256_file(proposal_path)
                for nested in value.values():
                    refresh(nested)
            elif isinstance(value, list):
                for nested in value:
                    refresh(nested)
        refresh(package)
    else:
        policy = json.loads(policy_path.read_text(encoding='utf-8'))
        if fault == 'policy_driver':
            policy['choices'][0]['joint_drivers']['base']['new_operating_return'] = '.11'
        elif fault == 'policy_symbol':
            policy['symbol'] = '000333'
        elif fault == 'policy_action':
            policy['action'] = 'order'
        else:
            policy['joint_historical']['revenue']['value'] = '1'
        policy_path.write_text(json.dumps(policy), encoding='utf-8')
        digest = sha256_file(policy_path)
        receipt['economic_policy_binding']['sha256'] = digest
        package['research_case']['financial_summary']['pending_joint_capital_research']['policy_sha256'] = digest
        for source_row in package['sources']:
            if source_row['local_path'] == policy_path.relative_to(tmp_path).as_posix():
                source_row['sha256'] = digest
        if fault in ('policy_symbol', 'policy_action'):
            # Fully reseal the nested proposal and package references too; this
            # is not a test that succeeds merely because some old Hash remains.
            proposal_path = folder / 'valuation-proposal.json'
            proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
            for binding in proposal['source_bindings']:
                if binding['path'] == policy_path.relative_to(tmp_path).as_posix():
                    binding['sha256'] = digest
            proposal_path.write_text(json.dumps(proposal), encoding='utf-8')
            proposal_digest = sha256_file(proposal_path)
            def refresh_proposal_refs(value):
                if isinstance(value, dict):
                    if (value.get('path') == proposal_path.relative_to(tmp_path).as_posix()
                            or value.get('local_path') == proposal_path.relative_to(tmp_path).as_posix()):
                        value['sha256'] = proposal_digest
                    for nested in value.values():
                        refresh_proposal_refs(nested)
                elif isinstance(value, list):
                    for nested in value:
                        refresh_proposal_refs(nested)
            refresh_proposal_refs(package)
            assert all(sha256_file(tmp_path / b['path']) == b['sha256'] for b in proposal['source_bindings'])
    package_path.write_text(json.dumps(package), encoding='utf-8')
    work_path = folder / 'workbench.json'
    rebuilt = build_current_workbench_for_symbol(root=tmp_path, symbol=package['symbol'],
        package_path=package_path, output_path=folder / 'rebuilt-workbench.json',
        schedule_request=request, schedule_request_sha256='a' * 64,
        recommendation_schema_version='advisory-decision-recommendation-v3')['result']
    work_path.write_text(json.dumps(rebuilt), encoding='utf-8')
    descriptor = build_descriptor(package, root=tmp_path)
    receipt.update(candidate_valuation=rebuilt['valuation'],
        model_context=build_research_review_model_context(descriptor=descriptor, spec=build_research_run_spec(descriptor)),
        recommendation_type=rebuilt.get('suggested_state'), execution_status=rebuilt.get('suggested_state'),
        research_blockers=rebuilt.get('research_blockers', []), schedule_gate=rebuilt.get('schedule_gate'))
    packet_path = folder / 'consumed-review.json'
    packet = project_research_review_packet(root=tmp_path, package_path=package_path,
        package_sha256=sha256_file(package_path), workbench_path=work_path, workbench_sha256=sha256_file(work_path))
    packet_path.write_text(json.dumps(packet), encoding='utf-8')
    receipt['review_packet_binding']['sha256'] = sha256_file(packet_path)
    for binding in receipt['source_bindings']:
        binding['sha256'] = sha256_file(tmp_path / binding['path'])
    candidate_path = folder / 'candidate.json'
    candidate_path.write_text(json.dumps(receipt), encoding='utf-8')
    # Validate every outer identity before the semantic rejection assertion.
    assert all(sha256_file(tmp_path / b['path']) == b['sha256'] for b in receipt['source_bindings'])
    verify_current_decision_workbench(rebuilt)
    assert receipt['model_context'] == build_research_review_model_context(
        descriptor=build_descriptor(package, root=tmp_path), spec=build_research_run_spec(descriptor))
    if fault == 'proposal_driver_copy':
        from value_investment_agent.application.product.economic_review_materials import _joint_capital_review
        candidate_binding = dict(path=candidate_path.relative_to(tmp_path).as_posix(),
            sha256=sha256_file(candidate_path))
        verified = verify_pending_research_candidate(root=tmp_path, path=candidate_path,
            expected_sha256=candidate_binding['sha256'])
        before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
        review = _joint_capital_review(root=tmp_path, handoff=dict(candidate_binding=candidate_binding,
            symbol=verified['symbol'], model_context=verified['model_context']), now=datetime.now(timezone.utc))
        policy = json.loads(policy_path.read_bytes())
        assert review['scenarios'][1]['drivers'] == policy['choices'][0]['joint_drivers']['base']
        assert review['scenarios'][1]['drivers']['new_operating_return'] != '.99'
        assert review['scenarios'][1]['ledger'] == proposal['choices'][0]['joint_capital_ledgers']['base']
        assert review['status'] == 'CONDITIONAL_PATH_NOT_APPROVED' and review['action'] == 'no_order'
        assert all(p.read_bytes() == raw for p, raw in before.items())
        return
    with pytest.raises(ValueError, match='economic derivation|extracted value/unit/scope|policy identity/version'):
        verify_pending_research_candidate(root=tmp_path, path=candidate_path,
            expected_sha256=sha256_file(candidate_path))
    if fault in ('policy_symbol', 'policy_action'):
        # Counterfactual confirms the fixture is otherwise fully coherent:
        # remove only the new semantic guard inside this isolated test process.
        from value_investment_agent.application.product import pending_research_candidate as subject
        with monkeypatch.context() as patch:
            patch.setattr(subject, 'validate_proposal_policy_identity', lambda **kwargs: None)
            accepted_without_guard = verify_pending_research_candidate(root=tmp_path, path=candidate_path,
                expected_sha256=sha256_file(candidate_path))
            assert accepted_without_guard['status'] == 'PENDING_REVIEW'
            assert accepted_without_guard['action'] == 'no_order'


@pytest.mark.parametrize('mode', ['finite', 'joint'])
@pytest.mark.parametrize('field,value', [('symbol', '000333'), ('action', 'order')])
def test_builder_shares_no_order_policy_identity_guard(tmp_path, mode, field, value):
    package, path = proposal_inputs(tmp_path)
    if mode == 'joint':
        policy_inputs(tmp_path, package, path)
    policy = json.loads(path.read_text(encoding='utf-8'))
    policy[field] = value
    path.write_text(json.dumps(policy), encoding='utf-8')
    with pytest.raises(ValueError, match='policy identity/version'):
        run(tmp_path, package, path)
    assert not (tmp_path / 'runtime/proposal.json').exists()


@pytest.mark.skipif(os.environ.get('RUN_STAGED_CC1') != '1', reason='Opt-in public source E2E, no selectors changed')
def test_staged_cc1_unregistered_source_e2e():
    root = Path(__file__).resolve().parents[1]
    staged = root / 'runtime/d2-economic-research-20261023/cc1'
    script = staged / 'value_coherent_candidate_20261023.py'
    # Read literal research declarations only; never execute the archived script
    # with its original dual1 path or import it into the production domain.
    tree = ast.parse(script.read_text(encoding='utf-8'))
    constants = {}
    specs = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'D':
                constants[name] = D(ast.literal_eval(node.value.args[0]))
            if name == 'ASSUMPTIONS':
                specs = {ast.literal_eval(key): {kw.arg: ast.literal_eval(kw.value)
                    for kw in value.keywords} for key, value in zip(node.value.keys, node.value.values)}
    obs = json.loads((root / 'runtime/d2-economic-research-20261008/operating-mechanism-evidence-v1.json').read_text(encoding='utf-8'))
    observed = {row['id']: D(row['value']) for row in obs['official_observations']}
    def ttm(field):
        return observed['fy_' + field] + observed['h1_' + field] - observed['h1_prior_' + field]
    historical = dict(revenue=ttm('revenue'), cost=ttm('cost'),
        surcharges=D('28094002556.87'), selling=ttm('selling'), admin=ttm('admin'), research=ttm('research'),
        pre_tax_profit=constants['PBT0'], tax=constants['TAX0'], parent_profit=constants['PARENT0'],
        nonrecurring=constants['NR0'], da=constants['DA0'], cash=constants['CASH0'])
    drivers = {}
    ratio = historical['cost'] / historical['revenue']
    targets = dict(H1=observed['h1_cost'] / observed['h1_revenue'], TTM=ratio,
                   FY=observed['fy_cost'] / observed['fy_revenue'])
    for name, spec in specs.items():
        drivers[name] = dict(years=[dict(year=i, revenue_growth=spec['revenue_growth'],
            cost_ratio=str(ratio + (targets[spec['cost_target']] - ratio) * D(i) / 5)) for i in range(1, 6)],
            retention=str(constants['RETENTION']), operating_allocation=str(constants['OPERATING_ALLOCATION']),
            new_operating_return=spec['new_operating_return'],
            new_liquidity_return=str(constants['NEW_LIQUIDITY_RETURN']),
            parent_cash_conversion=str(constants['PARENT_CASH_CONVERSION']),
            terminal_growth=spec['terminal_growth'], terminal_profit_scale='1')
    package_path = root / 'runtime/pending-candidate-replay-v5-20261022-final/600519/package.json'
    assert sha256_file(package_path) == 'f100c2a26b0d61a3f9d90a1b60976b00d8217b55592360f6940b0696a46829bf'
    output = root / 'runtime/cc1-joint-unregistered-e2e' / uuid4().hex
    output.mkdir(parents=True)
    policy = dict(schema_version=JOINT_SCHEMA, action='no_order', symbol='600519',
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_package_sha256=sha256_file(package_path),
        profit_anchor_field='ttm_ex_nonrecurring_parent_profit_cny',
        profit_basis='Full parent aggregate ex-TTM proxy, not uniquely normalized earnings.',
        assumption_scope='RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST',
        rationale_bindings=[dict(id='cc1-script' if path == script else 'cc1-' + str(index),
            path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
            for index, path in enumerate(sorted(staged.iterdir())) if path.is_file()],
        joint_historical={key: dict(value=str(value), unit='CNY',
            scope=('consolidated_parent' if key in ('parent_profit', 'nonrecurring') else
                   'parent_cash_lookthrough_proxy' if key == 'cash' else 'consolidated'),
            source_id='cc1-script', rationale='Source-linked declaration in archived final CC1 script and independently reviewed historical bridge; not PDF certification.')
            for key, value in historical.items()},
        choices=[dict(id='CC1_CONTINUING', rationale='Continuing franchise joint-capital hypothesis; LOW confidence.',
            countercase='Terminal marginal capital efficiency and cash conversion may fail.',
            joint_drivers=drivers, cost_of_equity={name: str(constants['KE']) for name in drivers})],
        economic_review_items=['Review terminal capital efficiency, allocation and sustainable payout.'],
        assurance_limits=['Independent conditional review is not G3.', 'Strict historical PIT not proven.',
                          'Cash bridge is parent look-through research, not upstream distribution certification.'])
    review_path = staged / 'value-coherent-candidate-independent-review-20261023.md'
    review_source_id = next(row['id'] for row in policy['rationale_bindings']
                          if row['path'] == review_path.relative_to(root).as_posix())
    for item in policy['joint_historical'].values():
        item.update(mapping_basis='MANUALLY_REVIEWED_DECLARATION_NOT_MACHINE_EXTRACTED',
                    review_source_id=review_source_id)
    policy_path = output / 'policy.json'
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding='utf-8')
    from value_investment_agent.application.product.pending_research_candidate import prepare_pending_research_candidate
    request = dict(schema_version='research-schedule-request-v1', symbol='600519',
        source_id='LOCAL_VERIFIED_RESEARCH', period='2026-06-30',
        research_question_id='cc1_joint_conditional_review', blocker_id='joint_inputs_not_consumed',
        reopen_condition_met=True, new_evidence_ids=['cc1-script'])
    request_path = output / 'schedule-request.json'
    request_path.write_text(json.dumps(request), encoding='utf-8')
    result = prepare_pending_research_candidate(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), policy_path=policy_path, policy_sha256=sha256_file(policy_path),
        choice_id='CC1_CONTINUING', output_dir=output / 'pending', schedule_request=request,
        schedule_request_sha256=sha256_file(request_path))
    assert result['candidate_valuation']['status'] == 'conditional_research_only'
    assert result['price_admitted'] is result['approval_changed'] is False
    verified = verify_pending_research_candidate(root=root, path=output / 'pending/candidate.json',
        expected_sha256=sha256_file(output / 'pending/candidate.json'))
    assert verified['model_context'] == result['model_context']
    package = json.loads((output / 'pending/package.json').read_text(encoding='utf-8'))
    assert package['quote'] is None
    assert package['research_case']['financial_summary']['normalized_parent_profit_cny'] is None
    current = package['research_case']
    assert 'STRESS_ONLY' not in current['thesis']
    assert '不是全资本机械衰减路径' in current['thesis']
    assert '全资本强衰减' not in current['mispricing_hypothesis']
    assert all('全资本' not in blocker for blocker in current['blockers'])
    for item in current['counter_evidence']:
        if '全资本' in item['text'] or '强衰减' in item['text']:
            assert item['text'].startswith('历史版本 ')
    assert current['financial_summary']['predecessor_research_narrative']['package_binding']['sha256'] == policy['source_package_sha256']
    assert not any('finite model' in item or 'Strong-fade' in item for item in package['assumptions']['blockers'])
    proposal = json.loads((output / 'pending/valuation-proposal.json').read_text(encoding='utf-8'))
    assert proposal['baseline_scope'] == 'PREDECESSOR_MODEL_COMPARISON_NOT_CURRENT_JOINT_PATH'
    print('UNREGISTERED_CC1_CANDIDATE=' + str(output / 'pending/candidate.json'))
