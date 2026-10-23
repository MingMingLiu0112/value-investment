"""Source-bound economic diagnostics for pending equity research, without approval."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

from ...valuation_models.residual_income import scenario_value
from ..product.common import normalize_symbol
from .value_research_analysis import _available, _bound, load_current_value_research_analysis
from .economic_review_bundle import _build_economic_review_bundle


METHODOLOGY = [
    "https://pages.stern.nyu.edu/adamodar/New_Home_Page/valquestions/highgrowthperiod.htm",
    "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/cashflows.htm",
    "https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf",
]


def _number(value):
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Economic input must be finite")
    return result


def _ratio(numerator, denominator):
    return str(numerator / denominator) if denominator is not None and denominator > 0 else None


def _review_calculations(review: dict, catalog: dict, symbol: str, now: datetime) -> list[dict]:
    """Recalculate the supported historical bridges from their disclosed rows."""
    if not review:
        return []
    if review.get("symbol") != symbol:
        raise ValueError("Financial review belongs to another company")
    facts = {fact["id"]: fact for fact in review["facts"]}
    if len(facts) != len(review["facts"]):
        raise ValueError("Duplicate financial fact ID")
    # These are existing named calculation contracts, not a general formula evaluator.
    signs = {"calendar2025_paid_dividends": (1, 1),
        "calendar2025_parent_partial_cash_proxy": (1, 1, -1),
        "fy2025_plan_dividends": (1, 1),
        "fy_parent_FY2025_cash_capex_proxy": (1, -1),
        "ttm_ex_nonrecurring_parent_profit": (1, 1, -1)}
    rows = []
    for name, coefficients in signs.items():
        calculation = review.get("calculations", {}).get(name)
        if calculation is None:
            continue
        ids, columns = calculation["input_fact_ids"], calculation["input_column_indices"]
        if len(ids) != len(coefficients) or len(columns) != len(ids):
            raise ValueError("Invalid financial calculation inputs")
        terms, evidence = [], []
        for position, (fact_id, index, sign) in enumerate(zip(ids, columns, coefficients)):
            fact = facts[fact_id]
            source = catalog.get(fact["source_id"])
            binding = fact["source_binding"]
            if (source is None or source["sha256"] != binding["sha256"]
                    or binding["id"] != fact["source_id"]
                    or fact.get("unit") != "CNY" or fact.get("currency") != "CNY"
                    or type(index) is not int or not 0 <= index < len(fact["columns"])):
                raise ValueError("Financial row source, unit or column mismatch")
            expected_scope = ("consolidated_parent_attributable" if name == "ttm_ex_nonrecurring_parent_profit"
                else "listed_parent_external_shareholders_gross_tax" if name in
                {"calendar2025_paid_dividends", "fy2025_plan_dividends"} else "listed_parent_only")
            if fact.get("statement_scope") != expected_scope:
                raise ValueError("Financial calculation mixes ownership scopes")
            for field in ("available_at_conservative", "current_local_verified_at"):
                if binding.get(field):
                    _available(binding[field], now)
            column = fact["columns"][index]
            if name == "ttm_ex_nonrecurring_parent_profit":
                # Existing official review rows carry their accounting basis in
                # the disclosed label, not in the convenient local fact ID.
                label = "".join(str(fact.get("label", "")).split())
                expected_label = ("\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\u4e1c\u7684"
                                  "\u6263\u9664\u975e\u7ecf\u5e38\u6027\u635f\u76ca\u7684\u51c0\u5229\u6da6")
                if (label != expected_label or expected_label not in
                        "".join(str(fact.get("evidence_excerpt", "")).split())):
                    raise ValueError("TTM calculation requires disclosed ex-nonrecurring parent profit basis")
                period = {"H12026": "H1_2026", "H12025": "H1_2025"}.get(
                    column["period"], column["period"])
                if period != ("FY2025", "H1_2026", "H1_2025")[position]:
                    raise ValueError("TTM calculation requires ordered distinct FY2025/H1_2026/H1_2025 periods")
            if name in {"calendar2025_parent_partial_cash_proxy", "fy_parent_FY2025_cash_capex_proxy"} and column["period"] != "FY2025":
                raise ValueError("Cash calculation mixes reporting periods")
            terms.append(sign * _number(column["value"]))
            evidence.append(dict(fact_id=fact_id, source_id=fact["source_id"],
                sha256=binding["sha256"], source_url=binding.get("source_url"),
                physical_page=fact["physical_page"], excerpt=fact["evidence_excerpt"],
                statement_scope=fact["statement_scope"], period=column["period"],
                value=column["value"], coefficient=sign))
        computed = sum(terms, Decimal(0))
        if computed != _number(calculation["value"]):
            raise ValueError("Financial calculation does not reconcile")
        rows.append(dict(id=name, **calculation, recomputed_value=str(computed),
            calculation_verified=True, evidence=evidence))
    return rows


def load_current_value_economic_assessment(*, root: Path, symbol: str, now: datetime) -> dict | None:
    """Re-derive only the registered current version; malformed sources raise.

    A caller cannot inject an analysis dictionary, a price, or an approval. The
    inherited loader verifies the review packet and recalculates model outputs.
    Diagnostic model cash distributions remain assumptions, never issuer cash.
    """
    root, symbol = root.resolve(), normalize_symbol(symbol)
    analysis = load_current_value_research_analysis(root=root, symbol=symbol, now=now)
    if analysis is None:
        return None
    if analysis["symbol"] != symbol or analysis["action"] != "no_order":
        raise ValueError("Economic assessment identity mismatch")
    catalog = {source["id"]: source for source in analysis["source_catalog"]}
    if len(catalog) != len(analysis["source_catalog"]):
        raise ValueError("Economic assessment requires unique source IDs")
    for source in catalog.values():
        for field in ("source_available_at", "retrieved_at", "published_at"):
            if source.get(field):
                _available(source[field], now)
    for anchor in analysis["official_fact_anchors"]:
        if anchor["source_id"] not in catalog:
            raise ValueError("Economic fact anchor has no bound source")
    inputs = analysis["consumed_operating_inputs"]
    book, shares = _number(inputs["start_book_equity"]), _number(inputs["ordinary_shares"])
    if book <= 0 or shares <= 0:
        raise ValueError("Economic assessment requires positive equity and shares")
    summary = analysis["financial_summary"]
    historical = _number(summary.get("ttm_ex_nonrecurring_parent_profit_cny"))
    normalized = _number(summary.get("normalized_parent_profit_cny"))
    reconciliation = summary.get("historical_profit_reconciliation") or {}
    profit_bridge = dict(status="NOT_AVAILABLE", formula=None, inputs=[], computed_ttm_cny=None)
    if reconciliation:
        if reconciliation.get("symbol") != symbol:
            raise ValueError("Profit reconciliation belongs to another company")
        rows = reconciliation.get("source_rows", [])
        periods = {row["period"]: row for row in rows}
        if len(periods) != len(rows):
            raise ValueError("Duplicate profit bridge period")
        if set(periods) == {"FY2025", "H1_2026", "H1_2025"}:
            for row in rows:
                source = catalog.get(row["source_id"])
                if (source is None or source["sha256"] != row["sha256"]
                        or row.get("currency") != "CNY"
                        or row.get("profit_basis") != "attributable_to_parent"
                        or row.get("statement_scope") != "consolidated"):
                    raise ValueError("Profit bridge source or accounting scope mismatch")
                _bound(root, dict(path=row["path"], sha256=row["sha256"]))
            computed = (_number(periods["FY2025"]["ex_nonrecurring_profit_cny"])
                        + _number(periods["H1_2026"]["ex_nonrecurring_profit_cny"])
                        - _number(periods["H1_2025"]["ex_nonrecurring_profit_cny"]))
            if computed != historical or computed != _number(reconciliation["ttm_ex_nonrecurring_parent_profit_cny"]):
                raise ValueError("Profit bridge does not reconcile")
            profit_bridge = dict(status="HISTORICAL_RECONCILED_NOT_NORMALIZED",
                formula="FY2025 + H1_2026 - H1_2025", inputs=rows, computed_ttm_cny=str(computed))
    scenario_rows = []
    with localcontext() as context:
        context.prec = 48
        for scenario in analysis["scenarios"]:
            given = scenario["inputs"]
            cost = _number(given["cost_of_equity"])
            roes = [_number(value) for value in given["forecast_roes"]]
            result = scenario_value(book, shares, cost, dict(
                forecast_roe=roes, terminal_roe=given["terminal_roe"],
                terminal_growth=given["terminal_growth"], retention=given["retention"]))
            years = result["forecast_years"]
            first, last = _number(years[0]["net_income_assumption_cny"]), _number(years[-1]["net_income_assumption_cny"])
            scenario_rows.append(dict(scenario=scenario["scenario"],
                dated_per_share_value=scenario["per_share_value"],
                diagnostic_basis="UNDATED_BOOK_BASIS_NOT_REPLACEMENT_FOR_DATED_VALUATION",
                first_year_profit_cny=str(first),
                first_year_profit_to_historical_ttm=_ratio(first, historical),
                first_year_dividend_assumption_cny=years[0]["dividend_assumption_cny"],
                first_year_payout_ratio=str(1 - _number(given["retention"])),
                explicit_years=len(roes), years_above_equity_cost=sum(roe > cost for roe in roes),
                first_year_excess_roe=str(roes[0] - cost),
                final_explicit_profit_cny=str(last),
                explicit_profit_cagr=(str((last / first) ** (Decimal(1) / (len(roes) - 1)) - 1)
                    if first > 0 and last > 0 and len(roes) > 1 else None),
                terminal_excess_roe=str(_number(given["terminal_roe"]) - cost),
                cost_of_equity=str(cost), terminal_growth=given["terminal_growth"],
                terminal_spread=str(cost - _number(given["terminal_growth"])),
                terminal_residual_contribution_ratio=result["terminal_residual_contribution_ratio"],
                dividend_ri_reconciliation_cny=result["dividend_crosscheck_difference_cny"],
                implied_expectation_scope="REGISTERED_SCENARIO_CONDITIONS_NOT_MARKET_IMPLIED",
                cash_distribution_scope="SELF_FUNDED_MODEL_ASSUMPTION_NOT_SUSTAINABLE_ISSUER_DIVIDEND"))
    short_fade = summary.get("pending_model_choice") == "short-advantage"
    blockers = ["NORMALIZED_EARNINGS_NOT_ESTABLISHED", "SUSTAINABLE_DISTRIBUTABLE_CASH_NOT_ESTABLISHED",
        "ADVANTAGE_DURATION_AND_FADE_NOT_ECONOMICALLY_VALIDATED",
        "EQUITY_COST_INPUTS_REQUIRE_EXACT_VERSION_REVIEW", "CURRENT_MODEL_VALIDITY_REQUIRES_EVENT_REVIEW"]
    if short_fade:
        blockers.append("SHORT_ADVANTAGE_STRESS_IS_NOT_NEUTRAL_PRIMARY_VALUATION")
    historical_calculations = _review_calculations(
        summary.get("verified_financial_review") or {}, catalog, symbol, now)
    cash_rows = [row for row in historical_calculations if row["id"] != "ttm_ex_nonrecurring_parent_profit"]
    for row in historical_calculations:
        if row["id"] == "ttm_ex_nonrecurring_parent_profit":
            if _number(row["recomputed_value"]) != historical:
                raise ValueError("Financial review and earnings anchor differ")
            profit_bridge = dict(status="HISTORICAL_RECONCILED_NOT_NORMALIZED", formula=row["formula"],
                inputs=row["evidence"], computed_ttm_cny=row["recomputed_value"])
    cash_by_id = {row["id"]: row for row in cash_rows}
    cash_diagnostics = []
    paid = cash_by_id.get("calendar2025_paid_dividends")
    proxy = cash_by_id.get("calendar2025_parent_partial_cash_proxy")
    if paid is not None and proxy is not None:
        numerator, denominator = _number(proxy["recomputed_value"]), _number(paid["recomputed_value"])
        with localcontext() as context:
            context.prec = 48
            cash_diagnostics.append(dict(id="CALENDAR2025_PARTIAL_PARENT_CASH_TO_PAID_DIVIDEND",
                numerator_cny=str(numerator), denominator_cny=str(denominator),
                ratio=_ratio(numerator, denominator), difference_cny=str(numerator - denominator),
                evidence_calculation_ids=[proxy["id"], paid["id"]],
                scope="HISTORICAL_PARTIAL_PROXY_NOT_SUSTAINABILITY_OR_DISTRIBUTABLE_CASH",
                limitation="Investment cash can include nonrecurring receipts; financing, required liquidity, legal restrictions and future investment remain unbridged."))
    tasks = [
        dict(id="NORMALIZED_EARNINGS", question="Bridge reported and ex-nonrecurring profit to recurring after-tax parent earnings; quantify maintenance and accounting adjustments without pre-tax addbacks.", evidence_fields=["financial_summary", "official_fact_anchors"]),
        dict(id="CASH_RETURN", question="Reconcile parent cash, subsidiary upstreaming, mandatory investment, debt and distribution restrictions; distinguish payment calendar from profit year.", evidence_fields=["historical_cash_observations", "source_catalog"]),
        dict(id="PRIMARY_MODEL", question="Support the advantage duration and fade with business evidence; compare a continuity case against the stress and explain clean-surplus adjustments.", evidence_fields=["scenarios", "counter_evidence"]),
        dict(id="EQUITY_COST", question="Review dated CNY nominal risk-free, equity premium and beta inputs for this equity scope, with source dates and sensitivity.", evidence_fields=["assumptions", "sensitivity"]),
        dict(id="CURRENT_EXPECTATIONS", question="Use an independently verified PriceBridge and a bounded registered inverse model; report no solution rather than extending parameter bounds.", evidence_fields=["review_binding"]),
    ]
    accounting_review = _build_economic_review_bundle(root=root, analysis=analysis, now=now)
    # The outer assessment already records the same cutoff; omit the volatile
    # nested timestamp to keep its content fingerprint stable across replays.
    accounting_review.pop("evaluated_at")
    result = dict(schema_version="value-economic-assessment-v1", symbol=symbol, action="no_order",
        accounting_bridge_review=accounting_review,
        status="ECONOMIC_DIAGNOSTICS_COMPLETE_PRIMARY_NOT_ESTABLISHED", assessed_at=now.isoformat(),
        input_descriptor_sha256=analysis["input_descriptor_sha256"], review_binding=analysis["review_binding"],
        research_as_of=analysis["research_as_of"], valuation_date=analysis["valuation_date"],
        economic_assumptions_reviewed=False, primary_valuation_usable=False,
        strategy_admitted=False, action_admitted=False, approval_changed=False,
        model_applicability=dict(model=analysis["model_applicability"]["route"],
            assessment="STRESS_ONLY" if short_fade else "CONTINUITY_ALTERNATIVE_REQUIRES_VALIDATION",
            reasons=summary.get("pending_model_limits", []),
            clean_surplus_bridge=summary.get("financial_equity_bridge"),
            limitation="Zero terminal excess return does not prove a neutral valuation or that competitive advantage ends on schedule."),
        earnings=dict(historical_ex_nonrecurring_ttm_cny=str(historical) if historical is not None else None,
            normalized_parent_profit_candidate_cny=str(normalized) if normalized is not None else None,
            normalization_status="NOT_ESTABLISHED", historical_bridge=profit_bridge,
            note="Period-end equity ratios and next-year model profit are not disclosed weighted ROE or normalized earnings."),
        scenarios=scenario_rows, historical_cash_observations=cash_rows,
        cash_return_diagnostics=cash_diagnostics,
        sustainable_distribution_status="NOT_ESTABLISHED",
        reverse_expectations=dict(status="REQUIRES_VERIFIED_PRICEBRIDGE_AND_REGISTERED_INVERSE",
            market_implied_result=None, registered_scenario_conditions=scenario_rows),
        sensitivity=analysis["sensitivity"], assumptions=analysis["assumptions"],
        counter_evidence=analysis["counter_evidence"], thesis_breakers=analysis["thesis_breakers"],
        official_fact_anchors=analysis["official_fact_anchors"], source_catalog=analysis["source_catalog"],
        source_bindings=analysis["source_bindings"], blockers=blockers, next_verifications=tasks,
        methodology_sources=METHODOLOGY)
    for binding in result["source_bindings"]:
        _bound(root, binding)
    content = {key: value for key, value in result.items() if key != "assessed_at"}
    result["assessment_sha256"] = sha256(json.dumps(content, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
    return result
