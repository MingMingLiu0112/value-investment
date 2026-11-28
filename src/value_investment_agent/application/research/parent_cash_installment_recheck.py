"""Source-bound repayment sensitivity on the existing parent cash path."""
from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext
from pathlib import Path
import re

from . import parent_cash_maturity_recheck as maturity
from . import parent_cash_fixed_payment_recheck as fixed
from . import parent_cash_funding_revision_v1 as revision
from .direct_owner_cash_input_adapter_v2 import descriptor_from_payload
from ...domain.valuation import direct_parent_owner_cash_v2 as kernel
from ...valuation_models import direct_owner_cash_v2 as model

VERSION = "parent-cash-installment-recheck-v1"
BASE_BASIS = (
    "首年未知本金仅动用母公司当年经营现金扣除必要支出、已知本金及条件利息后的剩余，"
    "且不突破沿用的研究现金底线或最近两个可比九个月净偿债额的较低值；不计新增融资和投资回款来决定首笔金额。"
    "剩余代理本金完整滚存并按期初余额计息，下一年全额清偿仅为压力假设。"
)


def _net_repayment_history(root, receipt, matrix, evidence):
    year = evidence["year"] - 1
    source = matrix["sources"][f"9M{year % 100:02d}"]
    page = maturity._source_pages(root, receipt, source, 14)[13]
    if "母公司现金流量表" not in page:
        raise ValueError("INSTALLMENT_PARENT_CASH_STATEMENT_REQUIRED")
    amount = r"([0-9,]+\.\d{2})"

    def columns(label):
        rows = re.findall(rf"(?m)^[ \t]*{label}[ \t]+{amount}[ \t]+{amount}[ \t\r]*$", page)
        if len(rows) != 1:
            raise ValueError("INSTALLMENT_COMPARABLE_PARENT_CASH_COLUMNS_REQUIRED")
        return [Decimal(value.replace(",", "")) for value in rows[0]]

    draws = columns("取得借款收到的现金")
    repayments = columns("偿还债务支付的现金")
    if (draws[0] != Decimal(evidence["reported_9m_borrowing_cny"])
            or repayments[0] != Decimal(evidence["reported_9m_repayment_cny"])):
        raise ValueError("INSTALLMENT_PARENT_CASH_COLUMNS_MISMATCH")
    return [dict(period_end=date(year - index, 9, 30).isoformat(), scope="ISSUER_PARENT_STANDALONE",
                 currency="CNY", borrowing_cny=str(draw), repayment_cny=str(repaid),
                 net_repayment_cny=str(repaid - draw), physical_page=14, source_sha256=source["pdf_sha256"])
            for index, (draw, repaid) in enumerate(zip(draws, repayments, strict=True))]


def _installment(context, plan, evidence, paid):
    history = evidence["comparable_parent_net_repayment_observations"]
    historical_net = min(Decimal(row["net_repayment_cny"]) for row in history)
    if historical_net <= 0:
        raise ValueError("INSTALLMENT_HISTORICAL_NET_REPAYMENT_REQUIRED")
    first, boundary = context["years"][:2]
    shares, cost = (Decimal(context[key]) for key in ("ordinary_shares", "cost_of_equity"))
    state = {key: Decimal(value) for key, value in context["opening"].items()}
    try:
        _, opening = kernel._step(state, dict(kernel._flow(first["policy"]), payout_ratio=Decimal(0)),
            scheduled=Decimal(first["scheduled_owner_distribution_cny"]) + paid,
            year=first["year"], shares=shares, cost=cost)
    except ValueError as error:
        if str(error) != f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{first['year']}":
            raise
        opening = None
    flow = kernel._flow(boundary["policy"])
    cash_generated = flow["operating_cash"] - sum(flow[key] for key in (
        "maintenance_capex", "growth_capex", "commitments_outside_capex", "interest_outside_cfo",
        "other_mandatory_cash", "debt_repayment",
    )) - Decimal(boundary["scheduled_owner_distribution_cny"])
    # Exclude investment collections also from the cash-floor test.
    headroom = (opening["cash"] + cash_generated - flow["cash_floor"]) if opening is not None else None
    principal = Decimal(plan[0]["opening_proxy_residual_cny"])
    amount = (max(Decimal(0), min(principal, cash_generated, headroom, historical_net))
              if headroom is not None else Decimal(0)).quantize(maturity.CENT, rounding=ROUND_DOWN)
    return amount, dict(
        historical_parent_net_repayment_cny=str(historical_net),
        historical_net_repayment_observations=history,
        operating_cash_after_required_payments_cny=str(cash_generated),
        cash_headroom_excluding_investment_receipts_cny=str(headroom) if headroom is not None else None,
        cash_floor_cny=str(flow["cash_floor"]), boundary_installment_cny=str(amount),
    )


