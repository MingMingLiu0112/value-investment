"""Conditional timing of parent principal, with zero future refinancing and a closed tail."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
from pathlib import Path
import re

from . import parent_cash_fixed_payment_recheck as fixed
from . import parent_cash_funding_revision_v1 as revision
from .direct_owner_cash_agent_facts_v2 import read_parent_cash_agent_facts_v2
from .direct_owner_cash_compilation_v2 import financing_maturity_floor
from .direct_owner_cash_input_adapter_v2 import descriptor_from_payload
from ...infrastructure.filings.pdf_text import extract_pages
from ...valuation_models import direct_owner_cash_v2 as model

VERSION = "parent-cash-maturity-recheck-v1"
CENT = Decimal("0.01")
YI = Decimal(100000000)
BASKET = {"短借": "短期借款", "一年内到期非流动负债": "一年内到期的非流动负债",
          "其他流动负债整行": "其他流动负债", "长借": "长期借款", "租赁负债": "租赁负债"}


def _match(text, pattern):
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError("MATURITY_UNIQUE_ORIGINAL_LINE_REQUIRED")
    return Decimal(matches[0].replace(",", ""))


def _statement_amount(page, label):
    return _match(page, rf"(?m)^\s*{re.escape(label)}[ \t]+([\d,]+\.\d{{2}})(?=[ \t\r\n]|$)")


def _source_pages(root, receipt, meta, last):
    pins = [pin for pin in receipt["inputs"] if pin["sha256"] == meta["pdf_sha256"]]
    if len(pins) != 1:
        raise ValueError("MATURITY_PDF_BINDING_REQUIRED")
    path = revision._checked_path(root, root / pins[0]["path"])
    if sha256(path.read_bytes()).hexdigest() != meta["pdf_sha256"]:
        raise ValueError("MATURITY_ORIGINAL_BYTES_CHANGED")
    return extract_pages(path, limit=last)


def _evidence(root, receipt, spec, matrix, now):
    first = date.fromisoformat(spec["valuation_date"]).year + 1
    year = first + 1
    bridge = matrix[f"annual_year_{year}"]
    financing = spec["financing_revision"]
    sources = matrix["sources"]
    quarter = sources[f"9M{first % 100:02d}"]
    if (quarter["pdf_sha256"] != spec["quarterly_financing_source"]["sha256"]
            or matrix["issuer"] != spec["issuer_name"] or matrix["currency"] != "CNY"
            or date.fromisoformat(matrix["as_of"]) > now.date()):
        raise ValueError("MATURITY_ORIGINAL_SCOPE")
    pages = _source_pages(root, receipt, quarter, 14)
    if ("母公司资产负债表" not in pages[10] or "母公司现金流量表" not in pages[13]
            or spec["issuer_name"] not in "".join(pages[:2])):
        raise ValueError("MATURITY_PARENT_STATEMENTS_REQUIRED")
    components = {key: _statement_amount(pages[11], label) for key, label in BASKET.items()}
    draws = _statement_amount(pages[13], "取得借款收到的现金")
    repaid = _statement_amount(pages[13], "偿还债务支付的现金")
    annual = sources[f"FY{(first-1) % 100:02d}"]
    report = _source_pages(root, receipt, annual, 74)[73]
    opening = _match(re.sub(r"\s+", "", report),
                     r"公司（非公司合并范围口径）有息债务余额分别为[\d.]+亿元和([\d.]+)亿元") * YI
    native = read_parent_cash_agent_facts_v2(root=root, spec_binding=receipt["registered_spec"], now=now)
    constraints = native["constraints"]
    issues = constraints["issued_financing"]
    registered = _source_pages(root, receipt, sources["mtn"], 1)[0]
    compact = re.sub(r"\s+", "", registered)
    if spec["issuer_name"] not in compact or "接受公司债务融资工具注册" not in compact:
        raise ValueError("MATURITY_REGISTRATION_SOURCE_REQUIRED")
    ceiling = _match(compact, r"同意公司注册发行余额合计不超过([\d.]+)亿元人民币") * YI
    payments = matrix["prospective_debt_service"]["issues"]
    terms = {r["code"]: (r["due"], Decimal(r["face_cny"])) for r in payments}
    disclosed = {r["code"]: (r["maturity"], Decimal(r["principal_cny"])) for r in issues}
    if (not issues or len(terms) != len(payments) or len(disclosed) != len(issues) or terms != disclosed
            or any(r.get("actual_settlement_verified") or date.fromisoformat(r["maturity"]).year not in (first, year)
                   or Decimal(r["gross_issue_price_amount_cny"]) != Decimal(r["principal_cny"]) for r in issues)):
        raise ValueError("MATURITY_ISSUANCE_SCOPE_CHANGED")
    issued = sum(Decimal(r["gross_issue_price_amount_cny"]) for r in issues)
    due_first = financing_maturity_floor(constraints, first)
    due = financing_maturity_floor(constraints, year)
    proxy = opening + draws - repaid + issued - due_first - due
    basket = sum(components.values())
    for scenario in spec["scenarios"].values():
        first_row = scenario["years"][0]
        policy = first_row["policy"]
        if (first_row["year"] != first or Decimal(policy["new_borrowing"]["value"]) != draws + issued
                or Decimal(policy["debt_repayment"]["value"]) != repaid + due_first):
            raise ValueError("MATURITY_FIRST_YEAR_GROSS_PROCEEDS_CHANGED")
    if (issued != due_first + due or proxy < 0 or due <= 0 or financing["unknown_balance_is_forecast"] is not True
            or opening != Decimal(spec["opening"]["debt"]["value"])
            or proxy != Decimal(financing["residual_principal_cny"])
            or components != {k: Decimal(v) for k, v in bridge["basket_components_cny"].items()}
            or [opening, draws, repaid, proxy, due, basket, proxy-basket, components["短借"]] != [
                Decimal(bridge[k]) for k in ("scenario_opening_proxy_2025_cny", "reported_9m_borrowing_cny",
                "reported_9m_repayment_cny", "scenario_remaining_after_mtn_separated", "known_identified_mtn_face",
                "q3_diagnostic_gross_basket", "proxy_minus_basket", "q3_short_borrowing_carrying_amount")]
            or bridge["actual_remaining_bank_principal_due_cny"] is not None
            or bridge["actual_total_principal_upper_cny"] is not None
            or list(map(Decimal, bridge[f"optional_{year}_residual_repayment_cny"])) != [0, proxy]):
        raise ValueError("MATURITY_ORIGINAL_BRIDGE_MISMATCH")
    return dict(year=year, known_principal_cny=str(due), proxy_residual_cny=str(proxy),
                proxy_repayment_min_cny="0", proxy_repayment_max_cny=str(proxy),
                total_repayment_min_cny=str(due), total_repayment_max_cny=str(due + proxy),
                actual_unknown_maturity_cny=None, actual_total_principal_upper_cny=None,
                opening_reported_debt_cny=str(opening), reported_9m_borrowing_cny=str(draws),
                reported_9m_repayment_cny=str(repaid), first_year_contractual_maturities_cny=str(due_first),
                q3_carrying_basket_cny=str(basket), q3_basket_components_cny={k:str(v) for k,v in components.items()},
                proxy_minus_basket_cny=str(proxy-basket), q3_short_borrowing_cny=str(components["短借"]),
                short_borrowing_window_start=date(first, 10, 1).isoformat(),
                short_borrowing_window_end=date(year, 9, 30).isoformat(),
                registration_ceiling_cny=str(ceiling), observed_issuance_cny=str(issued),
                assumed_future_borrowing_cny="0", zero_new_borrowing_from_year=year, first_year=first,
                first_year_issue_proceeds_assumed_at_par_cny=str(issued),
                first_year_issue_proceeds_basis="DISCLOSED_ISSUANCE_ASSUMED_RECEIVED_AT_PAR",
                source_matrix_sha256=financing["originals_matrix_sha256"],
                known_maturities=[dict(code=r["code"], maturity=r["maturity"], principal_cny=r["principal_cny"])
                                  for r in issues if date.fromisoformat(r["maturity"]).year == year],
                opening_debt_reported_unit=matrix["opening_parent_debt"]["unit_in_source"],
                short_borrowing_window_basis="QUARTER_END_CARRYING_BALANCE_WITH_NO_CONTRACTUAL_YEAR_SPLIT",
                balance_basis="OPENING_REPORTED_DEBT_PLUS_BORROWING_LESS_REPAYMENTS_AT_PAR",
                basket_basis="CARRYING_VALUES_INCLUDING_FULL_OTHER_CURRENT_LIABILITIES_AND_LEASES",
                sources={k:sources[k]["pdf_sha256"] for k in (f"FY{(first-1)%100:02d}", f"9M{first%100:02d}", "scp", "mtn")})


def _prepare(context, evidence, rate, coupon, pay_year):
    """Replace only future financing. All borrowings through the first forecast year stay sealed."""
    context = deepcopy(context)
    rows = context["years"]
    year = evidence["year"]
    principal = Decimal(evidence["proxy_residual_cny"])
    known = Decimal(evidence["known_principal_cny"])
    if (rows[0]["year"] != year - 1 or pay_year not in (year, year+1) or rate < 0 or coupon < 0
            or [r["year"] for r in rows] != list(range(year-1, year-1+len(rows)))
            or rows[-1]["year"] < pay_year):
        raise ValueError("MATURITY_EXPLICIT_YEARS_REQUIRED")
    first = rows[0]["policy"]
    if Decimal(context["opening"]["debt"]) + Decimal(first["new_borrowing"]) - Decimal(first["debt_repayment"]) != principal + known:
        raise ValueError("MATURITY_OPENING_POOL_MISMATCH")
    plan = []
    residual = principal
    for row in rows[1:]:
        y = row["year"]
        due = known if y == year else Decimal(0)
        allocation = residual if y == pay_year else Decimal(0)
        interest = (residual * rate).quantize(CENT, rounding=ROUND_HALF_UP) + (coupon if y == year else 0)
        closing = residual - allocation
        row["policy"].update(debt_repayment=str(due + allocation), new_borrowing="0", interest_outside_cfo=str(interest))
        plan.append(dict(year=y, known_principal_cny=str(due), opening_proxy_residual_cny=str(residual),
                         assumed_proxy_repayment_cny=str(allocation), closing_proxy_residual_cny=str(closing),
                         new_borrowing_cny="0", interest_cny=str(interest)))
        residual = closing
    tail = context["terminal"]
    old = tail["policy"]
    # Only clear the previous explicit refinancing/interest legs after reconciling their entire basis.
    old_debt = Decimal(old["debt_repayment"])
    if (residual or Decimal(old["new_borrowing"]) != old_debt
            or Decimal(old["interest_outside_cfo"]) != (old_debt * rate).quantize(CENT, rounding=ROUND_HALF_UP)):
        raise ValueError("MATURITY_TERMINAL_FINANCING_UNRECONCILED")
    old.update(new_borrowing="0", debt_repayment="0", interest_outside_cfo="0")
    tail.pop("financing", None)
    return context, plan


def _calculate(context, scenario, paid, proposed, matrix, evidence, rate, coupon, pay_year, facts, name):
    context, plan = _prepare(context, evidence, rate, coupon, pay_year)
    issues = [{"maturity": i["due"], "principal_cny": i["face_cny"]} for i in matrix["prospective_debt_service"]["issues"]]
    result = fixed._scenario(context, scenario, paid, proposed, matrix, issues)
    if result["status"] == "CALCULATED":
        calc = result["calculation"]
        rows = calc["annual_rows"]
        # Independently run F1 on the corrected, reserved E2 policies and its original typed fact basis.
        typed = replace(facts.scenario_inputs[name], opening=context["opening"], terminal=context["terminal"],
                        years=[dict(year=r["year"], policy=r["cash_policy"], scheduled_owner_distribution_cny=
                                    r["scheduled_owner_distribution_cny"]) for r in rows],
                        forecast_roes=tuple(Decimal(r["roe_assumption"]) for r in rows),
                        forecast_retentions=tuple(Decimal(r["retention_assumption"]) for r in rows),
                        cost_of_equity=Decimal(context["cost_of_equity"]))
        confirmed = model.scenario_calculation(facts, typed)
        if (confirmed != calc or any(Decimal(r["closing_debt_cny"]) != Decimal(p["closing_proxy_residual_cny"])
                                      for r, p in zip(rows[1:], plan, strict=True))
                or any(Decimal(r["closing_debt_cny"]) for r in calc["terminal_rows"])):
            raise ValueError("MATURITY_F1_CASH_PATH_MISMATCH")
        result = dict(status="CALCULATED", per_share_value=confirmed["per_share_value"],
                      annual_rows=[{k:r[k] for k in ("year", "opening_cash_cny", "closing_cash_cny", "closing_debt_cny",
                                                    "total_owner_distribution_cny")} for r in rows],
                      terminal_closing_debt_cny=calc["terminal_rows"][-1]["closing_debt_cny"])
    return _with_payment_plan(result, plan)


def _with_payment_plan(result, plan):
    failed = result["ledger"]["year"] if result["status"] == "REJECTED" else None
    for row in plan:
        if failed is None:
            status = "CALCULATED_CONDITIONAL"
        elif row["year"] < failed:
            status = "BEFORE_FIRST_FAILURE"
        elif row["year"] == failed:
            status = "NOT_COMPLETED"
        else:
            status = "NOT_REACHED"
        row["payment_status"] = status
    return dict(result, financing_rows=plan, financing_rows_basis="CONDITIONAL_PAYMENT_PLAN", first_failed_year=failed)


def run_check(source_root, task_id, digest, now):
    """Cold, read-only recheck of both conditional endpoints against the same paid cash path."""
    root = Path(source_root).resolve()
    prior = fixed.run_check(root, task_id, digest, now)
    folder = root / "runtime/parent-cash-task-backed-receipts" / task_id / "funding-revisions" / digest
    receipt = revision._sibling(folder, "receipt", digest)
    assessment = receipt["current_reassessment"]
    spec = revision._sibling(folder, "reassessment-spec", assessment["revised_spec"])
    matrix = revision._sibling(folder, "financing-evidence", receipt["originals_matrix"])
    facts = descriptor_from_payload(revision._sibling(folder, "descriptor", receipt["descriptor"])).facts
    rejected, = [n for n,r in assessment["scenario_rows"].items() if r["status"] == "REJECTED"]
    contexts = fixed._native_inputs(root, spec, receipt, now, rejected)
    paid = Decimal(prior["source_payment"]["paid_cny"])
    proposed = Decimal(prior["conditional_target_cny"])
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        evidence = _evidence(root, receipt, spec, matrix, now)
        year = evidence["year"]
        coupon = sum(Decimal(i["coupon_if_act365_to_maturity"]) for i in matrix["prospective_debt_service"]["issues"]
                     if date.fromisoformat(i["due"]).year == year)
        rates = spec["financing_revision"]["unknown_rate_assumptions"]
        paths = [{n:_calculate(contexts[n], spec["scenarios"][n], paid, proposed, matrix, evidence,
                               Decimal(rates[n]), coupon, pay_year, facts, n) for n in ("bear", "base", "bull")}
                 for pay_year in (year, year+1)]
    primary, deferred = paths
    return dict(schema_version=VERSION, parent_receipt=digest, task_id=task_id,
                predecessor_input=prior["predecessor_input"], symbol=prior["symbol"], valuation_date=prior["valuation_date"],
                maturity_evidence=evidence, scenarios=primary, alternative_scenarios=deferred,
                scenario_basis="FULL_PROXY_REPAYMENT_IN_BOUNDARY_YEAR",
                alternative_basis="KNOWN_ONLY_THEN_FULL_PROXY_REPAYMENT_NEXT_YEAR_STRESS",
                status="REJECTED" if any(r["status"] == "REJECTED" for r in primary.values()) else "CALCULATED",
                current_research_range_adopted=False, action="no_order", formal_eligibility=False, current_comparable=False)
