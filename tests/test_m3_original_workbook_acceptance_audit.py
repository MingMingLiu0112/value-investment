from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from value_investment_agent.m1_sample_preregistration import (
    DEFAULT_PREREGISTRATION_PATH,
)
from value_investment_agent.m3_decision_application import (
    build_nonpersonal_decision_card_collection,
)
from value_investment_agent.m3_decision_review_sheet import (
    TARGET_SHEET,
    write_m3_decision_review_addon,
)
from value_investment_agent.m3_original_workbook_acceptance_audit import (
    M3OriginalWorkbookAcceptanceSpec,
    PENDING_HUMAN_REVIEW,
    audit,
    write_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage_frontend_package",
    ROOT / "scripts" / "stage_frontend_package.py",
)
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)

GENERATED_AT = datetime(2026, 9, 23, 11, 42, 28, tzinfo=timezone.utc)
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
            "evidence_refs": [],
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


def _collection():
    return build_nonpersonal_decision_card_collection(
        [_run("000651"), _run("600741"), _run("600887")],
        generated_at=GENERATED_AT,
        source_run_id="fixture-m1-run",
    )


def _spec(tmp_path: Path, *, tamper: bool = False) -> M3OriginalWorkbookAcceptanceSpec:
    source = tmp_path / "source.xlsx"
    workbook = Workbook()
    retained = workbook.active
    retained.title = "保留页"
    retained["A1"] = "用户手工内容"
    review = workbook.create_sheet(TARGET_SHEET)
    review["A1"] = "旧占位"
    workbook.save(source)

    input_path = tmp_path / "runs.json"
    input_path.write_text(
        json.dumps([_run("000651"), _run("600741"), _run("600887")]),
        encoding="utf-8",
    )
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_bytes(DEFAULT_PREREGISTRATION_PATH.read_bytes())

    addon = tmp_path / "addon.xlsx"
    addon_result = write_m3_decision_review_addon(
        _collection(),
        output=addon,
        root=tmp_path,
        security_names=NAMES,
    )
    candidate = tmp_path / "candidate.xlsx"
    graft = STAGE.replace_sheet(
        source,
        addon,
        candidate,
        _digest(source),
        TARGET_SHEET,
    )
    candidate_sha256 = _digest(candidate)
    if tamper:
        candidate.write_bytes(candidate.read_bytes() + b"tamper")

    manifest_path = tmp_path / "candidate.manifest.json"
    manifest = {
        "schema_version": "m3-original-workbook-candidate-v1",
        "generated_at": GENERATED_AT.isoformat(),
        "action": "no_order",
        "source_sha256": _digest(source),
        "candidate_sha256": candidate_sha256,
        "input": {
            "path": str(input_path),
            "sha256": _digest(input_path),
        },
        "preregistration": {
            "path": "preregistration.json",
            "sha256": _digest(preregistration),
        },
        "target_sheet": TARGET_SHEET,
        "original_sheets_preserved": graft["original_sheets_preserved"],
        "derived_sheets_replaced": graft["derived_sheets_replaced"],
        "original_parts_unchanged": graft["original_parts_unchanged"],
        "card_count": addon_result["card_count"],
        "positive_review_count": addon_result["positive_review_count"],
        "status": "candidate_verified_not_published",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    wps_dir = tmp_path / "WPSDrive"
    wps_dir.mkdir()
    wps_candidate = wps_dir / "candidate.xlsx"
    wps_candidate.write_bytes(candidate.read_bytes() if not tamper else candidate.read_bytes())
    canonical_wps = wps_dir / "canonical.xlsx"
    canonical_wps.write_bytes(source.read_bytes())

    wps_receipt = tmp_path / "wps-receipt.json"
    wps_receipt.write_text(
        json.dumps(
            {
                "status": "passed",
                "mode": "pre_publication",
                "sha256": candidate_sha256,
                "sheets": graft["original_sheets_preserved"]
                + graft["derived_sheets_replaced"],
                "target_sheet": TARGET_SHEET,
                "original_parts_unchanged": graft["original_parts_unchanged"],
                "action": "no_order",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return M3OriginalWorkbookAcceptanceSpec(
        source_path=source,
        source_sha256=_digest(source),
        candidate_path=candidate,
        candidate_sha256=candidate_sha256,
        manifest_path=manifest_path,
        manifest_sha256=_digest(manifest_path),
        input_path=input_path,
        input_sha256=_digest(input_path),
        preregistration_path=preregistration,
        preregistration_sha256=_digest(preregistration),
        generated_at=GENERATED_AT,
        wps_candidate_path=wps_candidate,
        wps_receipt_path=wps_receipt,
        wps_receipt_sha256=_digest(wps_receipt),
        canonical_wps_path=canonical_wps,
        canonical_sha256=_digest(source),
        expected_sheet_count=graft["original_sheets_preserved"]
        + graft["derived_sheets_replaced"],
        expected_original_sheets=graft["original_sheets_preserved"],
        expected_unchanged_parts=graft["original_parts_unchanged"],
    )


def test_audit_verifies_candidate_without_publishing(tmp_path: Path):
    receipt = audit(
        tmp_path,
        _spec(tmp_path),
        ci_evidence={"status": "success"},
        test_evidence={"passed": True, "passed_count": 7, "skipped_count": 0},
    )

    assert receipt["status"] == PENDING_HUMAN_REVIEW
    assert all(
        receipt["criteria"][key]["status"] == "DONE"
        for key in (
            "owc1_identity_and_manifest",
            "owc2_nonpersonal_negative_card_replay",
            "owc3_original_workbook_structure",
            "owc4_decision_sheet_fail_closed",
            "owc5_wps_and_canonical_boundary",
            "owc6_offline_regression_and_ci",
        )
    )
    assert (
        receipt["criteria"]["owc7_human_checkpoint_review"]["status"]
        == PENDING_HUMAN_REVIEW
    )
    assert receipt["blockers"] == []
    assert receipt["action"] == "no_order"


def test_audit_fails_closed_when_candidate_changes(tmp_path: Path):
    with pytest.raises(ValueError, match="M3 original-workbook candidate"):
        audit(
            tmp_path,
            _spec(tmp_path, tamper=True),
            ci_evidence={"status": "success"},
            test_evidence={"passed": True, "passed_count": 7, "skipped_count": 0},
        )


def test_receipt_writer_creates_versioned_pointer(tmp_path: Path):
    receipt = audit(
        tmp_path,
        _spec(tmp_path),
        ci_evidence={"status": "success"},
        test_evidence={"passed": True, "passed_count": 7, "skipped_count": 0},
    )
    output = write_receipt(receipt, root=tmp_path)

    receipt_path = tmp_path / output["receipt_path"]
    pointer_path = tmp_path / output["pointer_path"]
    assert receipt_path.is_file()
    assert pointer_path.is_file()
    assert _digest(receipt_path) == output["receipt_sha256"]
    assert json.loads(pointer_path.read_text(encoding="utf-8"))["sha256"] == output["receipt_sha256"]
