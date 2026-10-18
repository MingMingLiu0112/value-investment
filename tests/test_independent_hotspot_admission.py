from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from authorization_trust_registry_fixture import pin_test_trust_root
from value_investment_agent.domain.hotspot.independent_admission import (
    GATES, HotspotGateEvidence, evaluate_independent_hotspot,
)
from value_investment_agent.application.hotspot.independent_admission import (
    POINTER, PURPOSE, canonical_payload, load_independent_admission,
)

NOW = datetime(2026, 10, 18, 8, tzinfo=timezone.utc)


def gates():
    return tuple(HotspotGateEvidence(name, "PASS", NOW - timedelta(hours=1),
        NOW + timedelta(hours=1), hashlib.sha256(name.encode()).hexdigest()) for name in GATES)


def evaluate(evidence, authorization="VERIFIED"):
    return evaluate_independent_hotspot(symbol="000333", strategy_rule_version="test-rule-v1",
        evidence=evidence, now=NOW, authorization_status=authorization, namespace="TEST_ONLY")


def test_independent_risk_review_needs_no_value_valuation_or_g3():
    result = evaluate(gates())
    assert result["risk_review_eligible"] is True
    assert result["formal_eligibility"] is result["trade_eligible"] is False
    assert result["position_guidance"] is None
    assert result["action"] == "no_order"


@pytest.mark.parametrize("name", GATES)
@pytest.mark.parametrize("status", ["FAIL", "UNKNOWN"])
def test_each_hotspot_gate_independently_vetoes(name, status):
    rows = tuple(replace(row, status=status) if row.gate == name else row for row in gates())
    result = evaluate(rows)
    assert result["risk_review_eligible"] is False
    assert name + ":" + status in result["blockers"]


def test_missing_future_expired_and_duplicate_evidence():
    assert not evaluate(gates()[1:])["risk_review_eligible"]
    rows = gates()
    assert not evaluate((replace(rows[0], available_at=NOW + timedelta(minutes=1)), *rows[1:]))["risk_review_eligible"]
    assert not evaluate((replace(rows[0], expires_at=NOW), *rows[1:]))["risk_review_eligible"]
    assert not evaluate(rows, "MISSING")["risk_review_eligible"]
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate((*rows, rows[0]))


def test_non_ascii_security_identity_rejected():
    with pytest.raises(ValueError, match="identity"):
        evaluate_independent_hotspot(symbol="１２３４５６", strategy_rule_version="test-rule-v1",
            evidence=gates(), now=NOW, authorization_status="VERIFIED", namespace="TEST_ONLY")


@pytest.fixture
def release(tmp_path):
    def write(name, payload):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical_payload(payload)
        path.write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    key = Ed25519PrivateKey.generate()
    trust = {"schema_version": "independent-hotspot-trust-root-v1", "reviewer_id": "TEST_ONLY",
        "public_key": key.public_key().public_bytes_raw().hex(),
        "scopes": ["independent_hotspot_strategy_release"], "symbols": ["000333"],
        "valid_from": (NOW - timedelta(days=1)).isoformat(),
        "valid_until": (NOW + timedelta(days=1)).isoformat()}
    source = {**write("source.json", {"namespace": "TEST_ONLY", "action": "no_order"}),
        "namespace": "TEST_ONLY", "available_at": (NOW - timedelta(hours=2)).isoformat()}
    bindings = [write(name + ".json", {
        "schema_version": "independent-hotspot-gate-assessment-v1", "action": "no_order",
        "namespace": "TEST_ONLY", "symbol": "000333", "rule_version": "test-rule-v1",
        "gate": name, "status": "PASS", "available_at": (NOW - timedelta(hours=1)).isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(), "source_bindings": [source],
    }) for name in GATES]
    payload = {"schema_version": "independent-hotspot-release-v1", "action": "no_order",
        "symbol": "000333", "namespace": "TEST_ONLY", "rule_version": "test-rule-v1",
        "reviewer_id": "TEST_ONLY", "reviewed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(), "gates": bindings}

    def publish(purpose=PURPOSE):
        envelope = {"payload": payload,
                    "signature": key.sign(purpose + canonical_payload(payload)).hex()}
        row = {"symbol": "000333", "release": write("release.json", envelope),
               "trust": write("trust.json", trust)}
        write(POINTER, {"schema_version": "current-hotspot-independent-admission-v1",
                        "action": "no_order", "items": [row]})

    publish()
    return tmp_path, payload, trust, publish


def test_signed_isolated_release_without_value_can_reach_risk_review(release):
    root, _, trust, _ = release
    pin_test_trust_root(trust)
    result = load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)
    assert result["risk_review_eligible"] is True
    assert result["namespace"] == "TEST_ONLY"
    assert result["formal_eligibility"] is False
    with pytest.raises(ValueError, match="Test-only"):
        load_independent_admission(root, symbol="000333", now=NOW)


