"""Projection of a cold-recomputed direct-owner candidate into existing E2 view."""
from zoneinfo import ZoneInfo
from ..research.agent_review.web_research import _binding
from ..research.direct_owner_cash_research_v1 import replay_direct_owner_cash_receipt, _read
from ..decision.direct_owner_cash_price_draft_v1 import draft_direct_owner_cash_price

def read_direct_owner_cash_view(*,root,receipt_binding,now):
    if now.utcoffset() is None:raise ValueError("DIRECT_OWNER_AWARE_PUBLIC_CLOCK_REQUIRED")
    result=replay_direct_owner_cash_receipt(root=root,receipt_binding=receipt_binding,now=now)
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
            source_refs=result["source_bindings"]))
