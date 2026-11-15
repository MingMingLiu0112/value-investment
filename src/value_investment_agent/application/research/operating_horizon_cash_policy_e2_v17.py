"""Admit a source-bound V25 native-transport task through the existing E2 gate."""
from datetime import datetime
from pathlib import Path

from .operating_horizon_cash_policy_e2_v11 import read_generic_cash_policy_e2_input
from .agent_review.operating_horizon_task_v25_canonical import (
    CONTRACT, OperatingHorizonTaskService,
)

from .agent_review.operating_horizon_sources_v2_return_plan import VERSION as RETURN_PLAN_LOADER
from .agent_review.operating_horizon_sources_v3_parent_quarter import VERSION as PARENT_QUARTER_LOADER
from .agent_review.operating_horizon_sources_v4_cash_constraints import VERSION as CASH_CONSTRAINT_LOADER
from .agent_review.operating_horizon_sources_v5_parent_trade import VERSION as PARENT_TRADE_LOADER
from .agent_review.operating_horizon_sources_v6_industry_cost import VERSION as INDUSTRY_COST_LOADER
from .agent_review.operating_horizon_charter_sources_v1 import VERSION as CHARTER_LOADER

VERSION = "operating-horizon-cash-policy-e2-input-v17"


def missing_cash_constraint_citations(policy_years, context):
    """Identify terms whose cited sources cannot anchor a condition for E2."""
    from .agent_review.operating_cash_policy_draft_v16_generic import candidates

    evidence = {row["id"]: row for row in context["evidence"]}
    eligible_ids = candidates(context, context["source_binding"])
    missing = []
    for year, scenarios in policy_years.items():
        for scenario, path in scenarios.items():
            for term_name, term in path["terms"].items():
                anchors = {
                    evidence_id
                    for evidence_id in eligible_ids[term_name]
                    if evidence[evidence_id].get("scope") not in {
                        "ISSUER_FINANCING_DISCLOSURE", "ISSUER_PARENT_STANDALONE_BALANCE_PROXY",
                        "ISSUER_PARENT_UNDATED_COMMITMENT_BOUND", "ISSUER_INDUSTRY_COST_COMPOSITION",
                    }
                    and (evidence[evidence_id].get("scope") != "ISSUER_ARTICLES_RULE_TEXT"
                         or term_name == "reserve_ratio")
                    and not (term_name == "operating_wc_cash_cny"
                             and evidence[evidence_id].get("field") in {"parent_cfo", "cfo_cny"})
                    and not (term_name == "commitment_cash_cny"
                             and evidence[evidence_id].get("field") in {
                                 "parent_capex", "gross_capex_cny", "investment_income_cash_cny",
                             })
                }
                if anchors.isdisjoint(term["evidence_ids"]):
                    missing.append(dict(year=year, scenario=scenario, term=term_name))
    return missing


def _validate_cash_constraint_citations(policy_years, context):
    missing = missing_cash_constraint_citations(policy_years, context)
    if missing:
        raise ValueError("V25_E2_CASH_TERM_REQUIRES_APPLICABLE_ANCHOR:" + missing[0]["term"])


def read_v25_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    result = read_generic_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=CONTRACT, service_type=OperatingHorizonTaskService,
        version=VERSION, label="V25", service=service, staged_annual=True,
        additional_reported_fact_loaders=(RETURN_PLAN_LOADER, PARENT_QUARTER_LOADER,
                                          CASH_CONSTRAINT_LOADER, PARENT_TRADE_LOADER, INDUSTRY_COST_LOADER, CHARTER_LOADER))
    bound_service = service or OperatingHorizonTaskService(root)
    spec, _, _ = bound_service._load(task_id)
    binding = spec["source_loader_binding"]
    if "cash_transport" in binding or binding["version"] in (
        CASH_CONSTRAINT_LOADER, PARENT_TRADE_LOADER, INDUSTRY_COST_LOADER,
    ):
        _validate_cash_constraint_citations(result["policy_years"], bound_service._context(spec))
    return result



