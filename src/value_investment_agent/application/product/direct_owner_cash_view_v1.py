"""Projection of a cold-recomputed direct-owner candidate into existing E2 view."""
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo
from ..research.agent_review.web_research import _binding
from ..research.direct_owner_cash_research_v1 import replay_direct_owner_cash_receipt, _read
from ..decision.direct_owner_cash_price_draft_v1 import draft_direct_owner_cash_price

def _first_year_no_new_borrowing_stress(rows):
    """Conditional first-year cash-floor gap before owner distributions."""
    if not rows:
        return None
    first=rows[0]
    borrowing=Decimal(first["cash_policy"]["new_borrowing"])
    floor=Decimal(first["cash_policy"]["cash_floor"])
    cash_without_borrowing=Decimal(first["cash_before_distribution_cny"])-borrowing
    return dict(
        year=first["year"],removed_assumed_new_borrowing_cny=str(borrowing),
        cash_before_distribution_without_new_borrowing_cny=str(cash_without_borrowing),
        minimum_funding_gap_to_cash_floor_cny=str(max(Decimal(0),floor-cash_without_borrowing)),
        scope="CONDITIONAL_FIRST_YEAR_NO_NEW_BORROWING_NO_DISTRIBUTION_STRESS")


def _opening_debt_evidence_comparison(compiled):
    """Compare the forecast opening debt with identified parent balance rows only."""
    statements=compiled.get("evidence", {}).get("statements", [])
    if len(statements) != 1:
        return None
    balance=statements[0].get("balance_sheet", {})
    keys=("short_term_borrowings_cny", "current_noncurrent_liabilities_cny",
          "long_term_borrowings_cny", "lease_liabilities_cny")
    if any(key not in balance for key in keys):
        return None
    facts=[balance[key] for key in keys]
    if any(fact.get("scope") != "ISSUER_PARENT_STANDALONE" or
           fact.get("classification") != "FACT" or fact.get("currency") != "CNY" or
           fact.get("source_refs", {}).get("current_period") != compiled["valuation_date"]
           for fact in facts):
        return None
    identified=sum((Decimal(fact["current"]) for fact in facts), Decimal(0))
    assumed=Decimal(compiled["opening"]["debt"])
    return dict(scope="PARENT_IDENTIFIED_BALANCE_LINES_NOT_COMPLETE_DEBT_VERIFICATION",
        period=compiled["valuation_date"], forecast_opening_debt_cny=str(assumed),
        identified_parent_balance_lines_cny=str(identified),
        unexplained_difference_cny=str(assumed-identified),
        included_fields=list(keys), source_refs=[fact["source_refs"] for fact in facts],
        completeness_verified=False, maturity_schedule_verified=False)


def read_direct_owner_cash_view(*,root,receipt_binding,now):
    if now.utcoffset() is None:raise ValueError("DIRECT_OWNER_AWARE_PUBLIC_CLOCK_REQUIRED")
    result=replay_direct_owner_cash_receipt(root=root,receipt_binding=receipt_binding,now=now)
    basis=date.fromisoformat(result["compiled"]["valuation_date"])
    issues=(result["compiled"]["evidence"].get("constraints") or {}).get("issued_financing") or []
    after_basis=[row for row in issues if date.fromisoformat(row["issue_date"]) > basis]
    no_new_borrowing_stress={}
    for name in ("bear", "base", "bull"):
        rows=result["compiled"]["scenarios"][name]["calculation"]["annual_rows"]
        stress=_first_year_no_new_borrowing_stress(rows)
        if stress is not None:
            no_new_borrowing_stress[name]=stress
    financing_review=dict(basis_date=basis.isoformat(),
        post_basis_issuance_cny=str(sum((Decimal(row["principal_cny"]) for row in after_basis), Decimal(0))),
        post_basis_issue_codes=[row["code"] for row in after_basis],
        opening_debt_verified=False,outstanding_or_refinancing_verified=False,
        reason="POST_BASIS_ISSUANCE_IS_NOT_OPENING_DEBT_OR_CONFIRMED_REFINANCING",
        source_refs=[row["source_refs"] for row in after_basis],
        first_year_no_new_borrowing_stress=no_new_borrowing_stress,
        opening_debt_evidence_comparison=_opening_debt_evidence_comparison(result["compiled"])) if after_basis else None
    for binding in result["source_bindings"]:_binding(root,binding,runtime_only=False)
    receipt=_read(root,receipt_binding)
    spec=_read(root,receipt["spec_binding"])
    compiled=result["compiled"]
    value=result["valuation"]
    plan=dict(symbol=result["symbol"],research_version=spec["research_version"],
        valuation_input_version=result["input_descriptor_sha256"],
        model_id=result["package"]["requested_model"],model_type=value["model_type"],
        model_version=value["model_version"],valuation_date=value["valuation_date"],
        **{name:value[name+"_value"] for name in ("bear","base","bull")},
        source_bindings=result["source_bindings"],action="no_order")
    price=draft_direct_owner_cash_price(plan=plan,rule_config=spec.get("price_policy",{}),as_of=now.astimezone(ZoneInfo("Asia/Shanghai")).date())
    assumptions=[]; seen=set()
    for i,row in enumerate(compiled["assumptions"]):
        item=dict(name=row.get("name", "假设"+str(i+1)),rationale=row["rationale"],
            counter_evidence=row["counter_evidence"],reopen_condition=row["reopen_condition"])
        key=(item["rationale"],item["counter_evidence"],item["reopen_condition"])
        if key not in seen:
            seen.add(key); assumptions.append(item)
    annual={name:row["calculation"]["annual_rows"] for name,row in compiled["scenarios"].items()}
    return dict(schema_version="first-research-input-view-v1",status="SOURCE_BOUND_FIRST_INPUT_COMPILED",
        reason=None,symbol=result["symbol"],action="no_order",formal_eligibility=False,
        main_range_adopted=False,main_valuation_range=None,current_price=None,condition_price=None,
        personal_quantity=None,user_acceptance="NOT_CONFIRMED",
        scope=result["compilation_scope"],receipt_binding=receipt_binding,
        input_descriptor_sha256=result["input_descriptor_sha256"],input_fingerprint=result["input_fingerprint"],
        financial_basis=spec["valuation_date"],research_as_of=spec["research_as_of"],
        research_case=result["research_case"],valuation=value,valuation_status=result["valuation_status"],
        annual_ledgers={name:dict(rows=rows) for name,rows in annual.items()},
        blockers=result["blockers"],source_bindings=result["source_bindings"],
        compilation_scope=result["compilation_scope"],scenario_label_scope=result["scenario_label_scope"],
        sources=result["package"]["sources"],operating_assumptions=spec["scenarios"],
        source_review="PARENT_ORIGINALS_REPARSED_AND_SHARED_MODEL_RECONSUMED",
        investment_conclusion="UNAPPROVED_CONDITIONAL_OWNER_CASH_RESEARCH",
        direct_owner_cash=dict(method="DIRECT_CFO_LESS_EXPLICIT_CAPITAL_DEBT_AND_CONSTRAINED_DISTRIBUTIONS",
            valuation_basis=spec["valuation_date"],scope="ISSUER_PARENT_STANDALONE",
            annual_rows=annual,assumptions=assumptions,conditional_price=price,
            source_refs=result["source_bindings"],financing_review=financing_review))
