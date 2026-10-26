"""Explicit ten-year product intake into the existing unsigned research service.

The immutable five-year parent is an antecedent, never an implicit current.
No external ROE table, approval, private portfolio or live registry is accepted.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D, localcontext
from pathlib import Path

from .finite_advantage_research import _capital, _distribution
from .product_operating_research import build_product_operating_research
from ..product.common import require_inside, sha256_file, write_new_json, load_json_object
from ..product.incremental_validity import read_bound_json
from ..product.source_native_candidate_v2 import (
    verify_source_native_candidate, _groups, _bound, _stamp, _economic_workbench, CANDIDATE_FIELDS,
)
from ..product.company_research import _serialize_outcome
from ..product.decision_surface import verify_current_decision_workbench
from ..product.research_reviews import build_research_review_model_context
from ..product.research_review_packet import project_research_review_packet
from ..product.source_bound_inputs import source_catalog_sha256
from ...domain.valuation.product_continuation_cash_path_v1 import build_product_continuation_cash_path
from ...domain.valuation.finite_advantage_cash_path_v1 import SCOPE
from ...m1_valuation_package_builder import build_descriptor
from ...research_input import build_research_run_spec
from ...research_application import ResearchApplicationService


SCHEMA = 'product-continuation-pending-research-candidate-v1'
INPUT_MODE = 'SOURCE_NATIVE_PRODUCT_TEN_YEAR_V1'
CODE_ROOT = Path(__file__).resolve().parents[4]
IMPLEMENTATIONS = tuple('src/value_investment_agent/'+name for name in (
    'application/research/product_continuation_candidate.py',
    'application/research/product_operating_research.py', 'application/research/finite_advantage_research.py',
    'application/research/operating_earnings_bridge.py', 'infrastructure/filings/operating_erosion_sources.py',
    'infrastructure/filings/pdf_text.py', 'domain/valuation/product_continuation_cash_path_v1.py',
    'domain/valuation/finite_advantage_cash_path_v1.py', 'domain/valuation/operating_product_paths.py',
    'domain/valuation/operating_realization_erosion_v1.py', 'domain/valuation/source_native_cash_v1.py',
    'application/product/source_native_candidate_v2.py', 'm1_valuation_package_builder.py',
    'research_input.py', 'research_application.py', 'valuation_models/residual_income.py',
    'application/product/company_research.py', 'application/product/research_review_packet.py',
    'application/product/research_reviews.py', 'application/product/source_bound_inputs.py',
))
_EXECUTION_HASHES = {name: sha256_file(CODE_ROOT/name) for name in IMPLEMENTATIONS}


def _closure(root, refs):
    result = {}
    for item in refs:
        ref = {key: item[key] for key in ('path', 'sha256')}
        path = require_inside(root, root/ref['path'], 'continuation source')
        if path.relative_to(root).as_posix() != ref['path'] or sha256_file(path) != ref['sha256']:
            raise ValueError('Continuation source identity/hash drift')
        if ref['path'] in result and result[ref['path']] != ref:
            raise ValueError('Conflicting continuation source identity')
        result[ref['path']] = ref
    return list(result.values())


def _implementations(root):
    refs = []
    for name in IMPLEMENTATIONS:
        actual = _EXECUTION_HASHES[name]
        ref = _bound(root, require_inside(root, root/name, 'continuation implementation'))
        if ref['sha256'] != actual:
            raise ValueError('Root implementation differs from executing code')
        refs.append(ref)
    return refs


def _cold_center(root, request, now):
    """Explicit parent and policy reads; never call the current-pointer loader."""
    if set(request) != {'symbol', 'generated_at', 'source_candidate_binding', 'cash_policy_binding', 'continuation_policy_binding'}:
        raise ValueError('Exact source-bound continuation request required')
    clock = _stamp(request['generated_at'])
    if clock > now or now.utcoffset() is None:
        raise ValueError('Continuation request is not yet available')
    parent_ref = request['source_candidate_binding']
    parent = verify_source_native_candidate(root=root, path=root/parent_ref['path'], expected_sha256=parent_ref['sha256'], now=clock)
    _, source = read_bound_json(root, parent['source_package_binding'], 'continuation parent package')
    _, ledger = read_bound_json(root, parent['native_cash_ledger_binding'], 'continuation parent cash')
    policies = []
    for key, schema in (('cash_policy_binding', 'finite-advantage-cash-research-policy-v1'),
                        ('continuation_policy_binding', 'product-continuation-research-policy-v1')):
        _, policy = read_bound_json(root, request[key], 'continuation policy')
        if (policy['schema_version'] != schema or policy['symbol'] != parent['symbol']
                or policy['candidate_binding'] != parent_ref or policy['confidence'] != 'LOW'
                or policy['action'] != 'no_order' or _stamp(policy['generated_at']) > clock):
            raise ValueError('Continuation policy identity/availability mismatch')
        policies.append(policy)
    cash_policy, policy = policies
    if (any(not isinstance(policy.get(key), str) or not policy[key].strip() for key in
            ('rationale', 'cash_return_rationale', 'terminal_rationale', 'strongest_counter_evidence'))
            or not isinstance(policy.get('counter_evidence'), list) or not policy['counter_evidence']
            or any(not isinstance(text, str) or not text.strip() for text in policy['counter_evidence'])):
        raise ValueError('Explicit continuation economics and counter-evidence required')
    if request['symbol'] != parent['symbol'] or policy['center'] != 'FLAT_YEAR5_PRODUCT_LEVELS_AND_COST_RATIOS' or policy['continuation_years'] != 5:
        raise ValueError('Exact three-scenario flat ten-year product center required')
    facts = build_descriptor(source, root=root).facts
    implementations = _implementations(root)
    before = _closure(root, [parent_ref, parent['source_package_binding'], parent['native_cash_ledger_binding'],
        request['cash_policy_binding'], request['continuation_policy_binding'], *parent['source_bindings'], *implementations])
    generated = build_product_operating_research(root=root, package=source, ledger=ledger, facts=facts, evaluation_at=clock)
    if generated['status'] != 'CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED':
        raise ValueError('Original product sources cannot be cold replayed')
    centers, inputs = {}, {}
    with localcontext() as ctx:
        ctx.prec = 48
        for original in generated['scenarios']:
            name = original['scenario']
            if name in centers or name not in ('bear', 'base', 'bull'):
                raise ValueError('Duplicate or unknown center scenario')
            old, history = ledger['cases']['TIMING_DELAY'][name], ledger['history']
            opening = dict(scope=SCOPE, currency='CNY', book_equity_cny=str(facts.operating_inputs['start_book_equity']),
                ordinary_shares=str(facts.operating_inputs['ordinary_shares']), cash_cny=history['ttm']['cash_end'],
                unremitted_assets_cny='0', distribution_capacity_cny=history['ttm']['parent_retained_profit_end'],
                cash_floor_cny=old['cash_floor'], uncalled_fund_commitment_cny=history['known_uncalled_fund_commitment']['amount_cny'],
                selected_project_budget_cny=old['project_budget'])
            continuation = [dict(moutai_volume_growth='0', moutai_realization_growth='0', series_volume_growth='0',
                series_realization_growth='0', other_revenue_growth='0', cost_ratio=original['operating_rows'][-1]['drivers']['cost_ratio']) for _ in range(5)]
            capital = [_capital(y, D(old['project_budget'])/5 if y <= 5 else D(0),
                D(opening['uncalled_fund_commitment_cny']) if y == 1 else D(0), D(0), cash_policy['maintenance_rationale']) for y in range(1, 11)]
            distribution = [_distribution(y, cash_policy, persistent=False) for y in range(1, 11)]
            terminal = dict(method='STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT', rationale=policy['terminal_rationale'],
                operating_continuation='FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT',
                distribution_constraint_rationale=cash_policy['terminal_distribution_rationale'],
                capital_cash_row=_capital(11, D(0), D(0), D(0), cash_policy['maintenance_rationale']),
                distribution_row=_distribution(11, cash_policy, persistent=False, terminal=True))
            result = build_product_continuation_cash_path(opening_state=opening, first_five_product_rows=original['operating_rows'],
                continuation_policy=continuation, capital_cash_rows=capital, distribution_rows=distribution,
                cost_of_equity=ledger['plan']['ke'], incremental_cash_yield=ledger['plan']['incremental_parent_cash_yield'], terminal_policy=terminal)
            if not result['valuation']['usable'] or len(result['cash_rows']) != 10:
                raise ValueError('Ten-year cash or terminal constraints failed')
            if any(D(row['distribution_cny']) != D('.9')*D(row['profit_cny']) for row in result['cash_rows']):
                raise ValueError('Generic RI requires exact constant ten-percent retention')
            centers[name] = result
            inputs[name] = dict(cost_of_equity=str(D(ledger['plan']['ke'])), retention='0.1', terminal_growth='0',
                forecast_roes=[str(D(row['profit_cny'])/D(row['opening_book_cny'])) for row in result['cash_rows']],
                terminal_roe=str(D(result['terminal']['next_profit_cny'])/D(result['cash_rows'][-1]['closing_book_cny'])))
    if set(centers) != {'bear', 'base', 'bull'}:
        raise ValueError('Exactly three center scenarios required')
    refs = _closure(root, [*before, *generated['source_bindings']])
    return source, dict(schema_version='source-bound-product-ten-year-ledger-v1', action='no_order',
        generated_at=clock.isoformat(), financial_basis=source['facts']['as_of'], centers=centers, scenario_inputs=inputs,
        economic_explanation={key: deepcopy(policy.get(key)) for key in
            ('rationale', 'cash_return_rationale', 'terminal_rationale', 'counter_evidence', 'strongest_counter_evidence')},
        cash_conditions={key: deepcopy(cash_policy.get(key)) for key in
            ('maintenance_rationale', 'capacity_rationale', 'cash_mapping_rationale', 'terminal_distribution_rationale')}), refs


def _package(source, ledger, ledger_ref, refs, clock):
    package = deepcopy(source)
    for key in ('quote', 'valuation_approval', 'human_research_approval', 'research_reviews', 'event_materiality_review', 'entry_thesis', 'investment_consistency_review'):
        package[key] = None
    version = 'product-ten-year-'+clock.strftime('%Y%m%dT%H%M%S%fZ')
    package.update(package_version=version, descriptor_version=version, run_id=version)
    day = clock.astimezone(timezone(timedelta(hours=8))).date().isoformat()
    package['point_in_time'].update(research_as_of=day, computed_at=clock.isoformat(), available_at=clock.isoformat())
    package['research_case']['as_of'] = day
    package['research_case']['research_version'] = version
    package['research_case']['financial_summary']['product_ten_year_research'] = dict(
        scope='CONDITIONAL_RESEARCH_NOT_G3', ledger_binding=ledger_ref, normalized_parent_profit_cny=None,
        antecedent_research_version=source['research_case']['research_version'])
    catalog = {item['id']: item for item in package['sources']}
    extra = []
    for index, ref in enumerate([*refs, ledger_ref]):
        ident = 'product-ten-year-source-'+str(index)
        if ident in catalog:
            raise ValueError('Continuation source ID collision')
        extra.append(dict(id=ident, **ref))
        package['sources'].append(dict(id=ident, kind='research_artifact', local_path=ref['path'], location=ref['path'],
            sha256=ref['sha256'], source_available_at=clock.isoformat(), availability_basis='CURRENT_RESEARCH_NOT_HISTORICAL_PIT'))
    package['facts'].update(confidence='低', confidence_evidence=None, scenario_inputs=ledger['scenario_inputs'])
    package['facts']['evidence_refs'] += extra
    package['research_case']['evidence_refs'] += extra
    explanation = ledger['economic_explanation']
    # Keep first-five company assumptions, but never inherit a five-year-only thesis.
    package['research_case']['financial_summary']['product_ten_year_research'].update(
        economic_explanation=deepcopy(explanation), cash_conditions=deepcopy(ledger['cash_conditions']))
    if explanation.get('rationale'):
        package['research_case']['thesis'] += '\nTen-year conditional extension: '+explanation['rationale']
    if explanation.get('cash_return_rationale'):
        package['research_case']['return_driver'] += '\n'+explanation['cash_return_rationale']
    for text in explanation.get('counter_evidence') or []:
        package['research_case']['counter_evidence'].append(dict(kind='hypothesis', text=text,
            evidence_refs=[row['id'] for row in extra]))
    assumptions, bindings = [], []
    for field in ('cost_of_equity', 'retention', 'terminal_roe', 'terminal_growth', *[f'forecast_roes_{i}' for i in range(10)]):
        path = field.replace('forecast_roes_', 'forecast_roes.')
        values = {name: row['forecast_roes'][int(field.rsplit('_', 1)[1])] if field.startswith('forecast_roes_') else row[field]
                  for name, row in ledger['scenario_inputs'].items()}
        assumptions.append(dict(name=field, unit='ratio', **values, basis='SOURCE_NATIVE_TEN_YEAR_PRODUCT_CASH_RESEARCH',
            rationale='Cold product and cash calculation; flat continuation and lawful terminal payout remain LOW hypotheses.',
            confidence='low', sensitivity='high', evidence_refs=extra))
        bindings.extend(dict(assumption_name=field, scenario=name, field_path=path, expected_value=value, evidence_refs=extra)
                        for name, value in values.items())
    package['assumptions'] = dict(assumptions=assumptions, evidence_refs=extra, blockers=deepcopy(source['assumptions'].get('blockers', [])))
    package['assumption_bindings'] = bindings
    package['source_contract'].update(cutoff_at=clock.isoformat(), source_catalog_sha256=source_catalog_sha256(package['sources']))
    return package


def _run(root, package, package_ref, clock, centers):
    descriptor = build_descriptor(package, root=root)
    spec = build_research_run_spec(descriptor)
    native = _serialize_outcome(ResearchApplicationService(now_utc=lambda: clock).run_company_research(spec))
    if (not native['valuation'] or native['valuation']['status'] != 'conditional_research_only'
            or native['valuation']['confidence'] != '低'
            or native['decision_recommendation'].get('recommendation_type', native['decision_recommendation'].get('recommendation_action')) != 'NO_ACTION'):
        raise ValueError('Ten-year replay must remain LOW NO_ACTION')
    from ...valuation_models.residual_income import _shared_scenario_calculation
    with localcontext() as ctx:
        ctx.prec = 48
        for name, center in centers.items():
            calculation = _shared_scenario_calculation(descriptor.facts, descriptor.facts.scenario_inputs[name])
            if len(calculation['forecast_years']) != 10:
                raise ValueError('Typed RI did not consume all ten cash years')
            for projected, cash in zip(calculation['forecast_years'], center['cash_rows']):
                for model_key, cash_key in (('opening_book_equity_cny', 'opening_book_cny'),
                        ('net_income_assumption_cny', 'profit_cny'), ('dividend_assumption_cny', 'distribution_cny'),
                        ('closing_book_equity_cny', 'closing_book_cny')):
                    if abs(D(projected[model_key])-D(cash[cash_key])) > D('0.01'):
                        raise ValueError('Typed RI annual P/B/D differs from cold cash ledger')
            if abs(D(calculation['terminal_first_dividend_cny'])-D(center['terminal']['next_profit_cny'])) > D('0.01'):
                raise ValueError('Typed RI terminal dividend differs from cold terminal funds')
            origin = D(calculation.get('basis_origin_equity_value_cny', calculation['conditional_equity_value_cny']))
            if abs(origin-D(center['valuation']['equity_value_cny'])) > D('0.01'):
                raise ValueError('Typed RI differs from cold cash kernel value')
    work = dict(schema_version='product-current-workbench-request-v1', generated_at=clock.isoformat(),
        command='current_workbench', symbol=package['symbol'], action='no_order', research_status=native['status'],
        research_blockers=native['blockers'], portfolio_input_status='BLOCKED_PRIVATE_INPUT', position_guidance=None,
        schedule_gate=None, evidence_stops=[], canonical_workbook_written=False, suggested_state='NO_ACTION',
        input_descriptor_sha256=descriptor.input_sha256,
        research_receipt=dict(command='company_research', symbol=package['symbol'], action='no_order', input_sha256=dict(valuation_package=package_ref['sha256'])),
        source_verification=dict(status='LOCAL_BYTES_VERIFIED', scope='byte_integrity_not_economic_approval', source_contract_status='SOURCE_CUTOFF_AND_SCENARIO_BINDINGS_VALIDATED'))
    for field in ('current_status', 'valuation', 'price_bridge', 'price_attractiveness', 'pre_decision_eligibility', 'decision_recommendation', 'artifact_bundle'):
        work[field] = native[field]
    verify_current_decision_workbench(work)
    return work, build_research_review_model_context(descriptor=descriptor, spec=spec)


def prepare_product_continuation_candidate(*, root: Path, source_candidate_binding: dict,
        cash_policy_binding: dict, continuation_policy_binding: dict, output_dir: Path):
    root = root.resolve()
    clock = datetime.now(timezone.utc)
    parent = verify_source_native_candidate(root=root, path=root/source_candidate_binding['path'], expected_sha256=source_candidate_binding['sha256'], now=clock)
    request = dict(symbol=parent['symbol'], generated_at=clock.isoformat(), source_candidate_binding=deepcopy(source_candidate_binding),
        cash_policy_binding=deepcopy(cash_policy_binding), continuation_policy_binding=deepcopy(continuation_policy_binding))
    source, ledger, refs = _cold_center(root, request, clock)
    target = require_inside(root/'runtime', output_dir, 'ten-year candidate output')
    if target.exists():
        raise FileExistsError('Ten-year candidate output must be new')
    target.mkdir(parents=True)
    for filename, value in (('input.json', request), ('cash-ledger.json', ledger)):
        write_new_json(target/filename, value)
    refs = _closure(root, [*refs, _bound(root, target/'input.json')])
    package = _package(source, ledger, _bound(root, target/'cash-ledger.json'), refs, clock)
    write_new_json(target/'package.json', package)
    work, context = _run(root, package, _bound(root, target/'package.json'), clock, ledger['centers'])
    write_new_json(target/'workbench.json', work)
    packet = project_research_review_packet(root=root, package_path=target/'package.json', package_sha256=sha256_file(target/'package.json'),
        workbench_path=target/'workbench.json', workbench_sha256=sha256_file(target/'workbench.json'))
    write_new_json(target/'consumed-review.json', packet)
    candidate = dict(schema_version=SCHEMA, input_mode=INPUT_MODE, symbol=parent['symbol'], generated_at=clock.isoformat(),
        status='PENDING_REVIEW', action='no_order', source_candidate_binding=deepcopy(source_candidate_binding),
        input_binding=_bound(root, target/'input.json'), source_package_binding=_bound(root, target/'package.json'),
        native_cash_ledger_binding=_bound(root, target/'cash-ledger.json'), review_packet_binding=_bound(root, target/'consumed-review.json'),
        model_context=context, model_context_scope='ACTUALLY_CONSUMED', candidate_valuation=work['valuation'],
        candidate_research_as_of=package['point_in_time']['research_as_of'], execution_status='NO_ACTION', research_blockers=work['research_blockers'],
        review_groups=_groups(), implementation_bindings=_implementations(root), schedule_gate=None, schedule_consumed=False,
        approval_changed=False, research_admitted=False, price_admitted=False, canonical_written=False,
        registered_current_case_changed=False, primary_registered=False, position_guidance=None, strict_contemporaneous_pit='NOT_PROVEN',
        source_bindings=_closure(root, [*refs, *packet['source_bindings'], _bound(root, target/'cash-ledger.json'), _bound(root, target/'consumed-review.json')]))
    write_new_json(target/'candidate.json', candidate)
    return verify_product_continuation_candidate(root=root, path=target/'candidate.json', expected_sha256=sha256_file(target/'candidate.json'))


def verify_product_continuation_candidate(*, root: Path, path: Path, expected_sha256: str, now=None):
    root = root.resolve()
    path, candidate = read_bound_json(root, dict(path=path.relative_to(root).as_posix(), sha256=expected_sha256), 'ten-year candidate')
    require_inside(root/'runtime', path, 'ten-year candidate')
    clock = now or datetime.now(timezone.utc)
    if set(candidate) != CANDIDATE_FIELDS | {'input_binding', 'source_candidate_binding'}:
        raise ValueError('Exact ten-year candidate fields required')
    for field, filename in (('input_binding', 'input.json'), ('source_package_binding', 'package.json'),
                            ('native_cash_ledger_binding', 'cash-ledger.json'), ('review_packet_binding', 'consumed-review.json')):
        if candidate[field] != _bound(root, path.parent/filename):
            raise ValueError('Exact ten-year candidate file identity mismatch')
    _, request = read_bound_json(root, candidate['input_binding'], 'ten-year immutable inputs')
    if (candidate.get('schema_version') != SCHEMA or candidate.get('input_mode') != INPUT_MODE
            or candidate.get('generated_at') != request['generated_at'] or candidate.get('source_candidate_binding') != request['source_candidate_binding']
            or candidate.get('implementation_bindings') != _implementations(root)):
        raise ValueError('Ten-year schema/input/implementation identity mismatch')
    source, expected_ledger, refs = _cold_center(root, request, clock)
    _, ledger = read_bound_json(root, candidate['native_cash_ledger_binding'], 'ten-year derived cash')
    if ledger != expected_ledger:
        raise ValueError('Ten-year ledger differs from cold product/cash replay')
    refs = _closure(root, [*refs, candidate['input_binding']])
    generated = _stamp(request['generated_at'])
    expected_package = _package(source, ledger, candidate['native_cash_ledger_binding'], refs, generated)
    _, package = read_bound_json(root, candidate['source_package_binding'], 'ten-year package')
    if package != expected_package:
        raise ValueError('Ten-year package differs from exact cold inputs')
    work, context = _run(root, package, candidate['source_package_binding'], generated, ledger['centers'])
    saved = load_json_object(path.parent/'workbench.json', 'ten-year workbench')
    if _economic_workbench(saved) != _economic_workbench(work):
        raise ValueError('Ten-year workbench differs from actual typed replay')
    packet = project_research_review_packet(root=root, package_path=path.parent/'package.json', package_sha256=candidate['source_package_binding']['sha256'],
        workbench_path=path.parent/'workbench.json', workbench_sha256=sha256_file(path.parent/'workbench.json'))
    expected = dict(candidate, symbol=package['symbol'], status='PENDING_REVIEW', action='no_order', model_context=context,
        model_context_scope='ACTUALLY_CONSUMED', candidate_valuation=work['valuation'], candidate_research_as_of=package['point_in_time']['research_as_of'],
        execution_status='NO_ACTION', research_blockers=work['research_blockers'], review_groups=_groups(),
        schedule_gate=None, schedule_consumed=False, approval_changed=False, research_admitted=False, price_admitted=False,
        canonical_written=False, registered_current_case_changed=False, primary_registered=False, position_guidance=None, strict_contemporaneous_pit='NOT_PROVEN')
    if candidate != expected:
        raise ValueError('Ten-year candidate consumption/authority mismatch')
    if candidate['review_packet_binding'] != _bound(root, path.parent/'consumed-review.json') or load_json_object(path.parent/'consumed-review.json', 'ten-year packet') != packet:
        raise ValueError('Ten-year review packet differs from consumed inputs')
    closure = _closure(root, [*refs, *packet['source_bindings'], candidate['native_cash_ledger_binding'], candidate['review_packet_binding']])
    if candidate['source_bindings'] != closure:
        raise ValueError('Ten-year source closure mismatch')
    read_bound_json(root, candidate['input_binding'], 'ten-year final inputs')
    if sha256_file(path) != expected_sha256:
        raise ValueError('Ten-year candidate changed during verification')
    return candidate
