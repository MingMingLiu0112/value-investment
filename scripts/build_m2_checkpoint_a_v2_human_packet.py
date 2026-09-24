"""Build the versioned M2 Checkpoint A v2 human-review packet.

This command reads only immutable M2 verification v2, M7 v3, and M5 PDF
artifacts. It records the narrow human review conclusions supplied in the
2026-09-24 manual and writes an append-only HumanMilestoneReviewReceipt plus a
hash-bound Checkpoint A packet. It never marks Checkpoint A, B, D or M7 as
passed.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.human_milestone_review import (  # noqa: E402
    HUMAN_MILESTONE_RECEIPT_SCHEMA,
    M2_CHECKPOINT_A_V2_PACKET_SCHEMA,
    M5HumanMaterialityBinding,
    HumanMilestoneReviewReceipt,
    write_human_milestone_receipt,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402


DEFAULT_OUTPUT = ROOT / "runtime" / "m2-checkpoint-a-human-resubmission-20260924-v2"
DEFAULT_GENERATED_AT = datetime(
    2026,
    9,
    24,
    18,
    0,
    0,
    tzinfo=timezone(timedelta(hours=8)),
)
DEFAULT_REVIEWED_AT = date(2026, 9, 24)

M2_REPORT = ROOT / "runtime" / "m2-channel-verification-20260924-v2" / "report.json"
M2_MANIFEST = ROOT / "runtime" / "m2-channel-verification-20260924-v2" / "manifest.json"
M7_WORKBOOK = (
    ROOT / "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.xlsx"
)
M7_MANIFEST = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.m7-daily-workbench-manifest.json"
)
M5_PDF = (
    ROOT
    / "runtime"
    / "m5-disclosure-review-20260923T213249Z"
    / "600887"
    / "announcements"
    / "2026-09-24"
    / "1225578520.pdf"
)

PINNED_SHA256 = {
    M2_REPORT: "310d56e408655c7c46ef510a4ce3aab44d99ab9aeb021c9ddd41f140a2fb1653",
    M2_MANIFEST: "520d175d5a7696b970c091c88be9e8b5996a7627a58828594671f524e360aabe",
    M7_WORKBOOK: "d423ef1ab0114f97e4a20d2f7f770b85e74b3764d6484b63d2fec03c9da82718",
    M7_MANIFEST: "31f918dbf43b0d9b7faaf1f933dace64c1b449d32b675d1058d330e00161e75b",
    M5_PDF: "7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c",
}

HUMAN_DECISIONS = {
    "M2_CHECKPOINT_A": "NOT_APPROVED_PENDING_VERIFICATION_V2",
    "M3_NEGATIVE_CARDS": "PASS",
    "M3_CHECKPOINT_B": "PARTIAL_NOT_APPROVED",
    "M5_1225578520": "NOT_MATERIAL",
    "M7_SEMANTIC_STRUCTURE": "PASS",
    "M4_PRIVATE_INPUT": "PENDING",
    "M6_AUTHORIZATION": "PENDING",
    "M7_FINAL_UX": "PENDING",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(path: Path) -> None:
    expected = PINNED_SHA256[path]
    actual = _digest(path)
    if actual != expected:
        raise ValueError(
            f"{path.relative_to(ROOT)} changed: expected {expected}, got {actual}"
        )


def _load_json(path: Path) -> dict[str, Any]:
    _verify(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError(f"{path.relative_to(ROOT)} is not no_order")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path.resolve()), "sha256": _digest(path)}


def build_packet(
    *,
    generated_at: datetime,
    reviewed_at: date,
) -> dict[str, Any]:
    report = _load_json(M2_REPORT)
    manifest = _load_json(M2_MANIFEST)
    m7_manifest = _load_json(M7_MANIFEST)
    _verify(M7_WORKBOOK)
    _verify(M5_PDF)

    if manifest["report_sha256"] != _digest(M2_REPORT):
        raise ValueError("M2 report hash disagrees with its manifest")
    if m7_manifest["workbook_sha256"] != _digest(M7_WORKBOOK):
        raise ValueError("M7 workbook hash disagrees with its manifest")
    if m7_manifest.get("visible_sheet_count") != 10:
        raise ValueError("M7 v3 must have 10 visible sheets")
    if m7_manifest.get("hidden_sheet_count") != 2:
        raise ValueError("M7 v3 must have 2 hidden sheets")

    source_binding = report["source_binding"]
    summary = report["human_review_packet"]["summary"]
    by_channel = report["coverage_summary"]["by_channel"]
    expected_channels = {"quality", "dividend_cash_return", "value", "cyclical"}
    if set(by_channel) != expected_channels:
        raise ValueError("M2 v2 packet has an unexpected channel summary")

    m5_binding = M5HumanMaterialityBinding(
        symbol="600887",
        announcement_id="1225578520",
        human_decision=HUMAN_DECISIONS["M5_1225578520"],
        pdf_path=str(M5_PDF.relative_to(ROOT)),
        pdf_sha256=_digest(M5_PDF),
        reviewed_at=reviewed_at,
    )
    receipt = HumanMilestoneReviewReceipt(
        receipt_id="human-milestone-review-20260924-v2",
        sequence=1,
        reviewed_at=reviewed_at,
        review_scope="M2/M3/M5/M7 user-perspective review",
        decisions=HUMAN_DECISIONS,
        m5_bindings=(m5_binding,),
    )
    return {
        "schema_version": M2_CHECKPOINT_A_V2_PACKET_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "reviewed_at": reviewed_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "machine_acceptance_status": report["acceptance_status"],
        "human_checkpoint_a_status": receipt.decisions["M2_CHECKPOINT_A"],
        "overall_product_status": "PARTIAL",
        "verification": {
            "policy_version": report["policy_version"],
            "v1_status": source_binding["v1_status"],
            "pit_status": source_binding["pit_status"],
            "lead_count": summary["lead_count"],
            "by_channel": by_channel,
            "totals": {
                "VERIFIED_FOR_DEEP_RESEARCH": summary["verified_for_deep_research"],
                "REJECTED_AFTER_VERIFICATION": summary["rejected_after_verification"],
                "INSUFFICIENT_EVIDENCE": summary["insufficient_evidence"],
                "UNSUPPORTED": summary["unsupported"],
            },
            "report": {
                "path": str(M2_REPORT.relative_to(ROOT)),
                "sha256": _digest(M2_REPORT),
            },
            "manifest": {
                "path": str(M2_MANIFEST.relative_to(ROOT)),
                "sha256": _digest(M2_MANIFEST),
            },
        },
        "human_receipt": receipt.as_policy(),
        "m5_human_materiality": {
            "binding": m5_binding.as_policy(),
            "does_not_imply_m5_continuous_monitoring_pass": True,
        },
        "m7": {
            "information_architecture": receipt.decisions["M7_SEMANTIC_STRUCTURE"],
            "final_ux": receipt.decisions["M7_FINAL_UX"],
            "candidate": {
                "path": str(M7_WORKBOOK.relative_to(ROOT)),
                "sha256": _digest(M7_WORKBOOK),
            },
            "manifest": {
                "path": str(M7_MANIFEST.relative_to(ROOT)),
                "sha256": _digest(M7_MANIFEST),
            },
        },
        "pending_human_items": [
            "M2 Checkpoint A: verify true second-stage semantics in M7 v3",
            "M3 Checkpoint B: read the three negative decision cards",
            "M4: provide private IPS and portfolio inputs",
            "M6: authorize production and start the real shadow period",
            "M7: complete the five hands-on UX tasks on the user device",
        ],
        "forbidden_interpretations": [
            "Checkpoint A=PASS",
            "Checkpoint B=PASS",
            "600887=BUY",
            "M4=READY",
            "M6=AUTHORIZED",
            "M7=INITIAL_ASSISTED_USE",
        ],
        "next_action": "WAIT_FOR_HUMAN_CHECKPOINT_A_REVIEW",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(),
        default=DEFAULT_GENERATED_AT,
    )
    parser.add_argument("--reviewed-at", type=date.fromisoformat, default=DEFAULT_REVIEWED_AT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("Checkpoint A v2 output escapes project root")
    if output_dir.exists():
        raise ValueError(f"Checkpoint A v2 output already exists: {output_dir}")

    packet = build_packet(generated_at=args.generated_at, reviewed_at=args.reviewed_at)
    receipt = HumanMilestoneReviewReceipt(
        receipt_id="human-milestone-review-20260924-v2",
        sequence=1,
        reviewed_at=args.reviewed_at,
        review_scope=packet["human_receipt"]["review_scope"],
        decisions=packet["human_receipt"]["decisions"],
        m5_bindings=(
            M5HumanMaterialityBinding(
                symbol="600887",
                announcement_id="1225578520",
                human_decision=HUMAN_DECISIONS["M5_1225578520"],
                pdf_path=str(M5_PDF.relative_to(ROOT)),
                pdf_sha256=_digest(M5_PDF),
                reviewed_at=args.reviewed_at,
            ),
        ),
    )
    output_dir.mkdir(parents=True)
    receipt_output = write_human_milestone_receipt(receipt, output_dir)
    packet_output = _write_json(output_dir / "checkpoint-a-packet.json", packet)
    manifest_payload = {
        "schema_version": "m2-checkpoint-a-human-resubmission-manifest-v2",
        "generated_at": args.generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "human_receipt_schema": HUMAN_MILESTONE_RECEIPT_SCHEMA,
        "outputs": {
            "human_receipt": receipt_output,
            "checkpoint_a_packet": packet_output,
        },
        "inputs": {
            "m2_report": {"path": str(M2_REPORT), "sha256": _digest(M2_REPORT)},
            "m2_manifest": {"path": str(M2_MANIFEST), "sha256": _digest(M2_MANIFEST)},
            "m7_workbook": {"path": str(M7_WORKBOOK), "sha256": _digest(M7_WORKBOOK)},
            "m7_manifest": {"path": str(M7_MANIFEST), "sha256": _digest(M7_MANIFEST)},
            "m5_pdf": {"path": str(M5_PDF), "sha256": _digest(M5_PDF)},
        },
        "checkpoint_a_status": "READY_FOR_HUMAN_RESUBMISSION",
    }
    manifest_output = _write_json(output_dir / "manifest.json", manifest_payload)
    print(json.dumps(manifest_output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
