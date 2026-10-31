"""First v4 input compilation, without a predecessor, registration or approval.

Financial numbers come exclusively from the injected/server-owned cold PDF replay.
The source manifest's `verified`/PASS fields are never admission credentials.
This module only assembles existing contracts; it owns no financial formulas.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from ..product.common import encode_json_bytes, require_inside, write_new_bytes
from ..product.neutral_valuation_proposal import compile_joint_cash_choice_v4, _json_numbers
from ..product.source_bound_inputs import source_catalog_sha256
from ...domain.valuation.joint_capital_cash_path_v4 import HISTORICAL_FIELDS, SCOPE
from ...research_input import build_research_run_spec
from ...research_application import ResearchApplicationService
from .v4_input_adapter import build_v4_descriptor, scenario_payload, MODEL_VERSION
from .v4_valuation_router import build_v4_valuation_router

SCHEMA = 'first-research-input-spec-v1'
ASSUMPTIONS_SCHEMA = 'first-research-assumptions-v1'
RECEIPT_SCHEMA = 'first-research-input-receipt-v1'
MODEL = 'residual_income_or_equity_value'
COMPILATION_SCOPE = 'condition_scenarios_not_adopted_main_range'
NARRATIVE = {'industry', 'investment_path', 'thesis', 'return_driver',
             'mispricing_hypothesis', 'positives', 'counter_evidence', 'thesis_breakers', 'next_events'}


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(root, binding, closure):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str) or not isinstance(binding['sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])
            or Path(binding['path']).is_absolute() or '..' in Path(binding['path']).parts):
        raise ValueError('First compilation requires exact project-relative path/hash bindings')
    path = require_inside(root, root / binding['path'], 'first input source')
    raw = path.read_bytes()
    if _digest(raw) != binding['sha256']:
        raise ValueError('First input source hash mismatch: ' + binding['path'])
    if binding not in closure:
        closure.append(dict(binding))
    return raw


def _time(value, ceiling):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > ceiling:
        raise ValueError('First input source follows cutoff or lacks timezone')
    return stamp


def _number(value):
    if not isinstance(value, str):
        raise ValueError('Financial values require explicit Decimal strings')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid financial number') from error
    if not result.is_finite():
        raise ValueError('Nonfinite financial number')
    return result


def _binding(root, path, payload):
    raw = encode_json_bytes(payload)
    return dict(path=path.relative_to(root).as_posix(), sha256=_digest(raw)), raw


def _implementations():
    from importlib.resources import files
    from ... import research_application
    from ...infrastructure.filings import first_research_fact_replay_v1
    from ...domain.valuation import joint_capital_cash_path_v4
    from ...valuation_models import residual_income_path_v4
    from ..product import source_bound_inputs, neutral_valuation_proposal
    from . import v4_input_adapter
    modules = (research_application, joint_capital_cash_path_v4, residual_income_path_v4,
               source_bound_inputs, neutral_valuation_proposal, v4_input_adapter,
               first_research_fact_replay_v1)
    return {**{module.__name__: _digest(Path(module.__file__).read_bytes()) for module in modules},
            'value_investment_agent.domain.research.issuer_identity_registry.json':
                _digest(files('value_investment_agent.domain.research')
                        .joinpath('issuer_identity_registry.json').read_bytes()),
            __name__: _digest(Path(__file__).read_bytes())}


def _default_fact_replay(**kwargs):
    # A server implementation, never a dynamic import named by a submitted spec.
    from ...infrastructure.filings.first_research_fact_replay_v1 import replay_first_research_facts
    return replay_first_research_facts(**kwargs)


def _prepare(root, spec_binding, output, now, fact_replay):
    closure = []
    spec = json.loads(_read(root, spec_binding, closure))
    required = {'schema_version', 'action', 'symbol', 'name', 'profile_id', 'run_id',
                'point_in_time', 'native_facts_binding', 'capital_bindings', 'share_basis',
                'assumption_binding', 'research_case'}
    if (set(spec) != required or spec['schema_version'] != SCHEMA or spec['action'] != 'no_order'
            or spec['profile_id'] != 'quality_compounder'
            or not isinstance(spec['symbol'], str) or not re.fullmatch(r'[0-9]{6}', spec['symbol'])
            or not all(isinstance(spec[k], str) and spec[k].strip() for k in ('name', 'run_id'))):
        raise ValueError('Invalid first input spec; predecessors, market and approvals are forbidden')
    symbol, pit = spec['symbol'], spec['point_in_time']
    if set(pit) != {'report_period', 'research_as_of', 'valuation_date', 'available_at', 'computed_at'}:
        raise ValueError('Explicit first input point-in-time contract required')
    for field in ('report_period', 'research_as_of', 'valuation_date'):
        if date.fromisoformat(pit[field]).isoformat() != pit[field]:
            raise ValueError('Exact financial dates required')
    computed = _time(pit['computed_at'], now)
    cutoff = _time(pit['available_at'], computed)
    native_manifest = json.loads(_read(root, spec['native_facts_binding'], closure))
    _time(native_manifest['generated_at'], cutoff)
    replay = fact_replay(root=root, binding=deepcopy(spec['native_facts_binding']), now=now)
    if (replay.get('action') != 'no_order' or replay.get('symbol') != symbol
            or replay.get('financial_basis') != pit['valuation_date']):
        raise ValueError('Cold financial replay issuer/basis mismatch')
    # Use facts, not a caller-provided by_id map or verified boolean.
    facts = replay['facts']
    ids = [row['id'] for row in facts]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate cold fact identity')
    by_id = {row['id']: row for row in facts}
    sources = []
    for raw_source in replay['sources']:
        source = deepcopy(raw_source)
        if 'local_path' not in source:
            # Root's native locator format records public original availability;
            # retrieval here means this compilation's local replay, not download.
            source.update(local_path=source['path'], location=source['source_url'],
                kind='official_issuer_filing', source_available_at=source['available_at'],
                retrieved_at=cutoff.isoformat(),
                availability_basis='CURRENT_LOCAL_NATIVE_REPLAY_NOT_ORIGINAL_DOWNLOAD_OR_HISTORICAL_PIT',
                original_retrieved_at=source.get('original_retrieved_at'),
                parser_version=replay['schema_version'],
                issuer_identity=dict(venue='CNINFO', security_code=source['symbol'],
                    issuer_name=source['issuer_name'], organization_id=source.get('organization_id')))
        sources.append(source)
    catalog = {row['id']: row for row in sources}
    if len(catalog) != len(sources) or not sources:
        raise ValueError('Cold source catalog identity invalid')
    for source in sources:
        _read(root, dict(path=source['local_path'], sha256=source['sha256']), closure)
        available = _time(source['source_available_at'], cutoff)
        retrieved = _time(source['retrieved_at'], cutoff)
        if not source.get('availability_basis') or retrieved < available:
            raise ValueError('Cold source availability/retrieval mismatch')
        if source.get('published_at') and _time(source['published_at'], cutoff) > available:
            raise ValueError('Cold source availability precedes publication')
        if source.get('published_date') and date.fromisoformat(source['published_date']) > available.astimezone(
                ZoneInfo('Asia/Shanghai')).date():
            raise ValueError('Cold source availability precedes its publication date')
        identity = source.get('issuer_identity') or {}
        if (source['kind'] not in {'official_issuer_filing', 'official_exchange_filing'}
                or identity.get('security_code') != symbol):
            raise ValueError('Cold financial sources require the actual official issuer')
    assumptions = json.loads(_read(root, spec['assumption_binding'], closure))
    if (set(assumptions) != {'schema_version', 'action', 'symbol', 'financial_basis',
            'generated_at', 'assumption_scope', 'source_bindings', 'choice',
            'historical_bindings', 'scenarios'}
            or assumptions['schema_version'] != ASSUMPTIONS_SCHEMA
            or assumptions['action'] != 'no_order' or assumptions['symbol'] != symbol
            or assumptions['financial_basis'] != pit['valuation_date']
            or assumptions['assumption_scope'] != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'):
        raise ValueError('First D2 assumption identity/scope mismatch')
    _time(assumptions['generated_at'], cutoff)
    if not assumptions['source_bindings']:
        raise ValueError('D2 research needs bound rationale sources')
    for binding in assumptions['source_bindings']:
        raw = _read(root, binding, closure)
        try:
            node = json.loads(raw)
        except (ValueError, UnicodeError):
            node = None
        if isinstance(node, dict):
            for field in ('generated_at', 'available_at', 'computed_at'):
                if node.get(field):
                    _time(node[field], cutoff)
    missing, anchors, derivations = [], {}, {}

    def fact(fact_id, label, unit, scope, *, capital=False):
        row = by_id.get(fact_id)
        if row is None:
            missing.append(label)
            return None
        if (row['unit'] != unit or row['scope'] != scope
                or (row['period_end'] != pit['valuation_date'] if capital else
                    date.fromisoformat(row['period_end']) > date.fromisoformat(pit['valuation_date']))
                or row['source_id'] not in catalog
                or type(row['physical_page']) is not int or row['physical_page'] < 1
                or not all(isinstance(row.get(k), str) and row[k].strip() for k in ('label', 'excerpt'))):
            raise ValueError('Cold fact field/unit/scope/period/locator mismatch: ' + label)
        value = _number(row['value'])
        anchors[row['id']] = dict(field=row['id'], source_id=row['source_id'],
            physical_page=row['physical_page'], unit=unit, scope=scope,
            period_end=row['period_end'], source_value=row['value'],
            sha256=catalog[row['source_id']]['sha256'], label=row['label'], excerpt=row['excerpt'])
        return str(value)

    if set(spec['capital_bindings']) != {'start_book_equity', 'ordinary_shares'}:
        raise ValueError('Both direct capital fact bindings required')
    if spec['share_basis'] not in {'issued_ordinary_shares', 'ordinary_shares_excluding_treasury'}:
        raise ValueError('Explicit ordinary share basis required')
    book = fact(spec['capital_bindings']['start_book_equity'], 'start_book_equity',
                'CNY', 'consolidated_parent_equity', capital=True)
    shares = fact(spec['capital_bindings']['ordinary_shares'], 'ordinary_shares',
                  'shares', spec['share_basis'], capital=True)
    if ((book is not None and _number(book) <= 0) or (shares is not None and (
            _number(shares) <= 0 or _number(shares) != _number(shares).to_integral_value()))):
        raise ValueError('Positive equity and integral ordinary shares required')
    history = dict(scope=SCOPE, currency='CNY')
    mappings = assumptions['historical_bindings']
    if set(mappings) - (HISTORICAL_FIELDS - {'scope', 'currency'}):
        raise ValueError('Unknown historical binding fields')
    allowed_fields = {field: {field} for field in HISTORICAL_FIELDS}
    allowed_fields.update(nonrecurring={'parent_profit', 'ex_parent_profit'},
                          da={'depreciation', 'amortization', 'da'})

    def derive(node, field, depth=0):
        if depth > 3 or not isinstance(node, dict):
            raise ValueError('Historical derivation must be a bounded source operation')
        operation = node.get('operation')
        if operation not in {'DIRECT', 'TTM', 'SUM', 'DIFFERENCE'}:
            raise ValueError('Unsupported historical source derivation')
        leaves, values, periods, operand_sizes = [], [], [], []
        if set(node) == {'operation', 'fact_ids'}:
            fact_ids = node['fact_ids']
            if (not isinstance(fact_ids, list) or not 1 <= len(fact_ids) <= 6
                    or any(not isinstance(x, str) for x in fact_ids) or len(set(fact_ids)) != len(fact_ids)):
                raise ValueError('Historical source operation requires unique fact IDs')
            for ident in fact_ids:
                row = by_id.get(ident)
                if row is None:
                    missing.append('historical.' + field + ':' + ident)
                    return None
                if row['field'] not in allowed_fields[field]:
                    raise ValueError('Historical financial field identity mismatch: ' + field)
                scope = 'consolidated_parent' if field == 'nonrecurring' or field == 'parent_profit' else 'consolidated'
                value = fact(ident, 'historical.' + field, 'CNY', scope)
                values.append(_number(value))
                periods.append(row['period_end'])
                leaves.append(ident)
                operand_sizes.append(1)
        elif set(node) == {'operation', 'operands'} and operation in {'SUM', 'DIFFERENCE'}:
            operands = node['operands']
            if not isinstance(operands, list) or not 2 <= len(operands) <= 6:
                raise ValueError('Bounded historical operands required')
            for operand in operands:
                part = derive(operand, field, depth + 1)
                if part is None:
                    return None
                value, period, fact_ids = part
                values.append(value)
                periods.append(period)
                leaves.extend(fact_ids)
                operand_sizes.append(len(fact_ids))
        else:
            raise ValueError('Invalid historical operation fields')
        if len(leaves) != len(set(leaves)):
            raise ValueError('A historical operation cannot double count a native fact')
        if field == 'nonrecurring' and operation == 'DIFFERENCE':
            split = operand_sizes[0]
            if ({by_id[i]['field'] for i in leaves[:split]} != {'parent_profit'}
                    or {by_id[i]['field'] for i in leaves[split:]} != {'ex_parent_profit'}):
                raise ValueError('Nonrecurring bridge must be parent profit minus adjusted parent profit')
        with localcontext() as context:
            context.prec = 48
            if operation == 'DIRECT':
                if len(values) != 1:
                    raise ValueError('DIRECT requires one fact')
                result = values[0]
            elif operation == 'TTM':
                basis = date.fromisoformat(pit['valuation_date'])
                expected = [f'{basis.year-1}-12-31', basis.isoformat(), f'{basis.year-1}{basis.isoformat()[4:]}']
                if (len(values) != 3 or periods != expected or basis.month == 12
                        or len({by_id[i]['field'] for i in leaves}) != 1):
                    raise ValueError('TTM requires prior FY + current interim - prior interim of one field')
                result = values[0] + values[1] - values[2]
                return result, basis.isoformat(), leaves
            elif operation == 'SUM':
                if len(values) < 2 or len(set(periods)) != 1:
                    raise ValueError('SUM requires same-period facts')
                result = sum(values, Decimal(0))
            else:
                if len(values) != 2 or len(set(periods)) != 1:
                    raise ValueError('DIFFERENCE requires two same-period operands')
                result = values[0] - values[1]
            return result, periods[0], leaves

    for field in sorted(HISTORICAL_FIELDS - {'scope', 'currency'}):
        binding = mappings.get(field)
        if binding is None:
            missing.append('historical.' + field)
        elif isinstance(binding, dict) and ('operation' in binding or set(binding) == {'fact_id'}):
            if field in {'opening_cash', 'opening_distribution_capacity', 'cash_floor'}:
                raise ValueError('Owner cash/capacity/floor mapping must remain an explicit hypothesis')
            node = dict(operation='DIRECT', fact_ids=[binding['fact_id']]) if 'fact_id' in binding else binding
            derived = derive(node, field)
            if derived is not None:
                history[field] = str(derived[0])
                derivations[field] = dict(operation=deepcopy(node), fact_ids=derived[2],
                    period_end=derived[1], value=history[field], classification='SOURCE_ARITHMETIC_NOT_FORECAST')
        elif set(binding) == {'assumption'}:
            if field not in {'opening_cash', 'opening_distribution_capacity', 'cash_floor'}:
                raise ValueError('Reported historical financial amounts require cold facts, not hand-filled hypotheses')
            item = binding['assumption']
            if (set(item) != {'value', 'unit', 'scope', 'rationale', 'source_bindings'}
                    or item['unit'] != 'CNY' or not item['rationale'] or not item['source_bindings']
                    or item['scope'] != (SCOPE if field in {'opening_cash', 'opening_distribution_capacity', 'cash_floor'}
                                         else 'consolidated_parent' if field in {'parent_profit', 'nonrecurring'} else 'consolidated')):
                raise ValueError('Historical hypothesis needs explicit scope, rationale and sources')
            history[field] = str(_number(item['value']))
            for ref in item['source_bindings']:
                if ref not in assumptions['source_bindings']:
                    raise ValueError('Historical hypothesis cites an unbound D2 source')
        else:
            raise ValueError('Historical numbers must reference cold facts or explicit D2 hypotheses')
    if missing:
        return dict(status='MISSING_INPUTS', missing_inputs=sorted(set(missing)),
                    symbol=symbol, action='no_order', formal_eligibility=False,
                    external_acceptance_required=True, compilation_scope=COMPILATION_SCOPE,
                    main_range_adopted=False), None, closure
    scenario_nodes = assumptions['scenarios']
    if set(scenario_nodes) - {'bear', 'base', 'bull'}:
        raise ValueError('Unknown v4 scenario labels')
    missing_scenarios = sorted({'bear', 'base', 'bull'} - set(scenario_nodes))
    if missing_scenarios:
        return dict(status='MISSING_INPUTS', missing_inputs=['scenarios.' + s for s in missing_scenarios],
                    symbol=symbol, action='no_order', formal_eligibility=False,
                    external_acceptance_required=True, compilation_scope=COMPILATION_SCOPE,
                    main_range_adopted=False), None, closure
    if set(assumptions['choice']) != {'id', 'rationale', 'countercase'}:
        raise ValueError('One explicitly explained three-scenario choice required')
    assumption_id = 'first-assumptions-' + spec['assumption_binding']['sha256']
    choice = deepcopy(assumptions['choice'])
    for key, original in (('joint_drivers', 'drivers'), ('terminal_policy', 'terminal_policy'),
                          ('cost_of_equity', 'cost_of_equity')):
        choice[key] = {name: row[original] for name, row in scenario_nodes.items()}
    choice['scenario_bindings'] = {name: dict(source_id=assumption_id, field_path=['scenarios', name])
                                   for name in scenario_nodes}
    scenarios, ledgers = compile_joint_cash_choice_v4(choice=choice, historical=history, book=_number(book))
    serialized = {name: scenario_payload(row) for name, row in scenarios.items()}
    actual = dict(start_book_equity=book, ordinary_shares=shares, scenarios={})
    for name, row in serialized.items():
        actual['scenarios'][name] = deepcopy(row)
        actual['scenarios'][name]['forecast_roe'] = actual['scenarios'][name].pop('forecast_roes')
    proposal = dict(schema_version='joint-capital-cash-path-proposal-v4',
        input_mode='joint-capital-cash-path-proposal-v4', action='no_order', symbol=symbol,
        compilation_scope=COMPILATION_SCOPE, main_range_adopted=False,
        generated_at=pit['computed_at'], predecessor_package=None,
        source_bindings=deepcopy(closure), joint_historical=history, historical_derivations=derivations,
        historical_bindings=deepcopy(mappings),
        choices=[dict(choice, actual_calculation_inputs=actual, joint_capital_ledgers=_json_numbers(ledgers))])
    proposal_binding, proposal_bytes = _binding(root, output / 'proposal.json', proposal)
    # Every actually read source, including the two input manifests, is in the package.
    for binding in closure:
        if not any(s['local_path'] == binding['path'] and s['sha256'] == binding['sha256'] for s in sources):
            ident = assumption_id if binding == spec['assumption_binding'] else 'first-input-' + binding['sha256']
            sources.append(dict(id=ident, kind='research_artifact', location=binding['path'],
                local_path=binding['path'], sha256=binding['sha256'], source_available_at=pit['available_at'],
                retrieved_at=pit['available_at'], availability_basis='CURRENT_FIRST_COMPILATION_INPUT_NOT_HISTORICAL_PIT'))
    proposal_id = 'pending-joint-proposal-' + proposal_binding['sha256']
    sources.append(dict(id=proposal_id, kind='research_artifact', location=proposal_binding['path'],
        local_path=proposal_binding['path'], sha256=proposal_binding['sha256'],
        source_available_at=pit['available_at'], retrieved_at=pit['available_at'],
        availability_basis='CURRENT_FIRST_COMPILATION_NOT_HISTORICAL_PIT'))
    refs = [dict(id=s['id'], path=s['local_path'], sha256=s['sha256']) for s in sources]
    if set(spec['research_case']) != NARRATIVE:
        raise ValueError('Only source-aware research narrative fields are accepted')
    case = dict(deepcopy(spec['research_case']), symbol=symbol, name=spec['name'],
        run_id=spec['run_id'], as_of=pit['research_as_of'], generated_at=pit['computed_at'],
        research_version=SCHEMA, financial_period=pit['report_period'], quote_date=None,
        missing_date_reasons={'quote_date': 'No market input in first compilation'},
        evidence_status='verified', valuation_status='conditional_research_only', research_status='PENDING_REVIEW',
        financial_summary={k: v['source_value'] for k, v in anchors.items()}, evidence_refs=refs,
        blockers=['ECONOMIC_RESEARCH_NOT_APPROVED'])
    assumption_rows, bindings = [], []
    paths = ['cost_of_equity', 'terminal_roe', 'terminal_growth'] + [
        f'{prefix}.{i}' for prefix in ('forecast_roes', 'forecast_retentions') for i in range(10)]
    for path in paths:
        def consumed(row):
            bits = path.split('.')
            return row[bits[0]][int(bits[1])] if len(bits) == 2 else row[path]
        values = {name: consumed(row) for name, row in serialized.items()}
        assumption_rows.append(dict(name=path, unit='ratio', **values,
            basis='COMPILED_FROM_BOUND_D2_CHOICE_NOT_OFFICIAL_FORECAST', rationale=choice['rationale'],
            confidence='low', sensitivity='high', ordering='non_monotonic', evidence_refs=refs))
        bindings.extend(dict(assumption_name=path, scenario=name, field_path=path,
            expected_value=value, evidence_refs=refs) for name, value in values.items())
    package = dict(schema_version='m1-valuation-package-v2', descriptor_version=SCHEMA,
        symbol=symbol, name=spec['name'], profile_id='quality_compounder', requested_model=MODEL,
        run_id=spec['run_id'], point_in_time=deepcopy(pit),
        dependencies=dict(rule_version=SCHEMA, model_id=MODEL, model_version=MODEL_VERSION,
                          parser_version=replay.get('schema_version', 'cold-first-facts')),
        sources=sources, research_case=case,
        facts=dict(kind='quality_compounder', symbol=symbol, as_of=pit['valuation_date'], verified=True,
            confidence='低', evidence_refs=refs, blockers=[],
            operating_inputs=dict(start_book_equity=book, ordinary_shares=shares), scenario_inputs=serialized),
        # Economic approval belongs to the case/eligibility gate. Complete,
        # source-bound conditional arithmetic does not require that approval.
        assumptions=dict(assumptions=assumption_rows, evidence_refs=refs, blockers=[]),
        assumption_bindings=bindings,
        source_contract=dict(schema_version='source-bound-research-inputs-v3',
            cutoff_at=pit['available_at'], source_catalog_sha256=source_catalog_sha256(sources),
            distribution_input_status='NOT_ADMITTED', share_basis=spec['share_basis'],
            strict_contemporaneous_pit=False, fact_anchors=list(anchors.values()),
            consumed_fact_bindings=[dict(field_path='operating_inputs.' + field,
                anchor_field=fact_id, operation='DIRECT') for field, fact_id in spec['capital_bindings'].items()]))
    consumed_replay = dict(schema_version=replay.get('schema_version'), symbol=replay['symbol'],
        financial_basis=replay['financial_basis'], facts=facts, sources=replay['sources'],
        input_fingerprint=replay.get('input_fingerprint'))
    return dict(proposal=proposal, proposal_binding=proposal_binding, proposal_bytes=proposal_bytes,
                package=package, cold_replay_fingerprint=_digest(encode_json_bytes(consumed_replay))), spec, closure


def replay_first_research_input(*, root: Path, receipt_binding: dict, now: datetime,
                                fact_replay=None) -> dict:
    """Cold-reparse originals, recompile D2 inputs and execute the existing v4 service."""
    if now.utcoffset() is None:
        raise ValueError('Aware cold-recompilation clock required')
    root = root.resolve()
    closure = []
    receipt = json.loads(_read(root, receipt_binding, closure))
    if receipt.get('schema_version') != RECEIPT_SCHEMA or receipt.get('action') != 'no_order':
        raise ValueError('Invalid first compilation receipt')
    if receipt.get('implementation_sha256') != _implementations():
        raise ValueError('First compilation implementation changed; create a new version')
    output = _path_from_binding(root, receipt['package_binding']).parent
    prepared, spec, inputs = _prepare(root, receipt['spec_binding'], output, now,
                                      fact_replay or _default_fact_replay)
    if spec is None:
        raise ValueError('Cold first compilation has missing inputs')
    if prepared['cold_replay_fingerprint'] != receipt['cold_replay_fingerprint']:
        raise ValueError('Cold facts changed since first compilation')
    if _read(root, prepared['proposal_binding'], closure) != prepared['proposal_bytes']:
        raise ValueError('Cold proposal differs')
    package = json.loads(_read(root, receipt['package_binding'], closure))
    if encode_json_bytes(package) != encode_json_bytes(prepared['package']):
        raise ValueError('Cold package differs from actual source and D2 consumption')
    descriptor = build_v4_descriptor(package, root=root)
    outcome = ResearchApplicationService(router=build_v4_valuation_router(), now_utc=lambda: now).run_company_research(
        build_research_run_spec(descriptor))
    if descriptor.input_sha256 != receipt['input_descriptor_sha256']:
        raise ValueError('Cold input descriptor differs')
    for binding in inputs + closure:
        _read(root, binding, [])
    from ..product.company_research import _serialize_outcome
    research_result = _serialize_outcome(outcome)
    source_bindings = []
    for binding in inputs + closure:
        if binding not in source_bindings:
            source_bindings.append(binding)
    fingerprint = _digest(encode_json_bytes(dict(descriptor=descriptor.input_sha256,
        sources=source_bindings, cold_facts=receipt['cold_replay_fingerprint'],
        implementation=receipt['implementation_sha256'])))
    return dict(status='COLD_RECOMPILED', action='no_order', formal_eligibility=False,
        formal_fact_count=0, approval_changed=False, economic_quality_proven=False,
        input_descriptor_sha256=descriptor.input_sha256, issuer_identity_status=outcome.issuer_identity_status,
        valuation_status=outcome.valuation.status if outcome.valuation else 'NOT_READY',
        valuation=json.loads(outcome.valuation.to_json()) if outcome.valuation else None,
        input_fingerprint=fingerprint, source_bindings=source_bindings,
        package_binding=receipt['package_binding'], proposal_binding=receipt['proposal_binding'],
        research_case=package['research_case'], research_result=research_result,
        artifact_bundle=research_result['artifact_bundle'], blockers=research_result['blockers'],
        annual_ledgers=prepared['proposal']['choices'][0]['joint_capital_ledgers'],
        scope='FIRST_SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_APPROVAL',
        compilation_scope=COMPILATION_SCOPE, main_range_adopted=False,
        main_valuation_range=None, external_acceptance_required=True,
        external_acceptance_scope='NOT_GRANTED_BY_THIS_COMPILER',
        scenario_label_scope='V4_COMPATIBILITY_KEYS_NOT_ADOPTED_MAIN_BEAR_BASE_BULL_RANGE')


def _path_from_binding(root, binding):
    return require_inside(root / 'runtime', root / binding['path'], 'first compilation output')


def build_first_research_input(*, root: Path, spec_binding: dict, output_dir: Path,
                               now: datetime, fact_replay=None) -> dict:
    """Publish only new proposal/package/cold receipt; never register a current candidate."""
    if now.utcoffset() is None:
        raise ValueError('Aware first compilation clock required')
    root = root.resolve()
    output = require_inside(root / 'runtime', output_dir.resolve(), 'first compilation output')
    if output.exists():
        raise FileExistsError('First compilation output must be new')
    prepared, spec, closure = _prepare(root, spec_binding, output, now, fact_replay or _default_fact_replay)
    if spec is None:
        return prepared
    write_new_bytes(output / 'proposal.json', prepared['proposal_bytes'])
    descriptor = build_v4_descriptor(prepared['package'], root=root)
    package_binding, package_bytes = _binding(root, output / 'package.json', prepared['package'])
    write_new_bytes(output / 'package.json', package_bytes)
    receipt = dict(schema_version=RECEIPT_SCHEMA, action='no_order', formal_eligibility=False,
        formal_fact_count=0, approval_changed=False, economic_quality_proven=False,
        compilation_scope=COMPILATION_SCOPE, main_range_adopted=False,
        external_acceptance_required=True, external_acceptance_scope='NOT_GRANTED_BY_THIS_COMPILER',
        status='FIRST_INPUT_COMPILED', symbol=spec['symbol'], spec_binding=deepcopy(spec_binding),
        proposal_binding=prepared['proposal_binding'], package_binding=package_binding,
        input_descriptor_sha256=descriptor.input_sha256,
        cold_replay_fingerprint=prepared['cold_replay_fingerprint'],
        source_bindings=closure, predecessor_package=None, approvals_created=0,
        market_inputs_consumed=False, account_inputs_consumed=False,
        implementation_sha256=_implementations())
    rb, raw = _binding(root, output / 'receipt.json', receipt)
    write_new_bytes(output / 'receipt.json', raw)
    cold = replay_first_research_input(root=root, receipt_binding=rb, now=now, fact_replay=fact_replay)
    cold_binding, cold_bytes = _binding(root, output / 'cold-recompile.json', cold)
    write_new_bytes(output / 'cold-recompile.json', cold_bytes)
    return dict(receipt, receipt_binding=rb, cold_receipt_binding=cold_binding,
                cold_recompile=cold, input_fingerprint=cold['input_fingerprint'],
                artifact_bundle=cold['artifact_bundle'], research_result=cold['research_result'],
                research_case=cold['research_case'], annual_ledgers=cold['annual_ledgers'],
                source_bindings=cold['source_bindings'], external_acceptance_required=True)