def _prepare(context, evidence, rate, coupon, paid):
    boundary = evidence["year"]
    corrected, plan = maturity._prepare(context, evidence, rate, coupon, boundary + 1)
    amount, basis = _installment(corrected, plan, evidence, paid)
    first, second = plan[:2]
    remaining = Decimal(first["opening_proxy_residual_cny"]) - amount
    interest = (remaining * rate).quantize(maturity.CENT, rounding=ROUND_HALF_UP)
    first.update(assumed_proxy_repayment_cny=str(amount), closing_proxy_residual_cny=str(remaining))
    second.update(opening_proxy_residual_cny=str(remaining), assumed_proxy_repayment_cny=str(remaining),
                  interest_cny=str(interest))
    corrected["years"][1]["policy"]["debt_repayment"] = str(Decimal(first["known_principal_cny"]) + amount)
    corrected["years"][2]["policy"].update(debt_repayment=str(remaining), interest_outside_cfo=str(interest))
    basis["remaining_next_year_pressure_cny"] = str(remaining)
    return corrected, plan, basis


def _calculate(context, scenario, paid, proposed, matrix, evidence, rate, coupon, facts, name):
    corrected, plan, basis = _prepare(context, evidence, rate, coupon, paid)
    issues = [{"maturity": row["due"], "principal_cny": row["face_cny"]}
              for row in matrix["prospective_debt_service"]["issues"]]
    result = fixed._scenario(corrected, scenario, paid, proposed, matrix, issues)
    if result["status"] == "CALCULATED":
        calculation = result["calculation"]
        rows = calculation["annual_rows"]
        typed = replace(facts.scenario_inputs[name], opening=corrected["opening"], terminal=corrected["terminal"],
                        years=[dict(year=row["year"], policy=row["cash_policy"],
                                    scheduled_owner_distribution_cny=row["scheduled_owner_distribution_cny"])
                               for row in rows],
                        forecast_roes=tuple(Decimal(row["roe_assumption"]) for row in rows),
                        forecast_retentions=tuple(Decimal(row["retention_assumption"]) for row in rows),
                        cost_of_equity=Decimal(corrected["cost_of_equity"]))
        confirmed = model.scenario_calculation(facts, typed)
        if (confirmed != calculation
                or any(Decimal(row["closing_debt_cny"]) != Decimal(payment["closing_proxy_residual_cny"])
                       for row, payment in zip(rows[1:], plan, strict=True))
                or any(Decimal(row["closing_debt_cny"]) for row in calculation["terminal_rows"])):
            raise ValueError("INSTALLMENT_F1_CASH_PATH_MISMATCH")
        result = dict(status="CALCULATED", per_share_value=confirmed["per_share_value"],
                      annual_rows=[{key: row[key] for key in ("year", "opening_cash_cny", "closing_cash_cny",
                                    "closing_debt_cny", "total_owner_distribution_cny")} for row in rows],
                      terminal_closing_debt_cny=calculation["terminal_rows"][-1]["closing_debt_cny"])
    return dict(maturity._with_payment_plan(result, plan), installment_basis=basis)


def run_check(source_root, task_id, digest, now):
    """Read the parent receipt and re-evaluate all scenarios without new financing."""
    root = Path(source_root).resolve()
    prior = fixed.run_check(root, task_id, digest, now)
    folder = root / "runtime/parent-cash-task-backed-receipts" / task_id / "funding-revisions" / digest
    receipt = revision._sibling(folder, "receipt", digest)
    assessment = receipt["current_reassessment"]
    spec = revision._sibling(folder, "reassessment-spec", assessment["revised_spec"])
    matrix = revision._sibling(folder, "financing-evidence", receipt["originals_matrix"])
    facts = descriptor_from_payload(revision._sibling(folder, "descriptor", receipt["descriptor"])).facts
    rejected, = [name for name, row in assessment["scenario_rows"].items() if row["status"] == "REJECTED"]
    contexts = fixed._native_inputs(root, spec, receipt, now, rejected)
    paid = Decimal(prior["source_payment"]["paid_cny"])
    proposed = Decimal(prior["conditional_target_cny"])
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        evidence = maturity._evidence(root, receipt, spec, matrix, now)
        evidence["comparable_parent_net_repayment_observations"] = _net_repayment_history(root, receipt, matrix, evidence)
        coupon = sum(Decimal(row["coupon_if_act365_to_maturity"])
                     for row in matrix["prospective_debt_service"]["issues"]
                     if date.fromisoformat(row["due"]).year == evidence["year"])
        rates = spec["financing_revision"]["unknown_rate_assumptions"]
        scenarios = {name: _calculate(contexts[name], spec["scenarios"][name], paid, proposed, matrix,
                                      evidence, Decimal(rates[name]), coupon, facts, name)
                     for name in ("bear", "base", "bull")}
    return dict(schema_version=VERSION, parent_receipt=digest, task_id=task_id,
                predecessor_input=prior["predecessor_input"], symbol=prior["symbol"],
                valuation_date=prior["valuation_date"], maturity_evidence=evidence,
                scenarios=scenarios, base_basis=BASE_BASIS,
                scenario_basis="CONDITIONAL_OPERATING_SURPLUS_INSTALLMENT_THEN_NEXT_YEAR_REMAINDER",
                status="REJECTED" if any(row["status"] == "REJECTED" for row in scenarios.values()) else "CALCULATED",
                current_research_range_adopted=False, action="no_order", formal_eligibility=False,
                current_comparable=False)
