"""Recheck a sealed V3 cash path after an executed repurchase became non-discretionary."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import re

from . import parent_cash_funding_revision_v1 as revision
from . import direct_owner_cash_compilation_v2 as compiler
from ...domain.valuation import direct_parent_owner_cash_v2 as kernel
from ...infrastructure.filings.operating_event_terms import parse_operating_event_terms
from ...infrastructure.filings.pdf_text import extract_pages


def _paid_inputs(root, spec, now):
    """Recognize only a uniquely matched post-quarter first purchase and disclosed target."""
    reports = []
    proposals = []
    quarter = spec["quarterly_financing_source"]
    def pages(pin):
        name = revision._checked_path(root, root / pin["path"])
        if sha256(name.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("OWNER_PAYMENT_ORIGINAL_CHANGED")
        return extract_pages(name)

    for pin in spec["financing_revision"]["extra_source_bindings"]:
        if not pin["path"].lower().endswith(".pdf"):
            continue
        source = pages(pin)
        first = re.sub(r"\s+", "", source[0])
        if spec["issuer_name"] not in first or spec["symbol"] not in first:
            continue
        if "关于股份回购进展公告" in first:
            event = parse_operating_event_terms(source, symbol=spec["symbol"])
            if event["event_type"] == "REPORTED_BUYBACK_PROGRESS" and event["issuer_name"] == spec["issuer_name"]:
                reports.append((pin, event))
        if "中期利润分配预案" in first:
            match = re.findall(r"以此计算合计拟派发现金红利总额为([\d,]+\.\d{2})元", first)
            if len(match) == 1:
                proposals.append((pin, Decimal(match[0].replace(",", ""))))
    if len(reports) != 1 or len(proposals) != 1:
        raise ValueError("OWNER_PAYMENT_UNIQUE_ORIGINALS_REQUIRED")
    pin, event = reports[0]
    terms = event["terms"]
    quarter_pages = "".join(re.sub(r"\s+", "", p) for p in pages(quarter))
    starts = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日，公司实施了首次回购股份", quarter_pages)
    if len(starts) != 1:
        raise ValueError("OWNER_PAYMENT_FIRST_PURCHASE_UNPROVEN")
    start = date(*map(int, starts[0]))
    year = date.fromisoformat(spec["valuation_date"]).year + 1
    q3 = date(year, 9, 30)
    if (spec["issuer_name"] not in quarter_pages or spec["first_year_operating_cash_method"] != "OBSERVED_9M_PLUS_CONDITIONAL_Q4_V1"
            or not date.fromisoformat(terms["plan_start"]) <= start <= date.fromisoformat(terms["plan_end"])
            or not q3 < start <= date.fromisoformat(terms["through"]) <= date(year, 12, 31)
            or date.fromisoformat(event["published_date"]) > now.date()):
        raise ValueError("OWNER_PAYMENT_TIMING_OR_SCOPE")
    paid = Decimal(terms["cumulative_paid_cny"])
    if paid <= 0:
        raise ValueError("OWNER_PAYMENT_NOT_PAID")
    return paid, proposals[0][1], dict(first_trade=start.isoformat(), through=terms["through"],
        paid_cny=str(paid), published_date=event["published_date"], physical_pages=event["physical_pages"],
        source_refs=[{k:p[k] for k in ("path","sha256")} for p in (quarter, pin, proposals[0][0])])


def _native_inputs(root, spec, receipt, now, rejected):
    """The frozen compiler exposes no result on rejection. Recover only its verified input frame."""
    names = [n for n in spec["scenarios"] if n != rejected] + [rejected]
    ordered = dict(spec, scenarios={n:spec["scenarios"][n] for n in names})
    try:
        compiler.compile_source_bound_owner_cash_v2(root=root, spec=ordered, now=now,
            implemented_distribution=receipt["distribution_receipt"])
    except ValueError as error:
        # Same version-pinned and frame-checked diagnostic as the original cold replay.
        old = revision._rejected_run(error, ordered, rejected)
        if old != receipt["current_reassessment"]["scenario_rows"][rejected]:
            raise ValueError("OWNER_PAYMENT_PREDECESSOR_CHANGED") from error
        frame = error.__traceback__
        while frame.tb_frame.f_code is not compiler.compile_source_bound_owner_cash_v2.__code__:
            frame = frame.tb_next
        state = frame.tb_frame.f_locals
        result = {n: {k:state["scenarios"][n][k] for k in ("years","terminal","opening","cost_of_equity","ordinary_shares")} for n in names[:-1]}
        result[rejected] = dict(years=state["rows"], terminal=state["tail"], opening=state["opening"],
                                cost_of_equity=state["cost"], ordinary_shares=state["shares"])
        return result
    raise ValueError("OWNER_PAYMENT_EXPECTED_SEALED_REJECTION")


def _ledger(state, flow, year, scheduled, matrix, issues):
    D = Decimal
    due_rows = [i for i in issues if date.fromisoformat(i["maturity"]).year == year]
    due = sum((D(i["principal_cny"]) for i in due_rows), D(0))
    other = flow["debt_repayment"] - due
    if other < 0:
        raise ValueError("OWNER_PAYMENT_KNOWN_MATURITY_UNCOVERED")
    available = (state["cash"] + flow["operating_cash"] + flow["investment_cash_received"]
                 + flow["new_borrowing"] - sum(flow[k] for k in ("maintenance_capex", "growth_capex",
                 "commitments_outside_capex", "interest_outside_cfo", "other_mandatory_cash")) - due - other)
    coupon = sum((D(i["coupon_if_act365_to_maturity"]) for i in matrix["prospective_debt_service"]["issues"]
                  if date.fromisoformat(i["due"]).year == year), D(0))
    if coupon > flow["interest_outside_cfo"]:
        raise ValueError("OWNER_PAYMENT_INTEREST_SPLIT")
    gap = max(D(0), flow["cash_floor"] - available)
    return dict(year=year, opening_cash_cny=str(state["cash"]), operating_cash_cny=str(flow["operating_cash"]),
        investment_cash_cny=str(flow["investment_cash_received"]), new_borrowing_cny=str(flow["new_borrowing"]),
        known_principal_cny=str(due), assumed_other_repayment_cny=str(other), interest_cny=str(flow["interest_outside_cfo"]),
        coupon_component_cny=str(coupon), other_interest_cny=str(flow["interest_outside_cfo"]-coupon),
        maintenance_capex_cny=str(flow["maintenance_capex"]), growth_capex_cny=str(flow["growth_capex"]),
        commitments_cny=str(flow["commitments_outside_capex"]), other_required_cash_cny=str(flow["other_mandatory_cash"]),
        scheduled_distribution_cny=str(scheduled), cash_before_distribution_cny=str(available),
        floor_cny=str(flow["cash_floor"]), floor_equals_opening_basis=False, shortfall_cny=str(gap),
        cash_if_unknown_not_due_cny=str(available+other), coverage_before_unknown_repayment_cny=str(available+other-flow["cash_floor"]),
        maturity_dates=[i["maturity"] for i in due_rows])


def _scenario(context, scenario, paid, proposed, matrix, issues):
    rows = deepcopy(context["years"])
    for row, original in zip(rows, scenario["years"], strict=True):
        if row["year"] != original["year"]:
            raise ValueError("OWNER_PAYMENT_YEAR_MISMATCH")
        row["policy"]["payout_ratio"] = str(original["policy"]["payout_ratio"]["value"])
    first = rows[0]
    profit = Decimal(first["policy"]["parent_profit"])
    prior_target = profit * Decimal(first["policy"]["payout_ratio"])
    if profit <= 0 or prior_target.quantize(Decimal(".01")) != paid + proposed:
        raise ValueError("OWNER_PAYMENT_OPTIONAL_TARGET_DOES_NOT_RECONCILE")
    first["scheduled_owner_distribution_cny"] = str(Decimal(first["scheduled_owner_distribution_cny"]) + paid)
    first["policy"]["payout_ratio"] = str(proposed / profit)
    shares, cost = (Decimal(context[k]) for k in ("ordinary_shares","cost_of_equity"))
    state = {k:Decimal(v) for k,v in context["opening"].items()}
    for row in rows:
        flow = dict(kernel._flow(row["policy"]), payout_ratio=Decimal(0))
        scheduled = Decimal(row["scheduled_owner_distribution_cny"])
        try:
            _, following = kernel._step(state, flow, scheduled=scheduled, year=row["year"], shares=shares, cost=cost)
        except ValueError as error:
            if str(error) != f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{row['year']}":
                raise
            ledger = _ledger(state, flow, row["year"], scheduled, matrix, issues)
            ledger["floor_equals_opening_basis"] = flow["cash_floor"] == Decimal(context["opening"]["cash"])
            if Decimal(ledger["shortfall_cny"]) <= 0:
                raise ValueError("OWNER_PAYMENT_DEFICIT_NOT_REPRODUCED")
            return dict(status="REJECTED", reason=str(error), ledger=ledger)
        state = following
    compiler._reserve_annual_cash_before_optional_payout(context["opening"], rows, shares, cost)
    result = kernel.compile_direct_owner_cash_path_v2(opening=context["opening"], years=rows,
        terminal=context["terminal"], ordinary_shares=str(shares), cost_of_equity=str(cost),
        scope=compiler.SCOPE, currency="CNY")
    return dict(status="CALCULATED", per_share_value=result["per_share_value"], calculation=result)


def run_check(root, task_id, receipt_sha256, now):
    root = Path(root).resolve()
    replayed = revision.replay(root, task_id, receipt_sha256, now)
    folder = root / "runtime/parent-cash-task-backed-receipts" / task_id / "funding-revisions" / receipt_sha256
    receipt = revision._sibling(folder, "receipt", receipt_sha256)
    assessment = receipt.get("current_reassessment", {})
    if assessment.get("status") != "REJECTED":
        raise ValueError("OWNER_PAYMENT_NO_REJECTED_PATH")
    rejected = [n for n,r in assessment["scenario_rows"].items() if r["status"] == "REJECTED"]
    if len(rejected) != 1:
        raise ValueError("OWNER_PAYMENT_SINGLE_CONSTRAINT_REQUIRED")
    spec = revision._sibling(folder, "reassessment-spec", assessment["revised_spec"])
    matrix = revision._sibling(folder, "financing-evidence", receipt["originals_matrix"])
    paid, proposed, sources = _paid_inputs(root, spec, now)
    # Q3 residual includes cash flows only through September. The Q4 substitute
    # is a prior-year investment-principal recovery. Neither can include a first
    # purchase in October. Reject another basis unless its treatment is reconciled.
    financing = spec["financing_revision"]
    pre_buyback_drain = (Decimal(financing["q3_other_drain_cny"])
                         - Decimal(financing["one_time_q4_net_principal_recovery_assumption_cny"]))
    for scenario in spec["scenarios"].values():
        policy = scenario["years"][0]["policy"]
        if (Decimal(policy["other_mandatory_cash"]["value"]) != pre_buyback_drain
                or Decimal(policy["commitments_outside_capex"]["value"]) != 0):
            raise ValueError("OWNER_PAYMENT_OTHER_OUTFLOWS_NOT_RECONCILED")
    contexts = _native_inputs(root, spec, receipt, now, rejected[0])
    issues = spec["financing_revision"]["known_maturities"]
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        outcomes = {n:_scenario(contexts[n], spec["scenarios"][n], paid, proposed, matrix, issues) for n in contexts}
    old = replayed["current_reassessment"]["scenario_rows"][rejected[0]]
    return dict(schema_version="fixed-owner-payment-cash-recheck-v1", symbol=spec["symbol"], task_id=task_id,
        parent_receipt=receipt_sha256, predecessor_input=assessment["revised_spec"]["sha256"],
        valuation_date=spec["valuation_date"], source_payment=sources, conditional_target_cny=str(proposed),
        predecessor_shortfall_cny=str(Decimal(old["floor"]) - Decimal(old["before"])), scenarios=outcomes,
        status="REJECTED" if any(r["status"]=="REJECTED" for r in outcomes.values()) else "CALCULATED",
        formal_eligibility=False, current_comparable=False, action="no_order")
