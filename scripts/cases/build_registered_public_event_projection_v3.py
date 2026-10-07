"""Append a PIT-time correction to the v2 registered public-event projection."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_PATH = Path(
    "runtime/prospective-public-event-20260928/"
    "registered-public-event-projection-v2.json"
)
PREDECESSOR_SHA256 = "f5938dc5b381230efd686078c923b8b4d0aab3562148f33ccbfa6c4749a12609"
NOTICE_SCHEMA = "midea-egm-notice-projection-v2"
NOTICE_ID = "1225582141"
NOTICE_DATE = "2026-09-28"
NOTICE_AVAILABLE_AT = "2026-09-29T00:00:00+08:00"
NOTICE_TIME_PRECISION = "DATE_ONLY_CONSERVATIVE_NEXT_DAY"
NOTICE_SHA256 = "94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _load_predecessor(root: Path) -> dict[str, Any]:
    path = (root / PREDECESSOR_PATH).resolve()
    if not path.is_relative_to((root / "runtime").resolve()) or not path.is_file():
        raise ValueError("v2 predecessor must exist under runtime")
    if _sha256(path) != PREDECESSOR_SHA256:
        raise ValueError("v2 predecessor SHA-256 mismatch")
    payload = _read_json(path)
    report = payload.get("report")
    projection = payload.get("projection")
    if (
        payload.get("action") != "no_order"
        or not isinstance(report, dict)
        or report.get("schema_version") != "registered-public-event-projection-v2"
        or report.get("event_count") != 9
        or report.get("strict_pit_proven") is not False
        or not isinstance(projection, dict)
        or projection.get("action") != "no_order"
    ):
        raise ValueError("v2 predecessor contract is invalid")
    expected_counts = {"events": 9, "audit_evidence": 11, "audit_decisions": 9}
    for key, expected_count in expected_counts.items():
        rows = projection.get(key)
        if not isinstance(rows, list) or len(rows) != expected_count:
            raise ValueError(f"v2 predecessor must contain {expected_count} {key}")
    return payload


def _load_notice(root: Path, path: Path, expected_sha256: str) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    if not source.is_relative_to((root / "runtime").resolve()) or not source.is_file():
        raise ValueError("notice v2 must be an existing file under runtime")
    if _sha256(source).lower() != expected_sha256.lower():
        raise ValueError("notice projection SHA-256 mismatch")

    payload = _read_json(source)
    sys.path[:0] = [str(root), str(root / "src")]
    from scripts.cases.build_midea_egm_notice_projection import build_projection_payload

    expected = build_projection_payload(root)
    if payload != expected:
        raise ValueError("notice projection does not match reverified source bytes and PIT contract")
    report = payload.get("report", {})
    if (
        report.get("schema_version") != NOTICE_SCHEMA
        or report.get("announcement_id") != NOTICE_ID
        or report.get("announcement_date") != NOTICE_DATE
        or report.get("source_available_at") != NOTICE_AVAILABLE_AT
        or report.get("source_time_precision") != NOTICE_TIME_PRECISION
        or report.get("strict_pit_admissible") is not False
        or report.get("action") != "no_order"
    ):
        raise ValueError("notice v2 date or PIT availability contract is invalid")
    evidence = payload.get("projection", {}).get("audit_evidence", [])
    if (
        len(evidence) != 1
        or evidence[0].get("sha256") != NOTICE_SHA256
        or evidence[0].get("available_at") != NOTICE_AVAILABLE_AT[:10]
    ):
        raise ValueError("notice v2 evidence must use its conservative PIT availability date")
    return payload


def build_projection_payload(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    notice_projection_path: Path,
    notice_projection_sha256: str,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    previous = _load_predecessor(root)
    notice = _load_notice(root, notice_projection_path, notice_projection_sha256)
    previous_projection = previous["projection"]
    notice_projection = notice["projection"]

    _require_preserved_final_event(previous_projection, notice_projection)
    audit_decision_additions = _require_preserved_final_audit_decision(
        previous_projection, notice_projection
    )

    old_evidence = previous_projection["audit_evidence"][-1]
    new_evidence = notice_projection["audit_evidence"][0]
    if old_evidence.get("evidence_id") != f"cninfo-{NOTICE_ID}":
        raise ValueError("v2 predecessor does not end with the pinned Midea notice")
    allowed_changes = {"title", "available_at"}
    if any(
        old_evidence.get(key) != new_evidence.get(key)
        for key in (set(old_evidence) | set(new_evidence)) - allowed_changes
    ):
        raise ValueError("v3 may only correct the Midea notice title and PIT available date")
    if old_evidence.get("available_at") != NOTICE_DATE:
        raise ValueError("v2 predecessor notice date differs from the pinned correction target")

    successor = deepcopy(previous)
    successor["projection"]["audit_evidence"][-1] = deepcopy(new_evidence)
    successor["projection"]["audit_decisions"][-1].update(
        deepcopy(audit_decision_additions)
    )
    report = successor["report"]
    report["schema_version"] = "registered-public-event-projection-v3"
    report["successor_of"] = "registered-public-event-projection-v2"
    report["predecessor_sha256"] = PREDECESSOR_SHA256
    report["appended_observation"]["pit_available_at"] = NOTICE_AVAILABLE_AT
    report["appended_observation"]["source_time_precision"] = NOTICE_TIME_PRECISION
    report["availability_correction"] = {
        "evidence_id": new_evidence["evidence_id"],
        "announcement_date": NOTICE_DATE,
        "previous_available_at": old_evidence["available_at"],
        "corrected_available_at": NOTICE_AVAILABLE_AT[:10],
        "source_available_at": NOTICE_AVAILABLE_AT,
    }
    report["action"] = "no_order"
    successor["action"] = "no_order"
    if successor["projection"]["action"] != "no_order":
        raise ValueError("v3 projection must remain no_order")
    return successor


_ALLOWED_AUDIT_ADDITIONS = {
    "reopen_condition_met": False,
    "reopen_evidence_refs": [],
}


def _require_preserved_final_event(previous_projection: dict[str, Any], notice_projection: dict[str, Any]) -> None:
    if notice_projection["events"] != [previous_projection["events"][-1]]:
        raise ValueError("v3 correction must preserve the existing final event")


def _require_preserved_final_audit_decision(
    previous_projection: dict[str, Any], notice_projection: dict[str, Any]
) -> dict[str, Any]:
    previous = previous_projection["audit_decisions"][-1]
    current_records = notice_projection["audit_decisions"]
    if len(current_records) != 1:
        raise ValueError("v3 correction must preserve the existing final audit_decision")
    current = current_records[0]
    if any(current.get(key) != value for key, value in previous.items()):
        raise ValueError("v3 correction must preserve the existing final audit_decision")
    additions = set(current) - set(previous)
    if not additions.issubset(_ALLOWED_AUDIT_ADDITIONS):
        raise ValueError("v3 correction introduced an unregistered audit_decision field")
    if any(current[key] != default for key, default in _ALLOWED_AUDIT_ADDITIONS.items() if key in additions):
        raise ValueError("v3 correction may only add empty audit_decision defaults")
    return {key: current[key] for key in additions}


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(f"Refusing to overwrite existing output: {target}") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notice-projection", required=True, type=Path)
    parser.add_argument("--notice-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = build_projection_payload(
            notice_projection_path=args.notice_projection,
            notice_projection_sha256=args.notice_sha256,
        )
        write_new_json(args.output, payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
