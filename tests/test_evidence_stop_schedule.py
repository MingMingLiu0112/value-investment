from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.application.product import run_company_research_for_symbol
from value_investment_agent.application.product.company_research import _verified_source_ids
from value_investment_agent.application.product import company_research
from value_investment_agent.domain.research.evidence_stop import (
    evaluate_research_schedule,
    evidence_stops_from_payload,
    schedule_request_from_payload,
)
from value_investment_agent.infrastructure.evidence.evidence_stop_schedule import (
    claim_research_schedule_once,
    recover_admitted_schedule,
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


def _recovery_fixture(root: Path, *, source_bytes: bytes = b"official filing bytes"):
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    ledger_bytes = json.dumps(LEDGER, ensure_ascii=False, indent=2).encode("utf-8")
    (config_dir / "research-evidence-stop-ledger-v1.json").write_bytes(ledger_bytes)
    evidence_path = root / "evidence" / "new-filing.pdf"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_bytes(source_bytes)
    source = {
        "id": "cninfo_1230000000",
        "kind": "official_issuer_filing",
        "location": "evidence/new-filing.pdf",
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "issuer_identity": {"security_code": "000333"},
    }
    request = _request()
    decision = evaluate_research_schedule(
        symbol="000333",
        stops=STOPS,
        request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    admission = claim_research_schedule_once(
        root=root,
        request=request,
        decision=decision,
        ledger_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
        request_sha256="b" * 64,
    )
    assert admission["created"] is True
    return request, source, hashlib.sha256(ledger_bytes).hexdigest()


def test_same_stopped_question_is_blocked_without_new_verified_evidence():
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=_request(),
    )
    assert decision["allowed"] is False
    assert decision["status"] == "BLOCKED_UNBOUND_EVIDENCE_ID"


def test_exact_registered_stop_stays_blocked_without_valid_new_evidence():
    request = _request()
    decision = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
    )
    assert decision["allowed"] is False
    assert decision["status"] == "BLOCKED_UNBOUND_EVIDENCE_ID"
    assert decision["matched_stop_ids"] == ["000333-share-denominator-2026-06-30"]


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


def test_recovery_requires_existing_admission_and_revalidates_official_source(tmp_path):
    request, source, ledger_hash = _recovery_fixture(tmp_path)
    evidence_path = tmp_path / source["location"]
    evidence_path.write_bytes(b"changed after admission")
    with pytest.raises(ValueError, match="issuer, hash and reopen validation"):
        recover_admitted_schedule(
            root=tmp_path,
            request=request,
            evidence_sources=[source],
            ledger_sha256=ledger_hash,
            request_sha256="b" * 64,
            interrupted_run_id="crashed-run-001",
        )
    assert not (tmp_path / "runtime" / "research-evidence-stop-recoveries").exists()


def test_recovery_requires_an_explicit_interrupted_run_id(tmp_path):
    request, source, ledger_hash = _recovery_fixture(tmp_path)
    with pytest.raises(ValueError, match="interrupted_run_id is required"):
        recover_admitted_schedule(
            root=tmp_path,
            request=request,
            evidence_sources=[source],
            ledger_sha256=ledger_hash,
            request_sha256="b" * 64,
            interrupted_run_id=" ",
        )
    assert not (tmp_path / "runtime" / "research-evidence-stop-recoveries").exists()


def test_recovery_rejects_issuer_mismatch(tmp_path):
    request, source, ledger_hash = _recovery_fixture(tmp_path)
    source["issuer_identity"]["security_code"] = "600519"
    with pytest.raises(ValueError, match="issuer, hash and reopen validation"):
        recover_admitted_schedule(
            root=tmp_path,
            request=request,
            evidence_sources=[source],
            ledger_sha256=ledger_hash,
            request_sha256="b" * 64,
            interrupted_run_id="crashed-run-001",
        )
    assert not (tmp_path / "runtime" / "research-evidence-stop-recoveries").exists()


