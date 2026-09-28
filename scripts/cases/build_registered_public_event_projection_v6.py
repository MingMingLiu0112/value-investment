"""Build a successor public-event view at a conservative date cutoff."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR_PATH = Path(
    "runtime/prospective-public-event-20260928/"
    "registered-public-event-projection-v5.json"
)
PREDECESSOR_SHA256 = "5e543f50690a71254a97ff5c39136cd2bb74d81d1e3c4d3600f023dc948487d6"
SOURCE_PATH = Path(
    "runtime/prospective-public-event-20260928/"
    "registered-public-event-projection-v3.json"
)
SOURCE_SHA256 = "75f419502c1f5c646d15913e455889a0d8c3ff08829b12316251c747702a3781"
WATERMARK_PATH = Path("config/prospective-public-event-watermarks-v9.json")
WATERMARK_SHA256 = "fa42a7aeb365185451fd2402390b631defc01d70d6ae310b47f29ab8465c8c49"
PREVIOUS_AS_OF = date(2026, 9, 28)
CURRENT_AS_OF = date(2026, 9, 29)
REGISTERED_SYMBOLS = {"000333", "600887", "601088"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_pinned(
    root: Path, relative: Path, digest: str, label: str,
) -> tuple[Path, dict[str, Any]]:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"{label} must be an existing repository file")
    if _sha256(path) != digest.lower():
        raise ValueError(f"{label} SHA-256 mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return path, payload


def _verify_bounded_observations(root: Path) -> tuple[dict[str, Any], ...]:
    _, watermarks = _read_pinned(
        root, WATERMARK_PATH, WATERMARK_SHA256, "watermark v9",
    )
    if watermarks.get("action") != "no_order" or watermarks.get("formal_watermark_advanced") is not False:
        raise ValueError("watermark v9 must remain a bounded no_order snapshot")
    rows = [
        row for row in watermarks.get("current_bounded_observations", [])
        if isinstance(row, dict) and row.get("scan_to") == CURRENT_AS_OF.isoformat()
    ]
    if {row.get("symbol") for row in rows} != REGISTERED_SYMBOLS or len(rows) != len(REGISTERED_SYMBOLS):
        raise ValueError("watermark v9 must bind one current bounded snapshot per registered symbol")

    verified: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["symbol"]):
        if (
            row.get("scan_from") != "2026-09-28"
            or row.get("coverage_status") != "SINGLE_DAY_SNAPSHOT_ONLY"
            or row.get("retrieval_clock_attestation") != "PROCESS_CLOCK_ONLY_UNATTESTED"
            or row.get("action") != "no_order"
        ):
            raise ValueError("current bounded observation scope or time assurance is invalid")
        retrieved_at = datetime.fromisoformat(row.get("retrieved_at", ""))
        if (
            retrieved_at.utcoffset() is None
            or retrieved_at.astimezone(ZoneInfo("Asia/Shanghai")).date() != CURRENT_AS_OF
        ):
            raise ValueError("current bounded observation timestamp must remain date-bounded and timezone-aware")

        receipt_path, receipt = _read_pinned(
            root, Path(row["scan_receipt_path"]), row["scan_receipt_sha256"],
            f"{row['symbol']} scan receipt",
        )
        _, index = _read_pinned(
            root, Path(row["index_path"]), row["index_sha256"],
            f"{row['symbol']} announcement index",
        )
        _, raw = _read_pinned(
            root, Path(row["raw_page_path"]), row["raw_page_sha256"],
            f"{row['symbol']} raw response",
        )
        expected_window = "2026-09-28~2026-09-29"
        page_refs = receipt.get("pagination", {}).get("page_refs", [])
        if (
            receipt.get("schema_version") != "cninfo-exact-issuer-single-day-receipt-v1"
            or receipt.get("symbol") != row["symbol"]
            or receipt.get("exact_query_date_filter") != expected_window
            or receipt.get("capture_status") != "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS"
            or receipt.get("action") != "no_order"
            or receipt.get("index_sha256") != row["index_sha256"]
            or len(page_refs) != 1
            or page_refs[0].get("sha256") != row["raw_page_sha256"]
            or Path(receipt.get("index_path", "")).as_posix() != Path(row["index_path"]).as_posix()
        ):
            raise ValueError("scan receipt does not bind the exact bounded observation")

        index_items = index.get("announcements") or []
        raw_items = raw.get("announcements") or []
        expected_ids = row.get("announcement_ids")
        if not isinstance(expected_ids, list):
            raise ValueError("bounded observation must declare announcement ids")
        indexed_ids = [item.get("announcementId") for item in index_items]
        raw_ids = [item.get("announcementId") for item in raw_items]
        if (
            indexed_ids != expected_ids
            or raw_ids != expected_ids
            or any(item.get("secCode") != row["symbol"] for item in index_items + raw_items)
        ):
            raise ValueError("bounded observation announcement identities do not reconcile")

        verified.append({
            "symbol": row["symbol"],
            "scan_from": row["scan_from"],
            "scan_to": row["scan_to"],
            "retrieved_at": row["retrieved_at"],
            "retrieval_clock_attestation": row["retrieval_clock_attestation"],
            "coverage_status": row["coverage_status"],
            "announcement_ids": expected_ids,
            "scan_receipt_path": receipt_path.relative_to(root).as_posix(),
            "scan_receipt_sha256": row["scan_receipt_sha256"],
            "index_sha256": row["index_sha256"],
            "raw_page_sha256": row["raw_page_sha256"],
        })
    return tuple(verified)


def build_projection_payload(repository_root: Path = ROOT) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    _, predecessor = _read_pinned(
        root, PREDECESSOR_PATH, PREDECESSOR_SHA256, "v5 predecessor",
    )
    source_path, source = _read_pinned(
        root, SOURCE_PATH, SOURCE_SHA256, "v3 source closure",
    )
    observations = _verify_bounded_observations(root)

    predecessor_report = predecessor.get("report")
    source_report = source.get("report")
    predecessor_projection = predecessor.get("projection")
    source_projection = source.get("projection")
    if (
        predecessor.get("action") != "no_order"
        or not isinstance(predecessor_report, dict)
        or predecessor_report.get("schema_version") != "registered-public-event-projection-v5"
        or predecessor_report.get("public_event_observation_as_of") != PREVIOUS_AS_OF.isoformat()
        or predecessor_report.get("source_evidence_path") != SOURCE_PATH.as_posix()
        or predecessor_report.get("source_evidence_sha256") != SOURCE_SHA256
        or not isinstance(predecessor_projection, dict)
        or not isinstance(source_report, dict)
        or source_report.get("schema_version") != "registered-public-event-projection-v3"
        or source.get("action") != "no_order"
        or not isinstance(source_projection, dict)
    ):
        raise ValueError("pinned v5/v3 projection chain is inconsistent")

    from value_investment_agent.application.product.public_event_projection import (
        project_public_event_projection_as_of,
    )

    previous_projection, previous_exclusions = project_public_event_projection_as_of(
        source_projection, PREVIOUS_AS_OF,
    )
    predecessor_current_view = deepcopy(predecessor_projection)
    quarantine = predecessor_current_view.pop("as_of_excluded_evidence", None)
    if (
        predecessor_current_view != previous_projection
        or predecessor_report.get("as_of_exclusions") != list(previous_exclusions)
        or not isinstance(quarantine, list)
        or len(quarantine) != len(previous_exclusions)
    ):
        raise ValueError("v5 is not a faithful as-of projection of its pinned v3 source")

    current_projection, current_exclusions = project_public_event_projection_as_of(
        source_projection, CURRENT_AS_OF,
    )
    if len(current_exclusions) > len(previous_exclusions):
        raise ValueError("successor cannot introduce additional future-available evidence")
    current_evidence_ids = {row.get("evidence_id") for row in current_projection["audit_evidence"]}
    resolved = [
        {
            "evidence_id": exclusion["evidence_id"],
            "available_at": exclusion["available_at"],
            "related_event_ids": exclusion["event_ids"],
        }
        for exclusion in previous_exclusions
        if date.fromisoformat(exclusion["available_at"]) <= CURRENT_AS_OF
    ]
    if any(row["evidence_id"] not in current_evidence_ids for row in resolved):
        raise ValueError("previously excluded evidence was not re-admitted at its conservative availability date")

    observed_ids = {
        announcement_id
        for observation in observations
        for announcement_id in observation["announcement_ids"]
    }
    resolved_ids = {
        evidence_id.removeprefix("cninfo-")
        for row in resolved
        for evidence_id in [row["evidence_id"]]
    }
    if not resolved_ids.issubset(observed_ids):
        raise ValueError("re-admitted evidence is absent from the latest bounded issuer observations")

    result = deepcopy(predecessor)
    result["projection"] = current_projection
    report = result["report"]
    report.update({
        "schema_version": "registered-public-event-projection-v6",
        "successor_of": "registered-public-event-projection-v5",
        "predecessor_sha256": PREDECESSOR_SHA256,
        "source_evidence_path": SOURCE_PATH.as_posix(),
        "source_evidence_sha256": SOURCE_SHA256,
        "public_event_observation_as_of": CURRENT_AS_OF.isoformat(),
        "public_event_observation_as_of_semantics": (
            "date-only availability cutoff; retrieval clocks are unattested; not strict PIT"
        ),
        "event_count": len(current_projection["events"]),
        "as_of_exclusions": list(current_exclusions),
        "resolved_prior_exclusions": resolved,
        "bounded_observation_watermark_path": WATERMARK_PATH.as_posix(),
        "bounded_observation_watermark_sha256": WATERMARK_SHA256,
        "bounded_observations": list(observations),
        "formal_watermark_advanced": False,
        "strict_pit_proven": False,
        "valuation_or_trade_conclusion_changed": False,
        "action": "no_order",
    })
    result["action"] = "no_order"
    return result


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
