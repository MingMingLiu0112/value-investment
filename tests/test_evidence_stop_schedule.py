from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.product import run_company_research_for_symbol
from value_investment_agent.application.product.company_research import _verified_source_ids
from value_investment_agent.domain.research.evidence_stop import (
    evaluate_research_schedule,
    evidence_stops_from_payload,
    schedule_request_from_payload,
)
from value_investment_agent.infrastructure.evidence.evidence_stop_schedule import (
    claim_research_schedule_once,
)


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "config" / "research-evidence-stop-ledger-v1.json"
LEDGER = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
STOPS = evidence_stops_from_payload(LEDGER)


def _request(**overrides):
    payload = {
        "schema_version": "research-schedule-request-v1",
        "symbol": "000333",
        "source_id": "CNINFO",
        "period": "2026-06-30",
        "research_question_id": "midea_ordinary_share_denominator",
        "blocker_id": "ordinary_share_denominator_unbounded",
        "reopen_condition_met": True,
        "new_evidence_ids": ["cninfo_1230000000"],
    }
    payload.update(overrides)
    return schedule_request_from_payload(payload)


def test_same_stopped_question_is_blocked_without_new_verified_evidence():
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=_request(),
    )
    assert decision["allowed"] is False
    assert decision["status"] == "BLOCKED_UNBOUND_EVIDENCE_ID"


def test_same_stopped_question_reopens_only_with_true_condition_and_new_bound_id():
    request = _request()
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    assert decision["allowed"] is True
    assert decision["status"] == "REOPENED_WITH_NEW_EVIDENCE"
    assert decision["new_evidence_ids"] == ["cninfo_1230000000"]

    false_condition = _request(reopen_condition_met=False)
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=false_condition,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    assert decision["status"] == "BLOCKED_REOPEN_CONDITION_FALSE"


def test_new_evidence_id_must_resolve_to_hash_bound_official_package_source(tmp_path):
    source = tmp_path / "evidence" / "new-filing.pdf"
    source.parent.mkdir()
    source.write_bytes(b"official filing bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    request = _request()
    package = {
        "sources": [{
            "id": "cninfo_1230000000",
            "kind": "official_issuer_filing",
            "location": "evidence/new-filing.pdf",
            "sha256": digest,
            "issuer_identity": {"security_code": "000333"},
        }]
    }
    assert _verified_source_ids(tmp_path, package, request) == frozenset({"cninfo_1230000000"})
    package["sources"][0]["kind"] = "unverified_aggregate"
    assert _verified_source_ids(tmp_path, package, request) == frozenset()
    package["sources"][0]["kind"] = "official_issuer_filing"
    package["sources"][0]["issuer_identity"]["security_code"] = "600519"
    assert _verified_source_ids(tmp_path, package, request) == frozenset()


def test_reused_evidence_id_does_not_reopen_stop():
    request = _request(new_evidence_ids=["1225531404"])
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
        verified_evidence_ids=frozenset({"1225531404"}),
    )
    assert decision["allowed"] is False
    assert decision["status"] == "BLOCKED_NO_NEW_EVIDENCE_ID"


def test_admitted_reopen_request_is_persistently_consumed_once(tmp_path):
    request = _request()
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    first = claim_research_schedule_once(
        root=tmp_path,
        request=request,
        decision=decision,
        ledger_sha256="a" * 64,
        request_sha256="b" * 64,
    )
    second = claim_research_schedule_once(
        root=tmp_path,
        request=request,
        decision=decision,
        ledger_sha256="a" * 64,
        request_sha256="b" * 64,
    )
    assert first["created"] is True
    assert second["created"] is False
    saved = json.loads(Path(first["receipt_path"]).read_text(encoding="utf-8"))
    assert saved["status"] == "ADMITTED_ONCE"
    assert saved["action"] == "no_order"


def test_consumption_receipt_refuses_symlink_path_outside_project_root(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, root / "runtime", target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlink unavailable: {error}")
    request = _request()
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    with pytest.raises(ValueError, match="symlink directories"):
        claim_research_schedule_once(
            root=root,
            request=request,
            decision=decision,
            ledger_sha256="a" * 64,
            request_sha256="b" * 64,
        )
    assert not list(outside.iterdir())


def test_other_scoped_question_is_blocked_without_a_registered_trigger():
    request = _request(
        research_question_id="new_official_issue",
        blocker_id="new_material_event",
    )
    blocked = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
    )
    assert blocked["allowed"] is False
    assert blocked["status"] == "BLOCKED_UNREGISTERED_SCOPE"
    allowed = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    assert allowed["allowed"] is False
    assert allowed["status"] == "BLOCKED_UNREGISTERED_SCOPE"


def test_company_research_entrypoint_blocks_unscoped_stopped_case_before_package_lookup():
    result = run_company_research_for_symbol(root=ROOT, symbol="000333")
    assert result["result"]["status"] == "BLOCKED_BY_RESEARCH_SCHEDULER"
    assert result["result"]["schedule_gate"]["status"] == "BLOCKED_SCOPE_REQUIRED"
    assert result["result"]["action"] == "no_order"


def test_case_without_registered_scope_is_blocked_by_gate():
    decision = evaluate_research_schedule(
        symbol="000651", stops=STOPS, request=None,
    )
    assert decision == {
        "allowed": False,
        "status": "BLOCKED_NO_REGISTERED_SCOPE",
        "matched_stop_ids": [],
        "reason": "Research requires an explicitly registered trigger scope.",
    }


def test_unregistered_moutai_research_is_blocked_before_package_lookup():
    result = run_company_research_for_symbol(root=ROOT, symbol="600519")
    assert result["result"]["status"] == "BLOCKED_BY_RESEARCH_SCHEDULER"
    assert result["result"]["schedule_gate"]["status"] == "BLOCKED_NO_REGISTERED_SCOPE"
