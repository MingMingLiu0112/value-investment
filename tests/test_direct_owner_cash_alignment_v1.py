"""TEST_ONLY cold-replayed direct receipt enters the shared F2 verifier."""
import json
from hashlib import sha256

import pytest

from test_direct_owner_cash_compilation_v1 import NOW, sample
from test_d2_conditional_shared_service import synthetic_chain
from test_p7_materiality_review_transport import transport
from value_investment_agent.application.research import direct_owner_cash_research_v1 as runner
from value_investment_agent.application.research.direct_owner_cash_alignment_v1 import (
    _capital_anchor, read_direct_owner_cash_alignment,
)


@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp("f")


def _bound(path, root, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(raw).hexdigest()}


def _receipt(monkeypatch, tmp_path):
    spec = sample(monkeypatch)
    source = _bound(tmp_path / "runtime/TEST_ONLY.json", tmp_path, {})
    spec["operating_sources"][0]["sha256"] = source["sha256"]
    spec_binding = _bound(tmp_path / "runtime/spec.json", tmp_path, spec)
    return runner.build_direct_owner_cash_receipt(
        root=tmp_path, spec_binding=spec_binding,
        output_dir=tmp_path / "runtime/output", now=NOW)["receipt_binding"]


def _register(tmp_path, receipt, *, schema="direct-owner-cash-alignment-input-v1", descriptor=None):
    original = runner._read(tmp_path, receipt)
    config = dict(schema_version=schema, candidate_binding=receipt,
                  input_descriptor_sha256=descriptor or original["input_descriptor_sha256"],
                  quote_bundle_binding=None, event_observation_bindings=[],
                  source_observation_bindings=[], reconciliation_binding=None,
                  materiality_review_binding=None)
    _bound(tmp_path / "config/pending-candidate-alignments-v1" / (receipt["sha256"] + ".json"),
           tmp_path, config)


def test_registered_direct_receipt_enters_shared_checks(monkeypatch, tmp_path):
    receipt = _receipt(monkeypatch, tmp_path)
    _register(tmp_path, receipt)
    result = read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=receipt, now=NOW)
    assert result["schema_version"] == "direct-owner-cash-alignment-v1"
    assert result["research_artifact_kind"] == "DIRECT_OWNER_CASH_RECEIPT"
    assert result["receipt_binding"] == receipt
    assert result["candidate_binding"] == receipt
    assert result["status"] == "BLOCKED"
    assert result["checks"] and result["evidence_bindings"]
    assert receipt in result["evidence_bindings"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["currentpricecomparison"] is False
    assert result["materiality_input_adapter"]["status"].startswith("INPUT_ADAPTER_REQUIRED")
    assert result["ordinary_shares_fact_anchor_status"] == "NO_MATCHED_OFFICIAL_SOURCE_ANCHOR"


def test_exact_receipt_registration_required(monkeypatch, tmp_path):
    receipt = _receipt(monkeypatch, tmp_path)
    result = read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=receipt, now=NOW)
    assert result["reason_codes"] == ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]
    assert not result["evidence_bindings"]


@pytest.mark.parametrize("fault", [None, "other_receipt", "damaged_envelope"])
def test_exact_materiality_envelope_consumed_without_granting_approval(monkeypatch, tmp_path, fault):
    from value_investment_agent.application.product.research_materiality_reviews import (
        build_direct_owner_cash_materiality_envelope,
    )
    from value_investment_agent.valuation_models.direct_owner_cash_v1 import MODEL_ID
    receipt = _receipt(monkeypatch, tmp_path)
    original = runner._read(tmp_path, receipt)
    replayed = runner.replay_direct_owner_cash_receipt(root=tmp_path, receipt_binding=receipt, now=NOW)
    package = replayed["package"]
    package_path = tmp_path / "runtime/review-package.json"
    package_ref = _bound(package_path, tmp_path, package)
    envelope_path = tmp_path / "runtime/review-envelope.json"
    envelope_ref = build_direct_owner_cash_materiality_envelope(
        root=tmp_path, package_path=package_path, package_sha256=package_ref["sha256"],
        receipt_path=tmp_path / receipt["path"], receipt_sha256=receipt["sha256"],
        model_validity_input=dict(model_id=MODEL_ID, valid_from=package["research_case"]["as_of"],
                                  events=[], blockers=[]), output_path=envelope_path)
    if fault == "other_receipt":
        envelope = runner._read(tmp_path, envelope_ref)
        envelope["receipt_binding"] = dict(receipt, sha256="f" * 64)
        envelope_ref = _bound(envelope_path, tmp_path, envelope)
    _register(tmp_path, receipt)
    config_path = tmp_path / "config/pending-candidate-alignments-v1" / (receipt["sha256"] + ".json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["materiality_envelope_binding"] = envelope_ref
    _bound(config_path, tmp_path, config)
    if fault == "damaged_envelope":
        envelope_path.write_bytes(b"{}")
    if fault:
        with pytest.raises(ValueError, match="RECEIPT_MISMATCH|HASH_CHANGED"):
            read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=receipt, now=NOW)
        return
    output = read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=receipt, now=NOW)
    assert output["materiality_input_adapter"]["status"] == "EXACT_DIRECT_REVIEW_ENVELOPE_BOUND"
    assert output["materiality_input_adapter"]["approval_granted"] is False
    assert envelope_ref in output["evidence_bindings"]
    assert package_ref in output["evidence_bindings"]
    assert output["input_descriptor_sha256"] == original["input_descriptor_sha256"]
    assert output["formal_eligibility"] is False and output["currentpricecomparison"] is False


