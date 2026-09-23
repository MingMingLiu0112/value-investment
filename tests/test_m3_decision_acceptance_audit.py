from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m1_sample_preregistration import (
    DEFAULT_PREREGISTRATION_PATH,
)
from value_investment_agent.m3_decision_acceptance_audit import (
    PENDING_HUMAN_REVIEW,
    M3DecisionAcceptanceSpec,
    audit,
    write_receipt,
)
from value_investment_agent.m3_decision_application import (
    build_nonpersonal_decision_card_collection,
)
from value_investment_agent.m3_decision_card_workbook import (
    write_decision_card_workbook,
)


GENERATED_AT = datetime(2026, 9, 23, 11, 42, 28, 970300, tzinfo=timezone.utc)
NAMES = {
    "000651": "格力电器",
    "600741": "华域汽车",
    "600887": "伊利股份",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(symbol: str) -> dict:
    return {
        "run_id": f"{symbol}-m1-run",
        "symbol": symbol,
        "status": "COMPLETED_WITH_BLOCKERS",
        "action": "no_order",
        "pre_decision_eligibility": {
            "schema_version": "post-m1-predecision-eligibility-v1",
            "symbol": symbol,
            "decision_as_of": "2026-09-22",
            "status": "NOT_ELIGIBLE",
            "approval_status": "REJECTED_NEEDS_REWORK",
            "model_validity_status": "STALE",
            "price_bridge_status": "STALE_MODEL",
            "event_review_watermark": "2026-09-22",
            "blockers": ["research_gate_not_ready"],
            "evidence_refs": [
                {
                    "id": f"{symbol}-filing",
                    "kind": "official_issuer_filing",
                    "source_url": f"https://example.com/{symbol}.pdf",
                    "sha256": "a" * 64,
                }
            ],
            "action": "no_order",
        },
        "gate": {"conclusion": "估值未就绪", "blockers": ["research_gate_not_ready"]},
        "human_approval": {
            "symbol": symbol,
            "status": "REJECTED_NEEDS_REWORK",
            "blockers": ["research_gate_not_ready"],
            "action": "no_order",
        },
        "valuation": {
            "symbol": symbol,
            "model_type": "fixture",
            "valuation_date": "2026-09-22",
            "confidence": "低",
            "status": "conditional_research_only",
        },
        "model_validity": {"symbol": symbol, "status": "STALE", "blockers": []},
        "price_bridge": {
            "symbol": symbol,
            "bridge_status": "STALE_MODEL",
            "blockers": [],
        },
        "price_attractiveness": {
            "symbol": symbol,
            "status": "NOT_ASSESSABLE",
            "blockers": [],
        },
        "current_research_status": {
            "symbol": symbol,
            "research_conclusion": "估值未就绪",
            "blockers": [],
        },
    }


def _collection() -> "object":
    return build_nonpersonal_decision_card_collection(
        [_run("000651"), _run("600741"), _run("600887")],
        generated_at=GENERATED_AT,
        source_run_id="fixture-m1-run",
    )


def _spec(tmp_path: Path, *, tamper: bool = False) -> M3DecisionAcceptanceSpec:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_bytes(DEFAULT_PREREGISTRATION_PATH.read_bytes())
    runs = tmp_path / "runs.json"
    runs.write_text(
        json.dumps([_run("000651"), _run("600741"), _run("600887")]),
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate.xlsx"
    result = write_decision_card_workbook(
        _collection(),
        output=candidate,
        root=tmp_path,
        security_names=NAMES,
    )
    if tamper:
        candidate.write_bytes(candidate.read_bytes() + b"tamper")
    candidate_sha256 = result["workbook_sha256"] if tamper else _digest(candidate)
    manifest_path = tmp_path / "candidate.manifest.json"
    manifest = {
        **result,
        "schema_version": "m3-decision-card-read-model-v1",
        "source_run_id": "fixture-m1-run",
        "generated_at": GENERATED_AT.isoformat(),
        "input": {"path": str(runs), "sha256": _digest(runs)},
        "input_failure_count": 0,
        "input_failures": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    wps = tmp_path / "wps-candidate.xlsx"
    wps.write_bytes(candidate.read_bytes())
    receipt_path = tmp_path / "wps-receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "sha256": result["workbook_sha256"],
                "sheets": 4,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"canonical")
    return M3DecisionAcceptanceSpec(
        input_path=runs,
        input_sha256=_digest(runs),
        preregistration_path=preregistration,
        preregistration_sha256=_digest(preregistration),
        candidate_path=candidate,
        candidate_sha256=candidate_sha256,
        manifest_path=manifest_path,
        manifest_sha256=_digest(manifest_path),
        generated_at=GENERATED_AT,
        wps_candidate_path=wps,
        wps_receipt_path=receipt_path,
        wps_receipt_sha256=_digest(receipt_path),
        canonical_workbook_path=canonical,
        canonical_sha256=_digest(canonical),
    )


def test_audit_completes_machine_gate_and_preserves_human_review(tmp_path):
    receipt = audit(
        tmp_path,
        _spec(tmp_path),
        ci_evidence={"status": "success"},
        test_evidence={"passed": True, "passed_count": 58, "skipped_count": 0},
    )

    assert receipt["status"] == PENDING_HUMAN_REVIEW
    assert receipt["criteria"]["m3c1_frozen_input_and_identity"]["status"] == "DONE"
    assert receipt["criteria"]["m3c2_nonpersonal_negative_card_semantics"]["status"] == "DONE"
    assert receipt["criteria"]["m3c3_source_hash_and_deterministic_replay"]["status"] == "DONE"
    assert receipt["criteria"]["m3c4_candidate_workbook_integrity"]["status"] == "DONE"
    assert receipt["criteria"]["m3c5_wps_and_canonical_workbook_boundary"]["status"] == "DONE"
    assert receipt["criteria"]["m3c6_offline_regression_and_ci"]["status"] == "DONE"
    assert (
        receipt["criteria"]["m3c7_human_entry_journal_and_comprehension"]["status"]
        == PENDING_HUMAN_REVIEW
    )
    assert receipt["blockers"] == []
    assert any("复述理由" in item for item in receipt["summary"]["human_review_items"])
    assert receipt["action"] == "no_order"


def test_audit_fails_closed_when_candidate_hash_changes(tmp_path):
    with pytest.raises(ValueError, match="M3 candidate workbook"):
        audit(
            tmp_path,
            _spec(tmp_path, tamper=True),
            ci_evidence={"status": "success"},
            test_evidence={"passed": True, "passed_count": 58},
        )


def test_write_receipt_creates_pointer_with_hash(tmp_path):
    receipt = audit(
        tmp_path,
        _spec(tmp_path),
        ci_evidence={"status": "success"},
        test_evidence={"passed": True, "passed_count": 58},
    )
    output = write_receipt(receipt, root=tmp_path)

    receipt_path = tmp_path / output["receipt_path"]
    pointer_path = tmp_path / output["pointer_path"]
    assert receipt_path.is_file()
    assert pointer_path.is_file()
    assert _digest(receipt_path) == output["receipt_sha256"]
    assert json.loads(pointer_path.read_text(encoding="utf-8"))["sha256"] == output["receipt_sha256"]
