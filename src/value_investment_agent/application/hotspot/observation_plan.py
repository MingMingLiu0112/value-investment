"""Source-bound independent observation and validation, before human approval."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .current_case_review import inspect_current_price_case, expire_price_action_plan
from .independent_price_conditions import project_independent_price_condition
from .price_action_case import project_current_price_action_plan
from .validation_evidence import build_hotspot_quantitative_validation


def _validation_summary(report: dict | None, *, symbol: str, case_binding: dict) -> dict:
    if report is None:
        return dict(status="NOT_RUN", applicability="NO_BOUND_VALIDATION",
            strategy_validation="NOT_PROVEN", signal_event_count=None, trade_count=None,
            execution_metrics=dict(status="UNASSESSABLE", cost_sensitivity=None),
            strict_pit_admitted=False, strict_oos_admitted=False,
            elapsed_real_shadow_sessions=0, formal_eligibility=False, action="no_order")
    same_case = any(row.get("symbol") == symbol and
        row.get("case_binding", {}).get("case_path") == case_binding["path"] and
        row.get("case_binding", {}).get("case_sha256") == case_binding["sha256"]
        for row in report.get("results", []))
    execution = report.get("metrics_scope") == "FROZEN_ORDER_EXECUTION_SIMULATION"
    count = report.get("trade_count")
    return dict(status=report["status"], protocol_binding=report["protocol_binding"],
        evidence_sha256=report["evidence_sha256"], evaluated_at=report["evaluated_at"],
        source_bindings=deepcopy(report.get("source_bindings", [])),
        namespace=report.get("namespace"), metrics_scope=report.get("metrics_scope"),
        applicability=("SAME_CASE_DESCRIPTIVE_ONLY" if same_case else
                       "EXECUTION_PROTOCOL_NOT_BOUND_TO_CURRENT_STRUCTURE" if execution else
                       "HISTORICAL_OTHER_CASES_NOT_CURRENT_STRUCTURE"),
        partitions=deepcopy(report.get("partitions")), strategy_validation="NOT_PROVEN",
        signal_event_count=report.get("signal_event_count"), trade_count=count,
        sample_status=(report.get("sample_status") if execution else "NO_EXECUTION_SAMPLE"),
        execution_metrics=(dict(status="INSUFFICIENT_SAMPLE" if report.get("sample_status") == "INSUFFICIENT" else "SIMULATION_ONLY",
            trade_count=count, folds=deepcopy(report["folds"]),
            cost_sensitivity=deepcopy(report["cost_sensitivity"])) if execution else
            deepcopy(report.get("execution_metrics", dict(status="UNASSESSABLE")))),
        strict_pit_admitted=False, strict_oos_admitted=False,
        elapsed_real_shadow_sessions=0, formal_eligibility=False, action="no_order")


def build_hotspot_observation_plan(*, root: Path, symbol: str, case_binding: dict,
        now: datetime, validation_binding: dict | None = None,
        allow_test_only: bool = False) -> dict:
    """Recompute a bound case and optional validation without changing pointers.

    Case bindings always identify the structure being observed. Validation
    bindings identify their own historical sample; neither substitutes for the
    other. The existing signed independent admission remains the review gate.
    """
    if type(allow_test_only) is not bool:
        raise ValueError("Test-only permission requires an explicit boolean")
    review = inspect_current_price_case(root=root, symbol=symbol, case_binding=case_binding, now=now)
    report = None
    if validation_binding is not None:
        report = build_hotspot_quantitative_validation(root=root,
            protocol_binding=validation_binding, now=now)
        if report.get("namespace") != "ACTUAL" and not allow_test_only:
            raise ValueError("Actual observation requires ACTUAL validation evidence")
    validation = _validation_summary(report, symbol=symbol, case_binding=case_binding)
    summary = {key: value for key, value in review.items() if key != "case"}
    output = dict(schema_version="hotspot-observation-plan-v1", symbol=symbol,
        strategy="HOTSPOT_SATELLITE", evaluated_at=now.isoformat(),
        status="UNASSESSABLE", current_data=summary, validation=validation,
        price_action_plan=None, position_guidance=None, holdings_status="UNKNOWN",
        personal_action="WATCH", formal_eligibility=False, risk_review_eligible=False,
        strategy_validation="NOT_PROVEN", action="no_order")
    if review["case"] is None:
        output["blockers"] = [review["reason"]]
        return output
    source = project_current_price_action_plan(review["case"])
    source.update(case_path=case_binding["path"], case_sha256=case_binding["sha256"],
        current_data_status=review["data_status"], source_integrity=review["source_integrity"])
    if review["data_status"] == "STALE":
        source = expire_price_action_plan(source, review=review)
    plan = project_independent_price_condition(root, symbol=symbol, plan=source, now=now,
                                              allow_test_only=allow_test_only)
    # This unsigned observation workflow cannot request a personalized review.
    plan.update(risk_review_eligible=False, action_intent="WATCH", position_guidance=None)
    rules = plan.get("conditional_action_rules", {})
    output.update(status="HISTORICAL_OBSERVATION_ONLY" if review["data_status"] == "STALE"
        else "OBSERVATION_ONLY", price_action_plan=plan,
        observation_conditions=dict(entry=deepcopy(rules.get("OPEN")),
            add=deepcopy(rules.get("ADD")), stop=deepcopy(rules.get("EXIT")),
            reduce=deepcopy(rules.get("REDUCE")), exit=deepcopy(rules.get("EXIT"))),
        blockers=list(dict.fromkeys([*plan["blockers"], "STRATEGY_VALIDATION_NOT_PROVEN",
            "OBSERVATION_PLAN_NOT_PERSONAL_ACTION"])),
        remaining_requirements=[
            dict(code="CURRENT_COMPLETED_SOURCE", status=review["data_status"],
                 required="Exact current case, completed exchange session and verified source bytes"),
            dict(code="EXECUTION_COST_EVIDENCE", status=validation["execution_metrics"]["status"],
                 required="Bound dated costs, orders, liquidity, suspension, limits and T+1 evidence"),
            dict(code="STRICT_PIT_AND_OOS", status="NOT_PROVEN",
                 required="Contemporaneous inputs, frozen strategy and untouched predeclared OOS"),
            dict(code="NATURAL_SHADOW_SESSIONS", status="NOT_PROVEN",
                 required="At least 20 verified real trading sessions; replay grants zero sessions"),
            dict(code="HUMAN_STRATEGY_APPROVAL", status=plan["independent_admission"].get("review_status", "NOT_PROVEN"),
                 required="Exact-version authorized independent strategy approval"),
            dict(code="PERSONAL_HOLDINGS_AND_RISK", status="NOT_EVALUATED",
                 required="Actual holding, remaining capacity and sellable inventory before ADD/REDUCE/EXIT"),
        ])
    # Bind dependencies again after both computations, guarding concurrent edits.
    final = inspect_current_price_case(root=root, symbol=symbol, case_binding=case_binding, now=now)
    if final != review:
        raise ValueError("Observation case changed during validation")
    return output
