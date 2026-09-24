#!/usr/bin/env python3
"""Build the current M7 daily workbench after M2 Checkpoint A acceptance.

This is a presentation-only successor to the frozen M7 daily v3 candidate.  It
reuses the protected daily-workbench renderer, corrects M2 to ``DONE /
HUMAN_PASS``, and adds two later read models:

* 600519 reconstructed official-disclosure continuity from the frozen M3
  historical baseline; and
* the real 600519 CNINFO disclosure queue that remains pending human
  materiality review.

It does not publish canonical, import private portfolio data, decide event
materiality, create production operations, or emit an order.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m3_reconstructed_evidence_continuity import (  # noqa: E402
    from_payload,
)

BASE_BUILDER = runpy.run_path(
    str(ROOT / "scripts" / "build_m7_daily_workbench.py"),
    run_name="build_m7_daily_workbench",
)

ACTION_NO_ORDER = BASE_BUILDER["ACTION_NO_ORDER"]
DEFAULT_GENERATED_AT = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
DEFAULT_OUTPUT = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v4_20260924.xlsx"
)

M3_MANIFEST = (
    ROOT
    / "runtime"
    / "m3-reconstructed-continuity-20260924T083028Z"
    / "manifest.json"
)
M3_TRACE = (
    ROOT
    / "runtime"
    / "m3-reconstructed-continuity-20260924T083028Z"
    / "trace.json"
)
M3_WORKBOOK = (
    ROOT
    / "runtime"
    / "m3-reconstructed-continuity-20260924T083028Z"
    / "A股价值投资_M3重建证据连续性候选_20260924.xlsx"
)
M3_INPUT_PAYLOAD = (
    ROOT
    / "runtime"
    / "m3-reconstructed-continuity-20260924T083028Z"
    / "input-payload.json"
)
M5_600519_QUEUE = (
    ROOT
    / "runtime"
    / "m5-600519-disclosure-queue-20260924"
    / "source"
    / "queue.json"
)
M5_600519_WPS_RECEIPT = (
    ROOT
    / "runtime"
    / "m5-600519-disclosure-queue-20260924"
    / "wps-receipt.json"
)
M5_600519_WORKBOOK = ROOT / "A股价值投资_M5真实披露待复核队列_600519_20260924.xlsx"

PINNED_SHA256 = {
    M3_MANIFEST: "7fc43957372adde5a0040e28017b815efe0e8cf64b00b2c3497d821d4ac2bf51",
    M3_TRACE: "9e2b5f8e386e9836b1af58234606be3e86327e98dbc00d3cd9e29e5637336103",
    M3_WORKBOOK: "719725a31749558d21070a1211862e2811d7b688082697ad9faad19ace930ccb",
    M3_INPUT_PAYLOAD: "61debe108eb95cb2e992c0f3caea5431a308cf78c0384d90d863e13667fd9896",
    M5_600519_QUEUE: "026a6e3502b15d8e38e8abdc8af41007a3f2874740d45514067153bd83983915",
    M5_600519_WPS_RECEIPT: "b49405347f643419cb69cd866378ffbcf5eee84273018367cb62fb569c3d5ec6",
    M5_600519_WORKBOOK: "02cd3499ed4e805f2d76d0f7f0aba89d02be123b02ae3723b43e80f1509eaa3c",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_pinned(path: Path) -> None:
    actual = digest(path)
    expected = PINNED_SHA256[path]
    if actual != expected:
        raise ValueError(
            f"{path.relative_to(ROOT)} changed: expected {expected}, got {actual}"
        )


def _load_pinned(path: Path) -> dict[str, Any]:
    _verify_pinned(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    if payload.get("action") not in (None, ACTION_NO_ORDER):
        raise ValueError(f"{path.relative_to(ROOT)} is not no_order")
    return payload


def _artifact(label: str, path: Path) -> dict[str, str]:
    return {
        "label": label,
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "action": ACTION_NO_ORDER,
    }


def _reconstructed_continuity_packet() -> dict[str, Any]:
    manifest = _load_pinned(M3_MANIFEST)
    trace = _load_pinned(M3_TRACE)
    input_payload = _load_pinned(M3_INPUT_PAYLOAD)
    _verify_pinned(M3_WORKBOOK)
    reconstructed = from_payload(input_payload)
    if manifest["trace_sha256"] != reconstructed.trace_sha256:
        raise ValueError("M3 reconstructed trace hash disagrees with its manifest")
    if manifest["input_payload_sha256"] != digest(M3_INPUT_PAYLOAD):
        raise ValueError("M3 reconstructed input hash disagrees with its manifest")
    if manifest["workbook"]["workbook_sha256"] != digest(M3_WORKBOOK):
        raise ValueError("M3 reconstructed workbook hash disagrees with its manifest")
    baseline = trace["baseline"]
    comparisons = [
        {
            "dimension": item.get("dimension"),
            "baseline_value": item.get("baseline_value"),
            "observation_id": item.get("observation_id"),
            "observation_value": item.get("observation_value"),
            "change_direction": item.get("change_direction"),
            "impact": item.get("impact"),
            "arithmetic_note": item.get("arithmetic_note"),
        }
        for item in trace.get("comparisons") or []
    ]
    return {
        "trace_id": trace["trace_id"],
        "symbol": trace["symbol"],
        "baseline_date": baseline["baseline_date"],
        "rule_version": baseline.get("rule_version"),
        "rule_registration_status": baseline.get("rule_registration_status"),
        "future_rule_version_used": baseline.get("future_rule_version_used"),
        "strict_contemporaneous_rule_pit": "NOT_PROVEN",
        "conclusion_status": trace["conclusion_status"],
        "actual_entry_present": trace["actual_entry_present"],
        "human_decision": trace["human_decision"],
        "requires_human_review": trace["requires_human_review"],
        "blockers": list(trace.get("blockers") or []),
        "comparisons": comparisons,
        "action": trace["action"],
        "artifacts": [
            _artifact("M3 重建证据连续性 manifest", M3_MANIFEST),
            _artifact("M3 重建证据连续性 trace", M3_TRACE),
            _artifact("M3 重建证据连续性工作簿", M3_WORKBOOK),
        ],
    }


def _pdf_sha256(item: dict[str, Any], symbol: str) -> str:
    target = f"{symbol}-pdf-{item.get('announcement_id')}"
    for reference in item.get("evidence_refs") or []:
        if reference.get("id") == target:
            return str(reference.get("sha256") or "")
    return ""


def _disclosure_queue_600519_packet() -> dict[str, Any]:
    queue = _load_pinned(M5_600519_QUEUE)
    _verify_pinned(M5_600519_WPS_RECEIPT)
    _verify_pinned(M5_600519_WORKBOOK)
    scan = queue["scans"][0]
    announcements = list(scan.get("announcements") or [])
    pending_items = [
        item
        for item in announcements
        if item.get("review_status") == "PENDING_HUMAN_REVIEW"
    ]
    return {
        "queue_id": queue["queue_id"],
        "symbol": scan["symbol"],
        "provider": queue["provider"],
        "parser_version": queue["parser_version"],
        "scan_from": queue["scan_from"],
        "scan_to": queue["scan_to"],
        "retrieved_at": queue["retrieved_at"],
        "coverage_status": scan.get("coverage_status"),
        "total_announcements": len(announcements),
        "pending_count": len(pending_items),
        "source_unavailable": sum(
            1
            for item in announcements
            if item.get("review_status") == "SOURCE_UNAVAILABLE"
        ),
        "pending_items": [
            {
                "announcement_id": item.get("announcement_id"),
                "published_at": item.get("published_at"),
                "title": item.get("title"),
                "rule_kind": item.get("rule_kind"),
                "review_status": item.get("review_status"),
                "source_url": item.get("source_url"),
                "pdf_sha256": _pdf_sha256(item, scan["symbol"]),
            }
            for item in pending_items
        ],
        "action": queue["action"],
        "artifacts": [
            _artifact("M5 600519 真实披露队列源数据", M5_600519_QUEUE),
            _artifact("M5 600519 真实披露队列工作簿", M5_600519_WORKBOOK),
            _artifact("M5 600519 WPS 只读收据", M5_600519_WPS_RECEIPT),
        ],
    }


def build_packet(generated_at: datetime) -> dict[str, Any]:
    packet = BASE_BUILDER["build_packet"](generated_at)
    reconstructed = _reconstructed_continuity_packet()
    disclosure_queue = _disclosure_queue_600519_packet()
    packet["m3"]["reconstructed_continuity"] = reconstructed
    packet["m5"]["disclosure_queue_600519"] = disclosure_queue
    packet["audit"]["artifacts"].extend(
        reconstructed["artifacts"] + disclosure_queue["artifacts"]
    )
    packet["stage_statuses"]["m2"] = [
        "M2",
        "ENGINEERING_DONE",
        "DONE",
        "HUMAN_PASS",
    ]
    return packet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
        default=DEFAULT_GENERATED_AT,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    receipt = BASE_BUILDER["write_daily_workbench"](
        build_packet(args.generated_at),
        output=args.output,
        root=ROOT,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
