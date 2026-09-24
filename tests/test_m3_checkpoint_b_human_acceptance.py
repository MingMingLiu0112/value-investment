from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts.build_m3_checkpoint_b_human_acceptance import (
    ACCEPTANCE_SCHEMA,
    CHECKPOINT_B_PACKET,
    DECISIONS,
    DEFAULT_GENERATED_AT,
    PREVIOUS_RECEIPT,
    STRICT_PIT_RECEIPT,
    SUPPLEMENTAL_DECISIONS,
    build_packet,
    build_receipt,
)
from value_investment_agent.human_milestone_review import (
    HumanMilestoneReviewReceipt,
    load_human_milestone_receipt,
)


ROOT = Path(__file__).resolve().parents[1]


def _require_real_artifacts() -> None:
    if any(
        not path.exists()
        for path in (CHECKPOINT_B_PACKET, PREVIOUS_RECEIPT, STRICT_PIT_RECEIPT)
    ):
        pytest.skip("M3 Checkpoint B real artifacts are not present in clean CI")


def test_partial_receipt_constants_preserve_the_review_boundary():
    assert DECISIONS["M3_CHECKPOINT_B"] == "PARTIAL"
    assert DECISIONS["M4_PRIVATE_INPUT"] == "PENDING_USER_PRIVATE_INPUT"
    assert DECISIONS["M6_AUTHORIZATION"] == "NOT_YET"
    assert SUPPLEMENTAL_DECISIONS == {
        "M3_NEGATIVE_CARD_HUMAN_REVIEW": "PASS",
        "M3_HUMAN_UNDERSTANDABILITY": "PASS",
        "M3_NO_FALSE_BUY_ADD": "PASS",
        "M3_BLOCKER": "STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN",
        "M4_PERSONALIZED_ACCEPTANCE": "PENDING_USER_PRIVATE_INPUT",
        "M6_PRODUCTION_AUTHORIZATION": "NOT_YET",
    }
    assert DECISIONS["M3_CHECKPOINT_B"] != "HUMAN_PASS"
    assert "HUMAN_PASS" not in {
        DECISIONS["M3_NEGATIVE_CARDS"],
        DECISIONS["M3_CHECKPOINT_B"],
    }


def test_real_checkpoint_b_packet_records_partial_not_pass():
    _require_real_artifacts()
    packet = build_packet(
        generated_at=DEFAULT_GENERATED_AT,
        reviewed_at=date(2026, 9, 24),
    )

    assert packet["schema_version"] == ACCEPTANCE_SCHEMA
    assert packet["checkpoint_b_status"] == "PARTIAL"
    assert packet["human_review_subchecks"] == {
        "M3_NEGATIVE_CARD_HUMAN_REVIEW": "PASS",
        "M3_HUMAN_UNDERSTANDABILITY": "PASS",
        "M3_NO_FALSE_BUY_ADD": "PASS",
    }
    assert packet["blocker"]["code"] == "STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN"
    assert packet["blocker"]["status"] == "NOT_PROVEN"
    assert packet["m4"]["personalized_acceptance"] == "PENDING_USER_PRIVATE_INPUT"
    assert packet["m6"]["production_authorization"] == "NOT_YET"
    assert packet["human_receipt"]["sequence"] == 3
    assert packet["human_receipt"]["decisions"]["M3_CHECKPOINT_B"] == "PARTIAL"
    assert packet["previous_receipt"]["sha256"] == (
        "9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20"
    )
    assert packet["action"] == "no_order"


def test_real_checkpoint_b_receipt_is_append_only_and_loadable():
    _require_real_artifacts()
    receipt = build_receipt(reviewed_at=date(2026, 9, 24))
    payload = receipt.as_policy()

    assert isinstance(receipt, HumanMilestoneReviewReceipt)
    assert payload["sequence"] == 3
    assert payload["supplemental_decisions"] == SUPPLEMENTAL_DECISIONS
    assert payload["previous_receipt_sha256"] == (
        "9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20"
    )
    assert payload["decisions"]["M3_CHECKPOINT_B"] == "PARTIAL"
    assert payload["decisions"]["M3_CHECKPOINT_B"] != "HUMAN_PASS"

    loaded = load_human_milestone_receipt(PREVIOUS_RECEIPT)
    assert loaded.sequence == 2
    assert loaded.as_policy() == json.loads(PREVIOUS_RECEIPT.read_text(encoding="utf-8"))


def test_partial_acceptance_never_contains_order_or_position_fields():
    _require_real_artifacts()
    packet = build_packet(
        generated_at=datetime(
            2026,
            9,
            24,
            22,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        reviewed_at=date(2026, 9, 24),
    )
    text = json.dumps(packet, ensure_ascii=False)
    assert "target_weight" not in text
    assert "position_size" not in text
    assert "order_quantity" not in text
    assert packet["action"] == "no_order"
