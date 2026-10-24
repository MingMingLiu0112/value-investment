"""Read-only economic explanations from verified native inputs and existing kernels.

No alternative candidate, signature, current registry, forecast engine or approval
is created. Diagnostic ratios/first-year identities are not new financial models.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from .common import require_inside, sha256_file
from .incremental_validity import read_bound_json
from .source_native_candidate_v2 import SCHEMA as NATIVE_SCHEMA, verify_source_native_candidate, _equal_numbers
from ...domain.valuation.source_native_cash_v1 import replay_timing_delay_inputs
from ...domain.valuation.joint_adverse_cash_v1 import diagnose_joint_adverse_cash
from ..research.operating_earnings_bridge import research_from_retained_sources
from ...m1_valuation_package_builder import build_descriptor
from ...valuation_models.residual_income import _shared_scenario_calculation

SCHEMA = 'source-native-economic-review-v1'
KE_CHALLENGE_DELTA = Decimal('0.02')
JOINT_SOURCE_SPEC = 'docs/current/two-company-earnings-bridge-20261024/sources.json'
JOINT_SCOPE = 'MECHANICAL_COUNTEREXAMPLE_NOT_FORECAST_OR_ACCOUNTING_FACT'
IMPLEMENTATIONS = (
    'src/value_investment_agent/application/product/source_native_economic_review_v1.py',
    'src/value_investment_agent/application/product/source_native_candidate_v2.py',
    'src/value_investment_agent/domain/valuation/source_native_cash_v1.py',
    'src/value_investment_agent/valuation_models/residual_income.py',
    'src/value_investment_agent/domain/valuation/joint_adverse_cash_v1.py',
    'src/value_investment_agent/application/research/operating_earnings_bridge.py',
    'src/value_investment_agent/infrastructure/filings/pdf_text.py',
    'src/value_investment_agent/infrastructure/filings/pdfium_runtime.py',
)
GROUP_NOTES = {
    'EARNINGS': ('\u76c8\u5229\u57fa\u7840',
        '\u62ab\u9732\u548c\u5386\u53f2\u5229\u6da6\u4e0d\u7b49\u4e8e\u6b63\u5e38\u5316\u672a\u6765\u5229\u6da6\uff1b\u6210\u672c\u3001\u7a0e\u53ca\u7ecf\u5e38\u91d1\u878d\u8d21\u732e\u7684\u65b0\u53d8\u5316\u4ecd\u662f\u53cd\u8bc1\u3002'),
    'DISTRIBUTION': ('\u73b0\u91d1\u5206\u914d',
        '\u6bcd\u516c\u53f8\u73b0\u91d1\u3001\u5408\u5e76\u5229\u6da6\u4e0e\u6cd5\u5b9a\u53ef\u5206\u914d\u5229\u6da6\u4e0d\u80fd\u4e92\u6362\u3002\u73b0\u91d1\u5e95\u7ebf\u662f\u5206\u6790\u653f\u7b56\uff0c'
        '\u4e0d\u8ba4\u8bc1\u5168\u90e8\u652f\u4ed8\u4e49\u52a1\u3001\u672a\u6765\u5206\u7ea2\u80fd\u529b\u6216\u6bcf\u4e2a\u652f\u4ed8\u65e5\u7684\u6d41\u52a8\u6027\u3002'),
    'DURATION': ('\u73b0\u91d1\u65f6\u5e8f',
        '\u9996\u5e74\u6682\u7559\u3001\u7b2c\u4e8c\u5e74\u5168\u989d\u6536\u56de\u662f\u53ef\u8bc1\u4f2a\u7684\u65f6\u5e8f\u5047\u8bf4\u3002\u672a\u6309\u671f\u6536\u56de\u6216\u6301\u7eed\u53d7\u9650\u5e94\u91cd\u5f00\u7814\u7a76\uff0c'
        '\u4e0d\u80fd\u7ee7\u7eed\u6cbf\u7528\u672c\u5206\u652f\uff1b\u5e74\u5ea6\u9884\u7b97\u95ed\u5408\u4e0d\u7b49\u4e8e\u5e74\u5185\u652f\u4ed8\u5b89\u5168\u3002'),
    'COST_TERMINAL': ('\u8d44\u672c\u6210\u672c\u4e0e\u7ec8\u503c',
        'DDM\u7ec8\u7aef\u80a1\u606f\u5360\u6bd4\u4e0eRI\u7ec8\u7aef\u5269\u4f59\u6536\u76ca\u5360\u6bd4\u7684\u5206\u5b50\u53e3\u5f84\u4e0d\u540c\u3002\u4e8c\u8005\u5bf9\u5e73\u4e0d\u8bc1\u660e'
        '\u7ec8\u7aef\u5168\u989d\u5206\u914d\u3001\u96f6\u589e\u957f\u6216\u8d44\u672c\u6210\u672c\u5408\u7406\uff1bKe\u6311\u6218\u4e0d\u662f\u76ee\u6807\u4ef7\u6216\u65b0\u5019\u9009\u6279\u51c6\u3002'),
    'EVENT_MODEL': ('\u4e8b\u4ef6\u4e0e\u6a21\u578b\u8fb9\u754c',
        '\u5386\u53f2\u80a1\u672c\u5206\u6bcd\u4e0e\u8d22\u52a1\u57fa\u51c6\u4e0d\u662f\u5f53\u524d\u80a1\u672c\u548c\u62a5\u4ef7\u8d44\u683c\u3002\u672c\u89c6\u56fe\u53ea\u89e3\u91ca\u672a\u6279\u51c6\u5019\u9009\uff0c'
        '\u4e0d\u6838\u9a8c\u6ce8\u518c\u5f53\u524dG3\u3001\u5f53\u524d\u4e8b\u4ef6\u3001\u6a21\u578b\u6709\u6548\u6027\u6216\u4ef7\u683c\u51c6\u5165\u3002'),
}


def _bound(root, ref):
    if (not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}
            or not isinstance(ref['path'], str) or not isinstance(ref['sha256'], str)):
        raise ValueError('Economic review requires exact path/hash bindings')
    path = require_inside(root, root / ref['path'], 'economic review source')
    if (path.relative_to(root).as_posix() != ref['path'] or sha256_file(path) != ref['sha256']):
        raise ValueError('Economic review source identity/hash drift')
    return path


def _json(root, ref):
    path = _bound(root, ref)
    _, value = read_bound_json(root, ref, 'native economic review')
    _bound(root, ref)
    return path, value


def _closure(root, refs):
    result = {}
    for ref in refs:
        if ref['path'] in result and result[ref['path']] != ref:
            raise ValueError('Economic review conflicting source identities')
        _bound(root, ref)
        result[ref['path']] = deepcopy(ref)
    return list(result.values())


def _kernel_projection(facts, scenario):
    """Only use kernel totals/rows; derived fractions are presentation diagnostics."""
    calculation = _shared_scenario_calculation(facts, scenario)
    factor = Decimal(calculation.get('basis_to_valuation_factor', '1'))
    ddm_total = Decimal(calculation['dividend_crosscheck_equity_value_cny'])
    explicit_dividend_pv = sum((Decimal(row['dividend_assumption_cny']) / Decimal(row['discount_factor'])
        for row in calculation['forecast_years']), Decimal(0)) * factor
    terminal_dividend_pv = ddm_total - explicit_dividend_pv
    return dict(kernel_calculation=calculation, per_historical_share_cny=calculation['per_share_value'],
        ddm_terminal_pv_cny=str(terminal_dividend_pv), ddm_explicit_pv_cny=str(explicit_dividend_pv),
        ddm_terminal_fraction=str(terminal_dividend_pv / ddm_total),
        ri_terminal_fraction=calculation['terminal_residual_contribution_ratio'],
        ri_terminal_pv_cny=str(Decimal(calculation['present_value_terminal_residual_income_cny']) * factor),
        convention='DDM_TERMINAL_DIVIDENDS_VS_RI_TERMINAL_RESIDUAL_NOT_INTERCHANGEABLE')


def _decimal_strings(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _decimal_strings(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_decimal_strings(item) for item in value]
    return value


def _joint_adverse_review(root, package, ledger, clock, refs):
    """Optional cold-original diagnostic; never substitute saved bridge results."""
    def unsupported(reason):
        return dict(status='UNSUPPORTED', reason=reason, rows=[], scope=JOINT_SCOPE, action='no_order')

    if not (root/JOINT_SOURCE_SPEC).is_file():
        return unsupported('No applicable retained earnings source specification')
    try:
        spec_ref = dict(path=JOINT_SOURCE_SPEC, sha256=sha256_file(root/JOINT_SOURCE_SPEC))
        _, specification = _json(root, spec_ref)
        refs.extend(_closure(root, [spec_ref]))
        executing_root = Path(__file__).resolve().parents[4]
        if sha256_file(executing_root/JOINT_SOURCE_SPEC) != spec_ref['sha256']:
            raise ValueError('Joint source specification differs from executing root')
        if (specification['schema_version'] != 'two-company-earnings-source-spec-v1'
                or specification['action'] != 'no_order'
                or specification['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'):
            raise ValueError('Unsupported joint source specification contract')
        symbol = package['research_case']['symbol']
        specs = deepcopy(specification['companies'].get(symbol))
        if not specs:
            return unsupported('No applicable company source specification')
        summary = package['research_case']['financial_summary']
        reconciliation = summary.get('historical_profit_reconciliation')
        if not reconciliation:
            return unsupported('No bound historical profit reconciliation')
        source_rows = reconciliation['source_rows']
        if (reconciliation['symbol'] != symbol or reconciliation['action'] != 'no_order'
                or reconciliation['report_period'] != package['facts']['as_of']
                or len(source_rows) != 3
                or [row['period'] for row in source_rows] != ['FY2025', 'H1_2026', 'H1_2025']
                or len(specs) != 2):
            raise ValueError('Joint earnings period/company identity mismatch')
        for spec, rows, periods in zip(specs, (source_rows[:1], source_rows[1:]),
                (['FY2025', 'FY2024'], ['H12026', 'H12025'])):
            row = rows[0]
            catalog = [item for item in package['sources'] if item['id'] == spec['source_id']]
            if len(catalog) != 1:
                raise ValueError('Joint earnings source must have one catalog identity')
            source = catalog[0]
            if (spec['symbol'] != symbol or spec['periods'] != periods
                    or source['issuer_identity']['security_code'] != symbol
                    or source['issuer_identity']['issuer_name'] != spec['issuer']
                    or source['kind'] != 'official_issuer_filing'
                    or source['local_path'] != row['path']
                    or source['location'] != spec['source_url']
                    or source['sha256'] != spec['sha256']):
                raise ValueError('Joint official source identity mismatch')
            for item in rows:
                if (item['source_id'] != spec['source_id'] or item['sha256'] != spec['sha256']
                        or item['source_url'] != spec['source_url'] or item['path'] != row['path']
                        or item['currency'] != 'CNY' or item['profit_basis'] != 'attributable_to_parent'
                        or item['statement_scope'] != 'consolidated'):
                    raise ValueError('Joint reconciliation source identity mismatch')
                reviewed = datetime.fromisoformat(item['reviewed_at'])
                if reviewed.utcoffset() is None or reviewed > clock:
                    raise ValueError('Joint reconciliation review is unavailable')
            published = datetime.fromisoformat(source['published_at'])
            if (published.utcoffset() is None
                    or published.astimezone(timezone(timedelta(hours=8))).date().isoformat() != spec['published_date']):
                raise ValueError('Joint publication date mismatch')
            for key in ('retrieved_at', 'source_available_at', 'original_retrieved_at', 'original_source_available_at'):
                available = datetime.fromisoformat(source[key])
                if available.utcoffset() is None or not published <= available <= clock:
                    raise ValueError('Joint source availability mismatch')
            spec['path'] = row['path']
            spec['original_acquired_at'] = source['original_retrieved_at']
            spec['fields'] = specification['common_fields'] + spec.get('extra_fields', [])
            refs.extend(_closure(root, [dict(path=spec['path'], sha256=spec['sha256'])]))
        bridge = research_from_retained_sources(root=root, specs=specs, now=clock)
        annual, interim = [item['rows']['ex_parent_profit'] for item in bridge['original_statements']]
        observed = (annual['values'][0], interim['values'][0], interim['values'][1])
        if any(Decimal(row['ex_nonrecurring_profit_cny']) != Decimal(value)
               for row, value in zip(source_rows, observed)):
            raise ValueError('Joint cold original differs from bound earnings rows')
        anchor = Decimal(bridge['ttm']['lines_cny']['ex_parent_profit'])
        if (anchor != Decimal(summary['ttm_ex_nonrecurring_parent_profit_cny'])
                or anchor != Decimal(reconciliation['ttm_ex_nonrecurring_parent_profit_cny'])):
            raise ValueError('Joint cold TTM differs from package anchor')
        result = diagnose_joint_adverse_cash(annual_profit_fact=annual, profit_anchor=anchor,
            plan=ledger['plan'], history=ledger['history'],
            opening_book=package['facts']['operating_inputs']['start_book_equity'],
            project_budget=ledger['cases']['TIMING_DELAY']['base']['project_budget'])
        if result['status'] == 'UNSUPPORTED':
            return unsupported(result.get('unsupported_reason') or 'Domain diagnostic unsupported')
        _closure(root, refs)
        return _decimal_strings(result)
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError, StopIteration) as error:
        return unsupported('Joint diagnostic failed closed: ' + str(error))


def _first_year_boundary(plan, case):
    first = case['annual_rows'][0]
    profit = Decimal(first['profit'])
    cash, floor = Decimal(first['opening_parent_cash']), Decimal(case['cash_floor'])
    project, fund = Decimal(first['project_cash']), Decimal(first['fund_capital_call'])
    retention = Decimal(plan['explicit_retention'])
    boundary = retention + (cash - project - fund - floor) / profit
    return dict(status='CASH_ONLY_FIRST_YEAR_IDENTITY',
        method='ALGEBRAIC_PROJECTION_OF_KERNEL_VERIFIED_FIRST_YEAR_ROW_NOT_NEW_LEDGER_REPLAY',
        formula='C1=C0+(retention-h)*P1-project1-fund1; C1>=F',
        original_withheld_fraction=plan['TIMING_DELAY']['withheld_fraction'],
        cash_only_delay_boundary_fraction=str(boundary), boundary_within_zero_one=0 <= boundary <= 1,
        original_cash_above_floor_cny=str(Decimal(first['cash_close']) - floor),
        inputs=dict(opening_parent_cash_cny=str(cash), analytical_floor_cny=str(floor),
            first_year_profit_cny=str(profit), project_cny=str(project), fund_call_cny=str(fund), retention=str(retention)),
        limitations=['First year only; fixed profit, payout, floor, project and fund timing.',
            'Not a delay probability, long-term safety threshold or approved strategy parameter.',
            'Retained-profit/legal/payment-date constraints may bind earlier; no alternative cash ledger is certified.',
            'Year-two release and later cash-income feedback require separate research.'])


def build_source_native_economic_review(*, root: Path, candidate_binding: dict,
                                      review_document_binding: dict | None = None,
                                      now: datetime | None = None) -> dict:
    """Return company-page-ready research diagnostics without current/approval reads or writes."""
    root = root.resolve()
    candidate_binding, review_document_binding = deepcopy(candidate_binding), deepcopy(review_document_binding)
    clock = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.utcoffset() is None:
        raise ValueError('Economic review requires an aware trusted clock')
    path, candidate = _json(root, candidate_binding)
    envelope = dict(schema_version=SCHEMA, action='no_order', candidate_binding=candidate_binding,
        approval_changed=False, research_admitted=False, price_admitted=False,
        formal_eligibility=False, strategy_approved=False, position_guidance=None,
        canonical_written=False, registered_current_case_changed=False)
    if candidate.get('schema_version') == 'pending-research-candidate-v1':
        _bound(root, candidate_binding)
        return dict(envelope, status='NOT_APPLICABLE', reason='Native TIMING_DELAY RI inputs required',
            scope='UNASSESSED_NON_NATIVE_CANDIDATE', scenarios=[])
    if candidate.get('schema_version') != NATIVE_SCHEMA:
        raise ValueError('Unsupported native economic candidate schema')
    if verify_source_native_candidate(root=root, path=path,
            expected_sha256=candidate_binding['sha256'], now=clock) != candidate:
        raise ValueError('Economic candidate changed during verification')
    _, package = _json(root, candidate['source_package_binding'])
    _, ledger = _json(root, candidate['native_cash_ledger_binding'])
    descriptor = build_descriptor(package, root=root)
    if descriptor.requested_model not in (None, 'residual_income_or_equity_value'):
        raise ValueError('Native economic review requires the consumed RI model')
    code_root = Path(__file__).resolve().parents[3]
    impl = []
    for name in IMPLEMENTATIONS:
        ref = dict(path=name, sha256=sha256_file(root/name))
        if sha256_file(code_root.parent/name) != ref['sha256']:
            raise ValueError('Economic review implementation differs from executing code')
        impl.append(ref)
    refs = _closure(root, [candidate_binding, *candidate['source_bindings'], *impl,
        *([review_document_binding] if review_document_binding is not None else [])])
    facts = descriptor.facts
    with localcontext() as context:
        context.prec = 48
        consumed = replay_timing_delay_inputs(plan=ledger['plan'], scenarios=ledger['cases']['TIMING_DELAY'],
            opening_book=facts.operating_inputs['start_book_equity'], history=ledger['history'])
        challenge_plan = deepcopy(ledger['plan'])
        challenge_plan['ke'] = str(Decimal(challenge_plan['ke']) + KE_CHALLENGE_DELTA)
        challenge_error = None
        try:
            challenge_inputs = replay_timing_delay_inputs(plan=challenge_plan, scenarios=ledger['cases']['TIMING_DELAY'],
                opening_book=facts.operating_inputs['start_book_equity'], history=ledger['history'])
        except ValueError as error:
            challenge_inputs, challenge_error = None, str(error)
        scenarios = []
        for name in ('bear', 'base', 'bull'):
            given, case = facts.scenario_inputs[name], ledger['cases']['TIMING_DELAY'][name]
            if not _equal_numbers(consumed[name], package['facts']['scenario_inputs'][name]):
                raise ValueError('Economic cash replay differs from consumed scenarios')
            original = _kernel_projection(facts, given)
            recorded = Decimal(candidate['candidate_valuation'][name+'_value'])
            quantum = Decimal(1).scaleb(recorded.as_tuple().exponent)
            if Decimal(original['per_historical_share_cny']).quantize(quantum) != recorded:
                raise ValueError('Economic kernel valuation differs from original candidate')
            original['candidate_per_historical_share_cny'] = str(recorded)
            original['matches_candidate_at_recorded_precision'] = True
            try:
                if challenge_inputs is None:
                    raise ValueError('Existing cash kernel cannot replay challenge: ' + challenge_error)
                if {k:v for k,v in challenge_inputs[name].items() if k != 'cost_of_equity'} != {
                        k:v for k,v in consumed[name].items() if k != 'cost_of_equity'}:
                    raise ValueError('Ke-only challenge changed cash/economic assumptions')
                challenged = _kernel_projection(facts, replace(given,
                    cost_of_equity=Decimal(challenge_inputs[name]['cost_of_equity'])))
                challenge = dict(status='CONDITIONAL_KERNEL_SENSITIVITY', delta_basis_points=200,
                    original_ke=str(given.cost_of_equity), challenged_ke=challenge_inputs[name]['cost_of_equity'],
                    changed_fields=['cost_of_equity'], result=challenged,
                    cash_ledger_scope='ORIGINAL_CASH_TRANSITIONS_UNCHANGED_KE_ONLY',
                    alternative_candidate_verified=False, interpretation='Not fair value, target price or price admission.')
            except ValueError as error:
                challenge = dict(status='UNSUPPORTED', reason=str(error), delta_basis_points=200,
                    alternative_candidate_verified=False)
            scenarios.append(dict(scenario=name, original=original, ke_plus_200bp=challenge,
                annual_cash_rows=deepcopy(case['annual_rows']),
                cash_replay_scope='ALL_TRANSITIONS_VERIFIED_BY_EXISTING_NATIVE_KERNEL',
                first_year_boundary=_first_year_boundary(ledger['plan'], case)))
    summary = package['research_case']['financial_summary']
    joint_adverse_cash = _joint_adverse_review(root, package, ledger, clock, refs)
    groups = [dict(deepcopy(group), title=GROUP_NOTES[group['id']][0],
        interpretation=GROUP_NOTES[group['id']][1], approval_status='PENDING_NOT_APPROVED',
        evidence_bindings=deepcopy(refs)) for group in candidate['review_groups']]
    result = dict(envelope, status='CONDITIONAL_ECONOMIC_RESEARCH', symbol=candidate['symbol'],
        confidence='LOW', scope='PENDING_NATIVE_CANDIDATE_NOT_PRIMARY_OR_CURRENT_VALUATION',
        g3_status='NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE', current_g3_status='NOT_QUERIED',
        strict_contemporaneous_pit='NOT_PROVEN', evaluated_at=clock.isoformat(),
        point_in_time=deepcopy(package['point_in_time']), model_context=deepcopy(candidate['model_context']),
        share_basis=dict(ordinary_shares=str(facts.operating_inputs['ordinary_shares']),
            financial_basis=facts.as_of.isoformat(), scope='BOUND_HISTORICAL_MODEL_DENOMINATOR_NOT_CURRENT_SHARES',
            current_shares=None, corporate_action_comparability='NOT_ASSESSED',
            evidence_refs=deepcopy(package['facts']['evidence_refs'])),
        source_catalog=deepcopy(package['sources']), source_bindings=refs,
        editorial_review=dict(binding=review_document_binding,
            scope='EDITORIAL_CONTEXT_NOT_NUMERIC_SOURCE_OR_PIT_OR_APPROVAL'),
        normalized_parent_profit_cny=None,
        normalized_profit_status='NOT_VERIFIED_OR_ADMITTED_BY_THIS_READ_MODEL',
        historical_profit_reconciliation=dict(status='BOUND_PACKAGE_DISCLOSURE_NOT_NEW_NORMALIZATION',
            reported_reconciliation=deepcopy(summary.get('historical_profit_reconciliation'))),
        plan_assumptions=deepcopy(ledger['plan']), history_scope=ledger['history']['scope'],
        historical_unknowns=deepcopy(ledger['history'].get('unknowns', [])),
        counter_evidence=deepcopy(package['research_case']['counter_evidence']),
        thesis_breakers=deepcopy(package['research_case']['thesis_breakers']),
        five_groups=groups, scenarios=scenarios, joint_adverse_cash=joint_adverse_cash,
        unsupported_challenges=[dict(id=name, status='UNSUPPORTED', reason=reason) for name, reason in (
            ('PERSISTENT_UPSTREAM_RESTRICTION', 'Frozen cash kernel requires full release in year two; no replacement ledger built.'),
            ('TERMINAL_APPROPRIATION_CONTINUES', 'Frozen cash kernel requires conditional terminal appropriation zero.'),
            ('DELAY_BOUNDARY_FULL_PATH', 'First-year algebra is not a new cash ledger or multi-year stress validation.'))])
    if verify_source_native_candidate(root=root, path=path,
            expected_sha256=candidate_binding['sha256'], now=clock) != candidate:
        raise ValueError('Economic candidate changed during projection')
    _closure(root, refs)
    return result
