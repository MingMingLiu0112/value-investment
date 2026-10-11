"""Read-only comparison of pinned, non-admitting daily research supplements."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .common import normalize_symbol, require_inside, sha256_bytes, sha256_file


_ROLES = ("valuation_proposal", "financial_review")
_PROVENANCE = {"generated_at", "source_bindings", "source_binding", "manifest_binding"}
_FLAGS = (
    "decision_changed", "research_date_advanced", "assumptions_approved",
    "g3_approved", "model_validity_approved", "model_approved", "price_admitted",
    "strict_pit_admitted", "canonical_written", "canonical_workbook_written",
)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"nonfinite JSON constant: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False)


def _semantic(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _semantic(item) for key, item in value.items() if key not in _PROVENANCE}
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def compare_research_supplements(
    *, root: Path, symbol: str, current_bindings: list[dict[str, Any]],
    previous_receipt_path: Path | None = None,
    previous_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    """Compare supported outputs without writing, recalculating or approving them.

    Missing sides/fields are UNAVAILABLE; malformed or altered pinned inputs
    raise ValueError. Unrelated current roles and previous outputs are ignored.
    Paths resolve relative to root, including those in nested source bindings.
    """
    root = Path(root).resolve(strict=True)
    symbol = normalize_symbol(symbol)
    if (previous_receipt_path is None) != (previous_receipt_sha256 is None):
        raise ValueError("previous receipt requires both path and SHA-256")
    verified: dict[Path, str] = {}
    evidence_paths: set[Path] = set()

    def verify(binding: Any, label: str, *, evidence: bool = True) -> Path:
        if not isinstance(binding, dict):
            raise ValueError(f"{label} requires a path/sha256 binding")
        value, digest = binding.get("path"), binding.get("sha256")
        if not isinstance(value, (str, Path)) or not str(value):
            raise ValueError(f"{label} requires a local path")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{label} requires an exact SHA-256")
        path = require_inside(root, root / value, label)
        if path in verified and verified[path] != digest:
            raise ValueError(f"{label} has conflicting hashes")
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"{label} missing file or hash mismatch")
        verified[path] = digest
        if evidence:
            evidence_paths.add(path)
        return path

    def read(binding: dict, label: str, *, evidence: bool = True) -> dict:
        path = verify(binding, label, evidence=evidence)
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant,
                                 object_pairs_hook=_object)
            json.dumps(payload, allow_nan=False)
        except (OSError, UnicodeError, ValueError) as error:
            raise ValueError(f"{label} requires valid finite UTF-8 JSON") from error
        if sha256_bytes(raw) != binding["sha256"]:
            raise ValueError(f"{label} changed during read")
        if not isinstance(payload, dict) or payload.get("action") != "no_order":
            raise ValueError(f"{label} must be a no_order object")
        return payload

    def sources(value: Any) -> None:
        if isinstance(value, dict):
            if "action" in value and value["action"] != "no_order":
                raise ValueError("supplement nested action must remain no_order")
            for key, item in value.items():
                if key == "source_bindings":
                    if not isinstance(item, list) or not item:
                        raise ValueError("source_bindings requires a nonempty list")
                    for binding in item:
                        verify(binding, "supplement source")
                elif key in {"source_binding", "manifest_binding"}:
                    verify(item, key)
                sources(item)
        elif isinstance(value, list):
            for item in value:
                sources(item)

    def supplement(binding: dict, role: str) -> dict:
        payload = read(binding, role)
        if payload.get("symbol", symbol) != symbol:
            raise ValueError("supplement symbol mismatch")
        if any(key in payload and payload[key] is not False for key in _FLAGS):
            raise ValueError("supplement must remain unadmitted and unchanged")
        if payload.get("position_guidance") is not None:
            raise ValueError("supplement cannot carry position guidance")
        if role == "financial_review" and payload.get("status") == "RESEARCH_SUPPLEMENT_UNAVAILABLE":
            sources(payload)
            return {"available": False, "reason": payload.get("error", "Supplement unavailable.")}
        if payload.get("symbol") != symbol:
            raise ValueError("supplement requires the requested symbol")
        if role == "valuation_proposal":
            if payload.get("schema_version") != "finite-neutral-valuation-proposal-v1":
                raise ValueError("unsupported valuation proposal schema")
        elif payload.get("status") != "SOURCE_VERIFIED_RESEARCH_SUPPLEMENT_NOT_ADMITTED":
            raise ValueError("unsupported financial review status")
        if "source_bindings" not in payload:
            raise ValueError("supplement requires source_bindings")
        sources(payload)
        return {"available": True, "fields": _semantic(payload)}

    if not isinstance(current_bindings, list):
        raise ValueError("current_bindings requires a list")
    current = {}
    for binding in current_bindings:
        if not isinstance(binding, dict):
            raise ValueError("current binding requires an object")
        role = binding.get("role")
        if role not in _ROLES:
            continue
        if role in current:
            raise ValueError("duplicate current supplement role")
        current[role] = supplement(binding, role)
    previous = {}
    previous_receipt_provenance = None
    if previous_receipt_path is not None:
        prior = read({"path": previous_receipt_path, "sha256": previous_receipt_sha256},
                     "previous daily receipt", evidence=False)
        if (prior.get("schema_version") != "daily-trade-assistant-receipt-v1"
                or prior.get("symbol") != symbol or not isinstance(prior.get("outputs"), dict)):
            raise ValueError("previous receipt schema/symbol/outputs mismatch")
        # Historical implementation pins are provenance, not current numerical dependencies.
        previous_receipt_provenance = {
            "receipt_path": require_inside(root, root / previous_receipt_path,
                                            "previous daily receipt").relative_to(root).as_posix(),
            "receipt_sha256": previous_receipt_sha256,
            "scope": "HISTORICAL_RUN_PROVENANCE_NOT_CURRENT_IMPLEMENTATION",
        }
        for role in _ROLES:
            if prior["outputs"].get(role) is not None:
                previous[role] = supplement(prior["outputs"][role], role)
    roles = {}
    for role in _ROLES:
        before, after = previous.get(role, {}), current.get(role, {})
        left, right = before.get("fields", {}), after.get("fields", {})
        fields = {}
        for key in sorted((left.keys() | right.keys()) - {"action", "symbol"}):
            old, new = left.get(key), right.get(key)
            status = "UNAVAILABLE" if old is None or new is None else (
                "UNCHANGED" if _equal(old, new) else "CHANGED_RESEARCH_ARTIFACT")
            fields[key] = {"status": status, "previous": old, "current": new}
        available = before.get("available", False) and after.get("available", False)
        roles[role] = {
            "status": "UNAVAILABLE" if not available else (
                "UNCHANGED" if _equal(left, right) else "CHANGED_RESEARCH_ARTIFACT"),
            "previous_available": before.get("available", False),
            "current_available": after.get("available", False),
            "previous_reason": before.get("reason"), "current_reason": after.get("reason"),
            "fields": fields,
        }
    for path, digest in verified.items():
        if sha256_file(path) != digest:
            raise ValueError("comparison input changed during comparison")
    return {
        "schema_version": "research-supplement-comparison-v1", "symbol": symbol,
        "scope": "PINNED_RESEARCH_SUPPLEMENTS_NOT_CURRENT_ADMISSION", "roles": roles,
        "official_facts_status": "NO_NEW_DISCLOSED_FACTS_ESTABLISHED",
        "interpretation": "Changes describe research artifacts, not new official disclosures or approvals.",
        "action": "no_order", "decision_changed": False, "research_date_advanced": False,
        "approval_changed": False, "current_admission": False, "position_guidance": None,
        "canonical_workbook_written": False,
        "previous_receipt_provenance": previous_receipt_provenance,
        "source_bindings": [{"path": path.relative_to(root).as_posix(), "sha256": digest}
                            for path, digest in sorted(verified.items()) if path in evidence_paths],
    }
