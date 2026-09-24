"""Record the partial human acceptance of M3 Checkpoint B.

This command turns the user's completed semantic review into an append-only
sequence-3 receipt.  It records the three passed sub-reviews, keeps the
overall checkpoint at ``PARTIAL``, and preserves the strict contemporaneous
rule PIT ``NOT_PROVEN`` blocker.  It does not create an Entry, Journal,
personal portfolio, position or order.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.human_milestone_review import (  # noqa: E402
    HUMAN_MILESTONE_RECEIPT_SCHEMA,
    HumanMilestoneReviewReceipt,
    write_human_milestone_receipt,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402


ACCEPTANCE_SCHEMA = "m3-checkpoint-b-human-acceptance-v1"
DEFAULT_OUTPUT = ROOT / "runtime" / "m3-checkpoint-b-human-acceptance-20260924-v1"
DEFAULT_GENERATED_AT = datetime(
    2026,
    9,
    24,
    22,
    0,
    0,
    tzinfo=timezone(timedelta(hours=8)),
)
DEFAULT_REVIEWED_AT = date(2026, 9, 24)

CHECKPOINT_B_PACKET = (
    ROOT
    / "runtime"
    / "m3-checkpoint-b-human-review-20260924-v1"
    / "checkpoint-b-packet.json"
)
PREVIOUS_RECEIPT = (
    ROOT
    / "runtime"
    / "m2-checkpoint-a-human-acceptance-20260924-v3"
    / "receipt.json"
)
STRICT_PIT_RECEIPT = (
    ROOT
    / "runtime"
    / "m3-strict-pit-evidence-audit-20260924T080000Z"
    / "receipt.json"
)

PINNED_SHA256 = {
    CHECKPOINT_B_PACKET: "fab538fb283b55b449d6c52be908216cbe2df06880a2c66848901371a15c7eb4",
    PREVIOUS_RECEIPT: "9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20",
    STRICT_PIT_RECEIPT: "9d161d6e7a52e0c061c7129510933f7b3701245bd6c65a444450b50002dbdf3c",
}

DECISIONS = {
    "M2_CHECKPOINT_A": "HUMAN_PASS",
    "M3_NEGATIVE_CARDS": "PASS",
    "M3_CHECKPOINT_B": "PARTIAL",
    "M5_1225578520": "NOT_MATERIAL",
    "M7_SEMANTIC_STRUCTURE": "PASS",
    "M4_PRIVATE_INPUT": "PENDING_USER_PRIVATE_INPUT",
    "M6_AUTHORIZATION": "NOT_YET",
    "M7_FINAL_UX": "PENDING",
}

SUPPLEMENTAL_DECISIONS = {
    "M3_NEGATIVE_CARD_HUMAN_REVIEW": "PASS",
    "M3_HUMAN_UNDERSTANDABILITY": "PASS",
    "M3_NO_FALSE_BUY_ADD": "PASS",
    "M3_BLOCKER": "STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN",
    "M4_PERSONALIZED_ACCEPTANCE": "PENDING_USER_PRIVATE_INPUT",
    "M6_PRODUCTION_AUTHORIZATION": "NOT_YET",
}

EXPECTED_CARD_SYMBOLS = {"000651", "600741", "600887"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_pinned(path: Path) -> str:
    expected = PINNED_SHA256.get(path)
    if expected is None:
        raise ValueError(f"No pinned SHA-256 for {path}")
    actual = _digest(path)
    if actual != expected:
        raise ValueError(f"{path.relative_to(ROOT)} changed: expected {expected}, got {actual}")
    return actual


def _load_pinned(path: Path) -> dict[str, Any]:
    _verify_pinned(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError(f"{path.relative_to(ROOT)} is not no_order")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> dict[str, str]:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path.resolve()), "sha256": _digest(path)}


def build_receipt(*, reviewed_at: date) -> HumanMilestoneReviewReceipt:
    """Build the exact sequence-3 receipt requested by the human reviewer."""
    previous_digest = _verify_pinned(PREVIOUS_RECEIPT)
    return HumanMilestoneReviewReceipt(
        receipt_id="human-milestone-review-20260924-v4",
        sequence=3,
        reviewed_at=reviewed_at,
        review_scope="M3 Checkpoint B partial human review",
        decisions=DECISIONS,
        supplemental_decisions=SUPPLEMENTAL_DECISIONS,
        previous_receipt_sha256=previous_digest,
    )


def build_packet(*, generated_at: datetime, reviewed_at: date) -> dict[str, Any]:
    """Validate the frozen review packet and build the partial acceptance packet."""
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")

    base = _load_pinned(CHECKPOINT_B_PACKET)
    strict_pit = _load_pinned(STRICT_PIT_RECEIPT)
    receipt = build_receipt(reviewed_at=reviewed_at)

    if base.get("checkpoint_b_status") != "PENDING_HUMAN_REVIEW":
        raise ValueError("Base M3 Checkpoint B packet is not pending human review")
    if base.get("strict_contemporaneous_rule_pit") != "NOT_PROVEN":
        raise ValueError("Base M3 packet changed the strict PIT blocker")
    if base.get("m2_governance", {}).get("status") != "HUMAN_PASS":
        raise ValueError("Base M3 packet no longer binds the M2 human acceptance")

    cards = base.get("cards")
    if not isinstance(cards, list) or len(cards) != 3:
        raise ValueError("M3 Checkpoint B packet must contain exactly three cards")
    symbols = {str(item.get("symbol")) for item in cards if isinstance(item, dict)}
    if symbols != EXPECTED_CARD_SYMBOLS:
        raise ValueError("M3 Checkpoint B packet contains an unexpected card set")
    for item in cards:
        if item.get("system_status") != "INSUFFICIENT_RESEARCH":
            raise ValueError("M3 Checkpoint B card no longer has insufficient research")
        if item.get("action") != ACTION_NO_ORDER:
            raise ValueError("M3 Checkpoint B card is not no_order")

    if strict_pit.get("status") != "NOT_PROVEN":
        raise ValueError("Strict PIT receipt is no longer NOT_PROVEN")
    replay_pit = strict_pit.get("replay") or {}
    if replay_pit.get("rule_registration_status") != "RETROSPECTIVE_RESEARCH_EXTENSION":
        raise ValueError("Strict PIT blocker no longer records retrospective rule use")
    if replay_pit.get("future_rule_version_used") is not True:
        raise ValueError("Strict PIT blocker no longer records future rule use")

    return {
        "schema_version": ACCEPTANCE_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "reviewed_at": reviewed_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "goal_id": "VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE",
        "checkpoint_b_status": "PARTIAL",
        "human_review_subchecks": {
            "M3_NEGATIVE_CARD_HUMAN_REVIEW": "PASS",
            "M3_HUMAN_UNDERSTANDABILITY": "PASS",
            "M3_NO_FALSE_BUY_ADD": "PASS",
        },
        "blocker": {
            "code": "STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN",
            "status": "NOT_PROVEN",
            "rule_version": replay_pit.get("rule_version"),
            "rule_registration_status": replay_pit.get("rule_registration_status"),
            "future_rule_version_used": replay_pit.get("future_rule_version_used"),
            "reason": (
                "The historical replay facts, announcements and quotes satisfy PIT, "
                "but the applied rule version is a retrospective research extension. "
                "The historical rule chain is not contemporaneous evidence."
            ),
            "next_action": (
                "Wait for a genuinely contemporaneous rule version and a later real "
                "event chain; do not fabricate historical rule registration evidence."
            ),
        },
        "cards": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "system_status": item["system_status"],
                "reason_category": item["reason_category"],
                "action": item["action"],
            }
            for item in cards
        ],
        "human_receipt": receipt.as_policy(),
        "previous_receipt": {
            "path": str(PREVIOUS_RECEIPT.relative_to(ROOT)),
            "sha256": _verify_pinned(PREVIOUS_RECEIPT),
        },
        "m4": {
            "personalized_acceptance": "PENDING_USER_PRIVATE_INPUT",
            "offline_engineering_allowed": True,
        },
        "m6": {
            "production_authorization": "NOT_YET",
            "production_actions_allowed": False,
        },
        "evidence": {
            "checkpoint_b_packet": {
                "path": str(CHECKPOINT_B_PACKET.relative_to(ROOT)),
                "sha256": _verify_pinned(CHECKPOINT_B_PACKET),
            },
            "strict_pit_receipt": {
                "path": str(STRICT_PIT_RECEIPT.relative_to(ROOT)),
                "sha256": _verify_pinned(STRICT_PIT_RECEIPT),
            },
        },
        "forbidden_interpretations": [
            "M3_CHECKPOINT_B=HUMAN_PASS",
            "strict contemporaneous rule PIT blocker ignored",
            "insufficient research converted into BUY/ADD",
            "simulated history treated as real returns",
            "M4 personalized acceptance authorized",
            "M6 production authorization granted",
        ],
        "next_action": "CONTINUE_M4_M5_OFFLINE_ENGINEERING",
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
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("M3 Checkpoint B acceptance output escapes project root")
    if output_dir.exists():
        raise ValueError(f"M3 Checkpoint B acceptance output already exists: {output_dir}")

    packet = build_packet(
        generated_at=args.generated_at,
        reviewed_at=args.reviewed_at,
    )
    receipt = build_receipt(reviewed_at=args.reviewed_at)
    output_dir.mkdir(parents=True)
    receipt_output = write_human_milestone_receipt(
        receipt,
        output_dir,
        PREVIOUS_RECEIPT,
    )
    packet_output = _write_json(output_dir / "checkpoint-b-partial-packet.json", packet)
    manifest = {
        "schema_version": "m3-checkpoint-b-human-acceptance-manifest-v1",
        "generated_at": args.generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "human_receipt_schema": HUMAN_MILESTONE_RECEIPT_SCHEMA,
        "checkpoint_b_status": "PARTIAL",
        "previous_receipt": {
            "path": str(PREVIOUS_RECEIPT.relative_to(ROOT)),
            "sha256": _verify_pinned(PREVIOUS_RECEIPT),
        },
        "outputs": {
            "human_receipt": receipt_output,
            "checkpoint_b_partial_packet": packet_output,
        },
        "inputs": {
            "checkpoint_b_packet": {
                "path": str(CHECKPOINT_B_PACKET.relative_to(ROOT)),
                "sha256": _verify_pinned(CHECKPOINT_B_PACKET),
            },
            "strict_pit_receipt": {
                "path": str(STRICT_PIT_RECEIPT.relative_to(ROOT)),
                "sha256": _verify_pinned(STRICT_PIT_RECEIPT),
            },
        },
    }
    manifest_output = _write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest_output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