def test_signed_direct_materiality_reaches_shared_consumer_and_rejects_wrong_candidate(
        transport, monkeypatch):
    """TEST_ONLY transport key; production signature and cold-replay checks run."""
    from copy import deepcopy
    from datetime import datetime, timezone

    from test_direct_owner_cash_materiality_review_context_v1 import _receipt_with_local_originals
    from test_p7_materiality_review_transport import _inputs
    from value_investment_agent.application.product.common import sha256_file
    from value_investment_agent.application.product.research_materiality_reviews import (
        build_direct_owner_cash_materiality_envelope, consume_materiality_review_response,
    )
    from value_investment_agent.application.research import pending_candidate_alignment as shared
    from value_investment_agent.application.research.value_research_analysis import _bound as read_bound
    from value_investment_agent.event_scan import event_scan_from_payload
    from value_investment_agent.infrastructure.evidence.trust_root_registry import _use_test_trust_registry
    from value_investment_agent.valuation_models.direct_owner_cash_v1 import MODEL_ID

    root = transport["root"]
    receipt_ref = _receipt_with_local_originals(monkeypatch, root)
    receipt = runner._read(root, receipt_ref)
    result = runner.replay_direct_owner_cash_receipt(root=root, receipt_binding=receipt_ref, now=NOW)
    package = result["package"]
    package_ref = _bound(root / "runtime/direct-review-package.json", root, package)
    basis = result["compiled"]["valuation_date"]
    scan_path = transport["scan_path"]
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan["validity_from"] = basis
    scan["scan_from"] = basis
    scan_path.write_text(json.dumps(scan, ensure_ascii=False), encoding="utf-8")
    scan_ref = {"path": scan_path.relative_to(root).as_posix(), "sha256": sha256_file(scan_path)}
    envelope_path = root / "runtime/direct-review-envelope.json"
    envelope_ref = build_direct_owner_cash_materiality_envelope(
        root=root, package_path=root / package_ref["path"], package_sha256=package_ref["sha256"],
        receipt_path=root / receipt_ref["path"], receipt_sha256=receipt_ref["sha256"],
        model_validity_input={"model_id": MODEL_ID, "valid_from": basis,
                              "events": [], "blockers": []}, output_path=envelope_path)
    from value_investment_agent.application.product.research_materiality_reviews import prepare_materiality_review_handoff
    handoff = prepare_materiality_review_handoff(
        root=root, package_path=envelope_path, package_sha256=envelope_ref["sha256"],
        scan_path=scan_path, scan_sha256=scan_ref["sha256"])
    handoff_ref = _bound(root / "runtime/direct-review-handoff.json", root, handoff)
    signed_review = deepcopy(transport["response"]["event_materiality"])
    signed_review.update(scan_sha256=scan_ref["sha256"], scan_from=basis,
                         scan_to=scan["scan_to"], model_context=handoff["model_context"])
    signed_response = dict(handoff["unsigned_response"],
                           reviewer_id=transport["response"]["reviewer_id"],
                           reviewed_at=transport["response"]["reviewed_at"],
                           event_materiality=signed_review)
    signed_transport = dict(transport, handoff=handoff, handoff_path=root / handoff_ref["path"],
                            handoff_hash=handoff_ref["sha256"], response=signed_response)
    registry, args = _inputs(signed_transport, suffix="-direct")
    with _use_test_trust_registry(registry):
        imported = consume_materiality_review_response(**args)
        scan_object = event_scan_from_payload(json.loads(scan_path.read_text(encoding="utf-8")))
        analysis = {"symbol": result["symbol"], "valuation_date": basis,
                    "review_binding": {"candidate_binding": receipt_ref,
                                       "package_binding": envelope_ref}}
        review, route = shared._materiality(
            root, analysis, imported["review_packet_binding"],
            [{"scan_binding": scan_ref, "full_calendar_window_elapsed": True}],
            [scan_object], datetime.now(timezone.utc), lambda ref: read_bound(root, ref))
        assert route["status"] == "EXISTING_AUTHENTICATED_MATERIALITY_REPLAYED"
        assert route["model_context"] == handoff["model_context"]
        assert len(review.decisions) == len(scan_object.announcements)
        assert imported["whole_model_approved"] is False
        assert imported["research_admitted"] is False

    _register(root, receipt_ref)
    config_path = root / "config/pending-candidate-alignments-v1" / (receipt_ref["sha256"] + ".json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["materiality_envelope_binding"] = envelope_ref
    config["candidate_binding"] = dict(receipt_ref, sha256="0" * 64)
    _bound(config_path, root, config)
    with pytest.raises(ValueError, match="DIRECT_MATERIALITY_ALIGNMENT_IDENTITY_MISMATCH"):
        read_direct_owner_cash_alignment(root=root, receipt_binding=receipt_ref, now=NOW)


@pytest.mark.parametrize("fault", ["old_schema", "different_descriptor"])
def test_old_candidate_or_different_descriptor_rejected(monkeypatch, tmp_path, fault):
    receipt = _receipt(monkeypatch, tmp_path)
    _register(tmp_path, receipt,
              schema="pending-candidate-alignment-input-v1" if fault == "old_schema" else "direct-owner-cash-alignment-input-v1",
              descriptor="f" * 64 if fault == "different_descriptor" else None)
    result = read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=receipt, now=NOW)
    assert result["status"] == "BLOCKED"
    assert "ALIGNMENT_CANDIDATE_OR_DESCRIPTOR_MISMATCH" in result["reason_codes"][0]


