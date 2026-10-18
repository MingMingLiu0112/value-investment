"""W7 freezes structure observations without promoting them to a signal."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest

from value_investment_agent.application.hotspot.validation_evidence import (
    _recomputed_digest,
    _incomplete_live_attempt,
    build_hotspot_structure_validation,
    write_hotspot_structure_validation,
)


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "runtime/hotspot-daily-selection/561a1e66bf424d4e87426fbf1f080106/report.json"
SELECTION_SHA256 = "c2ef47a982ea85f04ed4d5e6324f9beda00e0f80f55cd4b19590d1c96d53f4f1"
OTHER_SELECTION = ROOT / "runtime/hotspot-daily-selection/a781a7eb24024c45b3f9285f49d6f3c1/report.json"
# Frozen replay must not depend on the mutable daily publication pointer.
POINTER = ROOT / "config/archive/price-conditions-20261017-e65444f2.json"
NEGATIVE_CASES = (
    ROOT / "runtime/hotspot-current-price-cases/601318-2026-10-15-ca32740c2d9b45ebb82eb4ff594fa651/case.json",
    ROOT / "runtime/hotspot-current-price-cases/300059-2026-10-15-8e5a81bd67bd4d3bafd6ecd4d302b664/case.json",
    ROOT / "runtime/hotspot-current-price-cases/600030-2026-10-15-5f1bfecfa6fd4ee4bcc178791fcb0af3/case.json",
)
INCOMPLETE = ROOT / "runtime/hotspot-daily-selection/d808f5784a3f40a2ae77542ae5727e97"
EXPECTED_POOL = (
    "600150",
    "000338",
    "600176",
    "000560",
    "600667",
    "601857",
    "002008",
    "600019",
    "600127",
    "000333",
)


@pytest.fixture(scope="module")
def real_report() -> dict:
    assert sha256(POINTER.read_bytes()).hexdigest() == "e65444f2b42130161d02fb5397c15f09061cc0250f77888966f0b48026eb8a8d"
    return build_hotspot_structure_validation(
        root=ROOT,
        selection_report_path=SELECTION,
        selection_report_sha256=SELECTION_SHA256,
        current_price_conditions_path=POINTER,
        historical_case_paths=NEGATIVE_CASES,
        incomplete_live_directory=INCOMPLETE,
        incomplete_live_reason="TENCENT_ACQUISITION_HUNG_AND_WAS_INTERRUPTED",
        evaluated_at=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc),
    )


def test_real_frozen_replay_keeps_unassessed_members_and_negative_cases(real_report):
    assert tuple(item["symbol"] for item in real_report["candidate_pool"]) == EXPECTED_POOL
    assert real_report["selection_trade_date"] == "2026-10-16"
    assert real_report["pool_expiry_session"] == "2026-10-19"
    assert real_report["summary"] == {
        "pool_count": 10,
        "pool_industry_count": 10,
        "pool_assessed_count": 1,
        "pool_unassessed_count": 9,
        "case_count": 8,
        "conflict_or_rejected_count": 7,
        "structure_qualified_observation_count": 0,
    }
    assessed = [item for item in real_report["pool_structure_status"]
                if item["assessment_status"] == "BOUND_ASSESSED"]
    assert [(item["symbol"], item["structure_tier"]) for item in assessed] == [
        ("600150", "ACTIVE_ONLY")
    ]
    missing = [item for item in real_report["pool_structure_status"]
               if item["assessment_status"] == "UNAVAILABLE_NO_BOUND_MULTIPERIOD_CASE"]
    assert len(missing) == 9
    assert all("case_path" not in item and item["structure_tier"] == "UNASSESSED" for item in missing)
    historical = [item for item in real_report["case_structure_evidence"]
                  if item["role"] == "HISTORICAL_NEGATIVE_CASE"]
    assert {(item["symbol"], item["structure_tier"]) for item in historical} == {
        ("601318", "CONFLICT_OR_REJECTED"),
        ("300059", "CONFLICT_OR_REJECTED"),
        ("600030", "CONFLICT_OR_REJECTED"),
    }
    assert real_report["strategy_validation"] == "NOT_PROVEN"
    assert real_report["source_report_rule_version"] == "hotspot-dated-sector-liquidity-ranking-v2"
    assert real_report["replayed_rule_version"] == "hotspot-dated-sector-liquidity-ranking-v3"
    assert real_report["rule_extension_status"] == "RETROSPECTIVE_RESEARCH_EXTENSION"
    assert real_report["future_rule_version_used"] is True
    assert real_report["rule_pit_status"] == "NOT_PROVEN"
    assert real_report["classification_pit"] == "NOT_PROVEN"
    assert real_report["prospective_oos_admitted"] is False
    assert real_report["formal_eligibility"] is False
    assert real_report["portfolio_eligibility"] is None
    assert real_report["action"] == "no_order"
    assert real_report["trade_intent"] == "NO_TRADE"


def test_incomplete_live_attempt_is_hashed_but_never_admitted(real_report):
    attempt = real_report["incomplete_live_attempt"]
    assert attempt["status"] == "INCOMPLETE_NO_REPORT"
    assert attempt["used_as_evidence"] is False
    assert attempt["file_count"] == len(attempt["files"]) == 13
    assert attempt["total_bytes"] == sum(item["size_bytes"] for item in attempt["files"])
    assert re.fullmatch(r"[0-9a-f]{64}", attempt["content_sha256"])
    for item in attempt["files"]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        assert item["size_bytes"] == (ROOT / item["path"]).stat().st_size
        assert sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]


def test_writer_is_append_only_and_manifest_hashes_outputs(real_report, tmp_path):
    directory = tmp_path / "artifacts/current/hotspot-structure-validation-test"
    manifest = write_hotspot_structure_validation(real_report, root=tmp_path, output_dir=directory)
    assert manifest["strategy_validation"] == "NOT_PROVEN"
    assert manifest["rule_extension_status"] == "RETROSPECTIVE_RESEARCH_EXTENSION"
    assert manifest["future_rule_version_used"] is True
    assert manifest["rule_pit_status"] == "NOT_PROVEN"
    assert manifest["formal_eligibility"] is False
    assert manifest["action"] == "no_order"
    assert manifest["retained_non_evidence"]["used_as_evidence"] is False
    for name, binding in manifest["outputs"].items():
        path = tmp_path / binding["path"]
        assert sha256(path.read_bytes()).hexdigest() == binding["sha256"]
        assert json.loads((directory / "validation.json").read_text(encoding="utf-8"))[
            "evidence_sha256"
        ] == manifest["evidence_sha256"]
    report_text = (directory / "report.md").read_text(encoding="utf-8")
    assert "Unassessed pool members: 9" in report_text
    assert "Rule extension: RETROSPECTIVE_RESEARCH_EXTENSION" in report_text
    assert "Strategy validation: NOT_PROVEN" in report_text
    with pytest.raises(FileExistsError):
        write_hotspot_structure_validation(real_report, root=tmp_path, output_dir=directory)


def test_hash_mismatch_and_pre_availability_evaluation_fail_closed():
    with pytest.raises(ValueError, match="hash mismatch"):
        build_hotspot_structure_validation(
            root=ROOT,
            selection_report_path=SELECTION,
            selection_report_sha256="0" * 64,
            current_price_conditions_path=POINTER,
            historical_case_paths=NEGATIVE_CASES,
            evaluated_at=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc),
        )


def test_pointer_must_be_bound_to_the_exact_selection_report():
    digest = sha256(OTHER_SELECTION.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="different selection report"):
        build_hotspot_structure_validation(
            root=ROOT,
            selection_report_path=OTHER_SELECTION,
            selection_report_sha256=digest,
            current_price_conditions_path=POINTER,
            historical_case_paths=NEGATIVE_CASES,
            evaluated_at=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc),
        )


def test_historical_negative_case_cannot_be_an_active_observation(real_report):
    active_case = next(
        Path(ROOT / item["case_path"])
        for item in real_report["case_structure_evidence"]
        if item["role"] == "CURRENT_PRICE_CONDITION" and item["symbol"] == "600150"
    )
    with pytest.raises(ValueError, match="not a conflict or rejected"):
        build_hotspot_structure_validation(
            root=ROOT,
            selection_report_path=SELECTION,
            selection_report_sha256=SELECTION_SHA256,
            current_price_conditions_path=POINTER,
            historical_case_paths=(active_case,),
            evaluated_at=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc),
        )


def test_writer_rejects_semantic_upgrade_and_leaves_no_partial_output(real_report, tmp_path):
    upgraded = deepcopy(real_report)
    upgraded["strategy_validation"] = "PROVEN"
    upgraded["formal_eligibility"] = True
    upgraded["trade_intent"] = "OPEN"
    upgraded["evidence_sha256"] = _recomputed_digest(upgraded, "evidence_sha256")
    directory = tmp_path / "artifacts/current/rejected-upgrade"
    with pytest.raises(ValueError, match="trade intent"):
        write_hotspot_structure_validation(upgraded, root=tmp_path, output_dir=directory)
    assert not directory.exists()
    with pytest.raises(ValueError, match="precedes"):
        build_hotspot_structure_validation(
            root=ROOT,
            selection_report_path=SELECTION,
            selection_report_sha256=SELECTION_SHA256,
            current_price_conditions_path=POINTER,
            historical_case_paths=NEGATIVE_CASES,
            evaluated_at=datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rule_extension_status", "SOURCE_REPORTED_RULE_REPLAY", "rule-extension"),
        ("future_rule_version_used", False, "future-rule"),
        ("classification_pit", "PROVEN", "classification PIT"),
        ("replayed_rule_version", "hotspot-dated-sector-liquidity-ranking-v2", "rule versions"),
    ],
)
def test_writer_rejects_rule_semantics_tampering(
    real_report, tmp_path, field, value, message
):
    tampered = deepcopy(real_report)
    tampered[field] = value
    tampered["evidence_sha256"] = _recomputed_digest(tampered, "evidence_sha256")
    with pytest.raises(ValueError, match=message):
        write_hotspot_structure_validation(
            tampered,
            root=tmp_path,
            output_dir=tmp_path / f"artifacts/current/rejected-{field}",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("nested_case_upgrade", "nested validation case"),
        ("pool_close_mismatch", "pool close"),
        ("incomplete_used_as_evidence", "incomplete live attempt"),
        ("unassessed_case_binding", "unassessed pool member"),
    ],
)
def test_writer_rejects_nested_evidence_tampering(real_report, tmp_path, mutation, message):
    tampered = deepcopy(real_report)
    if mutation == "nested_case_upgrade":
        tampered["case_structure_evidence"][0]["action"] = "OPEN"
        tampered["case_structure_evidence"][0]["formal_eligibility"] = True
    elif mutation == "pool_close_mismatch":
        bound = next(item for item in tampered["pool_structure_status"]
                     if item["assessment_status"] == "BOUND_ASSESSED")
        candidate = next(item for item in tampered["candidate_pool"]
                         if item["symbol"] == bound["symbol"])
        candidate["close"] = "99.99"
    elif mutation == "incomplete_used_as_evidence":
        tampered["incomplete_live_attempt"]["used_as_evidence"] = True
    else:
        unassessed = next(item for item in tampered["pool_structure_status"]
                          if item["assessment_status"] != "BOUND_ASSESSED")
        unassessed["case_path"] = "runtime/unbound.json"
    tampered["evidence_sha256"] = _recomputed_digest(tampered, "evidence_sha256")
    with pytest.raises(ValueError, match=message):
        write_hotspot_structure_validation(
            tampered,
            root=tmp_path,
            output_dir=tmp_path / f"artifacts/current/rejected-{mutation}",
        )


def test_limitations_follow_pool_and_unassessed_counts():
    report = build_hotspot_structure_validation(
        root=ROOT,
        selection_report_path=SELECTION,
        selection_report_sha256=SELECTION_SHA256,
        current_price_conditions_path=POINTER,
        historical_case_paths=(NEGATIVE_CASES[0],),
        evaluated_at=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc),
        limit=5,
        pool_limit=5,
    )
    assert report["summary"]["pool_count"] == 5
    assert report["summary"]["pool_unassessed_count"] == 4
    assert (
        "The 5-symbol activity pool is not an entry list; "
        "4 symbols lack bound multi-period structure for the selection date."
        in report["limitations"]
    )


def test_incomplete_attempt_rejects_missing_directory_or_admitted_report(tmp_path):
    missing = tmp_path / "runtime/hotspot-daily-selection/missing"
    with pytest.raises(ValueError, match="does not exist"):
        _incomplete_live_attempt(tmp_path, missing, "failure")

    admitted = tmp_path / "runtime/hotspot-daily-selection/admitted"
    admitted.mkdir(parents=True)
    (admitted / "report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="already contains a report"):
        _incomplete_live_attempt(tmp_path, admitted, "failure")
