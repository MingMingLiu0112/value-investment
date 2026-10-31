"""One source-bound replacement bear, using existing native cash/RI contracts."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D, localcontext
import json
from pathlib import Path

from ..product.common import require_inside, sha256_file, write_new_json, write_new_bytes
from ..product.incremental_validity import read_bound_json
from ..product.source_native_candidate_v2 import verify_source_native_candidate, prepare_source_native_candidate
from ..product.source_bound_inputs import source_catalog_sha256
from ...domain.valuation.operating_realization_erosion_v1 import FIELDS, build_erosion_bear
from ...domain.valuation import operating_realization_erosion_v1 as operating
from .operating_earnings_bridge import extract_statement
from ...infrastructure.filings import operating_erosion_sources as source_provider


NEGATIVE_CONDITIONS = [
    'Mixed wine revenue/volume changes include product/channel mix; not a pure selling price.',
    'Repeating the rounded disclosed proxy five times is an assumption, not an issuer forecast.',
    'H1 cost ratio persisting for full future years ignores possible seasonality/recovery.',
    'Historical effective tax, parent attribution and residual finance contribution may change.',
    'Cash recovery, maintenance, statutory reserves or terminal full payout may fail.',
    'This alternative is not comprehensive downside, a probability bound or a trading price.',
]


def _plain(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False, allow_nan=False))


def build_source_native_operating_erosion(*, root: Path, candidate_binding: dict,
                                        output_dir: Path, now: datetime | None = None) -> dict:
    """Create immutable input/candidate only; never sign/register/advance current.

    Root must already retain the exact input closure. No network/archive fallback
    or .tmp imports. Existing base/bull scenario values and cash rows are intact.
    """
    root = root.resolve()
    clock = now or datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError('Aware observation clock required')
    candidate_binding = deepcopy(candidate_binding)
    candidate = verify_source_native_candidate(root=root, path=root/candidate_binding['path'],
        expected_sha256=candidate_binding['sha256'], now=clock)
    if datetime.fromisoformat(candidate['generated_at']) > clock:
        raise ValueError('This bounded input version requires an available native candidate')
    refs = [candidate_binding, *candidate['source_bindings']]
    closure = {}
    for ref in refs:
        if ref['path'] in closure and closure[ref['path']] != ref['sha256']:
            raise ValueError('Conflicting original closure bindings')
        closure[ref['path']] = ref['sha256']
    implementations = [Path(__file__), Path(operating.__file__), Path(source_provider.__file__)]
    code = {path: sha256_file(path) for path in implementations}
    def recheck():
        for path, digest in closure.items():
            target = require_inside(root, root/path, 'operating erosion original')
            if target.relative_to(root).as_posix() != path or sha256_file(target) != digest:
                raise ValueError('Original source closure drift')
        if any(sha256_file(path) != digest for path, digest in code.items()):
            raise ValueError('Operating implementation drift')
    recheck()
    _, old_package = read_bound_json(root, candidate['source_package_binding'], 'original native package')
    _, ledger = read_bound_json(root, candidate['native_cash_ledger_binding'], 'original native ledger')
    source_inputs = source_provider.read_operating_erosion_sources(root=root, symbol=candidate['symbol'],
        sources=old_package['sources'], fields=FIELDS)
    specs = source_inputs['specs']
    if any(closure.get(ref['path']) != ref['sha256'] for ref in source_inputs['source_bindings']):
        raise ValueError('Official statement outside original bound closure')
    statements = [extract_statement(root=root, spec=spec) for spec in specs]
    proxy = source_inputs['mixed_proxy']
    revenue_pct, volume_pct = proxy['revenue_yoy_pct'], proxy['volume_yoy_pct']
    # Parsing belongs to the same strict Decimal contract as the pure kernel.
    D(revenue_pct), D(volume_pct)
    original_scenarios = deepcopy(old_package['facts']['scenario_inputs'])
    generated = build_erosion_bear(annual={k: statements[0]['rows'][k]['values'] for k in FIELDS},
        interim={k: statements[1]['rows'][k]['values'] for k in FIELDS},
        wine_revenue_yoy_pct=revenue_pct, wine_volume_yoy_pct=volume_pct,
        ledger=ledger, opening_book=old_package['facts']['operating_inputs']['start_book_equity'])
    recheck()
    if generated['status'] == 'UNSUPPORTED':
        return _plain(dict(status='UNSUPPORTED', failure=generated['failure'],
            operating_rows=generated['operating_rows'], annual_rows=generated['annual_rows'],
            observed_at=clock.isoformat(), negative_conditions=NEGATIVE_CONDITIONS,
            candidate_created=False, source_bindings=refs, action='no_order'))
    with localcontext() as ctx:
        ctx.prec = 48
        anchor = D(generated['historical_ttm']['ex_parent_profit'])
        inherited_anchor = D(old_package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'])
        if anchor != inherited_anchor:
            raise ValueError('Official profit reconstruction differs from inherited anchor')
    target = require_inside(root/'runtime', output_dir, 'new operating input version')
    if target.exists():
        raise FileExistsError('Operating input version must be new')
    target.mkdir(parents=True)
    new_sources, new_refs = [], []
    def artifact(name, payload, ident, raw=False):
        path = target/name
        if raw: write_new_bytes(path, payload)
        else: write_new_json(path, _plain(payload))
        ref = dict(id=ident, path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
        new_refs.append(ref)
        new_sources.append(dict(id=ident, kind='research_artifact', location=ref['path'], local_path=ref['path'],
            sha256=ref['sha256'], source_available_at=clock.isoformat(), retrieved_at=clock.isoformat(),
            parser_version='operating-realization-erosion-v1', availability_basis='ACTUAL_NEW_RESEARCH_NOT_HISTORICAL_PIT'))
        return dict(path=ref['path'], sha256=ref['sha256'])
    for path in implementations:
        artifact(path.name, path.read_bytes(), 'erosion-code-'+path.stem, raw=True)
    evidence = dict(schema_version='source-native-operating-input-v1', symbol=candidate['symbol'],
        observed_at=clock.isoformat(), historical_statement_facts=statements,
        mixed_proxy=deepcopy(proxy),
        derived_historical_ratios=dict(identity_class='DERIVED_FROM_SOURCE_FACTS_NOT_FORECAST',
            mixed_realization_factor=generated['mixed_realization_factor'],
            h1_cost_ratio=generated['h1_cost_ratio']),
        research_assumptions=dict(repeat_mixed_proxy_years=5, h1_cost_ratio_from_year_one=True,
            cash_policy='UNCHANGED_JS2_TIMING_DELAY', negative_conditions=NEGATIVE_CONDITIONS),
        unknown=dict(normalized_profit=None, future_realized_prices=None, seasonality_adjustment=None,
                     tax_parent_attribution_changes=None, full_downside_bound=None),
        operating_rows=generated['operating_rows'], action='no_order')
    evidence['parameter_metadata'] = {
        'disclosed_wine_changes': dict(identity='SOURCE_FACT', observed_at=clock.isoformat(),
            source_binding=evidence['mixed_proxy']['source_binding'],
            negative_conditions=[NEGATIVE_CONDITIONS[0]]),
        'mixed_proxy_and_cost_ratio': dict(identity='DERIVED', observed_at=clock.isoformat(),
            source_bindings=specs, negative_conditions=NEGATIVE_CONDITIONS[:3]),
        'five_year_operating_path': dict(identity='RESEARCH_ASSUMPTION', observed_at=clock.isoformat(),
            source_binding=candidate['native_cash_ledger_binding'],
            mechanism='R_t=R_TTM*proxy**t; H1 cost ratio from t=1; other TTM ratios/residuals held',
            negative_conditions=NEGATIVE_CONDITIONS),
        'cash_equity_and_terminal_policy': dict(identity='INHERITED_RESEARCH_ASSUMPTION',
            observed_at=clock.isoformat(), source_binding=candidate['native_cash_ledger_binding'],
            negative_conditions=NEGATIVE_CONDITIONS[3:]),
        'unverified_future_quantities': dict(identity='UNKNOWN', observed_at=clock.isoformat(),
            fields=list(evidence['unknown']), negative_conditions=NEGATIVE_CONDITIONS),
    }
    artifact('operating-inputs.json', evidence, 'erosion-operating-inputs')
    new_ledger = dict(action='no_order', financial_basis=ledger['financial_basis'], generated_at=clock.isoformat(),
        plan=deepcopy(ledger['plan']), history=deepcopy(ledger['history']),
        cases=dict(TIMING_DELAY=generated['scenarios']))
    new_ledger['plan']['operating_states'] = 'Versioned compounded mixed-realization erosion bear; exact original base/bull'
    ledger_ref = artifact('cash-ledger.json', new_ledger, 'erosion-cash-ledger')
    package = deepcopy(old_package)
    version = candidate['symbol']+'-operating-realization-erosion-v1-'+clock.strftime('%Y%m%dT%H%M%S%fZ')
    package.update(package_version=version, descriptor_version=version, run_id=version, quote=None)
    research_day = clock.astimezone(timezone(timedelta(hours=8))).date().isoformat()
    package['point_in_time'].update(available_at=clock.isoformat(), computed_at=clock.isoformat(),
                                  research_as_of=research_day)
    package['research_case']['as_of'] = research_day
    package['sources'] += new_sources
    package['source_contract']['cutoff_at'] = clock.isoformat()
    package['source_contract']['source_catalog_sha256'] = source_catalog_sha256(package['sources'])
    package['facts']['scenario_inputs']['bear'] = generated['scenario_inputs']['bear']
    for name in ('base', 'bull'):
        assert package['facts']['scenario_inputs'][name] == original_scenarios[name]
        assert new_ledger['cases']['TIMING_DELAY'][name] == ledger['cases']['TIMING_DELAY'][name]
    declaration = package['research_case']['financial_summary']['js2_economic_review']
    declaration.update(source_result_sha256=ledger_ref['sha256'], joint_assumptions=new_ledger['plan'],
        historical_cash_bridge=new_ledger['history'], scope='CONDITIONAL_RESEARCH_NOT_G3', branch='TIMING_DELAY',
        five_groups={key:'PENDING_FORMAL_REVIEW' for key in declaration['five_groups']})
    package['facts']['evidence_refs'] += new_refs
    package['research_case']['evidence_refs'] += new_refs
    for item in package['assumptions']['assumptions']:
        name = item['name']
        value = package['facts']['scenario_inputs']['bear']
        item['bear'] = value['forecast_roes'][int(name.rsplit('_', 1)[1])] if name.startswith('forecast_roes_') else value[name]
        item['evidence_refs'] += new_refs
        item['basis'] = 'SOURCE_BOUND_OPERATING_EROSION_ASSUMPTION_NOT_FORECAST'
        item['rationale'] = 'Bear compounds the mixed proxy five times; H1 costs persist from year one. Base/bull unchanged. '+NEGATIVE_CONDITIONS[0]
        nums = [D(item[key]) for key in ('bear', 'base', 'bull')]
        item['ordering'] = 'ascending' if nums[0] <= nums[1] <= nums[2] else 'descending'
    for binding in package['assumption_bindings']:
        if binding['scenario'] == 'bear':
            value = package['facts']['scenario_inputs']['bear']
            for key in binding['field_path'].split('.'):
                value = value[int(key)] if isinstance(value, list) else value[key]
            binding['expected_value'] = value
            binding['evidence_refs'] += new_refs
    package_ref = artifact('package.json', package, 'erosion-package')
    recheck()
    prepared = prepare_source_native_candidate(root=root, package_binding=package_ref, ledger_binding=ledger_ref,
        output_dir=target/'candidate', now=clock)
    recheck()
    return dict(status='PENDING_NATIVE_RESEARCH_CANDIDATE_NOT_APPROVED', symbol=candidate['symbol'],
        observed_at=clock.isoformat(), source_package_binding=package_ref, native_cash_ledger_binding=ledger_ref,
        candidate_binding=dict(path=(target/'candidate/candidate.json').relative_to(root).as_posix(),
                               sha256=sha256_file(target/'candidate/candidate.json')),
        candidate_valuation=prepared['candidate_valuation'], base_bull_exactly_preserved=True,
        negative_conditions=NEGATIVE_CONDITIONS, normalized_parent_profit_cny=None,
        formal_eligibility=False, price_admitted=False, current_registry_changed=False, action='no_order')
