"""Conditional annual principal reduction with no post-opening refinancing."""
from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext
from pathlib import Path

from . import parent_cash_fixed_payment_recheck as fixed
from . import parent_cash_funding_revision_v1 as revision
from . import parent_cash_installment_recheck as installment
from . import parent_cash_maturity_recheck as maturity
from .direct_owner_cash_input_adapter_v2 import descriptor_from_payload
from ...domain.valuation import direct_parent_owner_cash_v2 as kernel
from ...valuation_models import direct_owner_cash_v2 as model

VERSION = "parent-cash-multiyear-recheck-v1"
BASE_BASIS = (
    "从已知到期年度到显式预测末年，每年用同一历史净偿债上限约束未知本金；"
    "当年母公司经营余量及现金底线进一步限制清偿，不以新增借款或投资回款支持分期。"
    "已知本金如期支付，未知本金按期初余额计条件利息并全额滚存。"
    "多年路径要求未付本金按真实到期安排或有效展期保留至计划付款日，且不假设新增借款。"
    "历史授信仅说明融资渠道，未证明展期或可提款；若期限或续借不可得，适用原提前到期压力。"
    "预测末仍有本金时拒绝终值。"
)


def _payment(principal, cap, generated, headroom):
    return max(Decimal(0), min(principal, cap, generated, headroom)).quantize(
        maturity.CENT, rounding=ROUND_DOWN)


def _prepare(context, evidence, rate, coupon, paid, issues, matrix):
    boundary = evidence["year"]
    # Use the existing validated opening pool and debt-only terminal bridge.
    corrected, _ = maturity._prepare(context, evidence, rate, coupon, boundary + 1)
    residual = Decimal(evidence["proxy_residual_cny"])
    history = evidence["comparable_parent_net_repayment_observations"]
    cap = min(Decimal(row["net_repayment_cny"]) for row in history)
    if cap <= 0:
        raise ValueError("MULTIYEAR_HISTORICAL_NET_REPAYMENT_REQUIRED")
    years = corrected["years"]
    shares, cost = (Decimal(corrected[key]) for key in ("ordinary_shares", "cost_of_equity"))
    state = {key: Decimal(value) for key, value in corrected["opening"].items()}
    plan = []
    basis = dict(annual_historical_net_repayment_cap_cny=str(cap),
                 historical_net_repayment_observations=history,
                 first_applicable_year=boundary, last_applicable_year=years[-1]["year"],
                 zero_new_borrowing_from_year=boundary, actual_unknown_maturity_cny=None,
                 financing_condition="CONTRACTUAL_MATURITY_OR_EFFECTIVE_EXTENSION_REQUIRED_WITHOUT_NEW_BORROWING",
                 financing_condition_verified=False)
    for row in years:
        year = row["year"]
        policy = row["policy"]
        scheduled = Decimal(row["scheduled_owner_distribution_cny"])
        if year < boundary:
            scheduled += paid
        else:
            known = sum((Decimal(issue["principal_cny"]) for issue in issues
                         if date.fromisoformat(issue["maturity"]).year == year), Decimal(0))
            interest = (residual * rate).quantize(maturity.CENT, rounding=ROUND_HALF_UP)
            interest += coupon if year == boundary else Decimal(0)
            policy.update(debt_repayment=str(known), interest_outside_cfo=str(interest), new_borrowing="0")
            flow = kernel._flow(policy)
            generated = flow["operating_cash"] - sum(flow[key] for key in (
                "maintenance_capex", "growth_capex", "commitments_outside_capex", "interest_outside_cfo",
                "other_mandatory_cash", "debt_repayment",
            )) - scheduled
            headroom = state["cash"] + generated - flow["cash_floor"]
            payment = _payment(residual, cap, generated, headroom)
            closing = residual - payment
            policy["debt_repayment"] = str(known + payment)
            plan.append(dict(year=year, known_principal_cny=str(known),
                             opening_proxy_residual_cny=str(residual), assumed_proxy_repayment_cny=str(payment),
                             closing_proxy_residual_cny=str(closing), new_borrowing_cny="0",
                             interest_cny=str(interest), operating_surplus_cny=str(generated),
                             cash_headroom_excluding_investment_receipts_cny=str(headroom)))
        flow = dict(kernel._flow(policy), payout_ratio=Decimal(0))
        try:
            _, following = kernel._step(state, flow, scheduled=scheduled, year=year, shares=shares, cost=cost)
        except ValueError as error:
            if str(error) != f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}":
                raise
            ledger = fixed._ledger(state, flow, year, scheduled, matrix, issues)
            return corrected, plan, basis, dict(status="REJECTED", reason=str(error), ledger=ledger)
        state = following
        if year >= boundary:
            residual = closing
            if state["debt"] != residual:
                raise ValueError("MULTIYEAR_ANNUAL_DEBT_PATH_MISMATCH")
    if residual:
        return corrected, plan, basis, dict(
            status="REJECTED", reason="MULTIYEAR_TERMINAL_PRINCIPAL_REMAINS",
            ledger=dict(year=years[-1]["year"] + 1, remaining_proxy_principal_cny=str(residual),
                        rejection_basis="UNSUPPORTED_TERMINAL_DEBT_WITHOUT_REFINANCING"))
    return corrected, plan, basis, None


