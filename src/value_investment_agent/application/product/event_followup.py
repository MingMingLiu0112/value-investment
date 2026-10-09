"""Project bounded, source-anchored explanations without investment admission."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import load_json_object, require_inside, sha256_file
from ..historical_validation.event_source_review import prepare_event_source_review
from .decision_surface import (
    current_recommendation_type,
    verify_current_decision_workbench,
)
from ...m1_valuation_package_builder import build_descriptor
from ...research_artifact_codecs import artifact_payload
from ...research_artifacts import canonicalize_artifact_payload
from ...research_run_contract import validate_assumption_bindings


MODEL_BOUND_SCHEMA = "research-event-followup-v2"
_MARKET_ZONE = ZoneInfo("Asia/Shanghai")
_IMPACT_KINDS = {
    "SUPPORTED_STARTING_FACTS_ONLY", "LIMITED_ZERO_RESTATEMENT",
    "UNQUANTIFIED_OPERATING_CHANGE", "DISTRIBUTION_RISK_UNRESOLVED",
    "DERIVED_DUPLICATE", "NO_NUMERIC_GUIDANCE",
    "UNQUANTIFIED_CAPITAL_ALLOCATION",
}


def _read_binding(root, binding, label):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError(f"{label} requires a path/hash binding")
    path = require_inside(root, root / binding["path"], label)
    if sha256_file(path) != binding["sha256"]:
        raise ValueError(f"{label} hash mismatch")
    return path


def _read_model_impacts(*, root, value, events, observed_at):
    """Bind research explanations to consumed parameters, never approve them."""
    if any(value.get(key) is not False for key in (
        "materiality_approved", "model_validity_approved", "investment_approved",
    )):
        raise ValueError("model-bound followup must explicitly retain unapproved gates")
    provenance = value.get("review_provenance")
    if (not isinstance(provenance, dict)
            or provenance.get("kind") != "INDEPENDENT_RESEARCH_EXPLANATION_NOT_APPROVAL"
            or not provenance.get("reviewer_id") or not provenance.get("integrator_id")):
        raise ValueError("model-bound followup requires explicit independent provenance")
    report = _read_binding(root, value.get("review_report"), "independent research report")
    binding = value.get("model_binding")
    workbench_path = _read_binding(root, binding, "model-bound workbench")
    workbench = load_json_object(workbench_path, "model-bound workbench")
    restored = verify_current_decision_workbench(workbench)
    recommendation = restored.recommendation
    if (recommendation.symbol != value["symbol"]
            or current_recommendation_type(recommendation) != "NO_ACTION"
            or datetime.fromisoformat(workbench["generated_at"]) > observed_at):
        raise ValueError("model-bound followup requires an earlier unadmitted same-company decision")
    sources = (workbench.get("source_verification") or {}).get("sources")
    if not sources:
        raise ValueError("model-bound followup requires local model inputs")
    for source in sources:
        _read_binding(root, source, "model-bound original")
    report_path = report.relative_to(root.resolve()).as_posix()
    report_hash = value["review_report"]["sha256"]
    if not any(source["path"].replace("\\", "/") == report_path
               and source["sha256"] == report_hash for source in sources):
        raise ValueError("independent report is not a consumed model source")
    assumption_set = restored.dependency_objects.get("valuation_assumptions")
    assumptions = {item.name: item for item in assumption_set.assumptions} if assumption_set else {}
    input_binding = value.get("model_input_binding")
    input_path = _read_binding(root, input_binding, "model input package")
    receipt_hash = ((workbench.get("research_receipt") or {}).get("input_sha256") or {}).get("valuation_package")
    if receipt_hash != input_binding["sha256"]:
        raise ValueError("model input package differs from the executed research receipt")
    descriptor = build_descriptor(load_json_object(input_path, "model input package"), root=root)
    if descriptor.input_sha256 != workbench.get("input_descriptor_sha256"):
        raise ValueError("model input descriptor differs from the executed research")
    for role, actual in (("financial_facts", descriptor.facts), ("valuation_assumptions", descriptor.assumptions)):
        expected = restored.dependency_objects.get(role)
        if actual is None or expected is None or canonicalize_artifact_payload(
            artifact_payload(actual)[1]
        ) != canonicalize_artifact_payload(artifact_payload(expected)[1]):
            raise ValueError("model input package differs from replayed " + role)
    if validate_assumption_bindings(descriptor.facts, descriptor.assumption_bindings):
        raise ValueError("model input bindings differ from consumed scenario inputs")
    consumed = {}
    for item in descriptor.assumption_bindings:
        consumed.setdefault(item.assumption_name, set()).add(item.scenario)
    impacts = value.get("assumption_impacts")
    if not isinstance(impacts, list) or not impacts:
        raise ValueError("model-bound followup requires per-announcement impacts")
    ids = [impact.get("announcement_id") for impact in impacts]
    if len(ids) != len(set(ids)) or set(ids) != set(events):
        raise ValueError("model-bound followup must cover every acquired announcement exactly")
    claims = {item["label"]: item["announcement_id"] for item in value["claims"]}
    normalized = []
    for impact in impacts:
        names = impact.get("assumption_names")
        if (not isinstance(names, list) or len(names) != len(set(names))
                or set(names) - assumptions.keys()
                or any(consumed.get(name) != {"bear", "base", "bull"} for name in names)
                or impact.get("kind") not in _IMPACT_KINDS
                or impact.get("parameters_changed") is not False
                or type(impact.get("user_visible")) is not bool
                or not isinstance(impact.get("reason"), str) or not impact["reason"].strip()
                or not isinstance(impact.get("reopen_condition"), str) or not impact["reopen_condition"].strip()):
            raise ValueError("model-bound impact has unknown parameters or an unsupported disposition")
        labels = impact.get("claim_labels")
        if (not isinstance(labels, list) or not labels
                or any(claims.get(label) != impact["announcement_id"] for label in labels)):
            raise ValueError("model-bound impact requires same-announcement original anchors")
        expected = impact.get("assumption_values")
        if not isinstance(expected, dict) or set(expected) != set(names):
            raise ValueError("model-bound impact requires the exact consumed parameter values")
        for name in names:
            assumption = assumptions[name]
            if not any(ref.get("path", "").replace("\\", "/") == report_path
                       and ref.get("sha256") == report_hash for ref in assumption.evidence_refs):
                raise ValueError("independent report is not bound to the affected assumption")
            values = expected[name]
            if not isinstance(values, dict) or set(values) != {"bear", "base", "bull"}:
                raise ValueError("model-bound impact requires three scenario values")
            for scenario, number in values.items():
                try:
                    actual = Decimal(str(number))
                except (InvalidOperation, ValueError):
                    raise ValueError("model-bound impact parameter must be numeric") from None
                if not actual.is_finite() or actual != Decimal(str(getattr(assumption, scenario))):
                    raise ValueError("model-bound impact differs from the consumed parameter")
        event = events[impact["announcement_id"]]
        normalized.append({**impact, "title": event["title"],
                           "published_at": event["published_at"]})
    # Recheck after PDF extraction and replay so no mutable report/model source
    # can be exchanged between evidence validation and the presentation handoff.
    _read_binding(root, value["review_report"], "independent research report")
    _read_binding(root, binding, "model-bound workbench")
    _read_binding(root, input_binding, "model input package")
    for source in sources:
        _read_binding(root, source, "model-bound original")
    return dict(model_binding=binding, model_input_binding=input_binding, review_report=value["review_report"],
                review_provenance=provenance, assumption_impacts=normalized)


def read_event_followup(*, root: Path, cutoff, path: Path, expected_sha256: str):
    path = require_inside(root, path, "event followup")
    if sha256_file(path) != expected_sha256:
        raise ValueError("event followup hash mismatch")
    value = load_json_object(path, "event followup")
    if (value.get("schema_version") not in {"research-event-followup-v1", MODEL_BOUND_SCHEMA}
            or value.get("scope") != "SOURCE_ANCHORED_EXPLANATION_ONLY"
            or value.get("action") != "no_order"):
        raise ValueError("event followup cannot authorize investment")
    point = datetime.fromisoformat(value["observed_at"])
    if point.utcoffset() is None or point.astimezone(_MARKET_ZONE).date() > cutoff:
        raise ValueError("event followup observation is outside product cutoff")
    binding = value["event_scan"]
    scan = require_inside(root, root / binding["path"], "event followup scan")
    packet = prepare_event_source_review(root=root, path=scan,
        expected_sha256=binding["sha256"], symbol=value["symbol"])
    if not packet["audit"]["evidence_integrity_verified"]:
        raise ValueError("event followup requires unchanged originals")
    events = {event["announcement_id"]: event for event in packet["events"]}
    claims = value.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("event followup requires source claims")
    rows = {}
    normalized = lambda text: "".join(text.split())
    labels = set()
    for claim in claims:
        label, summary = claim["label"], claim["summary"]
        if not isinstance(label, str) or not label.strip() or label in labels:
            raise ValueError("event followup labels must be new and unique")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("event followup summary is required")
        labels.add(label)
        event = events.get(claim["announcement_id"])
        if event is None:
            raise ValueError("event followup references unknown announcement")
        anchors = claim.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            raise ValueError("event followup requires page-specific anchors")
        for anchor in anchors:
            page = anchor["physical_page"]
            excerpt = anchor["excerpt"]
            if isinstance(page, bool) or not isinstance(page, int) or page < 1 or not excerpt.strip():
                raise ValueError("event followup requires positive pages and nonempty excerpts")
            matches = [record["text"] for source in event["sources"] for record in source["pages"]
                       if record["physical_page"] == page]
            if not any(normalized(excerpt) in normalized(text) for text in matches):
                raise ValueError("event followup anchor differs from original page")
        rows[label] = summary + "；原件：" + event["sources"][0]["source_url"]
    historical_labels = value.get("historical_labels", [])
    if len(set(historical_labels)) != len(historical_labels):
        raise ValueError("duplicate historical explanation labels")
    unresolved = value.get("unresolved_questions")
    if not isinstance(unresolved, list) or not unresolved or any(not isinstance(item, str) or not item.strip() for item in unresolved):
        raise ValueError("event followup must retain explicit unresolved questions")
    model_impacts = {}
    if value["schema_version"] == MODEL_BOUND_SCHEMA:
        model_impacts = _read_model_impacts(root=root, value=value, events=events, observed_at=point)
    if sha256_file(path) != expected_sha256:
        raise ValueError("event followup changed during read")
    return dict(symbol=value["symbol"], observed_at=point.isoformat(), rows=rows,
                historical_labels=historical_labels, unresolved_questions=unresolved,
                path=path.relative_to(root.resolve()).as_posix(), sha256=expected_sha256,
                scope="SOURCE_ANCHORED_EXPLANATION_ONLY", action="no_order", **model_impacts)
