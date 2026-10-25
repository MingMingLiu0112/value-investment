"""Source-bound product hypotheses through existing cash and RI calculations."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path

from ...domain.valuation.operating_product_paths import build_product_operating_paths
from ...domain.valuation.operating_realization_erosion_v1 import FIELDS
from ...domain.valuation.source_native_cash_v1 import replay_timing_delay_inputs
from ...infrastructure.filings.operating_erosion_sources import (
    read_operating_erosion_sources, read_product_revenue_sources,
)
from ...valuation_models.residual_income import (
    ResidualIncomeScenarioInputs, _shared_scenario_calculation,
)
from ..product.common import require_inside, sha256_file, write_new_json, write_new_bytes
from .operating_earnings_bridge import extract_statement


POLICY_PATH = 'config/research-assumptions/600519-product-operating-v1.json'
DRIVERS = frozenset({'moutai_volume_growth', 'moutai_realization_growth',
    'series_volume_growth', 'series_realization_growth', 'other_revenue_growth', 'cost_ratio'})


def build_product_operating_research(*, root: Path, package: dict, ledger: dict,
                                     facts, evaluation_at: datetime,
                                     _include_native_cases: bool = False) -> dict:
    """Research assumptions never replace the registered candidate or approval."""
    envelope = dict(schema_version='product-operating-research-v1', symbol=package['symbol'], action='no_order',
        formal_eligibility=False, research_admitted=False, price_admitted=False,
        confidence='LOW', normalized_parent_profit_cny=None, scenarios=[])
    root = root.resolve()
    policy_name = 'config/research-assumptions/'+package['symbol']+'-product-operating-v1.json'
    path = require_inside(root, root/policy_name, 'product operating assumptions')
    if not path.is_file():
        return dict(envelope, status='NOT_APPLICABLE', reason='No applicable product policy for this issuer.')
    policy_ref = dict(path=policy_name, sha256=sha256_file(path))
    policy = json.loads(path.read_bytes())
    available = datetime.fromisoformat(policy['generated_at'])
    if (evaluation_at.utcoffset() is None or available.utcoffset() is None
            or policy.get('schema_version') != 'product-operating-research-policy-v1'
            or policy.get('symbol') != package['symbol'] or policy.get('action') != 'no_order'
            or policy.get('identity_class') != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'
            or policy.get('confidence') != 'LOW' or policy.get('reference_period') != 'H12026'):
        raise ValueError('Product operating research policy identity/scope mismatch')
    if available > evaluation_at:
        return dict(envelope, status='NOT_YET_AVAILABLE', reason='Research policy postdates this evaluation.',
                    input_available_at=available.isoformat(), policy_binding=policy_ref)
    catalog = {row['id']:row for row in package['sources']}
    if not {'cninfo:1225114741', 'cninfo:1225475868'}.issubset(catalog):
        return dict(envelope, status='UNSUPPORTED', reason='Required issuer product/statement originals absent.')
    inputs = read_operating_erosion_sources(root=root, symbol=package['symbol'],
        sources=package['sources'], fields=FIELDS)
    statements = [extract_statement(root=root, spec=spec) for spec in inputs['specs']]
    annual, interim = ({key:row['rows'][key]['values'] for key in FIELDS} for row in statements)
    product = read_product_revenue_sources(root=root, sources=package['sources'],
        interim_revenue=interim['operating_revenue'][0])
    if set(policy['scenarios']) != {'bear', 'base', 'bull'}:
        raise ValueError('Exactly three product research hypotheses required')
    expanded = {}
    for name, scenario in policy['scenarios'].items():
        if (set(scenario) != DRIVERS | {'rationale'} or not scenario['rationale'].strip()
                or not isinstance(scenario['series_realization_growth'], list)
                or len(scenario['series_realization_growth']) != 5):
            raise ValueError('Product scenario needs five explicit years and economic rationale')
        expanded[name] = [{key:(scenario[key][year] if key == 'series_realization_growth' else scenario[key])
                           for key in DRIVERS} for year in range(5)]
    generated = build_product_operating_paths(annual=annual, interim=interim,
        product_revenue_cny=product['product_revenue_cny'], policy=expanded, ledger=ledger,
        opening_book=str(facts.operating_inputs['start_book_equity']))
    refs = [policy_ref, *inputs['source_bindings']]
    result = dict(envelope, status=generated['status'], policy_binding=policy_ref,
        input_available_at=available.isoformat(), evaluated_at=evaluation_at.isoformat(),
        assumption_scope=policy['identity_class'], source_bindings=refs,
        product_source=product, rationale=policy['rationale'],
        hypothesis_rationales={name:row['rationale'] for name,row in policy['scenarios'].items()},
        annual_drivers=expanded, counter_evidence=policy['counter_evidence'],
        thesis_breakers=policy['thesis_breakers'], unknowns=policy['unknowns'],
        cash_conditions=policy['inherited_cash_conditions'],
        historical_ttm=generated['historical_ttm'],
        reference_allocation=generated['reference_allocation'])
    if generated['status'] == 'UNSUPPORTED':
        result.update(failure=generated['failure'], operating_rows=generated['operating_rows'])
    else:
        replay = replay_timing_delay_inputs(plan=ledger['plan'], scenarios=generated['scenarios'],
            history=ledger['history'], opening_book=str(facts.operating_inputs['start_book_equity']))
        if replay != generated['scenario_inputs']:
            raise ValueError('Product operating cash inputs differ from native replay')
        with localcontext() as context:
            context.prec = 48
            for name in ('bear', 'base', 'bull'):
                values = replay[name]
                scenario = ResidualIncomeScenarioInputs(
                    cost_of_equity=Decimal(values['cost_of_equity']),
                    forecast_roes=tuple(map(Decimal, values['forecast_roes'])),
                    terminal_roe=Decimal(values['terminal_roe']),
                    terminal_growth=Decimal(values['terminal_growth']), retention=Decimal(values['retention']))
                calculation = _shared_scenario_calculation(facts, scenario)
                challenged = _shared_scenario_calculation(facts,
                    replace(scenario, cost_of_equity=scenario.cost_of_equity+Decimal('.02')))
                case = generated['scenarios'][name]
                result['scenarios'].append(dict(scenario=name,
                    rationale=policy['scenarios'][name]['rationale'],
                    per_historical_share_cny=calculation['per_share_value'],
                    ke_plus_200bp_per_historical_share_cny=challenged['per_share_value'],
                    operating_rows=deepcopy(generated['operating_rows'][name]),
                    annual_cash_rows=deepcopy(case['annual_rows']),
                    native_scenario_inputs=values, terminal_profit=case['terminal_profit'],
                    cash_replay_scope='ALL_TRANSITIONS_VERIFIED_BY_EXISTING_NATIVE_KERNEL'))
        result['status'] = 'CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED'
        if _include_native_cases:
            result['native_cash_cases'] = deepcopy(generated['scenarios'])
    for ref in refs:
        target = require_inside(root, root/ref['path'], 'product operating source final read')
        if sha256_file(target) != ref['sha256']:
            raise ValueError('Product operating source changed during research')
    return result


def prepare_product_operating_candidate(*, root: Path, candidate_binding: dict,
                                        output_dir: Path, now: datetime | None = None) -> dict:
    """Freeze this research through the existing unsigned native intake contract."""
    from ..product.incremental_validity import read_bound_json
    from ..product.source_native_candidate_v2 import verify_source_native_candidate, prepare_source_native_candidate
    from ..product.source_bound_inputs import source_catalog_sha256
    from ...m1_valuation_package_builder import build_descriptor
    root = root.resolve()
    clock = now or datetime.now(timezone.utc)
    original = verify_source_native_candidate(root=root, path=root/candidate_binding['path'],
        expected_sha256=candidate_binding['sha256'], now=clock)
    _, package = read_bound_json(root, original['source_package_binding'], 'original product research package')
    _, old_ledger = read_bound_json(root, original['native_cash_ledger_binding'], 'original product research cash')
    descriptor = build_descriptor(package, root=root)
    research = build_product_operating_research(root=root, package=package, ledger=old_ledger,
        facts=descriptor.facts, evaluation_at=clock, _include_native_cases=True)
    if research['status'] != 'CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED':
        raise ValueError('Product research cannot create a candidate: '+research['status'])
    target = require_inside(root/'runtime', output_dir, 'product research candidate output')
    if target.exists():
        raise FileExistsError('Product operating candidate requires a new immutable directory')
    target.mkdir(parents=True)
    new_refs, new_sources = [], []
    def save(name, value, ident, raw=False):
        path = target/name
        if raw:
            write_new_bytes(path, value)
        else:
            write_new_json(path, value)
        ref = dict(id=ident, path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
        new_refs.append(ref)
        new_sources.append(dict(id=ident, kind='research_artifact', location=ref['path'], local_path=ref['path'],
            sha256=ref['sha256'], source_available_at=clock.isoformat(), retrieved_at=clock.isoformat(),
            parser_version='product-operating-research-v1',
            availability_basis='ACTUAL_NEW_RESEARCH_NOT_HISTORICAL_PIT'))
        return dict(path=ref['path'], sha256=ref['sha256'])
    policy = root/research['policy_binding']['path']
    policy_saved_ref = save('assumptions.json', policy.read_bytes(), 'product-operating-policy', raw=True)
    save('operating-research.json', {k:v for k,v in research.items() if k != 'native_cash_cases'},
         'product-operating-research')
    for name in ('application/research/product_operating_research.py',
                 'domain/valuation/operating_product_paths.py',
                 'infrastructure/filings/operating_erosion_sources.py'):
        path = root/'src/value_investment_agent'/name
        save(path.name, path.read_bytes(), 'product-operating-code-'+path.stem, raw=True)
    ledger = deepcopy(old_ledger)
    ledger['generated_at'] = clock.isoformat()
    ledger['cases'] = dict(TIMING_DELAY=research['native_cash_cases'])
    ledger['plan']['operating_states'] = 'Explicit product volume/realization/cost hypotheses; all cash states recomputed'
    ledger_ref = save('cash-ledger.json', ledger, 'product-operating-cash-ledger')
    package = deepcopy(package)
    version = package['symbol']+'-product-operating-'+clock.strftime('%Y%m%dT%H%M%S%fZ')
    package.update(package_version=version, descriptor_version=version, run_id=version, quote=None)
    day = clock.astimezone(timezone(timedelta(hours=8))).date().isoformat()
    package['point_in_time'].update(available_at=clock.isoformat(), computed_at=clock.isoformat(), research_as_of=day)
    package['research_case']['as_of'] = day
    package['sources'] += new_sources
    package['source_contract']['cutoff_at'] = clock.isoformat()
    package['source_contract']['source_catalog_sha256'] = source_catalog_sha256(package['sources'])
    package['facts']['scenario_inputs'] = {row['scenario']:row['native_scenario_inputs'] for row in research['scenarios']}
    package['facts']['evidence_refs'] += new_refs
    package['research_case']['evidence_refs'] += new_refs
    declaration = package['research_case']['financial_summary']['js2_economic_review']
    declaration.update(source_result_sha256=ledger_ref['sha256'], joint_assumptions=ledger['plan'],
        historical_cash_bridge=ledger['history'], scope='CONDITIONAL_RESEARCH_NOT_G3', branch='TIMING_DELAY',
        five_groups={key:'PENDING_FORMAL_REVIEW' for key in declaration['five_groups']})
    package['research_case']['financial_summary']['product_operating_research'] = dict(
        policy_binding=policy_saved_ref, assumption_scope=research['assumption_scope'],
        reference_allocation=research['reference_allocation'], counter_evidence=research['counter_evidence'],
        thesis_breakers=research['thesis_breakers'], normalized_parent_profit_cny=None)
    for assumption in package['assumptions']['assumptions']:
        for scenario in ('bear', 'base', 'bull'):
            value = package['facts']['scenario_inputs'][scenario]
            field = assumption['name']
            assumption[scenario] = value['forecast_roes'][int(field.rsplit('_', 1)[1])] if field.startswith('forecast_roes_') else value[field]
        assumption['evidence_refs'] += new_refs
        assumption.update(basis='SOURCE_BOUND_PRODUCT_OPERATING_RESEARCH_ASSUMPTION',
            rationale='Product volume/realization, costs, tax and parent cash jointly determine this scenario; not an issuer forecast.')
        values = [Decimal(assumption[name]) for name in ('bear', 'base', 'bull')]
        assumption['ordering'] = 'ascending' if values[0] <= values[1] <= values[2] else 'descending'
    for binding in package['assumption_bindings']:
        value = package['facts']['scenario_inputs'][binding['scenario']]
        for key in binding['field_path'].split('.'):
            value = value[int(key)] if isinstance(value, list) else value[key]
        binding['expected_value'] = value
        binding['evidence_refs'] += new_refs
    package_ref = save('package.json', package, 'product-operating-package')
    prepared = prepare_source_native_candidate(root=root, package_binding=package_ref,
        ledger_binding=ledger_ref, output_dir=target/'candidate', now=clock)
    verify_source_native_candidate(root=root, path=root/candidate_binding['path'],
        expected_sha256=candidate_binding['sha256'], now=clock)
    for ref in research['source_bindings']:
        if sha256_file(require_inside(root, root/ref['path'], 'product policy final identity')) != ref['sha256']:
            raise ValueError('Product operating source changed during candidate construction')
    return dict(status='PENDING_NATIVE_RESEARCH_NOT_APPROVED', action='no_order',
        candidate_binding=dict(path=(target/'candidate/candidate.json').relative_to(root).as_posix(),
                               sha256=sha256_file(target/'candidate/candidate.json')),
        candidate_valuation=prepared['candidate_valuation'], formal_eligibility=False,
        current_registry_changed=False, baseline_candidate_binding=deepcopy(candidate_binding))