def test_recovery_requires_a_prior_admission_receipt(tmp_path):
    request, source, ledger_hash = _recovery_fixture(tmp_path)
    admission_path = next(
        (tmp_path / "runtime" / "research-evidence-stop-consumptions").glob("*.json")
    )
    admission_path.unlink()
    with pytest.raises(ValueError, match="admission receipt must be a file"):
        recover_admitted_schedule(
            root=tmp_path,
            request=request,
            evidence_sources=[source],
            ledger_sha256=ledger_hash,
            request_sha256="b" * 64,
            interrupted_run_id="crashed-run-001",
        )
    assert not (tmp_path / "runtime" / "research-evidence-stop-recoveries").exists()


def test_recovery_receipt_is_auditable_and_repeated_calls_do_not_retry(tmp_path):
    request, source, ledger_hash = _recovery_fixture(tmp_path)
    first = recover_admitted_schedule(
        root=tmp_path,
        request=request,
        evidence_sources=[source],
        ledger_sha256=ledger_hash,
        request_sha256="b" * 64,
        interrupted_run_id="crashed-run-001",
    )
    second = recover_admitted_schedule(
        root=tmp_path,
        request=request,
        evidence_sources=[source],
        ledger_sha256=ledger_hash,
        request_sha256="b" * 64,
        interrupted_run_id="crashed-run-001",
    )
    assert first["created"] is True
    assert first["status"] == "RECOVERY_RECORDED_AWAITING_EXPLICIT_RESUME"
    assert first["automatic_retry"] is False
    assert first["resume_performed"] is False
    assert second["created"] is False
    assert second["status"] == "RECOVERY_ALREADY_RECORDED"
    assert second["automatic_retry"] is False
    assert second["resume_performed"] is False
    receipts = list((tmp_path / "runtime" / "research-evidence-stop-recoveries").glob("*.json"))
    assert len(receipts) == 1
    saved = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert saved["schema_version"] == "research-evidence-stop-recovery-v1"
    assert saved["new_evidence_ids"] == ["cninfo_1230000000"]
    assert saved["admission_receipt_sha256"]
    assert saved["interrupted_run_id"] == "crashed-run-001"
    assert saved["automatic_retry"] is False
    assert saved["resume_performed"] is False
    assert saved["action"] == "no_order"


def test_recovery_rejects_changed_ledger_or_request_hash(tmp_path):
    request, source, ledger_hash = _recovery_fixture(tmp_path)
    with pytest.raises(ValueError, match="ledger hash"):
        recover_admitted_schedule(
            root=tmp_path,
            request=request,
            evidence_sources=[source],
            ledger_sha256="c" * 64,
            request_sha256="b" * 64,
            interrupted_run_id="crashed-run-001",
        )
    with pytest.raises(ValueError, match="does not match the requested recovery"):
        recover_admitted_schedule(
            root=tmp_path,
            request=request,
            evidence_sources=[source],
            ledger_sha256=ledger_hash,
            request_sha256="d" * 64,
            interrupted_run_id="crashed-run-001",
        )
    assert not (tmp_path / "runtime" / "research-evidence-stop-recoveries").exists()


