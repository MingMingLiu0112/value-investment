"""Explain verified public workflow progress without granting investment authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .public_strategy_assessment import project_strategy_decision


def _object(value):
    return value if isinstance(value, dict) else {}


def _texts(value):
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return str(value) if parsed.is_finite() and parsed > 0 else None


def _date(value):
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value, str) else None
    except ValueError:
        return None


def _step(key, label, status, reason):
    return dict(key=key, label=label, status=status, reason=reason)


def _gap(code, category, summary, next_action, url):
    return dict(code=code, category=category, summary=summary, next_action=next_action, url=url)


def build_strategy_readiness(item: dict, packet: dict | None) -> dict:
    """Consume application-verified rows; READY describes a step, never a trade.

    Published hashes and current-case checks remain the caller's responsibility.
    This projection has no private account, signing, mutation or order capability.
    """
    symbol = item.get("symbol")
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("Readiness requires an exact security identity")
    hotspot = item.get("strategy") in {"hotspot", "HOTSPOT_SATELLITE"}
    strategy = "HOTSPOT_SATELLITE" if hotspot else "CORE_VALUE"
    plan = _object(item.get("price_action_plan"))
    try:
        view = project_strategy_decision(plan, symbol=symbol)
        if view["strategy"] != strategy:
            raise ValueError("Strategy mismatch")
    except (TypeError, ValueError):
        plan = {}
    packet = _object(packet)
    trusted = (packet.get("action") == "no_order"
               and packet.get("packet_status") == "CURRENT"
               and packet.get("source_bindings_verified") is True
               and isinstance(packet.get("publication_id"), str)
               and bool(packet["publication_id"]))
    company = _object(_object(packet.get("company_statuses")).get(symbol)) if trusted else {}
    valuation = _object(_object(packet.get("valuation_statuses")).get(symbol)) if trusted else {}
    if company.get("symbol") != symbol:
        company = {}
    if valuation.get("symbol") != symbol:
        valuation = {}
    output = dict(schema_version="strategy-readiness-v1", strategy=strategy,
        action="no_order", authorization_granted=False, steps=[], primary_gap=None,
        conditional_valuation=None, price_snapshot=None,
        independent_of_value_valuation=hotspot)
    steps = output["steps"]
    steps.append(_step("screen", "候选入选", "READY", "已列入本次展示范围；初筛不等于投资批准。"))
    if hotspot:
        _hotspot(output, plan, symbol)
    else:
        _value(output, company, valuation, plan, symbol, packet if trusted else {})
    steps.append(_step("portfolio", "双策略组合容量", "NOT_EVALUATED",
        "公开研究不读取私人账户；需核验现金、双策略预算、同股及行业集中度和原始持仓逻辑。"))
    steps.append(_step("human_decision", "人工操作复核", "PENDING",
        "策略确认与个人操作确认分别保留；本流程不下单，也不凭进度标签批准交易。"))
    return output


def _value(output, company, valuation, plan, symbol, packet):
    steps = output["steps"]
    url = f"/decisions/{symbol}"
    registered = _object(company.get("registered_research"))
    missing = _texts(registered.get("missing_inputs"))
    steps.append(_step("research", "基本面与财务研究", "PARTIAL" if company else "PENDING",
        registered.get("summary") or "尚未绑定完整的公司研究，初筛结果不能代替财务分析。"))
    values = _object(valuation.get("conditional_range"))
    scenario_date = _date(_object(valuation.get("price_comparison")).get("valuation_date"))
    scenario_date = scenario_date or _date(_object(packet.get("dates")).get("research_as_of"))
    # A revalidated pending candidate is a separate version, not a rewrite of
    # the frozen publication. Invalid current analysis must not reuse its values.
    analysis = _object(plan.get("research_analysis")) if packet else {}
    if analysis:
        values, scenario_date = {}, None
        if (analysis.get("schema_version") == "value-research-analysis-v1"
                and analysis.get("symbol") == symbol and analysis.get("action") == "no_order"
                and analysis.get("status") == "CONDITIONAL_ANALYSIS_VERIFIED"
                and analysis.get("arithmetic_complete") is True
                and analysis.get("economic_assumptions_reviewed") is False
                and analysis.get("action_admitted") is False):
            scenarios = analysis.get("scenarios")
            if (isinstance(scenarios, list) and len(scenarios) == 3
                    and all(isinstance(row, dict) for row in scenarios)
                    and {row.get("scenario") for row in scenarios} == {"bear", "base", "bull"}):
                values = {row["scenario"]: row.get("per_share_value") for row in scenarios}
                scenario_date = _date(analysis.get("valuation_date"))
    numbers = [_number(values.get(key)) for key in ("bear", "base", "bull")]
    complete = (all(numbers) and scenario_date is not None
                and Decimal(numbers[0]) <= Decimal(numbers[1]) <= Decimal(numbers[2]))
    if complete:
        output["conditional_valuation"] = dict(zip(("bear", "base", "bull"), numbers))
        output["conditional_valuation"].update(currency=values.get("currency", "CNY"),
            as_of=scenario_date, scope="UNAPPROVED_RESEARCH_ONLY")
    steps.append(_step("valuation", "情景估值与假设", "PARTIAL" if complete else "PENDING",
        "悲观、中性、乐观情景已有计算；经济假设及适用性须独立复核，不能直接当作买入价。"
        if complete else "当前展示尚无完整绑定的三情景估值；不代表不存在历史研究底稿。"))
    validity = (_object(analysis.get("model_validity")) if analysis else
        _object(valuation.get("model_validity")) or _object(_object(company.get("price_bridge")).get("model_validity")))
    valid = validity.get("status") == "VALID" and validity.get("blockers") == []
    steps.append(_step("model_validity", "重大事件与模型有效性", "READY" if valid else "PENDING",
        "当前绑定模型有效性已核验，估值和操作批准仍须分别判断。" if valid
        else "当前模型有效性尚未确立；新公告及原经济假设须完成重大性复核。"))
    price, trade_date = _number(plan.get("reference_close")), _date(plan.get("market_trade_date"))
    if price and trade_date and plan.get("current_quote_verified") is True:
        output["price_snapshot"] = dict(value=price, date=trade_date, usage="DISPLAY_ONLY")
    steps.append(_step("price", "报价与价值比较", "PARTIAL" if output["price_snapshot"] else "PENDING",
        "已核验收盘报价，可作事实展示；是否能比较价值和形成操作条件仍由价格桥判断。"
        if output["price_snapshot"] else "当前价尚未与有效估值完成可用比较；不清空已有研究情景。"))
    conditions = all(isinstance(plan.get(key), dict) for key in
        ("entry_condition", "add_condition", "reduce_condition", "exit_condition"))
    steps.append(_step("action_policy", "买入与加减仓条件", "PARTIAL" if conditions else "PENDING",
        "已有条件计划，仍需原假设、价格政策和人工批准一致。" if conditions
        else "尚未形成完整适用的买入、加仓、减仓、退出价格与逻辑条件。"))
    actions = company.get("pending_actions")
    actions = [x for x in actions if isinstance(x, dict)] if isinstance(actions, list) else []
    evidence_action = next((x for x in actions if x.get("code") == "REGISTERED_RESEARCH_GAP"), None)
    if missing or not complete:
        output["primary_gap"] = _gap("RESEARCH_INPUTS_INCOMPLETE", "RESEARCH",
            missing[0] if missing else "缺少可用的完整估值输入与情景。",
            evidence_action.get("label") if evidence_action else "补齐有来源的财务输入与有依据的假设，生成研究情景后复核。", url)
    elif not valid:
        output["primary_gap"] = _gap("MODEL_AND_EVENT_REVIEW_PENDING", "REVIEW",
            "已有研究情景，但当前模型和事件复核未闭合。", "核验新公告影响、关键假设和模型适用性，再提交现有复核流程。", url)
    else:
        output["primary_gap"] = _gap("VALUE_ACTION_REVIEW_PENDING", "REVIEW",
            "研究结果不自动授予交易资格。", "复核价格政策、个人组合容量与买卖一致性。", url)


def _hotspot(output, plan, symbol):
    steps = output["steps"]
    decision_id = plan.get("decision_id")
    safe_id = decision_id if isinstance(decision_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", decision_id) else symbol
    url = f"/decisions/{safe_id}?independent_hotspot=true"
    periods = _object(plan.get("period_structure"))
    period_states = {"UPTREND", "DOWNTREND", "RANGE", "BREAKOUT", "BREAKDOWN"}
    structured = all(periods.get(key) in period_states for key in ("daily", "60m", "15m"))
    state = plan.get("signal_state")
    unusable = state in {"STALE", "BLOCKED", "EXPIRED", "HISTORICAL_OBSERVATION_NOT_ADMITTED"} or not plan
    steps.append(_step("structure", "趋势与完整周期结构", "PARTIAL" if structured and not unusable else "PENDING",
        "已有日线、60分钟与15分钟结构观察；仍须核验触发、成交空间及失效条件。"
        if structured and not unusable else "当前结构来源或有效期尚不可用，旧价位不能当作当前入场条件。"))
    admission = _object(plan.get("independent_admission"))
    steps.append(_step("validation", "独立波段策略验证", "PARTIAL" if admission else "PENDING",
        "波段独立于价值估值；需真实时点数据、样本外、成本及观察验证和对应版本批准。"))
    price, trade_date = _number(plan.get("current_reference_price")), _date(plan.get("market_trade_date"))
    if price and trade_date and not unusable:
        output["price_snapshot"] = dict(value=price, date=trade_date, usage="DISPLAY_ONLY")
    steps.append(_step("price", "行情与计划时效", "PARTIAL" if output["price_snapshot"] else "PENDING",
        "已保留带日期的参考价；不等于可以按该价格成交。" if output["price_snapshot"]
        else "当前有效参考价未确立，过期价位不用于操作。"))
    conditions = all(isinstance(plan.get(key), dict) for key in
        ("entry_condition", "add_condition", "reduce_condition", "exit_condition"))
    steps.append(_step("action_policy", "突破、加仓与退出条件", "PARTIAL" if conditions and not unusable else "PENDING",
        "有条件计划；加仓和卖出仍需核实已有持仓、原始逻辑及可卖数量。" if conditions and not unusable
        else "需完整结构确认、入场条件、失效价位及费用后空间，不能仅凭热度操作。"))
    output["primary_gap"] = (_gap("CURRENT_STRUCTURE_UNAVAILABLE", "DATA",
        "当前价格结构或源文件验证未通过。", "核验行情日期、原始K线和当前计划绑定，保留历史观察但停止使用旧入场价。", url)
        if unusable else _gap("HOTSPOT_VALIDATION_AND_REVIEW_PENDING", "STRATEGY_VALIDATION",
        "结构观察不等于波段策略已验证或获准使用。", "查看真实回放、费用、样本外及观察证据，再确认对应策略版本；不需要价值估值先通过。", url))


def attach_strategy_readiness(summary: dict, items: list[dict], packet: dict | None) -> dict:
    result = deepcopy(summary)
    if len(result.get("items", [])) != len(items):
        raise ValueError("Readiness requires the complete evaluated row set")
    for row, item in zip(result.get("items", []), items):
        if row.get("symbol") != item.get("symbol"):
            raise ValueError("Readiness cannot cross security identities")
        row["readiness"] = build_strategy_readiness(item, packet)
    return result
