"""Hash-bound archived replay facts for a Root-owned read-only Web route."""
from pathlib import Path
import json

from .event_replay import _bound_bytes


FOLDER = "artifacts/current/tl11-p5-20261014"


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