def test_other_scoped_question_is_normal_research_without_a_matching_trigger():
    request = _request(
        research_question_id="new_official_issue",
        blocker_id="new_material_event",
    )
    blocked = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
    )
    assert blocked["allowed"] is True
    assert blocked["status"] == "ALLOW_NORMAL_RESEARCH"
    assert blocked["matched_stop_ids"] == []
    allowed = evaluate_research_schedule(
        symbol="000333", stops=STOPS, request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    assert allowed["allowed"] is True
    assert allowed["status"] == "ALLOW_NORMAL_RESEARCH"
    assert "new_evidence_ids" not in allowed


def test_normal_research_scope_does_not_consume_or_reopen_a_registered_stop(tmp_path):
    request = _request(
        research_question_id="new_official_issue",
        blocker_id="new_material_event",
    )
    decision = evaluate_research_schedule(
        symbol="000333",
        stops=STOPS,
        request=request,
        verified_evidence_ids=frozenset({"cninfo_1230000000"}),
    )
    result = claim_research_schedule_once(
        root=tmp_path,
        request=request,
        decision=decision,
        ledger_sha256="a" * 64,
        request_sha256="b" * 64,
    )
    assert decision["status"] == "ALLOW_NORMAL_RESEARCH"
    assert result == {
        "created": True,
        "consumed": False,
        "status": "NORMAL_RESEARCH_NOT_CONSUMED",
        "schedule_id": None,
        "receipt_path": None,
    }
    assert not (tmp_path / "runtime").exists()


def test_company_research_entrypoint_blocks_unscoped_stopped_case_before_package_lookup():
    result = run_company_research_for_symbol(root=ROOT, symbol="000333")
    assert result["result"]["status"] == "BLOCKED_BY_RESEARCH_SCHEDULER"
    assert result["result"]["schedule_gate"]["status"] == "BLOCKED_SCOPE_REQUIRED"
    assert result["result"]["action"] == "no_order"


def test_fresh_case_without_registered_stop_allows_normal_research():
    request = _request(symbol="000651")
    decision = evaluate_research_schedule(
        symbol="000651", stops=STOPS, request=request,
    )
    assert decision["allowed"] is True
    assert decision["status"] == "ALLOW_NORMAL_RESEARCH"
    assert decision["matched_stop_ids"] == []


def test_fresh_case_reaches_research_application_without_consuming_a_stop(
    tmp_path, monkeypatch,
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "research-evidence-stop-ledger-v1.json").write_bytes(
        LEDGER_PATH.read_bytes()
    )
    package = tmp_path / "synthetic-package.json"
    package.write_text('{"symbol":"000651"}\n', encoding="utf-8")
    called = {}

    class RecordingResearchService:
        def __init__(self, repository):
            pass

        def run_company_research(self, spec):
            called["spec"] = spec
            return {"completed": True}

    monkeypatch.setattr(
        company_research, "_package_for_symbol", lambda *_args: package
    )
    monkeypatch.setattr(
        company_research, "build_descriptor", lambda _payload, *, root: {}
    )
    monkeypatch.setattr(
        company_research, "build_research_run_spec", lambda descriptor:
        SimpleNamespace(input_descriptor_sha256='a' * 64)
    )
    monkeypatch.setattr(
        company_research, "ResearchApplicationService", RecordingResearchService
    )
    monkeypatch.setattr(
        company_research, "_serialize_outcome", lambda outcome: outcome
    )

    request_payload = {
        "schema_version": "research-schedule-request-v1",
        "symbol": "000651",
        "source_id": "CNINFO",
        "period": "2025-12-31",
        "research_question_id": "fresh_company_scope",
        "blocker_id": "initial_research",
        "reopen_condition_met": False,
        "new_evidence_ids": [],
    }
    result = run_company_research_for_symbol(
        root=tmp_path,
        symbol="000651",
        package_path=package,
        schedule_request=request_payload,
        schedule_request_sha256="b" * 64,
    )

    assert called["spec"].input_descriptor_sha256 == 'a' * 64
    assert result["result"]["schedule_gate"]["status"] == "ALLOW_NORMAL_RESEARCH"
    assert "schedule_consumption" not in result["result"]


def test_symbol_without_research_case_scope_remains_blocked():
    decision = evaluate_research_schedule(
        symbol="600519", stops=STOPS, request=None,
    )
    assert decision == {
        "allowed": False,
        "status": "BLOCKED_NO_REGISTERED_SCOPE",
        "matched_stop_ids": [],
        "reason": "A fresh ResearchCase scope is required for normal research.",
    }


@pytest.mark.parametrize('descriptor_rejected', [False, True])
def test_explicit_daily_inputs_reach_descriptor_before_one_shot_consumption(
    tmp_path, monkeypatch, descriptor_rejected,
):
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'research-evidence-stop-ledger-v1.json').write_bytes(LEDGER_PATH.read_bytes())
    package = tmp_path / 'package.json'
    original = dict(symbol='600887', model_validity_input=dict(model_id='test',
        valid_from='2026-09-22', events=[{'existing': 'retained'}]))
    package.write_text(json.dumps(original), encoding='utf-8')
    quote = tmp_path / 'quote.json'
    event = tmp_path / 'event.json'
    quote.write_text('{}', encoding='utf-8')
    event.write_text('{}', encoding='utf-8')
    digest = hashlib.sha256(b'{}').hexdigest()
    calls = []
    monkeypatch.setattr(company_research, 'evaluate_research_schedule', lambda **kwargs:
        dict(allowed=True, status='SYNTHETIC_ALLOWED_TEST_ONLY'))
    def descriptor(payload, *, root):
        calls.append('validate')
        assert payload['quote']['bundle_sha256'] == digest
        assert payload['quote']['bundle_path'] == 'quote.json'
        assert payload['model_validity_input']['event_scan_ref']['sha256'] == digest
        assert payload['model_validity_input']['event_scan_ref']['path'] == 'event.json'
        assert payload['model_validity_input']['events'] == [{'existing': 'retained'}]
        if descriptor_rejected:
            raise ValueError('Quote date cannot follow research as-of')
        return payload
    monkeypatch.setattr(company_research, 'build_descriptor', descriptor)
    monkeypatch.setattr(company_research, 'build_research_run_spec', lambda payload:
        SimpleNamespace(input_descriptor_sha256='a' * 64))
    def claim(**kwargs):
        calls.append('consume')
        return dict(created=True)
    monkeypatch.setattr(company_research, 'claim_research_schedule_once', claim)
    class Service:
        def __init__(self, repository):
            pass
        def run_company_research(self, spec):
            calls.append('calculate')
            return dict(symbol='600887', action='no_order')
    monkeypatch.setattr(company_research, 'ResearchApplicationService', Service)
    monkeypatch.setattr(company_research, '_serialize_outcome', lambda payload: payload)
    kwargs = dict(root=tmp_path, symbol='600887', package_path=package,
        quote_path=quote, quote_sha256=digest, event_path=event, event_sha256=digest,
        schedule_request=dict(schema_version='research-schedule-request-v1',
            symbol='600887', source_id='CNINFO', period='2026-06-30',
            research_question_id='synthetic', blocker_id='synthetic',
            reopen_condition_met=True, new_evidence_ids=['synthetic']),
        schedule_request_sha256='b' * 64)
    if descriptor_rejected:
        with pytest.raises(ValueError, match='research as-of'):
            run_company_research_for_symbol(**kwargs)
        assert calls == ['validate']
    else:
        result = run_company_research_for_symbol(**kwargs)
        assert calls == ['validate', 'consume', 'calculate']
        assert result['receipt']['input_sha256']['quote'] == digest
        assert result['receipt']['input_sha256']['event'] == digest
    assert json.loads(package.read_text(encoding='utf-8')) == original


