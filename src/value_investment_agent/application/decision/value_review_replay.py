"""Bounded isolated arithmetic replay; not a full admission or approval replay."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ...human_research_approval import artifact_fingerprint
from ...m1_valuation_package_builder import build_quality_facts, build_research_case
from ...research_artifact_codecs import artifact_payload
from ...valuation_router import VALUATION_MODEL_REGISTRY
from ...valuation_router import ValuationRouter, ROUTE_SUPPORTED
from ...research_profile import PROFILES


def replay_value_review_inputs(root, *, package_binding, explanation_binding, isolated_root):
    """Copy only two payloads and their direct valuation/facts/case references.

    Uses the existing typed builders and registered shared model. Deliberately
    does not build a full descriptor or traverse event scans, source catalogs,
    approval dependencies or inherited historical audits. Exact input artifact
    fingerprints must match the published decision dependency refs.
    """
    root = Path(root).resolve()
    isolated_root = Path(isolated_root).resolve()
    if not isolated_root.is_relative_to(root / ".tmp") or isolated_root.exists():
        raise ValueError("Replay requires a new isolated directory under repository .tmp")
    bindings = {}

    def verified_bytes(binding):
        name = binding["path"]
        path = (root / name).resolve()
        if (Path(name).is_absolute() or not path.is_relative_to(root)
                or not name.startswith("runtime/")
                or any(term in name.lower() for term in ("private", "journal", "secret", ".tmp"))):
            raise ValueError("Replay requires relative public inputs")
        if path.stat().st_size >= 32 * 1024 * 1024:
            raise ValueError("Replay source exceeds bounded copy limit")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            raise ValueError("Replay source hash mismatch")
        existing = bindings.get(name)
        if existing and existing["sha256"] != binding["sha256"]:
            raise ValueError("Conflicting replay source hashes")
        bindings[name] = dict(path=name, sha256=binding["sha256"])
        return raw

    package = json.loads(verified_bytes(package_binding))
    explanation = json.loads(verified_bytes(explanation_binding))
    route = ValuationRouter().route(PROFILES[package["profile_id"]], package.get("requested_model"))
    if (explanation.get("action") != "no_order" or package["symbol"] != explanation["symbol"]
            or route.status != ROUTE_SUPPORTED or route.model_type != "residual_income_or_equity_value"):
        raise ValueError("Replay input identity mismatch")
    references = [*explanation["valuation"]["evidence_refs"],
        *package["research_case"]["evidence_refs"], *package["facts"]["evidence_refs"]]
    for ref in references:
        if ref.get("path"):
            verified_bytes(dict(path=ref["path"], sha256=ref["sha256"]))
    isolated_root.mkdir(parents=True)
    copied = []
    for binding in bindings.values():
        raw = verified_bytes(binding)
        destination = isolated_root / binding["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        copied.append({**binding, "size_bytes": len(raw), "copy_hash_matches":
            hashlib.sha256(destination.read_bytes()).hexdigest() == binding["sha256"]})

    # From this point the arithmetic reads only copied payloads, never root inputs.
    package = json.loads((isolated_root / package_binding["path"]).read_bytes())
    explanation = json.loads((isolated_root / explanation_binding["path"]).read_bytes())
    facts = build_quality_facts(package["facts"])
    case = build_research_case(package["research_case"])
    expected = {ref["role"]: ref["payload_sha256"] for ref in explanation["decision_dependency_refs"]}
    input_checks = {role: dict(expected_sha256=expected[role],
        replayed_sha256=artifact_fingerprint(artifact_payload(obj)[1]))
        for role, obj in (("research_case", case), ("financial_facts", facts))}
    if any(row["expected_sha256"] != row["replayed_sha256"] for row in input_checks.values()):
        raise ValueError("Isolated inputs differ from published consumed fingerprints")
    valuation = VALUATION_MODEL_REGISTRY.build(route.selected_model).value(facts, case)
    payload = artifact_payload(valuation)[1]
    digest = artifact_fingerprint(payload)
    checks = {field: payload.get(field) == explanation["valuation"].get(field)
        for field in ("symbol", "model_type", "model_version", "valuation_date", "status",
                      "bear_value", "base_value", "bull_value")}
    full_match = digest == expected["valuation"]
    return dict(schema_version="value-direct-input-isolated-replay-v1", symbol=case.symbol,
        status="EXACT_VALUATION_REPLAY" if full_match and all(checks.values()) else "VALUATION_REPLAY_MISMATCH",
        executed_at=datetime.now(timezone.utc).isoformat(), action="no_order",
        scope="DIRECT_CONSUMED_INPUTS_AND_SHARED_ARITHMETIC_NOT_FULL_ADMISSION_RESTORE",
        copied_inputs=copied, copied_file_count=len(copied), copied_bytes=sum(row["size_bytes"] for row in copied),
        input_artifact_checks=input_checks, output_checks=checks,
        expected_valuation_sha256=expected["valuation"], replayed_valuation_sha256=digest,
        full_payload_match=full_match, replayed_valuation=payload,
        g3_approved=False, event_review_approved=False, formal_eligibility=False,
        portfolio_eligibility=None, registered_current_case_changed=False)
