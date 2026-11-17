"""Recalculate an existing annual cash plan against source-bound nine-month facts.

This is an explicit retained-plan sensitivity, not an adopted E1 successor.
The caller must still review all capital, debt and distribution policies.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .direct_owner_cash_research_v1 import replay_direct_owner_cash_receipt, _read
from .parent_direct_cash_research import read_parent_direct_cash_research, _bound
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.quarterly_parent_operating_facts import (
    parse_quarterly_parent_operating_facts, build_quarterly_parent_operating_observations,
)
from ...domain.valuation.parent_remaining_year_cash import build_parent_remaining_year_cash
from ...domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path
from ..product.common import require_inside


def review_parent_remaining_year(*, root, receipt_binding, source, period_end, now,
                                 capital_policy_mode="RETAIN_ANNUAL_PLAN"):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("REMAINING_REVIEW_AWARE_TIME_REQUIRED")
    if not isinstance(source, dict) or set(source) != {"path", "sha256", "url", "acquired_at"}:
        raise ValueError("REMAINING_REVIEW_EXACT_SOURCE_REQUIRED")
    if not re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF", source["url"]):
        raise ValueError("REMAINING_REVIEW_OFFICIAL_SOURCE_REQUIRED")
    acquired = datetime.fromisoformat(source["acquired_at"])
    published = date.fromisoformat(source["url"].split("/")[-2])
    if (acquired.utcoffset() is None or acquired > now
            or published > acquired.astimezone(ZoneInfo("Asia/Shanghai")).date()
            or date.fromisoformat(period_end) > published):
        raise ValueError("REMAINING_REVIEW_SOURCE_NOT_AVAILABLE")
    if (not source["path"].startswith("runtime/") or "\\" in source["path"]
            or ".." in source["path"].split("/")
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])):
        raise ValueError("REMAINING_REVIEW_SOURCE_BINDING_INVALID")
    path = require_inside(root / "runtime", root / source["path"], "remaining year source")
    if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("REMAINING_REVIEW_SOURCE_CHANGED")
    receipt = _read(root, receipt_binding)
    spec = _read(root, receipt["spec_binding"])
    original = replay_direct_owner_cash_receipt(root=root, receipt_binding=receipt_binding, now=now)
    if capital_policy_mode not in {"RETAIN_ANNUAL_PLAN", "REPORTED_9M_PLUS_PRIOR_Q4"}:
        raise ValueError("REMAINING_REVIEW_CAPITAL_POLICY_MODE_UNSUPPORTED")
    pages = extract_pages(path)
    kwargs = dict(symbol=spec["symbol"], issuer_name=spec["issuer_name"], period_end=period_end)
    facts = parse_quarterly_parent_operating_facts(pages, **kwargs)
    observed = build_quarterly_parent_operating_observations(pages, **kwargs)
    for row in observed:
        row["source_refs"] = [dict(ref, **source) for ref in row["source_refs"]]
        row["source_binding_required"] = False
    current, comparative = observed
    histories = [row for binding in spec["operating_sources"]
        for row in read_parent_direct_cash_research(root=root, receipt_binding=binding,
            evaluated_at=now)["observed"]
        if row["period_end"] == f"{int(period_end[:4])-1}-12-31"]
    if len(histories) != 1 or int(spec["valuation_date"][:4]) + 1 != int(period_end[:4]):
        raise ValueError("REMAINING_REVIEW_EXACT_FIRST_YEAR_HISTORY_REQUIRED")
    results = {}
    with localcontext() as ctx:
        ctx.prec = 48
        for name, scenario in original["compiled"]["scenarios"].items():
            forecast = original["compiled"]["operating_forecasts"][name][0]
            assumption = forecast["assumptions"]
            other_actual = Decimal(current["cfo"]) - Decimal(current["customer_cash"]) + Decimal(current["supplier_cash"])
            q4 = dict(symbol=spec["symbol"], scope=spec["scope"], currency="CNY",
                classification="FORECAST_ASSUMPTION", period_start=f"{period_end[:4]}-10-01",
                period_end=f"{period_end[:4]}-12-31",
                revenue=str(Decimal(assumption["revenue"]) - Decimal(current["revenue"])),
                cost=str(Decimal(assumption["cost"]) - Decimal(current["cost"])),
                other_operating_cash=str(Decimal(assumption["other_operating_cash"]) - other_actual),
                source_refs=[receipt_binding, source],
                rationale="保留原全年收入成本及其他经营现金假设；扣除已发生九个月，剩余季度按上年同季收付机制重算。不是自动采纳全年目标。",
                counter_evidence="剩余季度目标可能已不合理，同季收付与税费可能变化；历史差分不保证未来实现。",
                reopen_condition="新的同口径经营事实、收付政策或全年经营目标变化时重开研究。")
            annual = None
            try:
                annual = build_parent_remaining_year_cash(historical_full_year=histories[0],
                    historical_nine_months=comparative, current_nine_months=current,
                    q4_forecast=q4, as_of=now.date())
                rows = deepcopy(scenario["years"])
                rows[0]["policy"]["operating_cash"] = annual["full_year"]["cfo"]["total"]
                policy = rows[0]["policy"]
                previous_capex = str(Decimal(policy["maintenance_capex"]) + Decimal(policy["growth_capex"]))
                policy_changes = {}
                if capital_policy_mode == "REPORTED_9M_PLUS_PRIOR_Q4":
                    statements = [s for s in original["compiled"]["evidence"]["statements"]
                        if s["period_end"] == histories[0]["period_end"]]
                    if len(statements) != 1:
                        raise ValueError("REMAINING_REVIEW_PRIOR_FY_CAPITAL_SOURCE_REQUIRED")
                    statement = statements[0]
                    for target, section, annual_field, quarter_field in (
                        ("gross_capex", "cash_flow", "gross_capex_cny", "cash_capex"),
                        ("investment_cash_received", "cash_flow", "investment_income_cash_cny", "investment_income_cash_cny"),
                    ):
                        reported = facts["cash_fields"][quarter_field]
                        old_year = Decimal(statement[section][annual_field]["current"])
                        prior_q4 = old_year - Decimal(reported["comparative"])
                        if prior_q4 < 0:
                            raise ValueError("REMAINING_REVIEW_NEGATIVE_PRIOR_Q4_CAPITAL_FLOW:" + target)
                        updated = Decimal(reported["current"]) + prior_q4
                        policy_changes[target] = dict(classification="FORECAST_ASSUMPTION",
                            fact_9m=reported["current"], assumed_q4=str(prior_q4), full_year=str(updated),
                            rationale="当年九个月原件事实加上年同季度支出/收现的条件假设；非未来承诺或必然重复。",
                            counter_evidence="项目支付与子公司分红有时点波动，上年第四季度不代表当年必然实现。")
                        if target == "gross_capex":
                            old_total = Decimal(policy["maintenance_capex"]) + Decimal(policy["growth_capex"])
                            if old_total <= 0:
                                raise ValueError("REMAINING_REVIEW_CAPEX_MIX_ASSUMPTION_REQUIRED")
                            maintenance = updated * Decimal(policy["maintenance_capex"]) / old_total
                            policy["maintenance_capex"] = str(maintenance)
                            policy["growth_capex"] = str(updated - maintenance)
                            policy_changes[target]["allocation_scope"] = "RETAINED_FORECAST_MAINTENANCE_GROWTH_RATIO_NOT_REPORTED_FACT"
                        else:
                            policy[target] = str(updated)
                # Full-year plans cannot silently fall below cash already spent
                # or received; expose a conflict instead of fabricating Q4.
                if Decimal(policy["maintenance_capex"]) + Decimal(policy["growth_capex"]) < Decimal(facts["cash_fields"]["cash_capex"]["current"]):
                    raise ValueError("REMAINING_REVIEW_ANNUAL_CAPEX_BELOW_REPORTED_9M")
                if Decimal(policy["investment_cash_received"]) < Decimal(facts["cash_fields"]["investment_income_cash_cny"]["current"]):
                    raise ValueError("REMAINING_REVIEW_ANNUAL_INVESTMENT_RECEIPTS_BELOW_REPORTED_9M")
                calculation = compile_direct_owner_cash_path(opening=scenario["opening"],
                    years=rows, terminal=scenario["terminal"], ordinary_shares=scenario["ordinary_shares"],
                    cost_of_equity=scenario["cost_of_equity"], scope=spec["scope"], currency="CNY")
                q4_profit = Decimal(policy["parent_profit"])-Decimal(facts["fields"]["net_profit"]["current"])
                q4_cash = Decimal(annual["full_year"]["cfo"]["forecast_q4"])
                warnings = []
                if q4_profit < 0:
                    warnings.append("RETAINED_ANNUAL_PROFIT_IMPLIES_Q4_LOSS")
                if q4_cash < 0:
                    warnings.append("RETAINED_PLAN_IMPLIES_Q4_OPERATING_CASH_OUTFLOW")
                results[name] = dict(status="CONDITIONAL_RECALCULATION_NOT_ADOPTED", annual=annual,
                    calculation=calculation, retained_owner_policies=not policy_changes,
                    capital_policy_changes=policy_changes, prior_annual_capex=previous_capex,
                    reported_9m_parent_profit=facts["fields"]["net_profit"]["current"],
                    retained_annual_parent_profit=policy["parent_profit"],
                    implied_q4_parent_profit=str(q4_profit),
                    economic_review=dict(classification="RETAINED_PLAN_STRESS_NOT_NEW_EARNINGS_FORECAST",
                        warnings=warnings, adopted=False,
                        explanation="从旧全年目标扣除已发生九个月所得的剩余季度要求；若隐含亏损或经营现金净流出，必须解释其经营与收付机制，不能当作已认可的Base。",
                        next_evidence="核查四季度销量、价格、成本、税费及经营收付变化，重新研究全年假设而非自动年化前三季度。"))
            except ValueError as error:
                results[name] = dict(status="REQUIRES_ECONOMIC_REVISION", reason=str(error),
                    remaining_quarter_assumption=q4,
                    annual=annual)
    if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("REMAINING_REVIEW_SOURCE_CHANGED")
    for binding in [receipt_binding, receipt["spec_binding"], receipt["result_binding"],
                    *original["source_bindings"], *spec["operating_sources"]]:
        _bound(root, binding)
    return dict(schema_version="parent-remaining-year-review-v1", symbol=spec["symbol"],
        candidate_binding=receipt_binding, input_descriptor_sha256=original["input_descriptor_sha256"],
        source_binding=source, reported_facts=facts, scenarios=results,
        capital_policy_mode=capital_policy_mode,
        status="SOURCE_BOUND_REMAINING_YEAR_REVIEW", action="no_order",
        formal_eligibility=False, successor_adopted=False, current_price_qualified=False,
        limitation="保留既有全年经营及其他资本政策的条件重算；不能当作已完成所有政策更新的E1后继或当前买价。")


def read_registered_remaining_year_review(*, root, receipt_binding, symbol, now):
    """Existing public quarter source registry; never write or collect on GET."""
    from ..product.common import load_json_object
    path = Path(root) / "config/current-operating-parent-quarter-v1.json"
    if not path.exists():
        return None
    registered = load_json_object(path, "registered parent quarter source")
    entry = registered.get(symbol)
    if entry is None:
        return None
    if not isinstance(entry, dict) or set(entry) != {"source", "period_end"}:
        raise ValueError("REMAINING_REVIEW_REGISTRY_ENTRY_INVALID")
    result = review_parent_remaining_year(root=root, receipt_binding=receipt_binding,
        now=now, **entry, capital_policy_mode="REPORTED_9M_PLUS_PRIOR_Q4")
    if result["symbol"] != symbol:
        raise ValueError("REMAINING_REVIEW_REGISTRY_ISSUER_MISMATCH")
    return result