def test_unregistered_moutai_research_is_blocked_before_package_lookup():
    result = run_company_research_for_symbol(root=ROOT, symbol="600519")
    assert result["result"]["status"] == "BLOCKED_BY_RESEARCH_SCHEDULER"
    assert result["result"]["schedule_gate"]["status"] == "BLOCKED_NO_REGISTERED_SCOPE"


@pytest.mark.parametrize('drift', [None, 'package', 'ledger', 'reviews'])
def test_reviewed_package_runs_actual_shared_entry_and_guards_consumed_bytes(tmp_path, monkeypatch, drift):
    from dataclasses import replace
    from test_human_research_approval import _receipt, DECISION_REJECTED_NEEDS_REWORK
    from test_research_application import _identity_source
    from value_investment_agent.m1_valuation_package_builder import build_descriptor
    from value_investment_agent.research_input import build_research_run_spec
    from value_investment_agent.research_application import ResearchApplicationService
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.human_research_approval import artifact_fingerprint
    from value_investment_agent.research_run_contract import valuation_result_sha256

    # All fixtures are local copies; the real ledger and real company approvals remain untouched.
    config = tmp_path / 'config'
    config.mkdir()
    ledger = config / 'research-evidence-stop-ledger-v1.json'
    ledger.write_text(json.dumps(dict(schema_version='research-evidence-stop-ledger-v1', stops=[])), encoding='utf-8')
    payload = json.loads((ROOT / 'config/m1-valuation-packages-v1/600887-quality-compounder.json').read_text(encoding='utf-8'))
    payload['quote'] = None
    payload['model_validity_input'] = None
    payload['run_id'] = 'synthetic-entry-integration-only'
    identity = _identity_source('600887').as_policy()['issuer_identity']
    for source in payload['sources']:
        if source['kind'] == 'official_issuer_filing':
            source['issuer_identity'] = identity
            source['kind'] = 'annual_report'
            source['location'] = 'https://www.cninfo.com.cn/synthetic-test-only.pdf#' + source['id']
    package = tmp_path / 'package.json'
    package.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    descriptor = build_descriptor(payload, root=tmp_path)
    baseline = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(build_research_run_spec(descriptor))
    canonical = descriptor.as_policy()
    approval = replace(_receipt(decision=DECISION_REJECTED_NEEDS_REWORK,
        price_assessment_eligible=False, remaining_blockers=('SYNTHETIC_REVIEW_REJECTION',)),
        valuation_artifact_sha256=valuation_result_sha256(baseline.valuation),
        valuation_model_version=baseline.valuation.model_version,
        research_case_sha256=artifact_fingerprint(canonical['research_case']),
        facts_artifact_sha256=artifact_fingerprint(canonical['facts']),
        assumption_set_sha256=artifact_fingerprint(canonical['assumptions']))
    approval_path = tmp_path / 'approval.json'
    approval_path.write_text(json.dumps(approval.as_policy()), encoding='utf-8')
    reviews = tmp_path / 'reviews.json'
    reviews.write_text(json.dumps(dict(schema_version='shared-research-review-inputs-v1',
        symbol='600887', action='no_order', bindings=dict(human_approval=dict(path=approval_path.name,
            sha256=hashlib.sha256(approval_path.read_bytes()).hexdigest())))), encoding='utf-8')
    request = dict(schema_version='research-schedule-request-v1', symbol='600887', source_id='TEST_ONLY',
        period='2026-06-30', research_question_id='synthetic-entry', blocker_id='initial_research',
        reopen_condition_met=False, new_evidence_ids=[])
    if drift:
        class DriftingService(ResearchApplicationService):
            def run_company_research(self, spec):
                outcome = super().run_company_research(spec)
                target = {'package': package, 'ledger': ledger, 'reviews': reviews}[drift]
                target.write_bytes(target.read_bytes() + b' ')
                return outcome
        monkeypatch.setattr(company_research, 'ResearchApplicationService', DriftingService)
    output = tmp_path / 'result.json'
    kwargs = dict(root=tmp_path, symbol='600887', package_path=package,
        schedule_request=request, output_path=output, reviews_path=reviews,
        reviews_sha256=hashlib.sha256(reviews.read_bytes()).hexdigest())
    if drift:
        with pytest.raises(ValueError, match='changed during execution'):
            run_company_research_for_symbol(**kwargs)
        assert not output.exists()
        return
    result = run_company_research_for_symbol(**kwargs)
    assert result['result']['human_research_approval']['decision'] == DECISION_REJECTED_NEEDS_REWORK
    assert 'SYNTHETIC_REVIEW_REJECTION' in result['result']['blockers']
    assert result['result']['input_descriptor_sha256'] != descriptor.input_sha256
    assert result['receipt']['input_sha256']['valuation_package'] == hashlib.sha256(package.read_bytes()).hexdigest()
    assert result['receipt']['input_sha256']['research_reviews'] == hashlib.sha256(reviews.read_bytes()).hexdigest()
    assert result['result']['schedule_gate']['status'] == 'ALLOW_NORMAL_RESEARCH'
    assert result['result']['action'] == 'no_order'
    assert result['result']['pre_decision_eligibility'] is None
    from value_investment_agent.presentation.read_models.shadow_daily_review import render_shadow_company_review
    research = result['result']
    projection = dict(symbol='600887', suggested_state='NOT_READY', blockers=research['blockers'])
    card = render_shadow_company_review(research=dict(result=research,
        session_date=research['as_of'], run_id=research['run_id']),
        model=dict(valuation_result=research['valuation'], model_validity=research['model_validity'],
            price_bridge=research['price_bridge']), decision=projection, product=projection,
        audit=dict(input_consistency_status='SYNTHETIC_TEST_ONLY', blockers=[]))
    assert 'SYNTHETIC_REVIEW_REJECTION' in card and 'action=no_order' in card
    (tmp_path / 'synthetic-entry-card.md').write_text(
        '# SYNTHETIC INTEGRATION TEST ONLY - NOT INVESTMENT RESEARCH\n\n' + card, encoding='utf-8')
