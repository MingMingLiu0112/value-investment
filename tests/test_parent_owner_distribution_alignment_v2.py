"""Strict F2 alignment for the implemented owner-distribution successor."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from test_parent_remaining_year_successor import case as predecessor_case_fixture
from value_investment_agent.application.research import parent_remaining_year_successor as predecessor
from value_investment_agent.application.research import parent_owner_distribution_successor_v2 as successor
from value_investment_agent.application.research.direct_owner_cash_research_v1 import _bytes
from value_investment_agent.application.research.parent_owner_distribution_alignment_v2 import (
    INPUT_SCHEMA,
    _consumed_financial_update_closure,
    read_parent_owner_distribution_alignment,
)
from value_investment_agent.application.research.pending_candidate_alignment import (
    _financial_update_closure_status,
)

NOW = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)


def bound(root, path, payload):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = payload if isinstance(payload, bytes) else _bytes(payload)
    target.write_bytes(raw)
    return {"path": path, "sha256": sha256(raw).hexdigest()}


@pytest.fixture
def aligned_case(tmp_path, monkeypatch):
    root, old_spec, _ = predecessor_case_fixture.__wrapped__(tmp_path, monkeypatch)
    old_ref = bound(root, "runtime/TEST_ONLY-predecessor-spec.json", old_spec)
    old_receipt = predecessor.build_parent_remaining_year_successor(
        root=root, spec_binding=old_ref,
        output_dir=root / "runtime/TEST_ONLY-predecessor-output", now=NOW,
    )["receipt_binding"]
    original = bound(root, "runtime/TEST_ONLY-implemented-original.pdf", b"TEST_ONLY original")
    reconciliation = bound(root, "runtime/TEST_ONLY-basis-ledger.json", {
        "distributions": [{
            "cash_per_share": "0.90", "cash_amount": "0.90",
            "cash_payment_date": "2026-06-05",
            "evidence": [{"binding": original}],
        }],
    })
    spec = {
        "schema_version": successor.SCHEMA, "action": "no_order",
        "predecessor_binding": old_receipt,
        "distribution_evidence": {"original": original, "reconciliation": reconciliation},
        "distribution": {
            "period_year": 2026, "paid_date": "2026-06-05", "per_share_cny": "0.90",
            "eligible_shares": "10", "total_cny": "9.00",
            "scope": successor.SCOPE, "currency": "CNY", "classification": "FACT",
        },
        "computed_at": NOW.isoformat(), "research_as_of": "2026-11-18",
        "run_id": "TEST_ONLY-owner-distribution-alignment",
        "research_version": "TEST_ONLY-owner-distribution-alignment-v2",
        "reasons": "TEST_ONLY exact implemented distribution inclusion",
    }
    spec_ref = bound(root, "runtime/TEST_ONLY-owner-distribution-spec.json", spec)
    receipt = successor.build_parent_owner_distribution_successor(
        root=root, spec_binding=spec_ref,
        output_dir=root / "runtime/TEST_ONLY-owner-distribution-output", now=NOW,
    )["receipt_binding"]
    receipt_payload = json.loads((root / receipt["path"]).read_text(encoding="utf-8"))
    config = {
        "schema_version": INPUT_SCHEMA,
        "candidate_binding": receipt,
        "input_descriptor_sha256": receipt_payload["input_descriptor_sha256"],
        "quote_bundle_binding": None,
        "event_observation_bindings": [],
        "source_observation_bindings": [],
        "reconciliation_binding": None,
        "materiality_review_binding": None,
    }
    config_path = "config/pending-candidate-alignments-v1/" + receipt["sha256"] + ".json"
    bound(root, config_path, config)
    return root, receipt, spec_ref, original, reconciliation


def read(case):
    root, receipt, *_ = case
    return read_parent_owner_distribution_alignment(
        root=root, receipt_binding=receipt, now=NOW,
    )


def test_exact_distribution_inclusion_passes_without_promoting_shared_gates(aligned_case):
    result = read(aligned_case)
    inclusion = result["implemented_distribution_model_inclusion"]
    assert inclusion["status"] == "PASS"
    assert inclusion["reason_code"] == "IMPLEMENTED_DISTRIBUTION_INCLUDED_IN_MODEL"
    assert inclusion["per_share_cny"] == "0.90"
    assert inclusion["paid_date"] == "2026-06-05"
    assert inclusion["total_cny"] == "9.00"
    assert inclusion["period_cash_coverage_complete"] is False
    assert result["status"] == "BLOCKED"
    assert result["currentpricecomparison"] is False
    assert {row["id"] for row in result["checks"]} == {
        "quote", "capital_structure", "distributions", "material_events", "financial_updates",
    }
    assert any(row["status"] != "PASS" for row in result["checks"])
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


@pytest.mark.parametrize("fault", ["amount", "date", "hash", "later_year"])
def test_distribution_or_reconciliation_tampering_is_rejected(aligned_case, fault):
    root, receipt, spec_ref, original, reconciliation = aligned_case
    receipt_payload = json.loads((root / receipt["path"]).read_text(encoding="utf-8"))
    result_path = root / receipt_payload["result_binding"]["path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if fault == "later_year":
        rows = result["valuation"]["assumptions"]["scenario_calculations"]["base"]["annual_rows"]
        later = deepcopy(rows[0])
        later["year"] += 1
        later["scheduled_owner_distribution_cny"] = "1"
        rows.append(later)
        bound(root, receipt_payload["result_binding"]["path"], result)
        with pytest.raises(ValueError, match="HASH_CHANGED|COLD_REPLAY_CHANGED"):
            read(aligned_case)
        return

    ledger = json.loads((root / reconciliation["path"]).read_text(encoding="utf-8"))
    if fault == "amount":
        ledger["distributions"][0]["cash_per_share"] = "0.91"
    elif fault == "date":
        ledger["distributions"][0]["cash_payment_date"] = "2026-06-06"
    else:
        ledger["distributions"][0]["evidence"][0]["binding"] = dict(original, sha256="0" * 64)
    new_reconciliation = bound(root, "runtime/TEST_ONLY-basis-ledger-mutated.json", ledger)
    spec = json.loads((root / spec_ref["path"]).read_text(encoding="utf-8"))
    spec["distribution_evidence"]["reconciliation"] = new_reconciliation
    new_spec = bound(root, "runtime/TEST_ONLY-owner-distribution-spec-mutated.json", spec)
    new_receipt = successor.build_parent_owner_distribution_successor(
        root=root, spec_binding=new_spec,
        output_dir=root / "runtime/TEST_ONLY-owner-distribution-mutated", now=NOW,
    )["receipt_binding"]
    with pytest.raises(ValueError, match="RECONCILIATION_TERMS_MISMATCH"):
        read_parent_owner_distribution_alignment(root=root, receipt_binding=new_receipt, now=NOW)


def test_old_receipt_is_rejected(aligned_case):
    root, _, spec_ref, *_ = aligned_case
    spec = json.loads((root / spec_ref["path"]).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="EXACT_V2_RECEIPT"):
        read_parent_owner_distribution_alignment(
            root=root, receipt_binding=spec["predecessor_binding"], now=NOW,
        )


def test_source_closure_is_required(aligned_case):
    root, receipt, *_ = aligned_case
    receipt_payload = json.loads((root / receipt["path"]).read_text(encoding="utf-8"))
    result_ref = receipt_payload["result_binding"]
    result = json.loads((root / result_ref["path"]).read_text(encoding="utf-8"))
    result["source_bindings"].remove(result["distribution_evidence"]["original"])
    new_result_ref = bound(root, result_ref["path"], result)
    receipt_payload["result_binding"] = new_result_ref
    new_receipt = bound(root, receipt["path"], receipt_payload)
    with pytest.raises(ValueError, match="COLD_REPLAY_CHANGED|VERSION_INVALID"):
        read_parent_owner_distribution_alignment(root=root, receipt_binding=new_receipt, now=NOW)


def financial_closure(aligned_case):
    root, receipt, *_ = aligned_case
    receipt_payload = json.loads((root / receipt["path"]).read_text(encoding="utf-8"))
    result = successor.replay_parent_owner_distribution_successor(
        root=root, receipt_binding=receipt, now=NOW,
    )
    closure = _consumed_financial_update_closure(
        result=result, receipt=receipt_payload, root=root, now=NOW,
        candidate_binding=receipt,
    )
    return root, receipt, receipt_payload, result, closure


def test_financial_update_closure_requires_actual_predecessor_cold_recompute(aligned_case):
    _, receipt, _, result, closure = financial_closure(aligned_case)
    assert closure[0]["status"] == "EXACT_FINANCIAL_UPDATE_COLD_RECOMPUTED_IN_CANDIDATE"
    assert closure[0]["candidate_binding"] == receipt
    assert closure[0]["input_descriptor_sha256"] == result["input_descriptor_sha256"]
    assert closure[0]["action"] == "no_order"


def test_financial_update_pass_is_separate_from_materiality(aligned_case):
    _, receipt, _, result, closure = financial_closure(aligned_case)
    source = closure[0]["source_binding"]
    analysis = {
        "review_binding": {"candidate_binding": receipt},
        "input_descriptor_sha256": result["input_descriptor_sha256"],
        "consumed_financial_updates": closure,
        "source_bindings": [source],
    }
    events = [{"facts": [{
        "binding": source,
        "terms": {"financial_update": {"period_end": closure[0]["period_end"]}},
    }]}]
    status = _financial_update_closure_status(analysis, events)
    assert status["status"] == "PASS"
    assert status["reason_codes"] == []
    assert status["scope"] == "EXACT_CANDIDATE_FINANCIAL_UPDATE_CLOSURE"


def test_source_presence_without_recompute_closure_cannot_pass(aligned_case):
    _, receipt, receipt_payload, result, _ = financial_closure(aligned_case)
    source = result["source_bindings"][0]
    analysis = {
        "review_binding": {"candidate_binding": receipt},
        "input_descriptor_sha256": receipt_payload["input_descriptor_sha256"],
        "source_bindings": [source],
    }
    events = [{"facts": [{
        "binding": source,
        "terms": {"financial_update": {"period_end": "2026-09-30"}},
    }]}]
    assert _financial_update_closure_status(analysis, events) is None
    analysis["consumed_financial_updates"] = [{
        "status": "SOURCE_PRESENT_ONLY", "period_end": "2026-09-30",
        "source_binding": source, "candidate_binding": receipt,
        "input_descriptor_sha256": receipt_payload["input_descriptor_sha256"],
        "action": "no_order",
    }]
    with pytest.raises(ValueError, match="CLOSURE_INVALID"):
        _financial_update_closure_status(analysis, events)


def test_unconsumed_newer_update_requires_recomputation(aligned_case):
    _, receipt, _, result, closure = financial_closure(aligned_case)
    analysis = {
        "review_binding": {"candidate_binding": receipt},
        "input_descriptor_sha256": result["input_descriptor_sha256"],
        "consumed_financial_updates": closure,
    }
    newer = {"path": "runtime/TEST_ONLY-newer-q3.pdf", "sha256": "f" * 64}
    events = [{"facts": [{
        "binding": newer,
        "terms": {"financial_update": {"period_end": "2027-09-30"}},
    }]}]
    status = _financial_update_closure_status(analysis, events)
    assert status["status"] == "BLOCKED"
    assert status["reason_codes"] == ["FINANCIAL_UPDATE_REQUIRES_RECOMPUTATION"]


def test_total_f2_remains_blocked_and_no_order_with_financial_closure(aligned_case):
    result = read(aligned_case)
    assert result["status"] == "BLOCKED"
    assert result["currentpricecomparison"] is False
    assert result["formal_eligibility"] is False
    assert result["action"] == "no_order"


def test_reported_parent_financing_conflict_blocks_financial_update(aligned_case):
    _, receipt, _, result, closure = financial_closure(aligned_case)
    closure[0]["financing_comparison"] = {"status": "CONFLICT"}
    source = closure[0]["source_binding"]
    analysis = {
        "review_binding": {"candidate_binding": receipt},
        "input_descriptor_sha256": result["input_descriptor_sha256"],
        "consumed_financial_updates": closure,
    }
    events = [{"facts": [{"binding": source, "terms": {"financial_update": {
        "period_end": closure[0]["period_end"],
    }}}]}]
    observed = _financial_update_closure_status(analysis, events)
    assert observed["status"] == "BLOCKED"
    assert observed["reason_codes"] == ["REPORTED_PARENT_FINANCING_EXCEEDS_FULL_YEAR_POLICY"]
