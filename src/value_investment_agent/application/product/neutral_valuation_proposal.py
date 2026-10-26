"""Review finite alternative earnings paths through the existing valuation model."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
import hashlib
from pathlib import Path

from .common import load_json_object, require_inside, sha256_file, write_new_json, encode_json_bytes
from .source_bound_inputs import verify_package_local_sources
from .financial_valuation_rebase import rebase_proposal_facts
from ...m1_valuation_package_builder import build_descriptor
from ...valuation_models.residual_income import (
    QualityCompounderFacts, ResidualIncomeEquityValuationModel,
    ResidualIncomeScenarioInputs, current_projection, _shared_scenario_calculation,
    valuation_time_factor,
)
from ...domain.valuation.joint_capital_path import HISTORICAL_FIELDS, compile_joint_capital_path


JOINT_SCHEMA = 'joint-capital-path-proposal-v1'
JOINT_CASH_SCHEMA = 'joint-capital-cash-path-proposal-v2'


def validate_proposal_policy_identity(*, policy, package, package_sha256, candidate_symbol=None):
    """Construction and readback must enforce the same no-order source identity."""
    if (policy.get('schema_version') not in ('finite-earnings-path-proposal-v1', JOINT_SCHEMA, JOINT_CASH_SCHEMA)
            or policy.get('action') != 'no_order' or policy.get('symbol') != package.get('symbol')
            or policy.get('source_package_sha256') != package_sha256
            or (candidate_symbol is not None and policy.get('symbol') != candidate_symbol)):
        raise ValueError('proposal policy identity/version mismatch')


def _json_numbers(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_numbers(item) for item in value]
    return value


def _joint_inputs(policy, package, sources, root):
    generated = datetime.fromisoformat(policy['generated_at'])
    if generated.utcoffset() is None or generated > datetime.now(timezone.utc):
        raise ValueError('joint proposal availability must be actual, aware and not future')
    if policy.get('assumption_scope') != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST':
        raise ValueError('joint proposal must explicitly declare research assumptions')
    catalog = {row['id']: row for row in package['sources']}
    for row in policy['rationale_bindings']:
        if row.get('id'):
            if row['id'] in catalog:
                raise ValueError('joint rationale source id conflicts with package source')
            catalog[row['id']] = dict(local_path=row['path'], sha256=row['sha256'])
    declared = policy['joint_historical']
    if not isinstance(declared, dict) or set(declared) != HISTORICAL_FIELDS:
        raise ValueError('joint historical inputs must be complete, not defaulted')
    values = {}
    for field, item in declared.items():
        scope = ('consolidated_parent' if field in ('parent_profit', 'nonrecurring')
                 else 'parent_cash_lookthrough_proxy' if field == 'cash' else 'consolidated')
        if (not isinstance(item, dict) or item.get('unit') != 'CNY' or item.get('scope') != scope
                or not isinstance(item.get('rationale'), str) or not item['rationale'].strip()
                or item.get('source_id') not in catalog):
            raise ValueError('joint historical unit/ownership/source/rationale mismatch: ' + field)
        source = catalog[item['source_id']]
        path = require_inside(root, root / source['local_path'], 'joint historical source')
        if sha256_file(path) != source['sha256']:
            raise ValueError('joint historical source hash mismatch')
        sources.append((path, source['sha256']))
        # Manual research declarations cannot masquerade as machine extraction.
        if 'field_path' in item:
            if (not isinstance(item['field_path'], list) or not item['field_path']
                    or any(not isinstance(key, str) for key in item['field_path'])):
                raise ValueError('joint extracted observation requires a concrete field path')
            node = load_json_object(path, 'joint extracted observation')
            for key in item['field_path']:
                node = node[key] if isinstance(node, dict) else node[int(key)]
            if (_profit_amount(node['value']) != _profit_amount(item['value'])
                    or node.get('unit') != item['unit'] or node.get('scope') != item['scope']):
                raise ValueError('joint historical extracted value/unit/scope mismatch')
        else:
            review = catalog.get(item.get('review_source_id'))
            if (item.get('mapping_basis') != 'MANUALLY_REVIEWED_DECLARATION_NOT_MACHINE_EXTRACTED'
                    or not review or item['review_source_id'] == item['source_id']):
                raise ValueError('joint manual mapping requires an explicit independent review source')
            review_path = require_inside(root, root / review['local_path'], 'joint historical review')
            if sha256_file(review_path) != review['sha256']:
                raise ValueError('joint historical review hash mismatch')
            sources.append((review_path, review['sha256']))
        values[field] = item['value']
    return values


def compile_joint_choice(*, choice, historical, book, anchor):
    """Same economic compiler for construction and read-only candidate replay."""
    if (set(choice) != {'id', 'rationale', 'countercase', 'joint_drivers', 'cost_of_equity'}
            or any(not isinstance(choice[key], str) or not choice[key].strip()
                   for key in ('id', 'rationale', 'countercase'))
            or set(choice['joint_drivers']) != {'bear', 'base', 'bull'}
            or set(choice['cost_of_equity']) != {'bear', 'base', 'bull'}):
        raise ValueError('joint choice requires explicit three-scenario drivers and rationale')
    scenarios, ledgers = {}, {}
    for name in ('bear', 'base', 'bull'):
        ledger = compile_joint_capital_path(start_book=book, profit_anchor=anchor,
            historical=historical, drivers=choice['joint_drivers'][name])
        if isinstance(choice['cost_of_equity'][name], (bool, float)):
            raise ValueError('joint cost requires an explicit decimal value')
        cost = _profit_amount(choice['cost_of_equity'][name])
        if not Decimal('0.01') <= cost <= Decimal('0.30') or cost <= ledger['terminal_growth']:
            raise ValueError('joint cost must exceed growth within explicit research bounds')
        scenarios[name] = ResidualIncomeScenarioInputs(cost, ledger['forecast_roe'],
            ledger['terminal_roe'], ledger['terminal_growth'], ledger['retention'])
        ledgers[name] = _json_numbers(ledger)
    return scenarios, ledgers


_PROFIT_FIELDS = {
    'ttm_ex_nonrecurring_parent_profit_cny': ('consolidated_parent_profit_ex_nonrecurring', 'ex_nonrecurring_profit_cny'),
    'ttm_reported_parent_profit_cny': ('consolidated_parent_profit', 'reported_profit_cny'),
}


def _profit_amount(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('proposal earnings anchor has an invalid financial amount') from None
    if not result.is_finite():
        raise ValueError('proposal earnings anchor must be finite')
    return result


# V2 is an explicit successor; legacy finite/joint construction stays intact.
_JOINT_CASH_IMPLEMENTATIONS = (
    'src/value_investment_agent/domain/valuation/joint_capital_cash_path_v2.py',
    'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
    'src/value_investment_agent/valuation_models/residual_income_path_v2.py',
    'src/value_investment_agent/valuation_models/residual_income.py',
)


def _cash_keys(value, fields, label):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError('Exact joint cash ' + label + ' fields required')


def _cash_available(value, cutoff):
    if not isinstance(value, str):
        raise ValueError('Joint cash availability requires an aware timestamp')
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > cutoff:
        raise ValueError('Joint cash source/policy is not yet available')
    return stamp


def _cash_node(binding, catalog, root, sources):
    _cash_keys(binding, 'source_id field_path', 'source binding')
    keys = binding['field_path']
    if (type(binding['source_id']) is not str or binding['source_id'] not in catalog
            or type(keys) is not list or not keys
            or any(type(key) is not str or not key for key in keys)):
        raise ValueError('Joint cash requires a concrete bound JSON field path')
    source = catalog[binding['source_id']]
    path = require_inside(root, root / source['local_path'], 'joint cash observation')
    if sha256_file(path) != source['sha256']:
        raise ValueError('Joint cash observation hash mismatch')
    sources.append((path, source['sha256']))
    node = load_json_object(path, 'joint cash observation')
    try:
        for key in keys:
            node = node[key] if type(node) is dict else node[int(key)]
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ValueError('Joint cash source field path does not resolve') from error
    return node


def compile_joint_cash_choice(*, choice, historical, book):
    """Compile ten annual retentions without a scalar-retention approximation."""
    import re
    from ...domain.valuation.joint_capital_cash_path_v2 import compile_joint_capital_cash_path
    from ...valuation_models.residual_income_path_v2 import ResidualIncomePathScenarioInputs

    _cash_keys(choice, 'id rationale countercase joint_drivers terminal_policy cost_of_equity scenario_bindings', 'choice')
    for key in ('id', 'rationale', 'countercase'):
        if type(choice[key]) is not str or not choice[key].strip():
            raise ValueError('Joint cash choice requires identity and economic explanation')
    for key in ('joint_drivers', 'terminal_policy', 'cost_of_equity', 'scenario_bindings'):
        _cash_keys(choice[key], 'bear base bull', key)
    scenarios, ledgers = {}, {}
    with localcontext() as context:
        context.prec = 48
        for name in ('bear', 'base', 'bull'):
            # Domain validates exact annual/terminal fields and plain Decimal strings.
            ledger = compile_joint_capital_cash_path(start_book=str(book), historical=historical,
                drivers=choice['joint_drivers'][name], terminal_policy=choice['terminal_policy'][name])
            raw_cost = choice['cost_of_equity'][name]
            if type(raw_cost) is not str or re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', raw_cost) is None:
                raise ValueError('Joint cash cost requires a plain Decimal string')
            cost = _profit_amount(raw_cost)
            if not Decimal('0.01') <= cost <= Decimal('0.30') or cost <= ledger['terminal_growth']:
                raise ValueError('Joint cash cost must exceed terminal growth within research bounds')
            if (ledger['funding_status'] != 'FUNDED' or any(
                    row['funding_status'] != 'FUNDED' or row['funding_shortfall'] != 0
                    for row in [*ledger['rows'], ledger['terminal']])):
                raise ValueError('Joint cash funding shortfall cannot be valued')
            scenarios[name] = ResidualIncomePathScenarioInputs(cost_of_equity=cost,
                forecast_roes=ledger['forecast_roe'], forecast_retentions=ledger['forecast_retentions'],
                terminal_roe=ledger['terminal_roe'], terminal_growth=ledger['terminal_growth'])
            ledgers[name] = ledger
    return scenarios, ledgers


def _joint_cash_profit_anchor(historical, case, field):
    """Return the v2 source-bound ex-nonrecurring parent-profit anchor."""
    if type(field) is not str or field not in _PROFIT_FIELDS:
        raise ValueError('Joint cash earnings anchor requires a supported parent-profit field')
    with localcontext() as context:
        context.prec = 48
        nonrecurring = _profit_amount(historical['nonrecurring'])
        anchor = _profit_amount(historical['parent_profit']) - nonrecurring
        # The compiler excludes nonrecurring profit. A reported-profit label is
        # equivalent only when the bound nonrecurring adjustment is zero.
        if _PROFIT_FIELDS[field][0] == 'consolidated_parent_profit' and nonrecurring != 0:
            raise ValueError('Joint cash earnings anchor reported/ex-nonrecurring scope mismatch')
        declared_anchor = _profit_amount(case.financial_summary.get(field))
        if anchor <= 0 or declared_anchor <= 0:
            raise ValueError('Joint cash earnings anchor must be positive')
        if anchor != declared_anchor:
            raise ValueError('Joint cash history differs from the source-bound profit anchor')
    return anchor


def _build_joint_cash_proposal(*, root, package, policy, package_path, package_sha256,
                             policy_path, policy_sha256, output_path, report_path):
    """V2 policy contract: strict joint_historical observations and bound scenarios.

    Each numeric history field has value/unit/scope/source_id/field_path/rationale;
    scope/currency are the domain contract literals. Cash/capacity/floor use the
    owner-equivalent scope; profit/nonrecurring use consolidated_parent, and the
    remaining statement fields use consolidated. Rationale bindings additionally
    declare id and available_at. Every scenario binding resolves to the complete
    {drivers, terminal_policy, cost_of_equity} research node, not a price or ROE
    table. Financial rebases and preferences are not implicitly inherited.
    """
    from ...domain.valuation.joint_capital_cash_path_v2 import HISTORICAL_FIELDS as CASH_FIELDS, SCOPE
    from ...valuation_models.residual_income_path_v2 import ResidualIncomeContractDispatcher, scenario_calculation

    _cash_keys(policy, 'schema_version action symbol source_package_sha256 generated_at assumption_scope '
        'profit_anchor_field profit_basis rationale_bindings joint_historical choices economic_review_items assurance_limits', 'policy')
    validate_proposal_policy_identity(policy=policy, package=package, package_sha256=package_sha256)
    generated = _cash_available(policy['generated_at'], datetime.now(timezone.utc))
    if policy['assumption_scope'] != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST':
        raise ValueError('Joint cash inputs must remain research assumptions')
    if type(policy['profit_basis']) is not str or not policy['profit_basis'].strip():
        raise ValueError('Joint cash profit basis must be explicit')
    for key in ('economic_review_items', 'assurance_limits'):
        if (type(policy[key]) is not list or not policy[key]
                or any(type(v) is not str or not v.strip() for v in policy[key])):
            raise ValueError('Joint cash economic limits must be explicit')
    for key in ('available_at', 'computed_at'):
        _cash_available(package['point_in_time'][key], generated)
    sources = [(package_path, package_sha256), (policy_path, policy_sha256),
        *verify_package_local_sources(root, package)]
    # Freeze implementation identities before compiling, then recheck with all
    # other inputs after arithmetic. Never seal code drift as the executed version.
    implementations = []
    code_root = Path(__file__).resolve().parents[4]
    for relative in _JOINT_CASH_IMPLEMENTATIONS:
        path = require_inside(root, root / relative, 'joint cash implementation')
        digest = sha256_file(path)
        if digest != sha256_file(code_root / relative):
            raise ValueError('Joint cash implementation differs from executing code')
        implementations.append(dict(path=relative, sha256=digest))
        sources.append((path, digest))
    catalog = {row['id']: row for row in package['sources']}
    if len(catalog) != len(package['sources']):
        raise ValueError('Joint cash source IDs must be unique')
    bindings = policy['rationale_bindings']
    if type(bindings) is not list or not bindings:
        raise ValueError('Joint cash requires source-bound economic rationale')
    for binding in bindings:
        _cash_keys(binding, 'id path sha256 available_at', 'rationale binding')
        if type(binding['id']) is not str or not binding['id'].strip() or binding['id'] in catalog:
            raise ValueError('Joint cash rationale source ID collision')
        _cash_available(binding['available_at'], generated)
        relative = Path(binding['path'])
        path = require_inside(root, root / relative, 'joint cash rationale')
        if (relative.is_absolute() or path.relative_to(root).as_posix() != binding['path']
                or sha256_file(path) != binding['sha256']):
            raise ValueError('Joint cash rationale path/hash mismatch')
        catalog[binding['id']] = dict(local_path=binding['path'], sha256=binding['sha256'])
        sources.append((path, binding['sha256']))
    declared = policy['joint_historical']
    if type(declared) is not dict or set(declared) != CASH_FIELDS:
        raise ValueError('Exact joint cash historical fields required')
    if declared['scope'] != SCOPE or declared['currency'] != 'CNY':
        raise ValueError('Joint cash historical ownership/currency mismatch')
    historical = dict(scope=SCOPE, currency='CNY')
    for field in sorted(CASH_FIELDS - {'scope', 'currency'}):
        item = declared[field]
        _cash_keys(item, 'value unit scope source_id field_path rationale', 'historical observation')
        scope = ('consolidated_parent' if field in ('parent_profit', 'nonrecurring') else
            SCOPE if field in ('opening_cash', 'opening_distribution_capacity', 'cash_floor') else 'consolidated')
        if (item['unit'] != 'CNY' or item['scope'] != scope
                or type(item['rationale']) is not str or not item['rationale'].strip()):
            raise ValueError('Joint cash historical unit/scope/rationale mismatch')
        node = _cash_node({k:item[k] for k in ('source_id', 'field_path')}, catalog, root, sources)
        if (type(node) is not dict or any(type(node.get(k)) is not str or node[k] != item[k]
                for k in ('value', 'unit', 'scope'))):
            raise ValueError('Joint cash historical value/unit/scope differs from source')
        historical[field] = item['value']
    choices = policy['choices']
    if type(choices) is not list or not 1 <= len(choices) <= 3:
        raise ValueError('Joint cash requires one to three choices')
    descriptor = build_descriptor(package, root=root)
    facts, case = descriptor.facts, descriptor.research_case
    if not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs:
        raise ValueError('Joint cash requires registered equity facts')
    anchor = _joint_cash_profit_anchor(historical, case, policy['profit_anchor_field'])
    model = ResidualIncomeContractDispatcher()
    baseline = model.value(facts, case)
    if baseline.status != 'conditional_research_only':
        raise ValueError('Joint cash baseline is not usable conditional research')
    book, shares = (facts.operating_inputs[k] for k in ('start_book_equity', 'ordinary_shares'))
    rows, ids = [], set()
    for choice in choices:
        scenarios, ledgers = compile_joint_cash_choice(choice=choice, historical=historical, book=book)
        if choice['id'] in ids:
            raise ValueError('Joint cash choice IDs must be distinct')
        ids.add(choice['id'])
        for name in ('bear', 'base', 'bull'):
            node = _cash_node(choice['scenario_bindings'][name], catalog, root, sources)
            expected = dict(drivers=choice['joint_drivers'][name], terminal_policy=choice['terminal_policy'][name],
                cost_of_equity=choice['cost_of_equity'][name])
            # JSON identity preserves integer/bool/float distinctions (True == 1
            # in Python must not authenticate a different source year).
            if encode_json_bytes(node) != encode_json_bytes(expected):
                raise ValueError('Joint cash scenario differs from source-bound drivers/terminal/cost')
        proposed = replace(facts, scenario_inputs=scenarios, confidence='低', confidence_evidence=None)
        valuation = model.value(proposed, case)
        if valuation.status != 'conditional_research_only':
            raise ValueError('Joint cash valuation must remain conditional')
        annuals = {}
        with localcontext() as context:
            context.prec = 48
            for name, scenario in scenarios.items():
                arithmetic = scenario_calculation(proposed, scenario)
                ledger = ledgers[name]
                for actual, consumed in zip(ledger['rows'], arithmetic['forecast_years'], strict=True):
                    for left, right in (('opening_book', 'opening_book_equity_cny'),
                            ('profit', 'net_income_assumption_cny'), ('distribution', 'dividend_assumption_cny'),
                            ('closing_book', 'closing_book_equity_cny')):
                        if abs(actual[left] - Decimal(consumed[right])) > Decimal('0.01'):
                            raise ValueError('Joint cash annual RI and cash path differ')
                if abs(ledger['terminal_distribution'] - Decimal(arithmetic['terminal_first_dividend_cny'])) > Decimal('0.01'):
                    raise ValueError('Joint cash terminal RI and distribution differ')
                origin = Decimal(arithmetic.get('basis_origin_equity_value_cny', arithmetic['conditional_equity_value_cny']))
                ddm = sum(row['distribution'] / (1 + scenario.cost_of_equity) ** row['year'] for row in ledger['rows'])
                ddm += ledger['terminal_distribution'] / (scenario.cost_of_equity - scenario.terminal_growth) / (1 + scenario.cost_of_equity) ** 10
                if (abs(origin-ddm) > Decimal('0.01') or
                        Decimal(arithmetic['per_share_value']) != getattr(valuation, name + '_value')):
                    raise ValueError('Joint cash RI/distribution discounted values differ')
                arithmetic['cash_distribution_crosscheck'] = dict(scope='CONDITIONAL_RI_TERMINAL_CONTINUATION_NOT_LEGAL_CASH_PROOF',
                    basis_origin_ddm_cny=str(ddm), difference_cny=str(origin-ddm))
                annuals[name] = arithmetic
        actual_inputs = dict(start_book_equity=str(book), ordinary_shares=str(shares),
            profit_anchor=str(anchor), scenarios={name:dict(cost_of_equity=str(s.cost_of_equity),
                forecast_roe=list(map(str, s.forecast_roes)), forecast_retentions=list(map(str, s.forecast_retentions)),
                retention_contract='annual-retention-v2', currency=s.currency,
                terminal_roe=str(s.terminal_roe), terminal_growth=str(s.terminal_growth)) for name,s in scenarios.items()})
        rows.append(dict(**choice, status='NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW',
            valuation=json.loads(valuation.to_json()), actual_calculation_inputs=actual_inputs,
            calculation_inputs_sha256=hashlib.sha256(encode_json_bytes(actual_inputs)).hexdigest(),
            annual_arithmetic=annuals, joint_capital_ledgers=_json_numbers(ledgers), input_mode=JOINT_CASH_SCHEMA))
    result = dict(schema_version=JOINT_CASH_SCHEMA, input_mode=JOINT_CASH_SCHEMA, symbol=case.symbol,
        status='NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW', action='no_order',
        generated_at=datetime.now(timezone.utc).isoformat(), baseline_valuation=json.loads(baseline.to_json()),
        baseline_scope='PREDECESSOR_MODEL_COMPARISON_NOT_CURRENT_JOINT_PATH',
        source_descriptor_sha256=descriptor.input_sha256, joint_historical=declared, choices=rows,
        implementation_bindings=implementations, cash_funding_status='PASS',
        profit_basis=policy['profit_basis'], normalized_profit=None,
        economic_review_items=policy['economic_review_items'], assurance_limits=policy['assurance_limits'],
        assumptions_approved=False, g3_approved=False, model_validity_approved=False,
        price_admitted=False, research_date_advanced=False, decision_changed=False,
        position_guidance=None, canonical_written=False,
        source_bindings=[dict(path=p.relative_to(root).as_posix(), sha256=d) for p,d in sources])
    for path, digest in sources:
        if sha256_file(path) != digest:
            raise ValueError('Joint cash proposal source changed during calculation')
    write_new_json(output_path, result)
    with report_path.open('x', encoding='utf-8') as report:
        report.write('# 十年联结资本现金路径候选待审\n\n'
            '逐年留存与现金分配已消费；终端为条件RI延续，不证明法律分配能力。\n'
            'action=no_order；G3、价格和投资准入均未改变。\n')
    return result


def _profit_anchor(root: Path, package: dict, case, field: str) -> Decimal:
    if field not in _PROFIT_FIELDS or case.financial_summary.get(field) is None:
        raise ValueError('proposal earnings anchor requires a declared parent-profit financial field')
    anchor = _profit_amount(case.financial_summary[field])
    if anchor <= 0:
        raise ValueError('proposal earnings anchor must be positive and finite')
    scope, component = _PROFIT_FIELDS[field]
    catalog = {source['id']: source for source in package.get('sources', [])}
    declarations = [row for row in package.get('source_contract', {}).get('fact_anchors', [])
                    if row.get('field') == field]
    if declarations:
        if len(declarations) != 1:
            raise ValueError('proposal earnings anchor has ambiguous financial declarations')
        declaration = declarations[0]
        value = _profit_amount(declaration.get('source_value'))
        source = catalog.get(declaration.get('source_id'))
        if (declaration.get('unit') != 'CNY' or declaration.get('scope') != scope
                or value != anchor or not source or source.get('kind') != 'official_issuer_filing'
                or type(declaration.get('physical_page')) is not int or declaration['physical_page'] < 1
                or declaration.get('period_end') != package['point_in_time']['report_period']):
            raise ValueError('proposal earnings anchor financial unit/scope/source/value mismatch')
        return anchor

    # Existing TTM research declares currency and parent attribution per source row.
    reconciliation = case.financial_summary.get('historical_profit_reconciliation')
    if not isinstance(reconciliation, dict):
        raise ValueError('proposal earnings anchor lacks a financial unit/scope declaration')
    bound = [source for source in catalog.values()
             if source.get('kind') == 'research_artifact'
             and source.get('parser_version') == 'historical-profit-reconciliation-v1'
             and source.get('local_path') and Path(source['local_path']).suffix == '.json']
    if (len(bound) != 1 or reconciliation.get('symbol') != case.symbol
            or reconciliation.get('report_period') != package['point_in_time']['report_period']
            or reconciliation.get('formula') != 'FY2025 + H1_2026 - H1_2025'
            or _profit_amount(reconciliation.get(field)) != anchor):
        raise ValueError('proposal earnings anchor TTM declaration mismatch')
    bound_path = require_inside(root, root / bound[0]['local_path'], 'proposal profit reconciliation')
    if load_json_object(bound_path, 'profit reconciliation') != reconciliation:
        raise ValueError('proposal earnings anchor differs from bound TTM reconciliation')
    rows = reconciliation.get('source_rows', [])
    if len(rows) != 3 or {row.get('period') for row in rows} != {'FY2025', 'H1_2026', 'H1_2025'}:
        raise ValueError('proposal earnings anchor requires complete declared TTM components')
    amounts = {}
    for row in rows:
        source = catalog.get(row.get('source_id'))
        if (row.get('currency') != 'CNY' or row.get('statement_scope') != 'consolidated'
                or row.get('profit_basis') != 'attributable_to_parent' or not source
                or source.get('kind') != 'official_issuer_filing' or row.get('sha256') != source.get('sha256')):
            raise ValueError('proposal earnings anchor TTM financial unit/scope/source mismatch')
        amounts[row['period']] = _profit_amount(row.get(component))
    if amounts['FY2025'] + amounts['H1_2026'] - amounts['H1_2025'] != anchor:
        raise ValueError('proposal earnings anchor TTM components do not reconcile')
    return anchor


def build_neutral_valuation_proposal(*, root: Path, package_path: Path,
        package_sha256: str, policy_path: Path, policy_sha256: str,
        output_path: Path) -> dict:
    root = root.resolve()
    package_path = require_inside(root, package_path, 'proposal source package')
    policy_path = require_inside(root, policy_path, 'proposal policy')
    output_path = require_inside(root / 'runtime', output_path, 'proposal output')
    report_path = output_path.with_suffix('.md')
    if output_path.exists() or report_path.exists():
        raise FileExistsError('proposal output already exists')
    if sha256_file(package_path) != package_sha256 or sha256_file(policy_path) != policy_sha256:
        raise ValueError('proposal input hash mismatch')
    package = load_json_object(package_path, 'proposal package')
    policy = load_json_object(policy_path, 'proposal policy')
    if policy.get('schema_version') == JOINT_CASH_SCHEMA:
        return _build_joint_cash_proposal(root=root, package=package, policy=policy,
            package_path=package_path, package_sha256=package_sha256,
            policy_path=policy_path, policy_sha256=policy_sha256,
            output_path=output_path, report_path=report_path)
    joint = policy.get('schema_version') == JOINT_SCHEMA
    validate_proposal_policy_identity(policy=policy, package=package, package_sha256=package_sha256)
    sources = [(package_path, package_sha256), (policy_path, policy_sha256),
               *verify_package_local_sources(root, package)]
    for binding in policy.get('rationale_bindings', []):
        path = require_inside(root, root / binding['path'], 'proposal rationale')
        if sha256_file(path) != binding['sha256']:
            raise ValueError('proposal rationale hash mismatch')
        sources.append((path, binding['sha256']))
    if not policy.get('rationale_bindings'):
        raise ValueError('proposal requires independently reviewable economic rationale')
    historical = _joint_inputs(policy, package, sources, root) if joint else None
    implementation_bindings = []
    if joint:
        for relative in (
                'src/value_investment_agent/domain/valuation/joint_capital_path.py',
                'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
                'src/value_investment_agent/valuation_models/residual_income.py'):
            path = require_inside(root, root / relative, 'joint implementation')
            digest = sha256_file(path)
            if relative != 'src/value_investment_agent/valuation_models/residual_income.py':
                implementation_bindings.append(dict(path=relative, sha256=digest))
            sources.append((path, digest))
    descriptor = build_descriptor(package, root=root)
    facts, case = descriptor.facts, descriptor.research_case
    if not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs:
        raise ValueError('proposal requires the existing registered equity model inputs')
    anchor_field = policy.get('profit_anchor_field')
    if not isinstance(anchor_field, str):
        raise ValueError('proposal earnings anchor requires a declared parent-profit financial field')
    model = ResidualIncomeEquityValuationModel()
    baseline = model.value(facts, case)
    rebase = None
    if policy.get('financial_rebase') is not None:
        facts, anchor, bindings, rebase = rebase_proposal_facts(
            root=root, symbol=case.symbol, facts=facts, policy=policy)
        sources.extend(bindings)
    else:
        anchor = _profit_anchor(root, package, case, anchor_field)
    choices = policy.get('choices')
    if (not isinstance(choices, list) or not 1 <= len(choices) <= 3
            or len({row['id'] for row in choices}) != len(choices)):
        raise ValueError('proposal requires one to three distinct economic choices')
    growths = policy.get('income_growth')
    if not joint and (not isinstance(growths, dict) or set(growths) != {'bear', 'base', 'bull'}):
        raise ValueError('proposal requires explicit three-scenario earnings conditions')
    if baseline.status != 'conditional_research_only':
        raise ValueError('proposal baseline is not a usable conditional calculation')
    book, shares = facts.operating_inputs['start_book_equity'], facts.operating_inputs['ordinary_shares']
    rows = []
    for choice in choices:
        joint_ledgers = {}
        if joint:
            scenarios, joint_ledgers = compile_joint_choice(choice=choice,
                historical=historical, book=book, anchor=anchor)
        else:
            years, fade = choice['growth_years'], choice['fade_years']
            if (type(years) is not int or type(fade) is not int or not 1 <= years <= 20
                or not 1 <= fade <= 20 or not choice.get('rationale') or not choice.get('countercase')):
                raise ValueError('proposal choice requires bounded duration, rationale and countercase')
            scenarios = {}
            for name, original in facts.scenario_inputs.items():
                growth = Decimal(str(growths[name]))
                if not growth.is_finite() or not Decimal('-0.10') <= growth <= Decimal('0.10'):
                    raise ValueError('proposal growth exceeds the registered research bounds')
                if rebase is not None:
                    condition = policy['scenario_conditions'][name]
                    cost = _profit_amount(condition['cost_of_equity'])
                    retention = _profit_amount(condition['retention'])
                    terminal_growth = _profit_amount(condition['terminal_growth'])
                    if not Decimal('0.08') <= cost <= Decimal('0.12') or not Decimal('0.10') <= retention <= Decimal('0.25'):
                        raise ValueError('proposal explicit cost/retention exceeds finite research bounds')
                    original = ResidualIncomeScenarioInputs(cost, original.forecast_roes,
                        cost, terminal_growth, retention)
                scenarios[name] = ResidualIncomeScenarioInputs(
                    cost_of_equity=original.cost_of_equity,
                    forecast_roes=tuple(current_projection(book, anchor, original.cost_of_equity,
                        growth, 1 - original.retention, years, fade)),
                    terminal_roe=original.terminal_roe, terminal_growth=original.terminal_growth,
                    retention=original.retention)
        proposed = replace(facts, scenario_inputs=scenarios, confidence='低', confidence_evidence=None)
        valuation = model.value(proposed, case)
        annuals, actual_inputs = {}, {}
        for name, scenario in scenarios.items():
            actual_inputs[name] = dict(cost_of_equity=str(scenario.cost_of_equity),
                forecast_roe=[str(value) for value in scenario.forecast_roes],
                terminal_roe=str(scenario.terminal_roe), terminal_growth=str(scenario.terminal_growth),
                retention=str(scenario.retention))
            arithmetic = _shared_scenario_calculation(proposed, scenario)
            timing = facts.valuation_timing
            with localcontext() as context:
                context.prec = 48
                elapsed, factor = ((Decimal(0), Decimal(1)) if timing is None else
                    valuation_time_factor(scenario.cost_of_equity, timing.basis_at, timing.valuation_at))
                origin = Decimal(arithmetic.get('basis_origin_equity_value_cny',
                                               arithmetic['conditional_equity_value_cny']))
                dated = Decimal(arithmetic['conditional_equity_value_cny'])
                per_share = Decimal(arithmetic['per_share_value'])
                model_per_share = getattr(valuation, f'{name}_value')
                if (per_share != model_per_share
                        or abs(origin * factor - dated) > Decimal('0.01')):
                    raise ValueError('proposal annual arithmetic/date bridge differs from shared valuation')
                arithmetic['date_bridge'] = dict(
                    scope='conditional_timing_transport_not_observed_equity_or_approval',
                    basis_at=None if timing is None else timing.basis_at.isoformat(),
                    valuation_at=None if timing is None else timing.valuation_at.isoformat(),
                    fractional_first_year_elapsed=str(elapsed), basis_to_valuation_factor=str(factor),
                    basis_origin_equity_value_cny=str(origin),
                    basis_origin_per_share_cny=str(per_share if timing is None else origin / shares),
                    valuation_date_equity_value_cny=str(dated), valuation_date_per_share_cny=str(per_share),
                    equity_transport_difference_cny=str(origin * factor - dated),
                    model_per_share_difference_cny=str(per_share - model_per_share))
            arithmetic['annual_schedule_scope'] = 'basis_origin_annual_cash_flows_not_valuation_date_present_values'
            annuals[name] = arithmetic
        inputs = dict(start_book_equity=str(book), ordinary_shares=str(shares),
            profit_anchor=str(anchor), profit_anchor_field=anchor_field, profit_anchor_unit='CNY',
            profit_anchor_scope=_PROFIT_FIELDS[anchor_field][0], scenarios=actual_inputs,
            valuation_timing=None if facts.valuation_timing is None else facts.valuation_timing.as_policy())
        rows.append(dict(**choice, status='NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW',
            valuation=json.loads(valuation.to_json()), actual_calculation_inputs=inputs,
            calculation_inputs_sha256=hashlib.sha256(encode_json_bytes(inputs)).hexdigest(),
            annual_arithmetic=annuals,
            base_difference_from_old_pressure=str(valuation.base_value - baseline.base_value)))
        if joint:
            rows[-1]['joint_capital_ledgers'] = joint_ledgers
            rows[-1]['input_mode'] = JOINT_SCHEMA
    preference = policy.get('research_preference')
    if preference is not None:
        if (not isinstance(preference, dict)
                or preference.get('choice_id') not in {choice['id'] for choice in rows}
                or preference.get('scope') != 'INDEPENDENT_RESEARCH_HYPOTHESIS_NOT_APPROVAL'
                or preference.get('confidence') != '低'
                or not all(isinstance(preference.get(key), str) and preference[key].strip()
                           for key in ('reason', 'countercase'))
                or not isinstance(preference.get('reopen_triggers'), list)
                or not preference['reopen_triggers']
                or not all(isinstance(item, str) and item.strip() for item in preference['reopen_triggers'])):
            raise ValueError('research preference must be a bounded unapproved existing hypothesis')
    result = dict(schema_version='finite-neutral-valuation-proposal-v1', symbol=case.symbol,
        status='NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW', action='no_order',
        generated_at=datetime.now(timezone.utc).isoformat(),
        original_research_as_of=case.as_of.isoformat(),
        original_valuation_date=baseline.valuation_date.isoformat(),
        date_semantics='New proposal computed now on retained financial/date basis; not a contemporaneous historical or current admitted valuation.',
        source_descriptor_sha256=descriptor.input_sha256,
        baseline_valuation=json.loads(baseline.to_json()), choices=rows,
        research_preference=preference,
        financial_rebase=rebase,
        profit_basis=policy['profit_basis'], normalized_profit=None,
        economic_review_items=policy['economic_review_items'],
        assurance_limits=policy['assurance_limits'],
        assumptions_approved=False, g3_approved=False, model_validity_approved=False,
        price_admitted=False, research_date_advanced=False, decision_changed=False,
        position_guidance=None, canonical_written=False,
        source_bindings=[dict(path=p.relative_to(root).as_posix(), sha256=d) for p, d in sources])
    for path, digest in sources:
        if sha256_file(path) != digest:
            raise ValueError('proposal source changed during calculation')
    if joint:
        result.update(input_mode=JOINT_SCHEMA, implementation_bindings=implementation_bindings,
            historical_input_scope='SOURCE_LINKED_RESEARCH_INPUT_NOT_PDF_CERTIFICATION',
            joint_historical=policy['joint_historical'],
            cash_funding_status=('FAIL' if any(ledger['cash_funding_status'] == 'FAIL'
                for row in rows for ledger in row['joint_capital_ledgers'].values()) else 'PASS'),
            baseline_scope='PREDECESSOR_MODEL_COMPARISON_NOT_CURRENT_JOINT_PATH',
            predecessor_research_version=package.get('package_version') or ('package-sha256:' + package_sha256))
    anchor_label = ('历史扣非归母盈利代理' if anchor_field == 'ttm_ex_nonrecurring_parent_profit_cny'
                    else '历史报告归母盈利代理')
    lines = [f'# {case.name}：主估值候选待审', '',
        '以下是同一剩余收益模型的条件研究备选，不是批准公允价值或买点。', '',
        f'{anchor_label}：{anchor / Decimal("100000000"):.2f}亿元；正常化盈利仍未确认。',
        f'原研究截止：{case.as_of}；新提案生成：{result["generated_at"]}。没有推进事件或价格准入。', '',
        '| 尾部选择 | 条件低档/中档/高档（元/股） | 中档相对旧压力 |', '| --- | --- | --- |']
    if joint:
        lines[-2] = '| 联结资本方案 | 条件低档/中档/高档（元/股） | 中档相对前版本 |'
        lines.insert(6, f'历史比较基线仅指前版本 {result["predecessor_research_version"]}，不描述当前joint模型。')
    for row in rows:
        value = row['valuation']
        label = ('五年联结资本路径＋持续经营终端' if joint else
                 f'{row["growth_years"]}年盈利段＋{row["fade_years"]}年全资本衰减')
        lines.append(f'| {row["id"]}：{label} | '
            + ' / '.join(f'{Decimal(value[key]):.2f}' for key in ('bear_value', 'base_value', 'bull_value'))
            + f' | {Decimal(row["base_difference_from_old_pressure"]):+.2f} |')
    lines.extend(['', '逐年明细保留财务基准日口径；日期桥按同一共享模型换算至估值日，不代表净资产已更新。', '',
        '| 尾部选择（中档） | 基准日价值（元/股） | 日期因子 | 估值日价值（元/股） | 模型差额 |',
        '| --- | --- | --- | --- | --- |'])
    for row in rows:
        bridge = row['annual_arithmetic']['base']['date_bridge']
        lines.append(f'| {row["id"]} | {Decimal(bridge["basis_origin_per_share_cny"]):.4f} | '
            f'{Decimal(bridge["basis_to_valuation_factor"]):.8f} | '
            f'{Decimal(bridge["valuation_date_per_share_cny"]):.4f} | {bridge["model_per_share_difference_cny"]} |')
    for row in rows:
        lines.extend(['', f'{row["id"]}经济依据：{row["rationale"]}', f'反面风险：{row["countercase"]}', ''])
        if joint:
            lines.extend(['五年联结路径为研究假设，不是正常化财务事实；母公司现金转换与终端资本效率仍待审。',
                '| 情景 | 条件现金资金检验 | 终端ROE假设 | 终端留存率 |', '| --- | --- | --- | --- |'])
            for name, ledger in row['joint_capital_ledgers'].items():
                lines.append(f'| {name} | {ledger["cash_funding_status"]} | '
                    f'{ledger["terminal_roe"]} | {ledger["terminal_retention"]} |')
    if rebase is not None:
        lines.extend(['## 本次真正消费的财报输入', '',
            f'归母权益：{book}元；披露总股数：{shares}股；财务基准日：{rebase["start_book_equity"]["period_end"]}。',
            '首个预测付款期为财务基准日之后一个完整年度，不是财年全年预测。',
            *[f'- {item}' for item in rebase['limitations']], '',
            '| 条件 | 权益成本 | 留存率 | 终值ROE | 终值增长 |',
            '| --- | --- | --- | --- | --- |'])
        for name, condition in rows[0]['actual_calculation_inputs']['scenarios'].items():
            lines.append(f'| {name} | {condition["cost_of_equity"]} | {condition["retention"]} | '
                f'{condition["terminal_roe"]} | {condition["terminal_growth"]} |')
        bridge = rebase.get('equity_bridge_result')
        if bridge:
            lines.extend(['', '## 历史归母权益对账：已勾稽，未来模型仍待审', '',
                f'期末归母权益：{bridge["reconciled_closing_parent_equity_cny"]}元；未解释差额：{bridge["unexplained_difference_cny"]}元。',
                f'只计利润和分红的权益：{bridge["naive_profit_distribution_equity_cny"]}元；'
                f'OCI及资本等调整：{bridge["outside_profit_adjustment_cny"]}元。',
                '对账使用报告归母利润而非扣非TTM；不把OCI损失加回盈利或股权价值。',
                '历史会计对账不证明未来无OCI/资本变动，也不证明现金可持续分配。'])
    if preference:
        lines.extend(['## 独立研究优先假设', '',
            f"- {preference['choice_id']}；低置信，未批准。{preference['reason']}",
            f"- 最强反证：{preference['countercase']}",
            *[f'- 重开条件：{item}' for item in preference['reopen_triggers']], ''])
    lines.extend(['## 真正需要审阅的经济选择', '', *[f'- {item}' for item in result['economic_review_items']],
        '', '## 尚未证明', '', *[f'- {item}' for item in result['assurance_limits']], '',
        '逐年权益、盈利、留存、分配、终端和Hash见同名JSON，使用已有共享模型精确复算。',
        '派息路径对账仅证明代数一致，不证明上市母公司能持续派息。', '', '## 证据', ''])
    lines.extend(f'- {row["path"]}；SHA-256={row["sha256"]}' for row in result['source_bindings'])
    lines.extend(['', 'action=no_order；正式研究、重大性及G3审批均未改变。', ''])
    write_new_json(output_path, result)
    with report_path.open('x', encoding='utf-8') as report:
        report.write('\n'.join(lines))
    return result
