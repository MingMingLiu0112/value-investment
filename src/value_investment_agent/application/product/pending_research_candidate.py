"""Compile a finite proposal into shared research inputs, without approval."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .neutral_valuation_proposal import (
    build_neutral_valuation_proposal, JOINT_SCHEMA, _joint_inputs, _profit_anchor,
    compile_joint_choice, validate_proposal_policy_identity,
)
from . import neutral_valuation_proposal as _neutral
from .financial_valuation_rebase import rebase_proposal_facts
from .source_bound_inputs import verify_package_local_sources
from .financial_review_attachment import load_financial_review_attachment
from .workbench import build_current_workbench_for_symbol
from .research_review_packet import build_research_review_packet, project_research_review_packet
from ...m1_valuation_package_builder import build_descriptor
from ..research.v4_input_adapter import build_descriptor_for_package
from ...research_input import build_research_run_spec
from .research_reviews import build_research_review_model_context


VALUATION_BASIS_SCOPE = 'EX_POST_PRIOR_COMPLETED_SESSION'
JOINT_IMPLEMENTATIONS = frozenset({
    'src/value_investment_agent/application/product/pending_research_candidate.py',
    'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
    'src/value_investment_agent/domain/valuation/joint_capital_path.py',
})


# Compatibility import while the parallel neutral v2 entrypoint is being added.
# A missing compiler is an error, never permission to reuse the v1 kernel.
JOINT_CASH_SCHEMA = getattr(_neutral, 'JOINT_CASH_SCHEMA', 'joint-capital-cash-path-proposal-v2')
JOINT_CASH_V3_SCHEMA = getattr(_neutral, 'JOINT_CASH_V3_SCHEMA', 'joint-capital-cash-path-proposal-v3')
JOINT_CASH_V4_SCHEMA = getattr(_neutral, 'JOINT_CASH_V4_SCHEMA', 'joint-capital-cash-path-proposal-v4')
JOINT_MODES = frozenset({JOINT_SCHEMA, JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA})
JOINT_CASH_IMPLEMENTATIONS = frozenset({
    'src/value_investment_agent/application/product/pending_research_candidate.py',
    'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
    'src/value_investment_agent/domain/valuation/joint_capital_cash_path_v2.py',
    'src/value_investment_agent/valuation_models/residual_income_path_v2.py',
    'src/value_investment_agent/valuation_models/residual_income.py',
})
JOINT_CASH_V3_IMPLEMENTATIONS = frozenset({
    'src/value_investment_agent/application/product/pending_research_candidate.py',
    'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
    'src/value_investment_agent/application/product/company_research.py',
    'src/value_investment_agent/application/product/workbench.py',
    'src/value_investment_agent/application/product/research_review_packet.py',
    'src/value_investment_agent/application/product/economic_review_materials.py',
    'src/value_investment_agent/application/product/historical_source_restore.py',
    'src/value_investment_agent/application/research/v3_review_context.py',
    'src/value_investment_agent/application/research/v3_valuation_router.py',
    'src/value_investment_agent/domain/valuation/joint_capital_cash_path_v3.py',
    'src/value_investment_agent/research_artifact_codecs.py',
    'src/value_investment_agent/application/research/v3_input_adapter.py',
    'src/value_investment_agent/valuation_models/residual_income_path_v3.py',
    'src/value_investment_agent/valuation_models/residual_income.py',
})
JOINT_CASH_V4_IMPLEMENTATIONS = frozenset({
    'src/value_investment_agent/application/product/pending_research_candidate.py',
    'src/value_investment_agent/application/product/neutral_valuation_proposal.py',
    'src/value_investment_agent/application/product/company_research.py',
    'src/value_investment_agent/application/product/workbench.py',
    'src/value_investment_agent/application/product/research_review_packet.py',
    'src/value_investment_agent/application/product/economic_review_materials.py',
    'src/value_investment_agent/application/product/historical_source_restore.py',
    'src/value_investment_agent/application/research/v4_review_context.py',
    'src/value_investment_agent/application/research/v4_valuation_router.py',
    'src/value_investment_agent/domain/valuation/joint_capital_cash_path_v4.py',
    'src/value_investment_agent/research_artifact_codecs.py',
    'src/value_investment_agent/application/research/v4_input_adapter.py',
    'src/value_investment_agent/valuation_models/residual_income_path_v4.py',
    'src/value_investment_agent/valuation_models/residual_income.py',
})


def _cash_entrypoint(name):
    entrypoint = getattr(_neutral, name, None)
    if not callable(entrypoint):
        raise ValueError('joint cash v2 neutral entrypoint unavailable: ' + name)
    return entrypoint


def _valuation_economics(payload):
    """Compare model outputs while permitting the consumer to add provenance refs."""
    value = deepcopy(payload)
    value.pop('evidence_refs', None)
    timing = (value.get('assumptions') or {}).get('valuation_timing')
    if isinstance(timing, dict):
        timing.pop('evidence_refs', None)
    return value


def _joint_cash_replay_inputs(policy, package, sources, root, mode=JOINT_CASH_SCHEMA):
    """Revalidate the neutral v2 source contract without creating a proposal."""
    if mode == JOINT_CASH_V4_SCHEMA:
        from ...domain.valuation.joint_capital_cash_path_v4 import HISTORICAL_FIELDS, SCOPE
    elif mode == JOINT_CASH_V3_SCHEMA:
        from ...domain.valuation.joint_capital_cash_path_v3 import HISTORICAL_FIELDS, SCOPE
    else:
        from ...domain.valuation.joint_capital_cash_path_v2 import HISTORICAL_FIELDS, SCOPE

    _neutral._cash_keys(policy, 'schema_version action symbol source_package_sha256 generated_at assumption_scope '
        'profit_anchor_field profit_basis rationale_bindings joint_historical choices economic_review_items assurance_limits', 'policy')
    generated = _neutral._cash_available(policy['generated_at'], datetime.now(timezone.utc))
    if policy['assumption_scope'] != 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST':
        raise ValueError('Joint cash inputs must remain research assumptions')
    for key in ('available_at', 'computed_at'):
        _neutral._cash_available(package['point_in_time'][key], generated)
    catalog = {row['id']: row for row in package['sources']}
    if len(catalog) != len(package['sources']) or not policy['rationale_bindings']:
        raise ValueError('Joint cash source IDs or rationale bindings invalid')
    for binding in policy['rationale_bindings']:
        _neutral._cash_keys(binding, 'id path sha256 available_at', 'rationale binding')
        _neutral._cash_available(binding['available_at'], generated)
        if not isinstance(binding['id'], str) or not binding['id'].strip() or binding['id'] in catalog:
            raise ValueError('Joint cash rationale source ID collision')
        relative = Path(binding['path'])
        path = require_inside(root, root/relative, 'joint cash rationale')
        if (relative.is_absolute() or path.relative_to(root).as_posix() != binding['path']
                or sha256_file(path) != binding['sha256']):
            raise ValueError('Joint cash rationale path/hash mismatch')
        sources.append((path, binding['sha256']))
        catalog[binding['id']] = dict(local_path=binding['path'], sha256=binding['sha256'])
    declared = policy['joint_historical']
    if not isinstance(declared, dict) or set(declared) != HISTORICAL_FIELDS:
        raise ValueError('Exact joint cash historical fields required')
    if declared['scope'] != SCOPE or declared['currency'] != 'CNY':
        raise ValueError('Joint cash historical ownership/currency mismatch')
    historical = dict(scope=SCOPE, currency='CNY')
    for field in sorted(HISTORICAL_FIELDS - {'scope', 'currency'}):
        item = declared[field]
        _neutral._cash_keys(item, 'value unit scope source_id field_path rationale', 'historical observation')
        scope = ('consolidated_parent' if field in ('parent_profit', 'nonrecurring') else
            SCOPE if field in ('opening_cash', 'opening_distribution_capacity', 'cash_floor') else 'consolidated')
        if (item['unit'] != 'CNY' or item['scope'] != scope
                or not isinstance(item['rationale'], str) or not item['rationale'].strip()):
            raise ValueError('Joint cash historical unit/scope/rationale mismatch')
        node = _neutral._cash_node({key: item[key] for key in ('source_id', 'field_path')},
                                  catalog, root, sources)
        if not isinstance(node, dict) or any(type(node.get(key)) is not str or node[key] != item[key]
                                              for key in ('value', 'unit', 'scope')):
            raise ValueError('Joint cash historical value/unit/scope differs from source')
        historical[field] = item['value']
    for choice in policy['choices']:
        for name in ('bear', 'base', 'bull'):
            node = _neutral._cash_node(choice['scenario_bindings'][name], catalog, root, sources)
            if node != dict(drivers=choice['joint_drivers'][name],
                            terminal_policy=choice['terminal_policy'][name],
                            cost_of_equity=choice['cost_of_equity'][name]):
                raise ValueError('Joint cash scenario differs from source-bound drivers/terminal/cost')
    return historical


def _joint_scenario_inputs(scenarios, mode):
    expected = {}
    for name, row in scenarios.items():
        if mode == JOINT_CASH_V4_SCHEMA:
            from ..research.v4_input_adapter import scenario_payload
            expected[name] = scenario_payload(row)
            continue
        elif mode == JOINT_CASH_V3_SCHEMA:
            from ..research.v3_input_adapter import scenario_payload
            expected[name] = scenario_payload(row)
            continue
        values = dict(cost_of_equity=str(row.cost_of_equity),
            forecast_roes=[str(value) for value in row.forecast_roes],
            terminal_roe=str(row.terminal_roe), terminal_growth=str(row.terminal_growth))
        if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
            if len(row.forecast_roes) != 10 or len(row.forecast_retentions) != 10:
                raise ValueError('joint cash v2 requires ten ROEs and annual retentions')
            values.update(forecast_retentions=[str(value) for value in row.forecast_retentions],
                          retention_contract='annual-retention-v2', currency='CNY')
        else:
            values['retention'] = str(row.retention)
        expected[name] = values
    return expected


def _joint_narrative(source, choice, package_binding, mode=JOINT_SCHEMA):
    """Project current hypotheses separately from immutable predecessor claims."""
    prior = source['research_case']
    version = source.get('package_version') or ('package-sha256:' + package_binding['sha256'])
    historical = f'历史版本 {version}（仅旧模型研究，不描述当前joint路径）：'
    model_terms = ('全资本', '强衰减', 'STRESS_ONLY', 'whole-equity', 'mechanical fade', '十年')

    def annotate(items):
        result = deepcopy(items)
        for item in result:
            if any(term in item.get('text', '') for term in model_terms):
                item['text'] = historical + item['text']
        return result

    thesis = ('本候选以历史盈利、权益和现金为锚点，实际消费十年现金约束经营与资本路径、'
        '逐年可达资金、持续投入及分配能力决定的留存与分配，并明确终端持续投入；'
        '不是固定留存率或零投入全额分配的默认路径。'
        '这是低置信、尚待经济审阅的研究假设，不是获准主估值。' + choice['rationale']
        if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA) else None)
    return dict(thesis=thesis or '本候选以历史归母盈利与权益为锚点，实际消费五年经营盈利、'
        '新增资本回报、留存与分配联结路径及持续经营终端；不是全资本机械衰减路径。'
        '这是低置信、尚待经济审阅的研究假设，不是获准主估值。' + choice['rationale'],
        mispricing_hypothesis='待检验的是本候选经营、资本配置及终端效率假设与外部预期的差异；'
        '未据当前价格验证预期差，不认定市场误定价。反证：' + choice['countercase'],
        positives=annotate(prior.get('positives', [])),
        counter_evidence=annotate(prior.get('counter_evidence', [])),
        thesis_breakers=annotate(prior.get('thesis_breakers', [])),
        next_events=annotate(prior.get('next_events', [])),
        predecessor_narrative=dict(scope='PREDECESSOR_RESEARCH_NOT_CURRENT_JOINT_MODEL',
            package_binding=deepcopy(package_binding), research_version=version,
            statements={key: deepcopy(prior.get(key)) for key in
                ('thesis', 'mispricing_hypothesis', 'positives', 'counter_evidence',
                 'thesis_breakers', 'next_events', 'blockers')},
            assumption_blockers=deepcopy(source['assumptions'].get('blockers', []))))


def _joint_implementations(bindings, mode=JOINT_SCHEMA):
    expected = (JOINT_CASH_V4_IMPLEMENTATIONS if mode == JOINT_CASH_V4_SCHEMA
        else JOINT_CASH_V3_IMPLEMENTATIONS if mode == JOINT_CASH_V3_SCHEMA
        else JOINT_CASH_IMPLEMENTATIONS if mode == JOINT_CASH_SCHEMA else JOINT_IMPLEMENTATIONS)
    if (not isinstance(bindings, list) or len(bindings) != len(expected)
            or any(not isinstance(row, dict) or set(row) != {'path', 'sha256'} for row in bindings)
            or {row['path'] for row in bindings} != expected):
        raise ValueError('joint candidate requires exact generator/neutral/helper implementation bindings')


def _verify_joint_economic_inputs(*, root, path, data, policy, package, descriptor):
    """Recompile the pinned hypotheses; no writes, signing or mutable selectors."""
    _joint_implementations(data.get('implementation_bindings'), data.get('input_mode', JOINT_SCHEMA))
    original_binding = package['supersedes']
    original_path = require_inside(root, root / original_binding['path'], 'joint predecessor')
    if (original_binding['sha256'] != policy['source_package_sha256']
            or sha256_file(original_path) != policy['source_package_sha256']
            or dict(path=original_binding['path'], sha256=original_binding['sha256']) not in data['source_bindings']):
        raise ValueError('joint candidate predecessor binding mismatch')
    original = load_json_object(original_path, 'joint predecessor')
    validate_proposal_policy_identity(policy=policy, package=original,
        package_sha256=original_binding['sha256'], candidate_symbol=package['symbol'])
    if data['input_mode'] in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        from .historical_source_restore import verify_or_restore_package_sources
        if data['input_mode'] == JOINT_CASH_V4_SCHEMA:
            from ..research.v4_input_adapter import build_predecessor_descriptor
        else:
            from ..research.v3_input_adapter import build_predecessor_descriptor
        verify_or_restore_package_sources(root, original,
            restore_dir=path.parent / 'historical-source-code', create=False)
        old_descriptor = build_predecessor_descriptor(original, root=root)
    else:
        verify_package_local_sources(root, original)
        old_descriptor = build_descriptor(original, root=root)
    old_facts = old_descriptor.facts
    source_checks = []
    mode = data['input_mode']
    historical_loader = (_joint_cash_replay_inputs
        if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA) else _joint_inputs)
    historical = (historical_loader(policy, original, source_checks, root, mode)
        if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA)
        else historical_loader(policy, original, source_checks, root))
    if policy.get('financial_rebase') is not None:
        old_facts, anchor, bindings, _ = rebase_proposal_facts(
            root=root, symbol=descriptor.symbol, facts=old_facts, policy=policy)
        source_checks.extend(bindings)
    elif mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        anchor = _neutral._joint_cash_profit_anchor(
            historical, old_descriptor.research_case, policy['profit_anchor_field'])
    else:
        anchor = _profit_anchor(root, original, old_descriptor.research_case, policy['profit_anchor_field'])
    choices = [choice for choice in policy['choices'] if choice['id'] == data['selected_choice']]
    if len(choices) != 1:
        raise ValueError('joint candidate must select one exact policy choice')
    book = old_facts.operating_inputs['start_book_equity']
    shares = old_facts.operating_inputs['ordinary_shares']
    compiler = (_cash_entrypoint('compile_joint_cash_choice_v4') if mode == JOINT_CASH_V4_SCHEMA
        else _cash_entrypoint('compile_joint_cash_choice_v3') if mode == JOINT_CASH_V3_SCHEMA
        else _cash_entrypoint('compile_joint_cash_choice') if mode == JOINT_CASH_SCHEMA
        else compile_joint_choice)
    if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        if Decimal(historical['parent_profit']) - Decimal(historical['nonrecurring']) != anchor:
            raise ValueError('Joint cash history differs from the source-bound profit anchor')
        scenarios, ledgers = compiler(choice=choices[0], historical=historical, book=book)
        ledgers = _neutral._json_numbers(ledgers)
        code_root = Path(__file__).resolve().parents[4]
        for ref in data['implementation_bindings']:
            if sha256_file(code_root/ref['path']) != ref['sha256']:
                raise ValueError('joint cash candidate implementation differs from executing code')
    else:
        scenarios, ledgers = compiler(choice=choices[0], historical=historical, book=book, anchor=anchor)
    expected = _joint_scenario_inputs(scenarios, mode)
    facts = package['facts']
    summary = package['research_case']['financial_summary']
    expected_summary = dict(input_mode=mode, scope='RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS',
        ledgers=ledgers, policy_sha256=data['economic_policy_binding']['sha256'], normalized_profit=None)
    if (facts['scenario_inputs'] != expected
            or Decimal(facts['operating_inputs']['start_book_equity']) != book
            or Decimal(facts['operating_inputs']['ordinary_shares']) != shares
            or facts.get('confidence') != '低'
            or summary.get('pending_joint_capital_research') != expected_summary
            or summary.get('normalized_parent_profit_cny') is not None):
        raise ValueError('joint candidate economic derivation differs from consumed inputs/ledger')
    narrative = _joint_narrative(original, choices[0], dict(
        path=original_binding['path'], sha256=original_binding['sha256']), mode)
    if (package['research_case']['thesis'] != narrative['thesis']
            or package['research_case']['mispricing_hypothesis'] != narrative['mispricing_hypothesis']
            or summary.get('predecessor_research_narrative') != narrative['predecessor_narrative']):
        raise ValueError('joint candidate current/predecessor narrative scope mismatch')
    for key in ('positives', 'counter_evidence', 'thesis_breakers', 'next_events'):
        actual = package['research_case'][key]
        if key == 'counter_evidence':
            if not actual or actual[-1].get('text') != choices[0]['countercase']:
                raise ValueError('joint candidate countercase scope mismatch')
            actual = actual[:-1]
        if actual != narrative[key]:
            raise ValueError('joint candidate historical evidence scope mismatch')
    proposal_path = path.parent / 'valuation-proposal.json'
    proposal_binding = dict(path=proposal_path.relative_to(root).as_posix(), sha256=sha256_file(proposal_path))
    if proposal_binding not in data['source_bindings']:
        raise ValueError('joint candidate proposal binding missing')
    proposal = load_json_object(proposal_path, 'joint consumed proposal')
    proposed_choices = [row for row in proposal['choices'] if row['id'] == data['selected_choice']]
    proposal_inputs = {name: {('forecast_roe' if key == 'forecast_roes' else key): value
                             for key, value in row.items()} for name, row in expected.items()}
    if (len(proposed_choices) != 1 or proposal.get('input_mode') != mode
            or proposed_choices[0].get('joint_capital_ledgers') != ledgers
            or proposed_choices[0]['actual_calculation_inputs']['scenarios'] != proposal_inputs
            or proposed_choices[0]['actual_calculation_inputs']['start_book_equity'] != str(book)
            or proposed_choices[0]['actual_calculation_inputs']['profit_anchor'] != str(anchor)
            or proposal.get('source_descriptor_sha256') != old_descriptor.input_sha256):
        raise ValueError('joint proposal economic derivation differs from consumed policy')
    if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        if (proposed_choices[0]['actual_calculation_inputs']['ordinary_shares'] != str(shares)
                or package['dependencies']['model_version'] != (
                    'residual-income-equity-path-v4' if mode == JOINT_CASH_V4_SCHEMA
                    else 'residual-income-equity-path-v3' if mode == JOINT_CASH_V3_SCHEMA
                    else 'residual-income-equity-path-v2')):
            raise ValueError('joint cash shares or actual model version mismatch')
    generated = datetime.fromisoformat(data['generated_at'])
    pit = package['point_in_time']
    if (generated.utcoffset() is None or generated > datetime.now(timezone.utc)
            or datetime.fromisoformat(policy['generated_at']) > generated
            or pit['research_as_of'] != generated.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
            or any(datetime.fromisoformat(pit[key]) != generated for key in ('available_at', 'computed_at'))
            or any(package.get(key) is not None for key in
                ('valuation_approval', 'human_research_approval', 'event_materiality_review', 'research_reviews'))):
        raise ValueError('joint candidate actual date or unapproved boundary mismatch')
    for source_path, digest in source_checks:
        if sha256_file(source_path) != digest:
            raise ValueError('joint source changed during economic replay')


def _basis_quote(root, binding, symbol, now):
    from .event_scan_supplement import _read
    from ...quote_session_conversion import quote_snapshot_from_bundle_file

    _read(root, binding)
    path = require_inside(root / 'runtime', root / binding['path'], 'valuation basis quote')
    quote = quote_snapshot_from_bundle_file(path, root, symbol=symbol,
        ref_id='pending-valuation-basis', expected_sha256=binding['sha256'],
        now=now, require_current_b1=True)
    if (quote.status != 'verified_close' or quote.blockers or quote.quote_date is None
            or quote.symbol != symbol
            or quote.quote_date >= now.astimezone(ZoneInfo('Asia/Shanghai')).date()):
        raise ValueError('valuation basis requires a current B1 prior completed session: '
                         + '; '.join(quote.blockers))
    close = datetime.combine(quote.quote_date, time(15), ZoneInfo('Asia/Shanghai'))
    return quote.quote_date.isoformat(), close.isoformat()


def _coverage_scan(root, package, windows, basis_day, generated_at):
    from .event_scan_supplement import _read, _scan

    if not isinstance(windows, list) or not 1 <= len(windows) <= 3:
        raise ValueError('candidate coverage requires one to three explicit retained windows')
    required_from = date.fromisoformat(package['point_in_time']['report_period']) + timedelta(days=1)
    predecessor = _read(root, {key: package['supersedes'][key] for key in ('path', 'sha256')})
    if (predecessor['symbol'] != package['symbol']
            or predecessor['point_in_time']['report_period'] != package['point_in_time']['report_period']):
        raise ValueError('candidate coverage predecessor issuer/report period mismatch')
    previous_ref = (predecessor.get('model_validity_input') or {}).get('event_scan_ref')
    scan_package = deepcopy(package)
    scan_package['model_validity_input'].pop('event_scan_ref', None)
    if previous_ref:
        previous = _read(root, {key: previous_ref[key] for key in ('path', 'sha256')})
        required_from = min(required_from, date.fromisoformat(previous['scan_from']))
        scan_package['model_validity_input']['event_scan_ref'] = previous_ref
    return _scan(root, scan_package, windows, required_from,
                 date.fromisoformat(basis_day), generated_at)


def prepare_pending_research_candidate(*, root: Path, package_path: Path,
        package_sha256: str, policy_path: Path, policy_sha256: str,
        choice_id: str, output_dir: Path, schedule_request: dict,
        schedule_request_sha256: str, computed_at: datetime | None = None,
        valuation_basis_quote_binding: dict | None = None,
        complete_coverage_windows: list[dict] | None = None) -> dict:
    """Use actual calculation time, retaining old versions and event debt.

    This prepares a new research version, not historical contemporaneous input.
    Market inputs and approvals are deliberately not inherited across versions.
    The ordinary scheduler and application still decide whether the run is legal.
    """
    root = root.resolve()
    output_dir = require_inside(root / 'runtime', output_dir, 'pending candidate')
    if output_dir.exists():
        raise FileExistsError('pending candidate directory already exists')
    if computed_at is not None:
        raise ValueError('actual candidate preparation does not accept an injected computation time')
    if (valuation_basis_quote_binding is None) != (complete_coverage_windows is None):
        raise ValueError('valuation basis and complete coverage windows must be supplied together')
    now = datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError('candidate computation time requires timezone')
    source = load_json_object(package_path, 'candidate source package')
    policy = load_json_object(policy_path, 'candidate economic policy')
    if (policy.get('schema_version') in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA)
            and valuation_basis_quote_binding is not None):
        raise ValueError('ECONOMIC_TERMINAL_MATERIALITY_HANDOFF_NOT_VERSIONED')
    if choice_id not in {row['id'] for row in policy.get('choices', [])}:
        raise ValueError('candidate must select an existing finite choice')
    if schedule_request.get('symbol') != source['symbol']:
        raise ValueError('candidate schedule issuer mismatch')
    day = now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if day < source['point_in_time']['research_as_of']:
        raise ValueError('candidate cannot predate the retained research version')
    if valuation_basis_quote_binding is not None:
        _basis_quote(root, valuation_basis_quote_binding, source['symbol'], now)
    output_dir.mkdir(parents=True)
    proposal_path = output_dir / 'valuation-proposal.json'
    proposal = build_neutral_valuation_proposal(root=root, package_path=package_path,
        package_sha256=package_sha256, policy_path=policy_path,
        policy_sha256=policy_sha256, output_path=proposal_path)
    if computed_at is None:
        now = datetime.now(timezone.utc)
        day = now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    choice = next(row for row in proposal['choices'] if row['id'] == choice_id)
    inputs = choice['actual_calculation_inputs']
    basis_day, basis_close = day, None
    inherited_timing = source.get('facts', {}).get('valuation_timing')
    if valuation_basis_quote_binding is None:
        if inherited_timing:
            inherited_at = datetime.fromisoformat(inherited_timing['valuation_at'])
            if inherited_at.utcoffset() is None:
                raise ValueError('inherited valuation time requires timezone')
            basis_day = inherited_at.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
        else:
            basis_day = source['point_in_time']['report_period']
    if valuation_basis_quote_binding is not None:
        basis_day, basis_close = _basis_quote(root, valuation_basis_quote_binding, source['symbol'], now)
        if basis_day < source['point_in_time']['report_period']:
            raise ValueError('valuation basis cannot precede the financial report period')
    candidate = deepcopy(source)
    version = f"pending-{source['symbol']}-{day}-{choice_id}-{policy_sha256[:12]}"
    candidate.update(schema_version='m1-valuation-package-v2', package_version=version,
                     descriptor_version=version, run_id=version)
    candidate['point_in_time'].update(research_as_of=day, valuation_date=basis_day,
        available_at=now.isoformat(), computed_at=now.isoformat())
    catalog = {}
    official_identities = {}
    index_bindings = policy.get('issuer_index_bindings', [])
    for binding in index_bindings:
        index_path = require_inside(root, root / binding['path'], 'candidate issuer index')
        if sha256_file(index_path) != binding['sha256']:
            raise ValueError('candidate issuer index hash mismatch')
        index = load_json_object(index_path, 'candidate issuer index')
        for row in index.get('announcements', []):
            if str(row.get('secCode')) != source['symbol']:
                continue
            identity = dict(venue='CNINFO', security_code=str(row['secCode']),
                issuer_name=row.get('secName'), organization_id=row.get('orgId'))
            if not identity['issuer_name'] or not identity['organization_id']:
                raise ValueError('candidate issuer index identity fields missing')
            url = urljoin('https://static.cninfo.com.cn/', row.get('adjunctUrl', ''))
            if not url.endswith('/' + str(row.get('announcementId')) + '.PDF'):
                raise ValueError('candidate issuer index announcement/attachment mismatch')
            if url in official_identities and official_identities[url] != identity:
                raise ValueError('candidate issuer index conflicting identity')
            official_identities[url] = identity

    mode = proposal.get('input_mode')

    def add_source(item):
        item = deepcopy(item)
        local = item.get('local_path', item['location'])
        path = require_inside(root, root / local, 'candidate source')
        if not path.is_file() or sha256_file(path) != item['sha256']:
            from .historical_source_restore import ARCHIVABLE_RESEARCH_PREFIXES
            relative = str(local).replace('\\', '/')
            if (mode not in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA)
                    or not relative.startswith(ARCHIVABLE_RESEARCH_PREFIXES)):
                raise ValueError('candidate requires original identical local bytes')
            restored = output_dir / 'historical-source-code' / f"{item['sha256'].lower()}.blob"
            if not restored.is_file() or sha256_file(restored) != item['sha256'].lower():
                raise ValueError('candidate historical research restore is unavailable')
            path = restored
        item['local_path'] = path.relative_to(root).as_posix()
        if not item.get('source_available_at'):
            published = item.get('published_at')
            # Old date-level official disclosure gets a conservative next-day
            # boundary, not an invented intraday time. New research is known now.
            available = (datetime.fromisoformat(published) + timedelta(days=1)
                if item['kind'] == 'official_issuer_filing' and published else now)
            item['source_available_at'] = available.isoformat()
            item['availability_basis'] = ('conservative_next_day_disclosure'
                if item['kind'] == 'official_issuer_filing' and published else 'current_candidate_acquisition')
        if datetime.fromisoformat(item['source_available_at']) > now:
            raise ValueError('candidate source is after actual computation cutoff')
        previous = catalog.get(item['id'])
        if previous and (previous['local_path'], previous['sha256']) != (item['local_path'], item['sha256']):
            raise ValueError('candidate source identity conflict')
        catalog[item['id']] = item

    for item in source['sources']:
        # A predecessor quote remains bound through the immutable predecessor
        # package, but is not a current basis source for an unquoted candidate.
        if valuation_basis_quote_binding is None and item.get('id') == 'pending-valuation-basis':
            continue
        add_source(item)
    for index, binding in enumerate(index_bindings):
        add_source(dict(id=f'candidate-official-index-{index}', kind='research_artifact',
            location=binding['path'], local_path=binding['path'], sha256=binding['sha256'],
            source_available_at=now.isoformat(), availability_basis='current_candidate_acquisition',
            source_url='https://www.cninfo.com.cn/new/hisAnnouncement/query'))
    joint = mode in JOINT_MODES
    joint_label = ('本候选十年现金约束资本、分配及终端持续投入未获主模型批准'
                   if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA)
                   else '本候选五年联结资本及持续经营终端未获主模型批准')
    proposal_ref = dict(id=('pending-joint-proposal-' + sha256_file(proposal_path) if joint
                           else 'pending-economic-proposal'), path=proposal_path.relative_to(root).as_posix(),
                        sha256=sha256_file(proposal_path))
    for index, binding in enumerate(proposal['source_bindings'] + [proposal_ref]):
        lineage_id = ('joint-lineage-' + sha256((binding['path'] + '\n' + binding['sha256']).encode()).hexdigest()
                      if joint else f'candidate-lineage-{index}')
        add_source(dict(id=binding.get('id', lineage_id),
            kind='research_artifact', location=binding['path'], local_path=binding['path'],
            sha256=binding['sha256'], source_available_at=now.isoformat(),
            availability_basis='current_candidate_acquisition', retrieved_at=now.isoformat(),
            parser_version='pending-finite-research-candidate-v1'))
    add_source(dict(id=proposal_ref['id'], kind='research_artifact', location=proposal_ref['path'],
        sha256=proposal_ref['sha256'], source_available_at=now.isoformat(),
        availability_basis='current_candidate_acquisition'))
    refs = [proposal_ref]
    rebase = proposal.get('financial_rebase')
    financial_review = None
    if rebase:
        financial_review = load_financial_review_attachment(root=root, symbol=source['symbol'],
            manifest_path=root / rebase['manifest_path'], manifest_sha256=rebase['manifest_sha256'])
        for item in financial_review['source_bindings']:
            if item.get('id') and item.get('source_url'):
                add_source(dict(id=item['id'], kind='official_issuer_filing', location=item['source_url'],
                    local_path=item['path'], sha256=item['sha256'],
                    source_available_at=item['available_at_conservative'],
                    availability_basis='retained_conservative_disclosure_bound',
                    issuer_identity=official_identities.get(item['source_url'])))
        for legacy in catalog.values():
            if legacy.get('kind') != 'official_issuer_filing' or legacy.get('issuer_identity'):
                continue
            matches = [item for item in financial_review['source_bindings']
                if item['sha256'] == legacy['sha256']
                and item.get('source_url') in official_identities]
            if len(matches) == 1:
                matched = matches[0]
                legacy['location'] = matched['source_url']
                legacy['issuer_identity'] = deepcopy(official_identities[matched['source_url']])
                legacy['identity_basis'] = 'exact_announcement_index_and_identical_retained_pdf_bytes'

    case = candidate['research_case']
    case.update(as_of=day, run_id=version, generated_at=now.isoformat(), research_version=version,
                quote_date=None, valuation_status='CONDITIONAL_RESEARCH_PENDING_REVIEW')
    case.setdefault('missing_date_reasons', {})['quote_date'] = 'New pending model has no admitted quote.'
    case['blockers'] = list(dict.fromkeys([*case.get('blockers', []),
        'pending_economic_model_review', 'pending_complete_event_materiality_review']))
    case['blockers'] = [
        (joint_label if joint
         else '本候选优势期和全资本衰减未获主模型批准')
        if item == '现有强衰减压力情景不是中性主估值' else item
        for item in case['blockers']]
    if joint:
        case['blockers'] = list(dict.fromkeys(
            joint_label
            if any(term in item for term in ('全资本', '强衰减', 'STRESS_ONLY', 'Strong-fade'))
            else item for item in case['blockers']))
    case['evidence_refs'].append(proposal_ref)
    case['thesis'] += (' 本候选实际消费十年现金约束及终端持续投入假设：'
                       if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA)
                       else ' 本候选实际消费五年联结资本假设：' if joint
                       else ' 本候选实际消费既有有限方案：') + choice['rationale']
    if joint:
        narrative = _joint_narrative(source, choice, dict(
            path=package_path.relative_to(root).as_posix(), sha256=package_sha256), mode)
        for key in ('thesis', 'mispricing_hypothesis', 'positives', 'counter_evidence',
                    'thesis_breakers', 'next_events'):
            case[key] = narrative[key]
    case['counter_evidence'].append(dict(kind='hypothesis', text=choice['countercase'],
                                        evidence_refs=[proposal_ref['id']]))
    summary = case['financial_summary']
    summary.update(parent_equity_cny=inputs['start_book_equity'], ordinary_shares=inputs['ordinary_shares'])
    anchor_field = (policy['profit_anchor_field']
        if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA) else inputs['profit_anchor_field'])
    summary[anchor_field] = inputs['profit_anchor']
    summary['normalized_parent_profit_cny'] = None
    summary['pending_model_choice'] = choice_id
    summary['pending_model_limits'] = proposal['assurance_limits']
    if proposal.get('input_mode') in JOINT_MODES:
        summary['predecessor_research_narrative'] = narrative['predecessor_narrative']
        diagnostics = summary.get('profit_adjustment_research')
        if isinstance(diagnostics, dict):
            diagnostics.update(scope='PREDECESSOR_RESEARCH_NOT_CURRENT_JOINT_MODEL',
                predecessor_research_version=narrative['predecessor_narrative']['research_version'],
                predecessor_package_sha256=package_sha256)
        summary['pending_joint_capital_research'] = dict(
            input_mode=mode, scope='RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS',
            ledgers=deepcopy(choice['joint_capital_ledgers']), policy_sha256=policy_sha256,
            normalized_profit=None)
        if proposal['cash_funding_status'] == 'FAIL':
            case['blockers'].append('joint_parent_cash_funding_failed')
    if financial_review:
        summary['verified_financial_review'] = financial_review
        summary['financial_equity_bridge'] = rebase.get('equity_bridge_result')
    facts = candidate['facts']
    facts.update(as_of=basis_day, confidence='低', kind='quality_compounder')
    facts['operating_inputs'].update(start_book_equity=inputs['start_book_equity'],
                                     ordinary_shares=inputs['ordinary_shares'])
    facts['scenario_inputs'] = {name: {**values, 'forecast_roes': values['forecast_roe']}
                               for name, values in inputs['scenarios'].items()}
    for values in facts['scenario_inputs'].values():
        values.pop('forecast_roe')
    timing = inputs.get('valuation_timing') or inherited_timing
    if timing:
        timing = deepcopy(timing)
        if basis_close is not None:
            timing['valuation_at'] = basis_close
        elif (datetime.fromisoformat(timing['valuation_at'])
              .astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != basis_day):
            raise ValueError('historical valuation basis differs from inherited timing')
        timing['evidence_refs'] = refs
        facts['valuation_timing'] = timing
        candidate['dependencies']['model_version'] = 'residual-income-equity-shared-dated-v2'
    elif basis_close is not None:
        raise ValueError('prior-session basis requires existing explicit dated capital timing')
    if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        candidate['dependencies']['model_version'] = (
            'residual-income-equity-path-v4' if mode == JOINT_CASH_V4_SCHEMA
            else 'residual-income-equity-path-v3' if mode == JOINT_CASH_V3_SCHEMA
            else 'residual-income-equity-path-v2')
    facts['evidence_refs'] = list({ref['id']: ref for ref in [*facts['evidence_refs'], proposal_ref]}.values())
    if financial_review:
        consumed_financial_ids = {ref['id'] for ref in
            inputs.get('valuation_timing', {}).get('evidence_refs', [])}
        official_refs = [dict(id=item['id'], path=catalog[item['id']]['local_path'], sha256=item['sha256'])
            for item in financial_review['source_bindings'] if item.get('id') in consumed_financial_ids
            and item.get('source_url')]
        if not official_refs or any(not catalog[ref['id']].get('issuer_identity') for ref in official_refs):
            raise ValueError('rebased financial inputs require exact official issuer index bindings')
        # Old sources remain immutable lineage; operative rebased facts use the
        # independently verified official IDs rather than legacy local aliases.
        facts['evidence_refs'] = [proposal_ref, *official_refs]
    names = ['cost_of_equity', 'terminal_roe', 'terminal_growth', 'retention']
    count = len(facts['scenario_inputs']['base']['forecast_roes'])
    names += [f'forecast_roes_{i}' for i in range(count)]
    if mode in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        if count != 10 or any(len(row.get('forecast_retentions', [])) != 10
                              for row in facts['scenario_inputs'].values()):
            raise ValueError('joint cash path requires ten ROEs and annual retentions')
        names.remove('retention')
        names += [f'forecast_retentions_{i}' for i in range(count)]
    assumptions, bindings = [], []
    for name in names:
        vector = next((key for key in ('forecast_roes', 'forecast_retentions')
                       if name.startswith(key + '_')), None)
        index = int(name[len(vector)+1:]) if vector else None
        field = f'{vector}.{index}' if vector else name
        values = {key: scenario[vector][index] if vector else scenario[name]
                  for key, scenario in facts['scenario_inputs'].items()}
        numbers = [Decimal(values[key]) for key in ('bear', 'base', 'bull')]
        if numbers[0] <= numbers[1] <= numbers[2]:
            ordering = 'ascending'
        elif numbers[0] >= numbers[1] >= numbers[2]:
            ordering = 'descending'
        else:
            ordering = 'non_monotonic'
        assumptions.append(dict(name=name, unit='ratio', **values,
            basis=('pending_joint_capital_path_not_official_forecast' if joint
                   else 'pending_finite_shared_model_choice_not_official_forecast'),
            rationale=choice['rationale'] + ' 反证：' + choice['countercase'],
            confidence='low', sensitivity='high', ordering=ordering,
            evidence_refs=refs, blockers=[]))
        bindings.extend(dict(assumption_name=name, scenario=key, field_path=field,
            expected_value=value, evidence_refs=refs) for key, value in values.items())
    inherited_assumption_blockers = source['assumptions'].get('blockers', [])
    if joint:
        inherited_assumption_blockers = [
            'Joint capital and continuing-franchise assumptions remain pending economic approval.'
            if ('Strong-fade' in item or 'Selected finite model' in item) else item
            for item in inherited_assumption_blockers]
    candidate['assumptions'] = dict(assumptions=assumptions, evidence_refs=refs,
        blockers=[('Selected joint capital assumptions remain pending economic approval.' if joint
                   else 'Selected finite model assumptions remain pending economic approval.')
            if item == 'Strong-fade stress assumptions are not admitted as the neutral main valuation.' else item
            for item in inherited_assumption_blockers])
    candidate['assumption_bindings'] = bindings
    candidate['quote'] = None
    candidate.pop('entry_thesis', None)
    candidate.pop('investment_consistency_review', None)
    if joint:
        # Changed economic inputs never inherit an approval of the predecessor.
        for key in ('valuation_approval', 'human_research_approval',
                    'event_materiality_review', 'research_reviews'):
            candidate.pop(key, None)
    candidate['model_validity_input'] = dict(model_id=candidate['dependencies']['model_version'],
        valid_from=basis_day, events=[], blockers=['pending_complete_event_materiality_review'])
    candidate['dependencies']['scan_watermark'] = None
    contract = deepcopy(source.get('source_contract', {}))
    contract.update(schema_version='source-bound-research-inputs-v1', cutoff_at=now.isoformat(),
        distribution_input_status='NOT_ADMITTED', strict_contemporaneous_pit='NOT_PROVEN',
        fact_semantics_scope='source_anchored_capital_and_historical_profit_not_normalized_forecast')
    if rebase:
        contract['fact_anchors'] = [dict(field=field, source_id=rebase[field]['source_id'],
            physical_page=rebase[field]['physical_page'], source_value=rebase[field]['value'],
            unit=rebase[field]['unit'], scope=('consolidated_parent_equity' if field == 'start_book_equity'
                else 'issued_ordinary_shares'), period_end=rebase[field]['period_end'])
            for field in ('start_book_equity', 'ordinary_shares')]
    candidate['source_contract'] = contract
    candidate['supersedes'] = dict(path=package_path.relative_to(root).as_posix(),
        sha256=package_sha256, reason='new pending finite research candidate, not approved/current admission')
    sealed_package_path = package_path
    sealed_policy_path = policy_path
    coverage = None
    if valuation_basis_quote_binding is not None:
        from .source_bound_inputs import source_catalog_sha256

        for key in ('valuation_approval', 'human_research_approval',
                    'event_materiality_review', 'research_reviews'):
            candidate.pop(key, None)
        scan = _coverage_scan(root, candidate, complete_coverage_windows, basis_day, now)
        scan_path = output_dir / 'event-scan.json'
        write_new_json(scan_path, scan)
        scan_binding = dict(path=scan_path.relative_to(root).as_posix(), sha256=sha256_file(scan_path))
        ref = dict(id='pending-event-' + scan_binding['sha256'], symbol=source['symbol'], **scan_binding)
        candidate['model_validity_input'].update(event_scan_ref=ref, event_scan_evidence_refs=[ref])
        candidate['dependencies']['scan_watermark'] = scan_binding['sha256']
        for identity, binding in (('pending-valuation-basis', valuation_basis_quote_binding),
                                  (ref['id'], scan_binding)):
            add_source(dict(id=identity, kind='research_artifact', location=binding['path'],
                local_path=binding['path'], sha256=binding['sha256'], retrieved_at=now.isoformat(),
                source_available_at=now.isoformat(), availability_basis='ACTUAL_READ_NOT_HISTORICAL_PIT',
                parser_version='pending-finite-research-candidate-v1'))
        contract.update(event_coverage_status='COMPLETE',
            source_catalog_sha256=source_catalog_sha256(list(catalog.values())))
        coverage = dict(observation_bindings=deepcopy(complete_coverage_windows),
            scan_binding=scan_binding, coverage_from=scan['scan_from'], review_cutoff=basis_day)
    candidate['sources'] = list(catalog.values())
    # Sources may gain exact issuer identity and retained-filing metadata even
    # when no quote/event coverage is requested. Bind the final catalog, not
    # the predecessor catalog inherited before those source mutations.
    from .source_bound_inputs import source_catalog_sha256
    contract['source_catalog_sha256'] = source_catalog_sha256(candidate['sources'])
    candidate['recommendation_schema_version'] = 'advisory-decision-recommendation-v3'
    if mode in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        from .historical_source_restore import verify_or_restore_package_sources
        retained_sources = verify_or_restore_package_sources(root, candidate,
            restore_dir=output_dir / 'historical-source-code')
        # A newly sealed v3 package must remain readable after repository code or
        # research configs move on. Rebind only its local byte locator to the
        # content-addressed candidate closure; preserve source ids, URLs, dates and
        # hashes, and keep the predecessor package itself separately bound below.
        rebound = []
        retained_locations = {}
        for source_item, (verified_path, digest) in zip(
                candidate['sources'], retained_sources, strict=True):
            if digest != source_item['sha256'].lower():
                raise ValueError('retained economic-terminal source order or identity mismatch')
            item = deepcopy(source_item)
            old_path = item['local_path']
            new_path = verified_path.relative_to(root).as_posix()
            aliases = {old_path, item.get('location')}
            for alias in aliases:
                if not isinstance(alias, str):
                    continue
                identity = (alias, digest)
                prior = retained_locations.get(identity)
                if prior is not None and prior != new_path:
                    raise ValueError('economic-terminal retained source path identity conflict')
                retained_locations[identity] = new_path
            item['local_path'] = new_path
            rebound.append(item)
        candidate['sources'] = rebound

        def retain_top_level_source(source_path, digest):
            retained = output_dir / 'historical-source-code' / f'{digest.lower()}.blob'
            if retained.exists():
                if sha256_file(retained) != digest.lower():
                    raise ValueError('top-level research source closure drift')
            else:
                retained.parent.mkdir(parents=True, exist_ok=True)
                with retained.open('xb') as handle:
                    handle.write(source_path.read_bytes())
            if sha256_file(retained) != digest.lower():
                raise ValueError('top-level research source closure is unavailable')
            return retained

        sealed_package_path = retain_top_level_source(package_path, package_sha256)
        sealed_policy_path = retain_top_level_source(policy_path, policy_sha256)
        retained_locations[(package_path.relative_to(root).as_posix(),
                            package_sha256.lower())] = sealed_package_path.relative_to(root).as_posix()
        retained_locations[(policy_path.relative_to(root).as_posix(),
                            policy_sha256.lower())] = sealed_policy_path.relative_to(root).as_posix()
        candidate['supersedes']['path'] = sealed_package_path.relative_to(root).as_posix()

        def rebind_reference(value):
            if isinstance(value, list):
                return [rebind_reference(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {key: rebind_reference(item) for key, item in value.items()}
            digest = result.get('sha256', '').lower()
            # ``location`` may be the immutable public URL and is part of the
            # evidence identity.  Only repository-local locators are rebound.
            for location_key in ('path', 'local_path'):
                location = result.get(location_key)
                retained = retained_locations.get((location, digest))
                if retained is not None:
                    result[location_key] = retained
            return result

        candidate = rebind_reference(candidate)
        candidate['source_contract']['source_catalog_sha256'] = source_catalog_sha256(candidate['sources'])
    else:
        verify_package_local_sources(root, candidate)
    descriptor = build_descriptor_for_package(candidate, root=root)
    spec = build_research_run_spec(descriptor)
    if mode == JOINT_CASH_V4_SCHEMA:
        from ..research.v4_review_context import build_v4_research_review_model_context
        context = build_v4_research_review_model_context(descriptor=descriptor, spec=spec)
        from ..research.v4_valuation_router import build_v4_valuation_router
        valuation_router = build_v4_valuation_router()
    elif mode == JOINT_CASH_V3_SCHEMA:
        from ..research.v3_review_context import build_v3_research_review_model_context
        context = build_v3_research_review_model_context(descriptor=descriptor, spec=spec)
        from ..research.v3_valuation_router import build_v3_valuation_router
        valuation_router = build_v3_valuation_router()
    else:
        context = build_research_review_model_context(descriptor=descriptor, spec=spec)
        valuation_router = None
    package_output = output_dir / 'package.json'
    write_new_json(package_output, candidate)
    workbench_path = output_dir / 'workbench.json'
    workbench = build_current_workbench_for_symbol(root=root, symbol=source['symbol'],
        package_path=package_output, output_path=workbench_path, schedule_request=schedule_request,
        schedule_request_sha256=schedule_request_sha256,
        recommendation_schema_version='advisory-decision-recommendation-v3',
        valuation_router=valuation_router)['result']
    if (mode in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA)
            and _valuation_economics(workbench.get('valuation')) != _valuation_economics(choice['valuation'])):
        raise ValueError('economic-terminal proposal valuation differs from shared application consumption')
    if workbench.get('decision_recommendation'):
        build_research_review_packet(root=root, package_path=package_output,
            package_sha256=sha256_file(package_output), workbench_path=workbench_path,
            workbench_sha256=sha256_file(workbench_path), output_path=output_dir / 'consumed-review.json')
    if coverage is not None:
        from .research_materiality_reviews import prepare_materiality_review_handoff

        handoff = prepare_materiality_review_handoff(root=root, package_path=package_output,
            package_sha256=sha256_file(package_output), scan_path=scan_path,
            scan_sha256=scan_binding['sha256'])
        if handoff['model_context'] != context:
            raise ValueError('candidate materiality handoff differs from the consumed model context')
        handoff_path = output_dir / 'materiality-handoff.json'
        write_new_json(handoff_path, handoff)
        coverage['handoff_binding'] = dict(path=handoff_path.relative_to(root).as_posix(),
                                            sha256=sha256_file(handoff_path))
    result = dict(schema_version='pending-research-candidate-v1', symbol=source['symbol'],
        status='PENDING_REVIEW', action='no_order', generated_at=now.isoformat(),
        candidate_research_as_of=day, financial_period=source['point_in_time']['report_period'],
        prior_research_as_of=source['point_in_time']['research_as_of'],
        selected_choice=choice_id, choice_rationale=choice['rationale'], countercase=choice['countercase'],
        retained_date_valuation=choice['valuation'],
        candidate_valuation=workbench.get('valuation'),
        model_context=context, approval_changed=False, research_admitted=False,
        model_context_scope=('ACTUALLY_CONSUMED' if workbench.get('decision_recommendation')
                             else 'PREPARED_NOT_CONSUMED'),
        execution_status=workbench.get('suggested_state'),
        schedule_gate=workbench.get('schedule_gate'),
        research_blockers=workbench.get('research_blockers', []),
        price_admitted=False, position_guidance=None, canonical_written=False,
        registered_current_case_changed=False, strict_contemporaneous_pit='NOT_PROVEN',
        event_coverage='NOT_REVIEWED_FOR_NEW_CANDIDATE',
        date_semantics='New unapproved research computed at actual time; old report basis and raw public dates retained; no historical PIT/current data admission.',
        model_limits=proposal['assurance_limits'], review_questions=proposal['economic_review_items'],
        review_groups=deepcopy(policy.get('human_review_groups', [])),
        economic_policy_binding=dict(path=sealed_policy_path.relative_to(root).as_posix(),
                                     sha256=policy_sha256),
        source_bindings=[dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
            for path in (sealed_package_path, sealed_policy_path, proposal_path,
                          package_output, workbench_path)],
        implementation_bindings=[dict(path=name, sha256=sha256_file(root / name))
            for name in ('src/value_investment_agent/application/product/pending_research_candidate.py',)
            if (root / name).is_file()],
        recommendation_type=workbench.get('suggested_state'),
        decision_blockers=list(dict.fromkeys([
            *(workbench.get('decision_recommendation') or {}).get('blockers', []),
            *workbench.get('research_blockers', [])])))
    for group in result['review_groups']:
        if (not isinstance(group, dict) or not all(isinstance(group.get(key), str) and group[key].strip()
                for key in ('id', 'question', 'support', 'countercase', 'impact'))
                or not isinstance(group.get('field_paths'), list) or not group['field_paths']):
            raise ValueError('economic review groups require concrete questions, evidence and scope')
        for field_path in group['field_paths']:
            value = candidate
            for key in field_path.split('.'):
                if not isinstance(value, dict) or key not in value:
                    raise ValueError('economic review group references an absent candidate field')
                value = value[key]
    all_sources = {item['path']: item for item in result['source_bindings']}
    if coverage is not None:
        result.update(valuation_basis_date=basis_day, valuation_basis_scope=VALUATION_BASIS_SCOPE,
            basis_binding=deepcopy(valuation_basis_quote_binding), coverage_binding=coverage,
            event_coverage='COMPLETE_PENDING_MATERIALITY_REVIEW', materiality_approved=False,
            current_market_validity_approved=False,
            date_semantics='Ex-post computation on retained prior-session basis; actual research, '
                'availability and computation times retained; not historical PIT or current validity.')
        for binding in [coverage['handoff_binding'], *scan['evidence_refs']]:
            all_sources[binding['path']] = dict(path=binding['path'], sha256=binding['sha256'])
        packet_path = output_dir / 'consumed-review.json'
        if packet_path.is_file():
            all_sources[packet_path.relative_to(root).as_posix()] = dict(
                path=packet_path.relative_to(root).as_posix(), sha256=sha256_file(packet_path))
    if mode in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        from .historical_source_restore import verify_or_restore_package_sources
        verified_candidate_sources = verify_or_restore_package_sources(
            root, candidate, restore_dir=output_dir / 'historical-source-code', create=False)
    else:
        verified_candidate_sources = verify_package_local_sources(root, candidate)
    for path, digest in verified_candidate_sources:
        if sha256_file(path) != digest:
            raise ValueError('candidate source changed during shared application run')
        relative = path.relative_to(root).as_posix()
        all_sources[relative] = dict(path=relative, sha256=digest)
    result['source_bindings'] = list(all_sources.values())
    if proposal.get('input_mode') in JOINT_MODES:
        result['input_mode'] = mode
        result['implementation_bindings'] = list({item['path']: item for item in [
            *result['implementation_bindings'], *proposal['implementation_bindings']]}.values())
        packet_path = output_dir / 'consumed-review.json'
        if workbench.get('decision_recommendation'):
            packet_binding = dict(path=packet_path.relative_to(root).as_posix(), sha256=sha256_file(packet_path))
            result['review_packet_binding'] = packet_binding
            all_sources[packet_binding['path']] = packet_binding
            result['source_bindings'] = list(all_sources.values())
    write_new_json(output_dir / 'candidate.json', result)
    return result


def verify_pending_research_candidate(*, root: Path, path: Path, expected_sha256: str) -> dict:
    """Bind visible candidate values to actual shared application artifacts."""
    from .decision_surface import verify_current_decision_workbench

    root = root.resolve()
    path = require_inside(root / 'runtime', path, 'pending candidate receipt')
    if sha256_file(path) != expected_sha256:
        raise ValueError('pending candidate receipt hash mismatch')
    data = load_json_object(path, 'pending candidate')
    if (data.get('schema_version') != 'pending-research-candidate-v1'
            or data.get('status') != 'PENDING_REVIEW' or data.get('action') != 'no_order'
            or any(data.get(key) is not False for key in ('approval_changed', 'research_admitted',
                'price_admitted', 'canonical_written', 'registered_current_case_changed'))
            or data.get('position_guidance') is not None
            or data.get('strict_contemporaneous_pit') != 'NOT_PROVEN'):
        raise ValueError('pending candidate admission boundary mismatch')
    sources = data.get('source_bindings')
    if not isinstance(sources, list) or not sources:
        raise ValueError('pending candidate source bindings missing')
    for item in sources:
        original = require_inside(root, root / item['path'], 'pending candidate source')
        if sha256_file(original) != item['sha256']:
            raise ValueError('pending candidate source drift')
    if data.get('input_mode') in JOINT_MODES:
        _joint_implementations(data.get('implementation_bindings'), data.get('input_mode', JOINT_SCHEMA))
    for item in data.get('implementation_bindings', []):
        implementation = require_inside(root, root / item['path'], 'candidate implementation')
        if sha256_file(implementation) != item['sha256']:
            raise ValueError('pending candidate implementation drift')
    package_path = path.parent / 'package.json'
    workbench_path = path.parent / 'workbench.json'
    if not {package_path.relative_to(root).as_posix(), workbench_path.relative_to(root).as_posix()}.issubset(
            {item['path'] for item in sources}):
        raise ValueError('pending candidate actual inputs and outputs not bound')
    package = load_json_object(package_path, 'candidate package')
    policy_binding = data['economic_policy_binding']
    policy_path = require_inside(root, root / policy_binding['path'], 'candidate economic policy')
    if policy_binding not in sources or sha256_file(policy_path) != policy_binding['sha256']:
        raise ValueError('candidate economic policy binding mismatch')
    policy = load_json_object(policy_path, 'candidate economic policy')
    if (policy.get('schema_version') in JOINT_MODES or data.get('input_mode') in JOINT_MODES):
        if policy.get('schema_version') != data.get('input_mode'):
            raise ValueError('joint candidate policy/input mode mismatch')
    if data.get('input_mode') in JOINT_MODES:
        _joint_implementations(data.get('implementation_bindings'), data.get('input_mode', JOINT_SCHEMA))
    if data.get('review_groups') != policy.get('human_review_groups', []):
        raise ValueError('candidate review questions differ from economic policy')
    descriptor = build_descriptor_for_package(package, root=root)
    spec = build_research_run_spec(descriptor)
    if data.get('input_mode') == JOINT_CASH_V4_SCHEMA:
        from ..research.v4_review_context import build_v4_research_review_model_context
        context = build_v4_research_review_model_context(descriptor=descriptor, spec=spec)
    elif data.get('input_mode') == JOINT_CASH_V3_SCHEMA:
        from ..research.v3_review_context import build_v3_research_review_model_context
        context = build_v3_research_review_model_context(descriptor=descriptor, spec=spec)
    else:
        context = build_research_review_model_context(descriptor=descriptor, spec=spec)
    if data.get('input_mode') in JOINT_MODES:
        _verify_joint_economic_inputs(root=root, path=path, data=data, policy=policy,
            package=package, descriptor=descriptor)
    basis_keys = {'valuation_basis_date', 'valuation_basis_scope', 'basis_binding', 'coverage_binding'}
    if basis_keys.intersection(data) or any(
            source.get('id') == 'pending-valuation-basis' for source in package.get('sources', [])):
        from .event_scan_supplement import _read
        from .research_materiality_reviews import prepare_materiality_review_handoff

        if not basis_keys.issubset(data) or data['valuation_basis_scope'] != VALUATION_BASIS_SCOPE:
            raise ValueError('candidate valuation basis scope or bindings missing')
        generated = datetime.fromisoformat(data['generated_at'])
        now = datetime.now(timezone.utc)
        if generated.utcoffset() is None or generated > now:
            raise ValueError('candidate basis generation time is unavailable')
        # Admission was current at actual generation; later audit does not admit today's market.
        basis_day, close = _basis_quote(root, data['basis_binding'], package['symbol'], generated)
        pit = package['point_in_time']
        coverage = data['coverage_binding']
        if (data['basis_binding'] not in sources
                or data['valuation_basis_date'] != basis_day
                or pit['valuation_date'] != basis_day or package['facts']['as_of'] != basis_day
                or package['model_validity_input']['valid_from'] != basis_day
                or package['facts'].get('valuation_timing', {}).get('valuation_at') != close
                or pit['research_as_of'] != generated.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
                or any(datetime.fromisoformat(pit[key]) != generated for key in ('available_at', 'computed_at'))
                or datetime.fromisoformat(package['source_contract']['cutoff_at']) != generated
                or package.get('quote') is not None
                or any(package.get(key) is not None for key in ('valuation_approval',
                    'human_research_approval', 'event_materiality_review', 'research_reviews'))
                or any(data.get(key) is not False for key in ('materiality_approved',
                    'current_market_validity_approved'))
                or data.get('event_coverage') != 'COMPLETE_PENDING_MATERIALITY_REVIEW'):
            raise ValueError('candidate valuation basis dates or admission boundary mismatch')
        expected_scan = _coverage_scan(root, package, coverage['observation_bindings'], basis_day, generated)
        scan_binding = coverage['scan_binding']
        handoff_binding = coverage['handoff_binding']
        ref = package['model_validity_input'].get('event_scan_ref', {})
        if (coverage['coverage_from'] != expected_scan['scan_from'] or coverage['review_cutoff'] != basis_day
                or _read(root, scan_binding) != expected_scan
                or any(ref.get(key) != scan_binding[key] for key in ('path', 'sha256'))
                or package['dependencies']['scan_watermark'] != scan_binding['sha256']
                or any(dict(path=b['path'], sha256=b['sha256']) not in sources
                       for b in [scan_binding, handoff_binding, *expected_scan['evidence_refs']])):
            raise ValueError('candidate complete coverage differs from acquired originals')
        expected_handoff = prepare_materiality_review_handoff(root=root,
            package_path=package_path, package_sha256=sha256_file(package_path),
            scan_path=root / scan_binding['path'], scan_sha256=scan_binding['sha256'])
        if (_read(root, handoff_binding) != expected_handoff or expected_handoff['model_context'] != context):
            raise ValueError('candidate materiality handoff differs from exact model context')
    workbench = load_json_object(workbench_path, 'candidate actual workbench')
    consumed = bool(workbench.get('decision_recommendation'))
    if data.get('input_mode') in (JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        terminal_proposal = load_json_object(path.parent / 'valuation-proposal.json', 'economic-terminal candidate proposal')
        terminal_choices = [row for row in terminal_proposal['choices']
            if row['id'] == data['selected_choice']]
        if len(terminal_choices) != 1:
            raise ValueError('economic-terminal candidate must bind one exact proposal choice')
        if (_valuation_economics(workbench.get('valuation'))
                != _valuation_economics(terminal_choices[0]['valuation'])):
            raise ValueError('economic-terminal proposal valuation differs from consumed workbench valuation')
        expected_candidate_valuation = workbench.get('valuation')
    else:
        expected_candidate_valuation = workbench.get('valuation')
    if (data['symbol'] != package['symbol'] or workbench['symbol'] != package['symbol']
            or data['candidate_research_as_of'] != package['point_in_time']['research_as_of']
            or data['model_context'] != context
            or data['candidate_valuation'] != expected_candidate_valuation
            or data.get('model_context_scope') != ('ACTUALLY_CONSUMED' if consumed else 'PREPARED_NOT_CONSUMED')
            or data.get('execution_status') != workbench.get('suggested_state')
            or data.get('research_blockers') != workbench.get('research_blockers', [])
            or data.get('schedule_gate') != workbench.get('schedule_gate')):
        raise ValueError('pending candidate differs from exact research inputs or outputs')
    if workbench.get('decision_recommendation'):
        from .research_reviews import verify_human_approval_transport_provenance
        verify_current_decision_workbench(
            workbench,
            human_approval_provenance_verifier=lambda approval: (
                verify_human_approval_transport_provenance(root, approval)
            ),
        )
        if workbench.get('input_descriptor_sha256') != descriptor.input_sha256:
            raise ValueError('pending candidate descriptor differs from actual consumption')
        if data.get('input_mode') in JOINT_MODES:
            packet_path = path.parent / 'consumed-review.json'
            binding = dict(path=packet_path.relative_to(root).as_posix(), sha256=sha256_file(packet_path))
            if data.get('review_packet_binding') != binding or binding not in sources:
                raise ValueError('joint candidate consumed review packet binding mismatch')
            expected = project_research_review_packet(root=root, package_path=package_path,
                package_sha256=sha256_file(package_path), workbench_path=workbench_path,
                workbench_sha256=sha256_file(workbench_path))
            if load_json_object(packet_path, 'joint consumed review packet') != expected:
                raise ValueError('joint candidate consumed review packet differs from exact inputs')
    if data.get('input_mode') in (JOINT_CASH_SCHEMA, JOINT_CASH_V3_SCHEMA, JOINT_CASH_V4_SCHEMA):
        for ref in [*data['source_bindings'], *data['implementation_bindings']]:
            if sha256_file(require_inside(root, root/ref['path'], 'joint cash final replay binding')) != ref['sha256']:
                raise ValueError('joint cash source/implementation changed during replay')
    if sha256_file(path) != expected_sha256:
        raise ValueError('pending candidate changed during verification')
    return data
