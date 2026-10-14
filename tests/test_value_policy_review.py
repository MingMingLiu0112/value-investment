from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest

from test_value_price_policy import NOW, fixture
from value_investment_agent.application.decision import value_price_policy as app


def review_fixture(tmp_path, monkeypatch):
    plan, draft, source = fixture(tmp_path, monkeypatch, rules=False)
    prepared = app.prepare_value_price_policy(tmp_path, draft, now=NOW)
    review = dict(schema_version="tl11-p5-value-model-review-v1", symbol="600887", action="no_order",
        reviewed_at=NOW.isoformat(), formal_eligibility=False, portfolio_eligibility=None,
        direct_hash_checks=deepcopy(draft["source_bindings"]),
        scenarios={k: plan[k] for k in ("bear", "base", "bull")},
        **{k: plan[k] for k in ("model_id", "model_type", "model_version", "valuation_input_version", "valuation_date")})
    manifest = dict(schema_version="value-policy-review-manifest-v1", action="no_order", items={"600887": {}})
    directory = tmp_path / "artifacts/current/tl11-p5-20261014"
    directory.mkdir(parents=True)
    docs = dict(model_review=review, draft=draft, preparation=prepared)
    for role, payload in docs.items():
        path = directory / ("value-" + role + ".json")
        raw = json.dumps(payload).encode()
        path.write_bytes(raw)
        manifest["items"]["600887"][role] = dict(path=path.relative_to(tmp_path).as_posix(),
            sha256=hashlib.sha256(raw).hexdigest())
    manifest_path = tmp_path / app.REVIEW_MANIFEST_PATH
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return plan, source, docs, manifest, manifest_path


def test_public_review_read_is_bound_readonly_and_never_selects_fraction(tmp_path, monkeypatch):
    _, _, docs, _, _ = review_fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    result = app.load_value_policy_review(tmp_path, "600887", NOW)
    assert result["model_review"] == docs["model_review"]
    assert result["draft"] == docs["draft"]
    assert result["preparation"]["status"] == "BLOCKED"
    assert all(v is None for v in result["preparation"]["draft_prices"].values())
    assert len(result["source_bindings"]) == 4
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("fault", ["file", "source", "basis", "future", "schema", "private", "escape", "unknown"])
def test_public_review_invalid_or_stale_bindings_raise_failclosed(tmp_path, monkeypatch, fault):
    plan, source, docs, manifest, manifest_path = review_fixture(tmp_path, monkeypatch)
    now = NOW
    if fault == "file":
        (tmp_path / manifest["items"]["600887"]["draft"]["path"]).write_bytes(b"tampered")
    elif fault == "source":
        source.write_bytes(b"changed")
    elif fault == "basis":
        plan["valuation_input_version"] = "c" * 64
    elif fault == "future":
        now -= timedelta(days=1)
    elif fault in {"schema", "private"}:
        doc = docs["model_review"]
        if fault == "schema":
            doc["action"] = "order"
        else:
            doc["direct_hash_checks"].append(dict(path="runtime/private/journal.json", sha256="a" * 64))
        binding = manifest["items"]["600887"]["model_review"]
        raw = json.dumps(doc).encode()
        (tmp_path / binding["path"]).write_bytes(raw)
        binding["sha256"] = hashlib.sha256(raw).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif fault == "escape":
        manifest["items"]["600887"]["draft"]["path"] = "artifacts/current/tl11-p5-20261014/value-../../private.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        app.load_value_policy_review(tmp_path, "000333" if fault == "unknown" else "600887", now)


@pytest.mark.parametrize("matches", [True, False])
def test_optional_isolated_receipt_must_match_consumed_valuation(tmp_path, monkeypatch, matches):
    plan, _, docs, manifest, manifest_path = review_fixture(tmp_path, monkeypatch)
    path = manifest_path.parent / "value-isolated-replay.json"
    receipt = dict(schema_version="value-direct-input-isolated-replay-v1", symbol="600887", action="no_order",
        expected_valuation_sha256=plan["valuation_input_version"],
        replayed_valuation_sha256=plan["valuation_input_version"] if matches else "b" * 64,
        status="EXACT_VALUATION_REPLAY", full_payload_match=True)
    raw = json.dumps(receipt).encode()
    path.write_bytes(raw)
    docs["model_review"]["isolated_replay"] = dict(receipt_binding=dict(
        path=path.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(raw).hexdigest()))
    binding = manifest["items"]["600887"]["model_review"]
    raw = json.dumps(docs["model_review"]).encode()
    (tmp_path / binding["path"]).write_bytes(raw)
    binding["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    if matches:
        assert len(app.load_value_policy_review(tmp_path, "600887", NOW)["source_bindings"]) == 5
    else:
        with pytest.raises(ValueError, match="prove current valuation"):
            app.load_value_policy_review(tmp_path, "600887", NOW)
