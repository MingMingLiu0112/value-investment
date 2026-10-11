"""Expose consumed facts and assumptions for review, never grant admission."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .decision_surface import verify_current_decision_workbench
from .source_bound_inputs import verify_package_local_sources
from ...research_artifact_codecs import artifact_payload
from ...m1_valuation_package_builder import build_descriptor


def build_research_review_packet(*, root: Path, package_path: Path,
                                package_sha256: str, workbench_path: Path,
                                workbench_sha256: str, output_path: Path) -> dict[str, Any]:
    root = root.resolve()
    package_path = require_inside(root, package_path, "review package")
    workbench_path = require_inside(root / "runtime", workbench_path, "review workbench")
    output_path = require_inside(root / "runtime", output_path, "review output")
    if sha256_file(package_path) != package_sha256 or sha256_file(workbench_path) != workbench_sha256:
        raise ValueError("research review input hash mismatch")
    package = load_json_object(package_path, "review package")
    workbench = load_json_object(workbench_path, "review workbench")
    verified = verify_current_decision_workbench(workbench)
    objects = {key: artifact_payload(value)[1] for key, value in verified.dependency_objects.items()}
    case, facts = objects["research_case"], objects["financial_facts"]
    if package["symbol"] != workbench["symbol"] or package["research_case"]["as_of"] != case["as_of"]:
        raise ValueError("research review identity/date mismatch")
    # The descriptor omits package-only locators, availability metadata and
    # anchors. Bind the original bytes as well as the normalized run contract.
    receipt = workbench.get("research_receipt") or {}
    if (receipt.get("command") != "company_research"
            or receipt.get("symbol") != workbench["symbol"]
            or receipt.get("action") != "no_order"
            or (receipt.get("input_sha256") or {}).get("valuation_package") != package_sha256):
        raise ValueError("review package differs from consumed package binding")
    local_sources = verify_package_local_sources(root, package)
    effective_package = dict(package)
    effective_package["facts"] = dict(package["facts"])
    if "kind" not in effective_package["facts"]:
        effective_package["facts"]["kind"] = effective_package["facts"].get("facts_type")
    effective_package["recommendation_schema_version"] = verified.recommendation.schema_version
    descriptor = build_descriptor(effective_package, root=root)
    if descriptor.input_sha256 != workbench.get("input_descriptor_sha256"):
        raise ValueError("review package differs from consumed source/input descriptor")
    for role, value in (("research_case", descriptor.research_case),
                        ("financial_facts", descriptor.facts),
                        ("valuation_assumptions", descriptor.assumptions)):
        declared = None if value is None else artifact_payload(value)[1]
        if declared != objects.get(role):
            raise ValueError(f"review package differs from consumed {role}")
    catalog = {source["id"]: source for source in package.get("sources", [])}
    def refs(items):
        result = []
        for item in items:
            source = catalog.get(item.get("id"))
            result.append({**item, "source_kind": source.get("kind") if source else None,
                "public_available_at": source.get("source_available_at") if source else item.get("available_at"),
                "published_at": source.get("published_at") if source else None,
                "source_url": source.get("location") if source else item.get("source_url"),
                "locator_status": "EXPLICIT_LOCATOR" if any(item.get(key) for key in
                    ("physical_page", "page", "table", "excerpt")) else "LOCATOR_NOT_IN_REFERENCE",
                "semantic_approval": "NOT_GRANTED_BY_FILE_VERIFICATION"})
        return result
    assumptions = objects.get("valuation_assumptions") or {}
    rows = []
    for assumption in assumptions.get("assumptions", []):
        bindings = [item for item in package.get("assumption_bindings", [])
                    if item["assumption_name"] == assumption["name"]]
        rows.append({"name": assumption["name"], "classification": "VALUATION_ASSUMPTION_NOT_OFFICIAL_FACT",
            "values": {key: assumption.get(key) for key in ("bear", "base", "bull", "unit")},
            "basis": assumption.get("basis"), "rationale_and_countercase": assumption.get("rationale"),
            "as_of": assumption.get("as_of"), "valuation_impact": assumption.get("sensitivity"),
            "confidence": assumption.get("confidence"), "consumption_bindings": bindings,
            "source_refs": refs(assumption.get("evidence_refs", [])),
            "review_status": "CONDITIONAL_RESEARCH_REQUIRES_EXACT_VERSION_APPROVAL",
            "blockers": assumption.get("blockers", [])})
    summary = case.get("financial_summary") or {}
    scope_review = summary.get("financial_scope_review") or {}
    result = {
        "schema_version": "research-review-packet-v1", "symbol": workbench["symbol"], "action": "no_order",
        "research_as_of": case["as_of"], "generated_at": workbench["generated_at"],
        "scope": "CONSUMED_RESEARCH_REVIEW_NOT_NEW_FACT_OR_APPROVAL",
        "input_descriptor_sha256": descriptor.input_sha256,
        "source_contract_status": (workbench.get("source_verification") or {}).get("source_contract_status"),
        "official_fact_anchors": (package.get("source_contract") or {}).get("fact_anchors", []),
        "consumed_operating_inputs": facts.get("operating_inputs"),
        "financial_summary": summary,
        "financial_summary_scope": "REPORTED_DERIVED_AND_RESEARCH_FIELDS_RETAIN_ORIGINAL_CLASSIFICATION",
        "assumptions": rows, "model_validity": objects.get("model_validity"),
        "gate": objects.get("research_gate"),
        "human_review_items": scope_review.get("not_accepted", []),
        "limited_financial_acceptance": scope_review,
        "strongest_counterevidence": case.get("counter_evidence", []),
        "next_triggers": case.get("next_events", []),
        "decision_blockers": (workbench.get("decision_recommendation") or {}).get("blockers", []),
        "valuation_status": (objects.get("valuation") or {}).get("status"),
        "research_admitted": False, "approval_changed": False, "position_guidance": None,
        "canonical_written": False,
        "source_bindings": [{"path": path.relative_to(root).as_posix(), "sha256": digest}
            for path, digest in [(package_path, package_sha256), (workbench_path, workbench_sha256), *local_sources]],
        "assurance_limits": ["File hashes do not verify economic explanations.",
            "Missing page/table locators remain explicit; no locator or approval is fabricated.",
            "Assumption values are consumed model conditions, not disclosed forecasts or buying prices."],
    }
    for item in result["source_bindings"]:
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError("research review source changed during consumption")
    write_new_json(output_path, result)
    return result
