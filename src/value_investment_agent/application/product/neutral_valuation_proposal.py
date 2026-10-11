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
from ...m1_valuation_package_builder import build_descriptor
from ...valuation_models.residual_income import (
    QualityCompounderFacts, ResidualIncomeEquityValuationModel,
    ResidualIncomeScenarioInputs, current_projection, _shared_scenario_calculation,
    valuation_time_factor,
)


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
    if (policy.get('schema_version') != 'finite-earnings-path-proposal-v1'
            or policy.get('action') != 'no_order' or policy.get('symbol') != package.get('symbol')
            or policy.get('source_package_sha256') != package_sha256):
        raise ValueError('proposal policy identity/version mismatch')
    sources = [(package_path, package_sha256), (policy_path, policy_sha256),
               *verify_package_local_sources(root, package)]
    for binding in policy.get('rationale_bindings', []):
        path = require_inside(root, root / binding['path'], 'proposal rationale')
        if sha256_file(path) != binding['sha256']:
            raise ValueError('proposal rationale hash mismatch')
        sources.append((path, binding['sha256']))
    if not policy.get('rationale_bindings'):
        raise ValueError('proposal requires independently reviewable economic rationale')
    descriptor = build_descriptor(package, root=root)
    facts, case = descriptor.facts, descriptor.research_case
    if not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs:
        raise ValueError('proposal requires the existing registered equity model inputs')
    anchor_field = policy.get('profit_anchor_field')
    if not isinstance(anchor_field, str):
        raise ValueError('proposal earnings anchor requires a declared parent-profit financial field')
    anchor = _profit_anchor(root, package, case, anchor_field)
    choices = policy.get('choices')
    if (not isinstance(choices, list) or not 1 <= len(choices) <= 3
            or len({row['id'] for row in choices}) != len(choices)):
        raise ValueError('proposal requires one to three distinct economic choices')
    growths = policy.get('income_growth')
    if not isinstance(growths, dict) or set(growths) != {'bear', 'base', 'bull'}:
        raise ValueError('proposal requires explicit three-scenario earnings conditions')
    model = ResidualIncomeEquityValuationModel()
    baseline = model.value(facts, case)
    if baseline.status != 'conditional_research_only':
        raise ValueError('proposal baseline is not a usable conditional calculation')
    book, shares = facts.operating_inputs['start_book_equity'], facts.operating_inputs['ordinary_shares']
    rows = []
    for choice in choices:
        years, fade = choice['growth_years'], choice['fade_years']
        if (type(years) is not int or type(fade) is not int or not 1 <= years <= 20
                or not 1 <= fade <= 20 or not choice.get('rationale') or not choice.get('countercase')):
            raise ValueError('proposal choice requires bounded duration, rationale and countercase')
        scenarios = {}
        for name, original in facts.scenario_inputs.items():
            growth = Decimal(str(growths[name]))
            if not growth.is_finite() or not Decimal('-0.10') <= growth <= Decimal('0.10'):
                raise ValueError('proposal growth exceeds the registered research bounds')
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
    result = dict(schema_version='finite-neutral-valuation-proposal-v1', symbol=case.symbol,
        status='NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW', action='no_order',
        generated_at=datetime.now(timezone.utc).isoformat(),
        original_research_as_of=case.as_of.isoformat(),
        original_valuation_date=baseline.valuation_date.isoformat(),
        date_semantics='New proposal computed now on retained financial/date basis; not a contemporaneous historical or current admitted valuation.',
        source_descriptor_sha256=descriptor.input_sha256,
        baseline_valuation=json.loads(baseline.to_json()), choices=rows,
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
    anchor_label = ('历史扣非归母盈利代理' if anchor_field == 'ttm_ex_nonrecurring_parent_profit_cny'
                    else '历史报告归母盈利代理')
    lines = [f'# {case.name}：主估值候选待审', '',
        '以下是同一剩余收益模型的条件研究备选，不是批准公允价值或买点。', '',
        f'{anchor_label}：{anchor / Decimal("100000000"):.2f}亿元；正常化盈利仍未确认。',
        f'原研究截止：{case.as_of}；新提案生成：{result["generated_at"]}。没有推进事件或价格准入。', '',
        '| 尾部选择 | 条件低档/中档/高档（元/股） | 中档相对旧压力 |', '| --- | --- | --- |']
    for row in rows:
        value = row['valuation']
        lines.append(f'| {row["id"]}：{row["growth_years"]}年盈利段＋{row["fade_years"]}年全资本衰减 | '
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
