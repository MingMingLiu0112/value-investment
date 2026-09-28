"""Build an as-of successor that excludes evidence unavailable by its cutoff."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import date
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_PATH = Path(
    "runtime/prospective-public-event-20260928/"
    "registered-public-event-projection-v3.json"
)
PREDECESSOR_SHA256 = "75f419502c1f5c646d15913e455889a0d8c3ff08829b12316251c747702a3781"
AS_OF_DATE = "2026-09-28"
DEFERRED_EVENT_ID = "midea-2026-egm-notice-1225582141"
DEFERRED_EVIDENCE_ID = "cninfo-1225582141"
DEFERRED_AVAILABLE_AT = "2026-09-29"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_predecessor(root: Path) -> dict[str, Any]:
    path = (root / PREDECESSOR_PATH).resolve()
    if not path.is_relative_to((root / "runtime").resolve()) or not path.is_file():
        raise ValueError("v3 predecessor must exist under runtime/")
    if _sha256(path) != PREDECESSOR_SHA256:
        raise ValueError("v3 predecessor SHA-256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = payload.get("report")
    if (
        payload.get("action") != "no_order"
        or not isinstance(report, dict)
        or report.get("schema_version") != "registered-public-event-projection-v3"
        or report.get("appended_observation", {}).get("announcement_date") != AS_OF_DATE
        or report.get("appended_observation", {}).get("pit_available_at")
        != "2026-09-29T00:00:00+08:00"
        or report.get("strict_pit_proven") is not False
        or not isinstance(payload.get("projection"), dict)
    ):
        raise ValueError("v3 predecessor does not match the pinned observation contract")
    return payload


def build_projection_payload(repository_root: Path = ROOT) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    previous = _read_predecessor(root)
    sys.path[:0] = [str(root), str(root / "src")]
    from value_investment_agent.application.product.public_event_projection import (
        project_public_event_projection_as_of,
    )

    prior_projection = previous["projection"]
    result_projection, exclusions = project_public_event_projection_as_of(
        prior_projection, date.fromisoformat(AS_OF_DATE),
    )
    expected_exclusions = ({
        "evidence_id": DEFERRED_EVIDENCE_ID,
        "available_at": DEFERRED_AVAILABLE_AT,
        "event_ids": [DEFERRED_EVENT_ID],
        "reason": "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF",
    },)
    if exclusions != expected_exclusions:
        raise ValueError("as-of filter did not isolate the expected future-available notice")
    if (
        len(prior_projection.get("events", [])) != 9
        or len(result_projection.get("events", [])) != 8
        or len(prior_projection.get("audit_evidence", [])) != 11
        or len(result_projection.get("audit_evidence", [])) != 10
        or len(prior_projection.get("audit_decisions", [])) != 9
        or len(result_projection.get("audit_decisions", [])) != 8
    ):
        raise ValueError("v4 as-of correction changed an unexpected number of projection rows")
    if any(
        item.get("event_id") == DEFERRED_EVENT_ID
        for item in result_projection["events"] + result_projection["audit_decisions"]
    ):
        raise ValueError("future-available event remains in the as-of projection")

    successor = deepcopy(previous)
    successor["projection"] = result_projection
    report = successor["report"]
    report["schema_version"] = "registered-public-event-projection-v4"
    report["successor_of"] = "registered-public-event-projection-v3"
    report["predecessor_sha256"] = PREDECESSOR_SHA256
    report["public_event_observation_as_of"] = AS_OF_DATE
    report["public_event_observation_as_of_semantics"] = (
        "date-only cutoff; local observation clock is unattested; not strict PIT"
    )
    report["event_count"] = len(result_projection["events"])
    report["as_of_exclusions"] = list(exclusions)
    report["strict_pit_proven"] = False
    report["valuation_or_trade_conclusion_changed"] = False
    report["action"] = "no_order"
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
