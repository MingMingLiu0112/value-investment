"""Append one hash-pinned Midea meeting notice to the registered M5 projection."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
NOTICE_SCHEMA = "midea-egm-notice-projection-v1"
NOTICE_ID = "1225582141"
NOTICE_DATE = "2026-09-28"
NOTICE_URL = "https://static.cninfo.com.cn/finalpage/2026-09-28/1225582141.PDF"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_notice_projection(
    repository_root: Path, projection_path: Path, expected_sha256: str,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    path = Path(projection_path).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    runtime_root = (root / "runtime").resolve()
    if not path.is_relative_to(runtime_root) or not path.is_file():
        raise ValueError("Notice projection must be an existing file under repository runtime")
    if len(expected_sha256) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in expected_sha256):
        raise ValueError("Notice projection SHA-256 must be 64 hexadecimal characters")
    actual_hash = _sha256(path)
    if actual_hash.lower() != expected_sha256.lower():
        raise ValueError("Notice projection SHA-256 mismatch")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Notice projection is not valid UTF-8 JSON") from error
    _validate_notice_projection(root, payload)
    return payload


def _validate_notice_projection(root: Path, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("action") != "no_order":
        raise ValueError("Notice projection action must be no_order")
    report = payload.get("report")
    projection = payload.get("projection")
    if not isinstance(report, dict) or report.get("schema_version") != NOTICE_SCHEMA:
        raise ValueError("Unexpected Midea meeting notice projection schema")
    if report.get("symbol") != "000333":
        raise ValueError("Notice projection issuer must be 000333")
    if report.get("announcement_id") != NOTICE_ID or report.get("announcement_date") != NOTICE_DATE:
        raise ValueError("Notice projection must identify the 2026-09-28 Midea notice")
    if report.get("valuation_or_trade_conclusion_changed") is not False:
        raise ValueError("Notice projection must leave valuation and trade conclusions unchanged")
    if not isinstance(projection, dict) or projection.get("action") != "no_order":
        raise ValueError("Notice event projection action must be no_order")
    events = projection.get("events")
    evidence = projection.get("audit_evidence")
    decisions = projection.get("audit_decisions")
    if not all(isinstance(rows, list) for rows in (events, evidence, decisions)):
        raise ValueError("Notice projection requires events, audit_evidence and audit_decisions arrays")
    if len(events) != 1 or len(evidence) != 1 or len(decisions) != 1:
        raise ValueError("Notice projection must contain exactly one event, evidence and decision")

    event, evidence_row, decision = events[0], evidence[0], decisions[0]
    expected_event_id = f"midea-2026-egm-notice-{NOTICE_ID}"
    expected_evidence_id = f"cninfo-{NOTICE_ID}"
    if (
        event.get("event_id") != expected_event_id
        or event.get("company_name") != "美的集团"
        or event.get("action") != "no_order"
        or event.get("event_type") not in {"MATERIAL_SUPPORTING_EVIDENCE", "MATERIAL_RISK_MONITOR"}
    ):
        raise ValueError("Projection must contain the single Midea meeting notice event")
    if event.get("evidence_refs") != [expected_evidence_id]:
        raise ValueError("Meeting notice event must reference its one notice evidence record")
    if (
        evidence_row.get("evidence_id") != expected_evidence_id
        or evidence_row.get("artifact_type") != "cninfo_original_pdf"
        or evidence_row.get("action") != "no_order"
        or evidence_row.get("source_url") != NOTICE_URL
    ):
        raise ValueError("Notice evidence identity or official source URL is invalid")
    evidence_path = (root / str(evidence_row.get("path", ""))).resolve()
    if not evidence_path.is_relative_to((root / "runtime").resolve()) or not evidence_path.is_file():
        raise ValueError("Notice original evidence must be an existing file under runtime")
    evidence_hash = evidence_row.get("sha256")
    if not isinstance(evidence_hash, str) or _sha256(evidence_path).lower() != evidence_hash.lower():
        raise ValueError("Notice original evidence SHA-256 mismatch")
    if (
        decision.get("event_id") != expected_event_id
        or decision.get("action") != "no_order"
        or decision.get("evidence_refs") != [expected_evidence_id]
    ):
        raise ValueError("Notice audit decision does not match the single event and evidence")


def build_projection_payload(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    notice_projection_path: Path,
    notice_projection_sha256: str,
) -> dict[str, Any]:
    """Compose the unchanged eight-event base with one verified bounded notice."""
    root = Path(repository_root).resolve()
    sys.path[:0] = [str(root), str(root / "src")]
    from scripts.cases.build_registered_public_event_projection import build_projection_payload as build_v1

    base = build_v1(root)
    notice_payload = _load_notice_projection(root, notice_projection_path, notice_projection_sha256)
    projection = deepcopy(base["projection"])
    notice = notice_payload["projection"]
    for key, identity_key in (
        ("events", "event_id"),
        ("audit_evidence", "evidence_id"),
        ("audit_decisions", "event_id"),
    ):
        existing = {row.get(identity_key) for row in projection[key]}
        for row in notice[key]:
            identity = row.get(identity_key)
            if not identity or identity in existing:
                raise ValueError(f"Duplicate or empty identity when appending notice to {key}")
            existing.add(identity)
            projection[key].append(deepcopy(row))

    if len(projection["events"]) != 9:
        raise ValueError("Combined M5 projection must contain exactly nine event cards")
    if any(row.get("action") != "no_order" for key in ("events", "audit_evidence", "audit_decisions") for row in projection[key]):
        raise ValueError("Combined M5 projection must remain no_order")
    projection["action"] = "no_order"
    return {
        "action": "no_order",
        "report": {
            "schema_version": "registered-public-event-projection-v2",
            "scope": ["000333", "600887", "601088"],
            "event_count": 9,
            "appended_observation": {
                "symbol": "000333",
                "announcement_id": NOTICE_ID,
                "announcement_date": NOTICE_DATE,
                "scope": "ONE_EXACT_ISSUER_CNINFO_OBSERVATION_ONLY",
            },
            "formal_watermark_advanced": False,
            "continuous_coverage_claimed": False,
            "multi_channel_coverage_claimed": False,
            "strict_pit_proven": False,
            "valuation_or_trade_conclusion_changed": False,
            "action": "no_order",
            "limitations": [
                "仅追加一条2026-09-28美的集团精确发行人CNINFO观察；不代表当日稍后公告已覆盖。",
                "不推进正式水位、连续覆盖、多渠道覆盖或strict PIT证明。",
                "该股东会通知仅为程序性后续事项，不代表议案通过或实施。",
                "不改变估值或交易结论；action=no_order。",
            ],
        },
        "projection": projection,
    }


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    import os

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
