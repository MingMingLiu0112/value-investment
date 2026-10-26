"""Bounded metadata-only status of the server's registered research workflows."""
import hashlib
from pathlib import Path
import re

from .web_research import (
    MAX_JSON, REGISTRY_PATH, REGISTRY_SCHEMA, REGISTRY_WORKFLOWS_SCHEMA,
    WORKFLOWS, _public_path, _raw, _json, read_web_agent_research,
)


def _verified_name(root, binding):
    """Read an optional issuer name from the already verified workbench bytes."""
    try:
        path = _public_path(root, binding["path"], runtime_only=True)
        raw = _raw(path, MAX_JSON)
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            return None
        workbench = _json(raw)
        for artifact in workbench["artifact_bundle"]["artifacts"]:
            if artifact.get("identity", {}).get("artifact_type") != "research_case":
                continue
            payload = artifact["canonical_payload"]
            case = _json(payload.encode("utf-8")) if isinstance(payload, str) else None
            name = case.get("name") if case is not None else None
            if isinstance(name, str) and 1 <= len(name.strip()) <= 200:
                return name.strip()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


def _review_queue_item(root, view):
    workflow = view["workflow"]
    findings = view["findings"]
    pending = sum(row.get("status") == "PENDING_HUMAN_REVIEW" for row in findings)
    sources = view.get("sources") or []
    source_times = [row.get("available_at") for row in sources
                    if isinstance(row, dict) and isinstance(row.get("available_at"), str)]
    scope = view["scope"]
    data_scope = view.get("data_scope")
    mode = view["mode"]
    test_only = (mode in {"MOCK", "OFFLINE_REPLAY"} or data_scope == "TEST_ONLY"
                 or str(scope).startswith("TEST_ONLY"))
    excerpt_origin = ("DERIVED_FROM_VERIFIED_PLAN"
                      if workflow == "hotspot" and data_scope == "PUBLIC_RESEARCH" else None)
    bindings = view["bindings"]
    return dict(
        symbol=view["symbol"], name=_verified_name(root, bindings["workbench"]),
        workflow=workflow, status="PENDING_HUMAN_REVIEW", verification_status=view["status"],
        research_as_of=view.get("research_as_of"), available_at=view.get("generated_at"),
        source_available_at=max(source_times) if source_times else None,
        source_scope=dict(
            scope=scope, data_scope=data_scope, mode=mode,
            classification=("TEST_ONLY_OR_MOCK_NOT_FORMAL_EVIDENCE" if test_only
                            else "RESEARCH_DRAFT_NOT_FORMAL_EVIDENCE"),
            test_only=test_only, formal_evidence=False, excerpt_origin=excerpt_origin),
        packet_binding=dict(bindings["packet"]),
        registration_binding=dict(bindings["registry"]),
        review_reason="VERIFIED_RESEARCH_FINDINGS_PENDING_HUMAN_REVIEW",
        review_reason_text=(f"{pending} registered finding(s) are locally verified but remain "
                            "pending human semantic and evidence review."),
        next_action="OPEN_REGISTERED_DRAFT_FOR_HUMAN_REVIEW",
        next_action_text=("Open the registered workflow draft and review its findings and sources. "
                          "This does not authorize an order, approval, or formal eligibility."),
        pending_findings_count=pending,
        action="no_order", approval_unchanged=True, formal_eligibility_unchanged=True,
        decision_changed=False)


def read_agent_research_status(root: Path, *, now) -> dict:
    """Replay at most 100 companies x existing five workflows; no providers or writes."""
    root = Path(root).resolve()
    result = dict(action="no_order", status="NOT_CONNECTED", items=[], failures=[],
                  review_queue=[], review_queue_count=0, approval_unchanged=True,
                  formal_eligibility_unchanged=True, decision_changed=False)
    try:
        path = _public_path(root, REGISTRY_PATH)
        if not path.exists():
            return result
        registry_raw = _raw(path, 64 * 1024)
        registry = _json(registry_raw)
        if (set(registry) != {"schema_version", "action", "cases"}
                or registry["schema_version"] not in {REGISTRY_SCHEMA, REGISTRY_WORKFLOWS_SCHEMA}
                or registry["action"] != "no_order" or not isinstance(registry["cases"], dict)
                or len(registry["cases"]) > 100):
            raise ValueError("Invalid bounded server registry")
        multi = registry["schema_version"] == REGISTRY_WORKFLOWS_SCHEMA
        for symbol, case in sorted(registry["cases"].items()):
            if (not re.fullmatch(r"[0-9]{6}", symbol) or not isinstance(case, dict)
                    or multi and (set(case) != {"workflows"} or not isinstance(case["workflows"], dict)
                                  or not case["workflows"] or set(case["workflows"]) - set(WORKFLOWS))):
                result["failures"].append(dict(symbol=None, workflow=None,
                    status="UNAVAILABLE", reason="INVALID_REGISTERED_CASE"))
                continue
            workflows = case["workflows"] if multi else {"legacy": case}
            for workflow in sorted(workflows):
                try:
                    view = read_web_agent_research(root, symbol=symbol, workflow=workflow, now=now)
                except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    view = dict(status="UNAVAILABLE", reason="REGISTERED_RESEARCH_VERIFICATION_FAILED")
                verified = view["status"] == "VERIFIED"
                findings = view.get("findings", []) if verified else []
                result["items"].append(dict(symbol=symbol, workflow=workflow, status=view["status"],
                    mode=view.get("mode") if verified else None,
                    research_cutoff=view.get("research_as_of") if verified else None,
                    packet_sha256=view.get("bindings", {}).get("packet", {}).get("sha256") if verified else None,
                    generated_at=view.get("generated_at") if verified else None,
                    findings_count=len(findings), pending_human_review=sum(
                        row.get("status") == "PENDING_HUMAN_REVIEW" for row in findings)))
                if verified and result["items"][-1]["pending_human_review"]:
                    result["review_queue"].append(_review_queue_item(root, view))
                if not verified:
                    result["failures"].append(dict(symbol=symbol, workflow=workflow,
                        status=view["status"], reason=view.get("reason", "REGISTERED_RESEARCH_VERIFICATION_FAILED")))
        if _raw(path, 64 * 1024) != registry_raw:
            raise ValueError("Registry changed during metadata verification")
        if result["items"] or result["failures"]:
            good = sum(row["status"] == "VERIFIED" for row in result["items"])
            result["status"] = "PARTIAL" if good and result["failures"] else "VERIFIED" if good else "UNAVAILABLE"
        result["review_queue_count"] = len(result["review_queue"])
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return dict(action="no_order", status="UNAVAILABLE", items=[], failures=[
            dict(symbol=None, workflow=None, status="UNAVAILABLE", reason="REGISTRY_VERIFICATION_FAILED")],
            review_queue=[], review_queue_count=0, approval_unchanged=True,
            formal_eligibility_unchanged=True, decision_changed=False)