def _calculate(context, scenario, paid, proposed, matrix, evidence, rate, coupon, facts, name):
    issues = [dict(maturity=row["due"], principal_cny=row["face_cny"])
              for row in matrix["prospective_debt_service"]["issues"]]
    corrected, plan, basis, blocked = _prepare(context, evidence, rate, coupon, paid, issues, matrix)
    result = blocked if blocked is not None else fixed._scenario(corrected, scenario, paid, proposed, matrix, issues)
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
            raise ValueError("MULTIYEAR_F1_CASH_PATH_MISMATCH")
        result = dict(status="CALCULATED", per_share_value=confirmed["per_share_value"],
                      annual_rows=[{key: row[key] for key in ("year", "opening_cash_cny", "closing_cash_cny",
                                    "closing_debt_cny", "total_owner_distribution_cny")} for row in rows],
                      terminal_closing_debt_cny=calculation["terminal_rows"][-1]["closing_debt_cny"])
    row = maturity._with_payment_plan(result, plan)
    if row.get("reason") == "MULTIYEAR_TERMINAL_PRINCIPAL_REMAINS":
        # Keep the installment `ledger` shape reserved for actual cash-floor gaps.
        row["terminal_principal_rejection"] = row.pop("ledger")
    return dict(row, installment_basis=basis)


def run_check(source_root, task_id, digest, now):
    """Replay the pinned parent, then compare annual reduction with the old stresses."""
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
        evidence["comparable_parent_net_repayment_observations"] = installment._net_repayment_history(
            root, receipt, matrix, evidence)
        boundary = evidence["year"]
        coupon = sum(Decimal(row["coupon_if_act365_to_maturity"])
                     for row in matrix["prospective_debt_service"]["issues"]
                     if date.fromisoformat(row["due"]).year == boundary)
        rates = spec["financing_revision"]["unknown_rate_assumptions"]
        scenarios, installment_stress, early_stress = {}, {}, {}
        for name in ("bear", "base", "bull"):
            args = (contexts[name], spec["scenarios"][name], paid, proposed, matrix, evidence,
                    Decimal(rates[name]), coupon)
            scenarios[name] = _calculate(*args, facts, name)
            installment_stress[name] = installment._calculate(*args, facts, name)
            early_stress[name] = maturity._calculate(*args, boundary, facts, name)
    return dict(schema_version=VERSION, parent_receipt=digest, task_id=task_id,
                predecessor_input=prior["predecessor_input"], symbol=prior["symbol"],
                valuation_date=prior["valuation_date"], maturity_evidence=evidence,
                scenarios=scenarios, base_basis=BASE_BASIS,
                scenario_basis="CONDITIONAL_ANNUAL_CASH_LIMITED_PRINCIPAL_REDUCTION",
                original_installment_stress=installment_stress, early_maturity_stress=early_stress,
                financing_condition_verified=False,
                unverified_financing_fallback_status=("REJECTED" if any(
                    row["status"] == "REJECTED" for row in early_stress.values()) else "CALCULATED"),
                status="REJECTED" if any(row["status"] == "REJECTED" for row in scenarios.values()) else "CALCULATED",
                current_research_range_adopted=False, action="no_order", formal_eligibility=False,
                current_comparable=False)
