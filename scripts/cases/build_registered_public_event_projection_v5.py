"""Bind post-cutoff evidence to an audit-only quarantine section."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_PATH = Path(
    "runtime/prospective-public-event-20260928/"
    "registered-public-event-projection-v4.json"
)
PREDECESSOR_SHA256 = "404cc518c40f6f7f83a866451eca2ab3957f680f3080585da2c61942d520fa5b"
SOURCE_PATH = Path(
    "runtime/prospective-public-event-20260928/"
    "registered-public-event-projection-v3.json"
)
SOURCE_SHA256 = "75f419502c1f5c646d15913e455889a0d8c3ff08829b12316251c747702a3781"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_pinned(root: Path, relative: Path, digest: str, label: str) -> dict[str, Any]:
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "runtime").resolve()) or not path.is_file():
        raise ValueError(f"{label} must exist under runtime/")
    if _sha256(path) != digest:
        raise ValueError(f"{label} SHA-256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("action") != "no_order":
        raise ValueError(f"{label} must be a no_order object")
    return payload


def build_projection_payload(repository_root: Path = ROOT) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    predecessor = _read_pinned(
        root, PREDECESSOR_PATH, PREDECESSOR_SHA256, "v4 predecessor",
    )
    source = _read_pinned(root, SOURCE_PATH, SOURCE_SHA256, "v3 source closure")
    report = predecessor.get("report")
    source_report = source.get("report")
    projection = predecessor.get("projection")
    source_projection = source.get("projection")
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != "registered-public-event-projection-v4"
        or report.get("successor_of") != "registered-public-event-projection-v3"
        or report.get("predecessor_sha256") != SOURCE_SHA256
        or not isinstance(source_report, dict)
        or source_report.get("schema_version") != "registered-public-event-projection-v3"
        or not isinstance(projection, dict)
        or not isinstance(source_projection, dict)
    ):
        raise ValueError("Pinned v4/v3 projection chain is inconsistent")

    exclusions = report.get("as_of_exclusions")
    source_records = source_projection.get("audit_evidence")
    source_events = source_projection.get("events")
    if not isinstance(exclusions, list) or not isinstance(source_records, list):
        raise ValueError("v4 exclusions and v3 source evidence are required")
    if not isinstance(source_events, list):
        raise ValueError("v3 source events are required")

    evidence_by_id = {
        row.get("evidence_id"): row
        for row in source_records
        if isinstance(row, dict) and isinstance(row.get("evidence_id"), str)
    }
    if len(evidence_by_id) != len(source_records):
        raise ValueError("v3 source evidence ids must be unique and valid")
    event_by_id = {
        row.get("event_id"): row
        for row in source_events
        if isinstance(row, dict) and isinstance(row.get("event_id"), str)
    }

    quarantined = []
    seen: set[str] = set()
    for exclusion in exclusions:
        if not isinstance(exclusion, dict):
            raise ValueError("v4 as-of exclusions must be objects")
        evidence_id = exclusion.get("evidence_id")
        record = evidence_by_id.get(evidence_id)
        event_ids = exclusion.get("event_ids")
        if (
            not isinstance(evidence_id, str)
            or evidence_id in seen
            or not isinstance(record, dict)
            or not isinstance(event_ids, list)
            or not event_ids
            or any(not isinstance(event_id, str) or event_id not in event_by_id for event_id in event_ids)
            or record.get("available_at") != exclusion.get("available_at")
            or exclusion.get("reason") != "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF"
        ):
            raise ValueError("v4 exclusion does not bind to exact v3 source evidence")
        for event_id in event_ids:
            if evidence_id not in event_by_id[event_id].get("evidence_refs", []):
                raise ValueError("v3 source event does not reference the excluded evidence")
        if evidence_id in {
            item.get("evidence_id") for item in projection.get("audit_evidence", [])
            if isinstance(item, dict)
        }:
            raise ValueError("quarantined evidence must stay outside active as-of evidence")
        seen.add(evidence_id)
        quarantined.append({
            "evidence": deepcopy(record),
            "reason": exclusion["reason"],
            "related_event_ids": list(event_ids),
        })

    successor = deepcopy(predecessor)
    successor_projection = successor["projection"]
    successor_projection["as_of_excluded_evidence"] = quarantined
    successor_report = successor["report"]
    successor_report["schema_version"] = "registered-public-event-projection-v5"
    successor_report["successor_of"] = "registered-public-event-projection-v4"
    successor_report["predecessor_sha256"] = PREDECESSOR_SHA256
    successor_report["source_evidence_path"] = SOURCE_PATH.as_posix()
    successor_report["source_evidence_sha256"] = SOURCE_SHA256
    successor_report["as_of_excluded_evidence_count"] = len(quarantined)
    successor_report["strict_pit_proven"] = False
    successor_report["valuation_or_trade_conclusion_changed"] = False
    successor_report["action"] = "no_order"
    successor["action"] = "no_order"
    return successor


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    target = Path(path).expanduser().resolve()
    if not target.is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("projection successor must be written under runtime/")
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(f"Refusing to overwrite existing output: {target}") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = build_projection_payload()
        write_new_json(args.output, payload)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