def test_source_damage_fails_cold_replay(monkeypatch, tmp_path):
    receipt = _receipt(monkeypatch, tmp_path)
    _register(tmp_path, receipt)
    (tmp_path / "runtime/TEST_ONLY.json").write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=receipt, now=NOW)


def test_two_public_gets_cold_replay_direct_alignment_without_writes(monkeypatch, tmp_path):
    from value_investment_agent.presentation.web_api import first_research_input_routes as routes
    from value_investment_agent.application.product import first_input_quote_alignment_v1 as quote_alignment
    from web_api.test_held_continuity_api import client_for

    receipt = _receipt(monkeypatch, tmp_path)
    _register(tmp_path, receipt)
    _bound(tmp_path / "config/current-first-research-inputs-v1.json", tmp_path,
           dict(schema_version="current-first-research-inputs-v1", action="no_order",
                cases={"600519": {"receipt": receipt}}))

    class TestClock:
        @staticmethod
        def now(_tz=None):
            return NOW

    monkeypatch.setattr(routes, "datetime", TestClock)
    monkeypatch.setattr(quote_alignment, "read_first_input_quote_alignment", lambda **_: {"status": "TEST_ONLY_UNRELATED"})
    monkeypatch.setattr(routes, "read_first_research_update", lambda **_: {"status": "NOT_STARTED"})
    monkeypatch.setattr(routes, "execute_quote_bridge_for_symbol", lambda *_args, **_kwargs: {
        "status": "NOT_STARTED", "quote": None, "price_admitted": False})
    client, _ = client_for(tmp_path, tmp_path / "TEST_ONLY-journal.jsonl", monkeypatch)

    def snapshot():
        return {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in tmp_path.rglob("*") if p.is_file()}

    before = snapshot()
    outputs = []
    for _ in range(2):
        response = client.get("/api/v1/first-research-inputs/600519")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "SOURCE_BOUND_FIRST_INPUT_COMPILED"
        alignment = body["direct_cash_alignment"]
        assert alignment["schema_version"] == "direct-owner-cash-alignment-v1"
        assert alignment["receipt_binding"] == receipt
        assert alignment["evidence_bindings"] and alignment["checks"]
        assert alignment["action"] == "no_order" and alignment["formal_eligibility"] is False
        outputs.append(alignment)
        assert snapshot() == before
    assert outputs[0] == outputs[1]


def test_wrong_receipt_binding_rejected_before_alignment(monkeypatch, tmp_path):
    receipt = _receipt(monkeypatch, tmp_path)
    _register(tmp_path, receipt)
    wrong = dict(receipt, sha256="0" * 64)
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        read_direct_owner_cash_alignment(root=tmp_path, receipt_binding=wrong, now=NOW)


@pytest.mark.parametrize("field,value", [("unit", "CNY"), ("period_end", "2024-12-31")])
def test_capital_anchor_rejects_wrong_unit_or_period(monkeypatch, tmp_path, field, value):
    receipt = _receipt(monkeypatch, tmp_path)
    result = runner.replay_direct_owner_cash_receipt(root=tmp_path, receipt_binding=receipt, now=NOW)
    compiled = json.loads(json.dumps(result["compiled"]))
    proof = compiled["evidence"]["statements"][0]["ordinary_shares_evidence"]
    proof["classification"] = "FACT"
    proof[field] = value
    with pytest.raises(ValueError, match="DIRECT_ALIGNMENT_CONSUMED_SHARE_FACT_INVALID"):
        _capital_anchor(compiled, [], result["symbol"])
