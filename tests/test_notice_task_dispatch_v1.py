"""The notice supplement must coexist with immutable legacy D2 tasks."""
import json
import hashlib
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research.agent_review import notice_task_dispatch_v1 as mod
from value_investment_agent.application.research.agent_review import operating_horizon_sources_v2 as sources
from test_operating_horizon_sources_v1 import source_env, NOW
from test_operating_horizon_draft_v1 import context


def test_conditioned_cash_research_explains_unknowns_without_rewriting_failure():
    row = {"status": "FAILED", "persisted_status": "FAILED",
           "error_code": "HORIZON_STRUCTURED_RESPONSE_OR_SOURCE_REJECTED",
           "research_result": {"years": {"2027": {"shareholder_cash_paths": {
               "base": {"terms": {
                   name: {"classification": "FORECAST_ASSUMPTION" if name == "target_payout_ratio"
                          else "UNKNOWN", "evidence_ids": []}
                   for name in mod._CASH_POLICY_TERMS}}}}}}}
    projected = mod._conditioned_research_view(row)
    assert projected["status"] == projected["persisted_status"] == "FAILED"
    assert projected["error_code"] == row["error_code"]
    assert projected["cash_policy_completeness"]["status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert len(projected["cash_policy_completeness"]["missing_terms"]) == 5
    assert projected["cash_policy_completeness"]["task_accepted"] is False
    assert projected["cash_policy_completeness"]["action"] == "no_order"
    assert "cash_policy_completeness" not in row


def test_rejected_sealed_response_reports_only_fixed_missing_terms():
    paths = {scenario: {name: {"classification": "FORECAST_ASSUMPTION",
                              "value": "0.75", "rationale": "untrusted model text"}
                        for name in mod._CASH_POLICY_TERMS}
             for scenario in ("bear", "base", "bull")}
    paths["base"]["accessible_profit_ratio"] = {
        "classification": "UNKNOWN", "value": None,
        "rationale": "untrusted model rationale"}
    del paths["bull"]["commitment_cash_cny"]
    packet = {"response": {"text": json.dumps({"years": {"2027": {
        "shareholder_cash_paths": paths}}})}}

    class SealedService:
        def _load(self, task_id):
            assert task_id == "rt-failed"
            return {}, {"response_binding": {"path": "sealed.json", "sha256": "a" * 64}}, {}

        def _bound(self, binding):
            assert binding["sha256"] == "a" * 64
            return packet

    row = {"status": "FAILED", "error_code": "HORIZON_EXACT_FIELDS_REQUIRED"}
    diagnostic = mod._sealed_failure_diagnostic(SealedService(), "rt-failed", row)
    assert diagnostic["e2_usable"] is False
    assert diagnostic["action"] == "no_order"
    assert diagnostic["missing_terms"] == [
        {"year": "2027", "scenario": "base", "term": "accessible_profit_ratio",
         "reason": "NOT_QUANTIFIED"},
        {"year": "2027", "scenario": "bull", "term": "commitment_cash_cny",
         "reason": "ABSENT"},
    ]
    assert "untrusted model" not in str(diagnostic)
    assert mod._sealed_failure_diagnostic(SealedService(), "rt-failed",
        {"status": "SUCCEEDED", "error_code": "HORIZON_EXACT_FIELDS_REQUIRED"}) is None
    broken = SealedService()
    broken._bound = lambda binding: (_ for _ in ()).throw(ValueError("HASH_MISMATCH"))
    assert mod._sealed_failure_diagnostic(broken, "rt-failed", row) is None


@pytest.mark.parametrize("status, wrong_denominator", [
    ("FAILED", False), ("SUCCEEDED", True),
])
def test_complete_cash_terms_cannot_upgrade_failed_or_economically_rejected_task(
        status, wrong_denominator):
    rationale = ("75% of parent company net profit" if wrong_denominator
                 else "conditional payout against consolidated attributable profit")
    row = {"status": status, "persisted_status": status,
           "research_result": {"years": {"2027": {"shareholder_cash_paths": {
               "base": {"terms": {name: {
                   "classification": "FORECAST_ASSUMPTION",
                   "evidence_ids": (["cninfo:1224808850:conditional-return-plan"]
                                    if name == "target_payout_ratio" else []),
                   "rationale": rationale,
               } for name in mod._CASH_POLICY_TERMS}}}}}}}
    projected = mod._conditioned_research_view(row)
    assert projected["cash_policy_completeness"]["status"] == "NO_VALIDATED_RESULT"
    assert projected["cash_policy_completeness"]["missing_terms"] == []
    assert projected["cash_policy_completeness"]["task_accepted"] is False
    assert projected["status"] == status
    assert projected["cash_policy_completeness"]["action"] == "no_order"


def test_dispatch_reads_each_task_with_its_original_source_version(tmp_path, monkeypatch):
    base = tmp_path / "tasks"
    base.mkdir()
    seen = []

    class FakeTask:
        def __init__(self, root, source_loader=None):
            self.base = base
            self.version = ("v4" if source_loader is mod.prior_stress_sources.build_operating_horizon_source_context
                            else "v3" if source_loader is mod.implementation_sources.build_operating_horizon_source_context
                            else "v2" if source_loader else "v1")

        def _directory(self, task_id):
            if task_id not in {"rt-old", "rt-new", "rt-implemented", "rt-prior-stress"}:
                raise ValueError("INVALID_TASK_ID")
            return base / task_id

        def read(self, task_id):
            seen.append((self.version, task_id))
            return {"task_id": task_id, "symbol": "600519", "updated_at": task_id}

    monkeypatch.setattr(mod, "AnnualTask", FakeTask)
    service = mod.NoticeAwareTaskService(tmp_path, kind="annual")
    for task_id, version in (("rt-old", "v1"), ("rt-new", "v2"),
                             ("rt-implemented", "v3"), ("rt-prior-stress", "v4")):
        directory = base / task_id
        directory.mkdir()
        (directory / "input.json").write_text(json.dumps({"symbol": "600519", "source_binding": {
            "path": f"runtime/operating-horizon-sources-{version}/source.json"}}), encoding="utf-8")
        assert service.read(task_id)["task_id"] == task_id
    assert seen == [("v1", "rt-old"), ("v2", "rt-new"), ("v3", "rt-implemented"),
                    ("v4", "rt-prior-stress")]
    assert len(service.list_for_symbol("600519")) == 4
    assert seen[-4:] == [("v3", "rt-implemented"), ("v2", "rt-new"), ("v1", "rt-old"),
                         ("v4", "rt-prior-stress")]


def test_dispatch_rejects_unsupported_source_version(tmp_path, monkeypatch):
    base = tmp_path / "tasks"
    base.mkdir()

    class FakeTask:
        def __init__(self, root, source_loader=None):
            self.base = base

        def _directory(self, task_id):
            return base / task_id

    monkeypatch.setattr(mod, "CashTask", FakeTask)
    service = mod.NoticeAwareTaskService(tmp_path, kind="cash")
    directory = base / "rt-bad"
    directory.mkdir()
    (directory / "input.json").write_text(json.dumps({"symbol": "600519", "source_binding": {
        "path": "runtime/operating-horizon-sources-v10/future.json"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="SOURCE_VERSION_UNSUPPORTED"):
        service.read("rt-bad")
    with pytest.raises(ValueError, match="SOURCE_VERSION_UNSUPPORTED"):
        service.list_for_symbol("600519")


def test_listing_replays_only_requested_issuer_and_preserves_identity_check(tmp_path, monkeypatch):
    base = tmp_path / "tasks"
    base.mkdir()
    seen = []

    class FakeTask:
        def __init__(self, root, source_loader=None):
            self.base = base

        def _directory(self, task_id):
            return base / task_id

        def read(self, task_id):
            seen.append(task_id)
            return {"task_id": task_id, "symbol": "600519", "updated_at": "2026-11-11"}

    monkeypatch.setattr(mod, "CashTask", FakeTask)
    service = mod.NoticeAwareTaskService(tmp_path, kind="cash")
    for task_id, symbol, source in (
        ("rt-matching", "600519", "v5"),
        ("rt-unrelated", "600887", "v5"),
    ):
        directory = base / task_id
        directory.mkdir()
        (directory / "input.json").write_text(json.dumps({
            "symbol": symbol,
            "source_binding": {"path": f"runtime/operating-horizon-sources-{source}/source.json"},
        }), encoding="utf-8")
    assert [row["task_id"] for row in service.list_for_symbol("600519")] == ["rt-matching"]
    assert seen == ["rt-matching"]
    with pytest.raises(ValueError, match="RESEARCH_TASK_INPUT_IDENTITY_MISMATCH"):
        service.list_for_symbol("600887")


def test_notice_context_replays_original_binding_and_rejects_changed_receipt(source_env, monkeypatch):
    root = source_env.root
    receipt = root / "receipt.json"
    receipt.write_bytes(b"TEST_ONLY_NOTICE_RECEIPT")
    config = root / sources.CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"schema_version": "operating-public-notice-selection-v1",
        "action": "no_order", "cases": {"123456": {"receipt_path": "receipt.json",
        "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}}}), encoding="utf-8")
    monkeypatch.setattr(sources.notice, "replay_proposed_dividend", lambda **kwargs: {
        "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/test.pdf",
        "original_sha256": "a" * 64, "available_at": NOW.isoformat(),
        "physical_page": 2, "per_share_cny": "1", "entitled_shares": 100,
        "proposed_total_cny": "100", "status": "TEST_ONLY_PROPOSAL"})
    first = sources.build_operating_horizon_source_context(root=root, symbol="123456", now=NOW)
    assert first["schema_version"] == sources.VERSION
    assert first["evidence"][-1]["kind"] == "OCR_VERIFIED_DERIVED_PROPOSAL_NOT_PAYMENT_OR_FORECAST_POLICY"
    replay = sources.build_operating_horizon_source_context(
        root=root, symbol="123456", now=NOW, binding=first["source_binding"])
    assert replay == first
    receipt.write_bytes(b"TAMPERED")
    with pytest.raises(ValueError, match="PUBLIC_NOTICE_RECEIPT_HASH_CHANGED"):
        sources.build_operating_horizon_source_context(
            root=root, symbol="123456", now=NOW, binding=first["source_binding"])
