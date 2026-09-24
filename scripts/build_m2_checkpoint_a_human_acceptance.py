"""Record append-only human acceptance of M2 Checkpoint A.

The v2 human-review packet remains frozen. This command reads the same
hash-pinned artifacts, records the user's explicit ``HUMAN_PASS`` decision in
sequence 2 of the HumanMilestoneReviewReceipt chain, and publishes a new
acceptance packet. It does not sign Checkpoint B, D or M7.
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
sys.path.insert(0, str(ROOT / "scripts"))

import build_m2_checkpoint_a_v2_human_packet as v2_builder  # noqa: E402
from value_investment_agent.human_milestone_review import (  # noqa: E402
    HUMAN_MILESTONE_RECEIPT_SCHEMA,
    M5HumanMaterialityBinding,
    HumanMilestoneReviewReceipt,
    write_human_milestone_receipt,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402


ACCEPTANCE_SCHEMA = "m2-checkpoint-a-human-acceptance-v3"
DEFAULT_OUTPUT = ROOT / "runtime" / "m2-checkpoint-a-human-acceptance-20260924-v3"
DEFAULT_GENERATED_AT = datetime(
    2026,
    9,
    24,
    19,
    0,
    0,
    tzinfo=timezone(timedelta(hours=8)),
)
DEFAULT_REVIEWED_AT = date(2026, 9, 24)

PREVIOUS_RECEIPT = (
    ROOT
    / "runtime"
    / "m2-checkpoint-a-human-resubmission-20260924-v2"
    / "receipt.json"
)
PREVIOUS_RECEIPT_SHA256 = (
    "5a29fad3af4b6c3521236aee6d7cd70884287b318b20d3c95535ba974567bd0a"
)

HUMAN_DECISIONS_V3 = {
    "M2_CHECKPOINT_A": "HUMAN_PASS",
    "M3_NEGATIVE_CARDS": "PASS",
    "M3_CHECKPOINT_B": "PARTIAL_NOT_APPROVED",
    "M5_1225578520": "NOT_MATERIAL",
    "M7_SEMANTIC_STRUCTURE": "PASS",
    "M4_PRIVATE_INPUT": "PENDING",
    "M6_AUTHORIZATION": "PENDING",
    "M7_FINAL_UX": "PENDING",
}

BACKLOG = [
    {
        "id": "BL-20260924-001",
        "status": "OPEN",
        "blocking": False,
        "milestone": "M2",
        "channel": "dividend_cash_return",
        "title": "Correct payout ratio and cash-conversion semantics before first positive VERIFIED",
        "trigger": (
            "Before any Dividend / Cash Return lead is promoted to "
            "VERIFIED_FOR_DEEP_RESEARCH"
        ),
        "acceptance": (
            "The verification policy separates declared, paid and one-off "
            "distributions, uses only realized cash-conversion evidence, and "
            "binds the calculation to dated source artifacts."
        ),
    },
    {
        "id": "BL-20260924-002",
        "status": "OPEN",
        "blocking": False,
        "milestone": "M2",
        "channel": "value",
        "title": "Add EV/EBIT or a Profile-equivalent capital-structure metric before first positive VERIFIED",
        "trigger": (
            "Before any Value-channel lead is promoted to "
            "VERIFIED_FOR_DEEP_RESEARCH"
        ),
        "acceptance": (
            "The value verification policy includes EV/EBIT or a justified "
            "Profile-equivalent metric with dated inputs and does not infer "
            "normalized earnings from a single-period PE/PB screen."
        ),
    },
]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path.resolve()), "sha256": _digest(path)}


def _m5_binding(reviewed_at: date) -> M5HumanMaterialityBinding:
    return M5HumanMaterialityBinding(
        symbol="600887",
        announcement_id="1225578520",
        human_decision=HUMAN_DECISIONS_V3["M5_1225578520"],
        pdf_path=str(v2_builder.M5_PDF.relative_to(ROOT)),
        pdf_sha256=_digest(v2_builder.M5_PDF),
        reviewed_at=reviewed_at,
    )


def build_acceptance_packet(
    *,
    generated_at: datetime,
    reviewed_at: date,
) -> dict[str, Any]:
    """Validate the frozen v2 artifacts and build the human-acceptance packet."""
    v2_packet = v2_builder.build_packet(
        generated_at=generated_at,
        reviewed_at=reviewed_at,
    )
    if not PREVIOUS_RECEIPT.is_file():
        raise ValueError("M2 Checkpoint A v2 human receipt is missing")
    previous_digest = _digest(PREVIOUS_RECEIPT)
    if previous_digest != PREVIOUS_RECEIPT_SHA256:
        raise ValueError(
            "M2 Checkpoint A v2 human receipt hash changed: "
            f"expected {PREVIOUS_RECEIPT_SHA256}, got {previous_digest}"
        )

    m5_binding = _m5_binding(reviewed_at)
    receipt = HumanMilestoneReviewReceipt(
        receipt_id="human-milestone-review-20260924-v3",
        sequence=2,
        reviewed_at=reviewed_at,
        review_scope="M2 Checkpoint A explicit human acceptance",
        decisions=HUMAN_DECISIONS_V3,
        m5_bindings=(m5_binding,),
        previous_receipt_sha256=previous_digest,
    )
    return {
        "schema_version": ACCEPTANCE_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "reviewed_at": reviewed_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "m2_acceptance_status": "DONE",
        "machine_acceptance_status": v2_packet["machine_acceptance_status"],
        "human_checkpoint_a_status": receipt.decisions["M2_CHECKPOINT_A"],
        "overall_product_status": "PARTIAL",
        "verification": v2_packet["verification"],
        "human_receipt": receipt.as_policy(),
        "previous_receipt": {
            "path": str(PREVIOUS_RECEIPT.relative_to(ROOT)),
            "sha256": previous_digest,
        },
        "m5_human_materiality": {
            "binding": m5_binding.as_policy(),
            "does_not_imply_m5_continuous_monitoring_pass": True,
        },
        "m7": v2_packet["m7"],
        "backlog": BACKLOG,
        "pending_human_items": [
            "M3 Checkpoint B: read the three negative decision cards",
            "M4: provide private IPS and portfolio inputs",
            "M6: authorize production and start the real shadow period",
            "M7: complete the five hands-on UX tasks on the user device",
        ],
        "forbidden_interpretations": [
            "M2_CHECKPOINT_A=HUMAN_PASS implies a BUY/ADD or position",
            "M2=DONE implies the overall M2-M7 product is ready",
            "Checkpoint B=PASS",
            "600887=BUY",
            "M4=READY",
            "M6=AUTHORIZED",
            "M7=INITIAL_ASSISTED_USE",
        ],
        "next_action": "CONTINUE_M3_M4_M5_M6_M7",
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
        raise ValueError("M2 Checkpoint A acceptance output escapes project root")
    if output_dir.exists():
        raise ValueError(f"M2 Checkpoint A acceptance output already exists: {output_dir}")

    packet = build_acceptance_packet(
        generated_at=args.generated_at,
        reviewed_at=args.reviewed_at,
    )
    output_dir.mkdir(parents=True)
    receipt = HumanMilestoneReviewReceipt(
        receipt_id="human-milestone-review-20260924-v3",
        sequence=2,
        reviewed_at=args.reviewed_at,
        review_scope="M2 Checkpoint A explicit human acceptance",
        decisions=HUMAN_DECISIONS_V3,
        m5_bindings=(_m5_binding(args.reviewed_at),),
        previous_receipt_sha256=_digest(PREVIOUS_RECEIPT),
    )
    receipt_output = write_human_milestone_receipt(
        receipt,
        output_dir,
        PREVIOUS_RECEIPT,
    )
    packet_output = _write_json(output_dir / "checkpoint-a-packet.json", packet)
    manifest_payload = {
        "schema_version": "m2-checkpoint-a-human-acceptance-manifest-v3",
        "generated_at": args.generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "human_receipt_schema": HUMAN_MILESTONE_RECEIPT_SCHEMA,
        "m2_acceptance_status": "DONE",
        "human_checkpoint_a_status": "HUMAN_PASS",
        "overall_product_status": "PARTIAL",
        "previous_receipt": {
            "path": str(PREVIOUS_RECEIPT),
            "sha256": _digest(PREVIOUS_RECEIPT),
        },
        "outputs": {
            "human_receipt": receipt_output,
            "checkpoint_a_packet": packet_output,
        },
        "inputs": {
            "m2_report": {
                "path": str(v2_builder.M2_REPORT),
                "sha256": _digest(v2_builder.M2_REPORT),
            },
            "m2_manifest": {
                "path": str(v2_builder.M2_MANIFEST),
                "sha256": _digest(v2_builder.M2_MANIFEST),
            },
            "m7_workbook": {
                "path": str(v2_builder.M7_WORKBOOK),
                "sha256": _digest(v2_builder.M7_WORKBOOK),
            },
            "m7_manifest": {
                "path": str(v2_builder.M7_MANIFEST),
                "sha256": _digest(v2_builder.M7_MANIFEST),
            },
            "m5_pdf": {
                "path": str(v2_builder.M5_PDF),
                "sha256": _digest(v2_builder.M5_PDF),
            },
        },
    }
    manifest_output = _write_json(output_dir / "manifest.json", manifest_payload)
    print(json.dumps(manifest_output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
