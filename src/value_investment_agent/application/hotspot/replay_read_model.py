"""Hash-bound archived replay facts for a Root-owned read-only Web route."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json

from .event_replay import _bound_bytes


FOLDER = "artifacts/current/tl11-p5-20261014"
REVIEW_POINTER = "config/hotspot-replay-review-v1.json"


def load_current_hotspot_validation(*, root: Path, now: datetime) -> dict:
    """Recompute the configured retained sample once per consumer request.

    This is evidence about a historical sample, not the signed strategy release.
    An unavailable archive must not hide independently verified current prices.
    """
    from .validation_evidence import build_hotspot_quantitative_validation

    if now.utcoffset() is None:
        raise ValueError("Validation read model requires a timezone-aware clock")
    result = dict(schema_version="hotspot-current-validation-context-v1",
        status="NOT_RUN", source_integrity="NOT_VERIFIED",
        reference_scope="RETAINED_SAMPLE_NOT_CURRENT_STRATEGY_ADMISSION",
        strategy_validation="NOT_PROVEN", signal_event_count=None,
        mature_five_session_count=None, right_censored_count=None, trade_count=None,
        execution_metrics=dict(status="UNASSESSABLE", trade_count=None,
            cost_sensitivity=None, t_plus_one_feasibility="UNKNOWN"),
        case_bindings=[], rule_versions=[], source_bindings=[],
        blockers=["RETAINED_VALIDATION_NOT_CONFIGURED"], strict_pit_admitted=False,
        strict_oos_admitted=False, prospective_oos_admitted=False,
        elapsed_real_shadow_sessions=0, formal_eligibility=False,
        performance_claim_allowed=False, action="no_order")
    root = Path(root).resolve()
    pointer = root / REVIEW_POINTER
    try:
        if not pointer.is_file():
            return result
        raw = pointer.read_bytes()
        pins = json.loads(raw)
        if not isinstance(pins, dict) or pins.get("action") != "no_order":
            raise ValueError("Invalid hotspot validation pointer")
        binding = pins.get("retained_manifest_binding")
        if binding is None:
            return result
        report = build_hotspot_quantitative_validation(root=root,
            protocol_binding=binding, now=now)
        if (report.get("schema_version") != "hotspot-retained-descriptive-validation-v1"
                or report.get("namespace") != "ACTUAL" or report.get("scope") != "DESCRIPTIVE"
                or report.get("action") != "no_order" or report.get("formal_eligibility") is not False
                or report.get("trade_count") is not None):
            raise ValueError("Current validation requires ACTUAL retained descriptive evidence")
        if pointer.read_bytes() != raw:
            raise ValueError("Hotspot validation pointer changed during replay")
        keys = ("namespace", "metrics_scope", "protocol_binding", "historical_protocol_binding",
            "evidence_sha256", "evaluated_at", "data_available_at", "partitions",
            "signal_event_count", "mature_five_session_count", "right_censored_count",
            "execution_metrics", "source_bindings", "historical_selection_status", "limitations")
        summary = {key: deepcopy(report[key]) for key in keys}
        result.update(**summary, status=report["status"], source_integrity="VERIFIED",
            pointer_binding=dict(path=REVIEW_POINTER, sha256=sha256(raw).hexdigest()),
            case_bindings=[deepcopy(row["case_binding"]) for row in report["results"]],
            rule_versions=sorted({row["rule_version"] for row in report["results"]}),
            sample_status="NO_EXECUTION_SAMPLE",
            blockers=["CONTEMPORANEOUS_SELECTION_AND_SOURCE_PIT_NOT_PROVEN",
                "DATED_COST_AND_EXECUTION_EVIDENCE_MISSING",
                "UNTOUCHED_STRATEGY_OOS_NOT_PROVEN", "REAL_SHADOW_SESSIONS_NOT_PROVEN"])
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
        result.update(status="UNAVAILABLE", source_integrity="NOT_VERIFIED",
            blockers=["RETAINED_VALIDATION_EVIDENCE_INVALID"], diagnostic=str(error))
    return result


def load_replay_summary(*, root: Path, manifest_sha256: str,
                        structure_manifest_sha256: str | None = None) -> dict:
    """Require externally pinned manifests; never reinterpret replay as current."""
    root = root.resolve()
    manifest = json.loads(_bound_bytes(root, {"path": FOLDER + "/replay-manifest-v1.json", "sha256": manifest_sha256}))
    if manifest.get("schema_version") != "hotspot-event-replay-manifest-v1" or manifest.get("action") != "no_order":
        raise ValueError("Replay manifest contract mismatch")
    expected = FOLDER + "/replay-results-v1.json"
    binding = next((row for row in manifest["outputs"] if row["path"] == expected), None)
    if binding is None:
        raise ValueError("Bound replay report missing")
    report = json.loads(_bound_bytes(root, binding))
    if report.get("schema_version") != "hotspot-five-case-replay-report-v1" or report.get("action") != "no_order":
        raise ValueError("Replay report contract mismatch")
    structure = None
    if structure_manifest_sha256 is not None:
        structure_manifest = json.loads(_bound_bytes(root, {
            "path": FOLDER + "/replay-structure-manifest-v1.json", "sha256": structure_manifest_sha256}))
        if (structure_manifest.get("schema_version") != "hotspot-structure-prefix-manifest-v1"
                or structure_manifest.get("action") != "no_order"
                or structure_manifest["output_binding"]["path"] != FOLDER + "/replay-structure-results-v1.json"):
            raise ValueError("Structure manifest contract mismatch")
        structure = json.loads(_bound_bytes(root, structure_manifest["output_binding"]))
        if (structure.get("schema_version") != "hotspot-descriptive-structure-prefix-report-v1"
                or structure.get("action") != "no_order"
                or structure.get("parent_spec_binding") != report["spec_binding"]
                or {row["symbol"] for row in structure["results"]} != {row["symbol"] for row in report["results"]}):
            raise ValueError("Structure report belongs to different frozen replay")
    structural = {row["symbol"]: row for row in structure["results"]} if structure else {}
    return {
        "schema_version": "hotspot-replay-web-summary-v1",
        "status": "HISTORICAL_DESCRIPTIVE_REPLAY_NOT_ADMITTED",
        "reference_scope": "FROZEN_REPLAY_NOT_CURRENT_JUDGMENT",
        "computed_at": report["computed_at"], "data_available_at": report["data_available_at"],
        "partitions": report["partitions"],
        "manifest_sha256": manifest_sha256, "structure_manifest_sha256": structure_manifest_sha256,
        "items": [{
            "symbol": row["symbol"], "case_sha256": row["case_binding"]["case_sha256"],
            "v1_rule_version": row["rule_version"], "v1_segments": row["segments"],
            "archived_v1_observation": row["last_observation"],
            "structure_rule_version": structural[row["symbol"]]["rule_version"] if row["symbol"] in structural else None,
            "structure_segments": structural[row["symbol"]]["segments"] if row["symbol"] in structural else None,
            "archived_structure_observation": structural[row["symbol"]]["last_observation"] if row["symbol"] in structural else None,
        } for row in report["results"]],
        "limitations": report["limitations"],
        "strict_pit_admitted": False, "strict_oos_admitted": False,
        "prospective_oos_admitted": False, "performance_claim_allowed": False,
        "formal_eligibility": False, "portfolio_eligibility": None,
        "elapsed_real_shadow_sessions": 0, "action": "no_order",
    }
