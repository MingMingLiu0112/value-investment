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

VERSION = "operating-horizon-cash-policy-e2-input-v17"


def _validate_cash_constraint_citations(policy_years, context):
    """Require a term-specific anchor apart from supplemental funding constraints."""
    from .agent_review.operating_cash_policy_draft_v16_generic import candidates

    scopes = {row["id"]: row.get("scope") for row in context["evidence"]}
    eligible_ids = candidates(context, context["source_binding"])
    for scenarios in policy_years.values():
        for path in scenarios.values():
            for term_name, term in path["terms"].items():
                anchors = {
                    evidence_id
                    for evidence_id in eligible_ids[term_name]
                    if scopes[evidence_id] != "ISSUER_FINANCING_DISCLOSURE"
                    and (scopes[evidence_id] != "ISSUER_ARTICLES_RULE_TEXT"
                         or term_name == "reserve_ratio")
                }
                if anchors.isdisjoint(term["evidence_ids"]):
                    raise ValueError("V25_E2_CASH_TERM_REQUIRES_APPLICABLE_ANCHOR:" + term_name)


def read_v25_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    result = read_generic_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=CONTRACT, service_type=OperatingHorizonTaskService,
        version=VERSION, label="V25", service=service, staged_annual=True,
        additional_reported_fact_loaders=(RETURN_PLAN_LOADER, PARENT_QUARTER_LOADER, CASH_CONSTRAINT_LOADER))
    bound_service = service or OperatingHorizonTaskService(root)
    spec, _, _ = bound_service._load(task_id)
    if spec["source_loader_binding"]["version"] == CASH_CONSTRAINT_LOADER:
        _validate_cash_constraint_citations(result["policy_years"], bound_service._context(spec))
    return result