def test_unpinned_self_authorization_is_rejected(release):
    root, _, _, _ = release
    with pytest.raises(ValueError, match="not pinned"):
        load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)


def test_value_review_scope_cannot_authorize_independent_hotspot(release):
    root, _, trust, publish = release
    trust["scopes"] = ["human_whole_model"]
    publish()
    pin_test_trust_root(trust)
    with pytest.raises(ValueError, match="purpose or scope"):
        load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)


def test_cross_purpose_signature_and_release_retirement(release):
    root, _, trust, publish = release
    pin_test_trust_root(trust)
    publish(b"value-review-transport-purpose")
    with pytest.raises(ValueError, match="signature invalid"):
        load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)
    publish()
    assert load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)["risk_review_eligible"]
    (root / POINTER).unlink()
    assert not load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)["risk_review_eligible"]


def test_sources_reverified_after_signed_release(release):
    root, _, trust, _ = release
    pin_test_trust_root(trust)
    (root / "source.json").write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)


def test_wrong_purpose_signature_and_expiry_rejected(release):
    root, payload, trust, publish = release
    pin_test_trust_root(trust)
    with pytest.raises(ValueError, match="expired"):
        load_independent_admission(root, symbol="000333", now=NOW + timedelta(hours=1), allow_test_only=True)
    envelope = json.loads((root / "release.json").read_bytes())
    envelope["signature"] = "00" * 64
    raw = canonical_payload(envelope)
    (root / "release.json").write_bytes(raw)
    pointer = json.loads((root / POINTER).read_bytes())
    pointer["items"][0]["release"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (root / POINTER).write_bytes(canonical_payload(pointer))
    with pytest.raises(ValueError, match="signature invalid"):
        load_independent_admission(root, symbol="000333", now=NOW, allow_test_only=True)


def test_missing_server_registry_is_observation_only(tmp_path):
    result = load_independent_admission(tmp_path, symbol="000333", now=NOW)
    assert result["status"] == "OBSERVATION_ONLY"
    assert result["review_status"] == "MISSING"
    assert all("VALUE" not in blocker and "G3" not in blocker for blocker in result["blockers"])


@pytest.mark.parametrize("variant", ["array", "wrapped", "missing_namespace", "wrong_namespace", "future_source"])
def test_actual_release_rejects_test_or_incomplete_source_provenance(release, variant):
    root, payload, trust, publish = release
    pin_test_trust_root(trust)
    payload["namespace"] = "ACTUAL"
    source_content = ([{"namespace": "TEST_ONLY"}] if variant == "array" else
        {"records": [{"namespace": "SIMULATED"}]} if variant == "wrapped" else
        {"namespace": "ACTUAL"})
    raw_source = canonical_payload(source_content)
    (root / "source.json").write_bytes(raw_source)
    for binding in payload["gates"]:
        gate_path = root / binding["path"]
        gate = json.loads(gate_path.read_bytes())
        gate["namespace"] = "ACTUAL"
        source = gate["source_bindings"][0]
        source.update(namespace="ACTUAL", sha256=hashlib.sha256(raw_source).hexdigest())
        if variant == "missing_namespace":
            del source["namespace"]
        elif variant == "wrong_namespace":
            source["namespace"] = "TEST_ONLY"
        elif variant == "future_source":
            source["available_at"] = (NOW + timedelta(minutes=1)).isoformat()
        raw = canonical_payload(gate)
        gate_path.write_bytes(raw)
        binding["sha256"] = hashlib.sha256(raw).hexdigest()
    publish()
    with pytest.raises(ValueError, match="Test-only source|namespace and availability"):
        load_independent_admission(root, symbol="000333", now=NOW)
