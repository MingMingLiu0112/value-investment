"""TEST_ONLY transports; source-native acceptance is executed separately."""
import copy
from datetime import datetime, timezone
import hashlib
import json

import pytest
import requests

from value_investment_agent.application.research import public_evidence as mod

REQUESTS = [
    dict(symbol="600519", issuer_name="TEST_ONLY A", period="2025-12-31", exchange="SSE"),
    dict(symbol="000544", issuer_name="TEST_ONLY B", period="2025-12-31", exchange="SZSE"),
]


@pytest.fixture
def transport(monkeypatch):
    calls = []
    def acquire(**kwargs):
        calls.append(kwargs["symbol"])
        folder = kwargs["output_dir"]
        folder.mkdir(parents=True)
        original = folder / "original.pdf"
        original.write_bytes(b"TEST_ONLY original " + kwargs["symbol"].encode())
        source = dict(symbol=kwargs["symbol"], period=kwargs["period"],
            path=original.relative_to(kwargs["root"]).as_posix(),
            sha256=mod._digest(original), source_url="https://static.cninfo.com.cn/TEST_ONLY.PDF",
            available_at="2026-01-01T00:00:00+00:00")
        packet = dict(source=source, fetched_at=source["available_at"], published_date="2026-01-01", completed_at="2026-01-01T00:00:01+00:00")
        mod._write(folder / "receipt.json", packet)
        return packet
    def retained(**kwargs):
        path = mod._bound(kwargs["root"], kwargs["receipt_binding"])
        packet = json.loads(path.read_bytes())
        source = packet["source"]
        if source["symbol"] != kwargs["symbol"] or source["period"] != kwargs["period"]:
            raise ValueError("TEST_ONLY identity")
        if mod._digest(kwargs["root"] / source["path"]) != source["sha256"]:
            raise ValueError("TEST_ONLY original drift")
        return packet
    def enrich(root, source, points, **kwargs):
        return dict(source_extraction=dict(identity=dict(source=vars(source)), page_texts=["TEST_ONLY"]),
                    adopted_points=[], action="no_order", formal_eligibility=False, symbol=source.symbol, period=source.period, evaluation_at=datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr(mod, "acquire_official_report", acquire)
    monkeypatch.setattr(mod, "load_retained_official_report", retained)
    monkeypatch.setattr(mod, "enrich_retained_company", enrich)
    return calls, acquire


def run(root, **kwargs):
    return mod.run_public_evidence(root=root, requests=kwargs.pop("requests", copy.deepcopy(REQUESTS)),
        output_dir=root / "runtime" / kwargs.pop("folder", "new"), **kwargs)


def test_acquire_replay_no_network_preserves_clocks_and_existing_consumer(tmp_path, transport):
    first = run(tmp_path, allow_network=True)
    before = mod.load_bundle(tmp_path, first)
    replay = run(tmp_path, folder="replay", previous_binding=first)
    after = mod.load_bundle(tmp_path, replay)
    assert transport[0] == ["600519", "000544"]
    assert all(i["reused"] for i in after["items"])
    assert [i["receipt"] for i in before["items"]] == [i["receipt"] for i in after["items"]]
    from value_investment_agent.infrastructure.screening.financial_export_v2 import load_retained_financial_export
    points, export = load_retained_financial_export(tmp_path / after["financial_export"]["path"],
                                                   evaluation_at=datetime.now(timezone.utc))
    assert points == []
    assert len(export["value_enrichment_sources"]) == 2
    mod.publish_public_evidence(tmp_path, replay)
    status = mod.public_evidence_status(tmp_path)
    assert status["status"] == "VERIFIED"
    assert status["exchanges"]["BSE"] == {"requested": 0, "verified": 0}
    assert all(row["fetched_at"] == "2026-01-01T00:00:00+00:00" for row in status["items"])
    assert status["formal_eligibility"] is False


def test_one_failure_continues_next_issuer(tmp_path, transport, monkeypatch):
    def fail(**kwargs):
        if kwargs["symbol"] == "600519":
            raise requests.Timeout("TEST_ONLY")
        return transport[1](**kwargs)
    monkeypatch.setattr(mod, "acquire_official_report", fail)
    binding = run(tmp_path, allow_network=True)
    packet = mod.load_bundle(tmp_path, binding)
    assert [i["status"] for i in packet["items"]] == ["MISSING", "VERIFIED"]
    assert packet["status"] == "PARTIAL"


def test_failed_refresh_explicit_historical_reference(tmp_path, transport, monkeypatch):
    first = run(tmp_path, allow_network=True)
    raw = (tmp_path / first["path"]).read_bytes()
    monkeypatch.setattr(mod, "acquire_official_report",
                        lambda **_: (_ for _ in ()).throw(requests.Timeout("TEST_ONLY")))
    new = run(tmp_path, folder="refresh", previous_binding=first, refresh=True, allow_network=True)
    packet = mod.load_bundle(tmp_path, new)
    assert all(i["status"] == "PARTIAL" and i["reused"] for i in packet["items"])
    assert all("RETAINED_HISTORY" in i["reason"] for i in packet["items"])
    assert (tmp_path / first["path"]).read_bytes() == raw


def test_corrupt_original_no_silent_network_fallback(tmp_path, transport):
    first = run(tmp_path, allow_network=True)
    packet = mod.load_bundle(tmp_path, first)
    receipt = json.loads((tmp_path / packet["items"][0]["receipt"]["path"]).read_bytes())
    (tmp_path / receipt["source"]["path"]).write_bytes(b"CORRUPT")
    next_binding = run(tmp_path, folder="again", previous_binding=first, allow_network=True)
    assert mod.load_bundle(tmp_path, next_binding)["items"][0]["status"] == "CONFLICT"
    assert len(transport[0]) == 2
    with pytest.raises(ValueError):
        mod.publish_public_evidence(tmp_path, first)
    assert not (tmp_path / mod.POINTER).exists()


def test_missing_no_network_not_zero_candidate_claim(tmp_path, transport):
    binding = run(tmp_path)
    mod.publish_public_evidence(tmp_path, binding)
    status = mod.public_evidence_status(tmp_path)
    assert status["status"] == "PARTIAL" and len(status["items"]) == 2
    assert all(r["status"] == "MISSING" for r in status["items"])
    assert not transport[0]


@pytest.mark.parametrize("change", ["hash", "clock", "scope", "request"])
def test_bundle_tampering_rejected(tmp_path, transport, change):
    binding = run(tmp_path, allow_network=True)
    path = tmp_path / binding["path"]
    packet = json.loads(path.read_bytes())
    if change == "clock":
        packet["generated_at"] = "2099-01-01T00:00:00+00:00"
    elif change == "scope":
        packet["formal_eligibility"] = True
    elif change == "request":
        packet["items"][0]["request"]["symbol"] = "600887"
    else:
        packet["ignored"] = "changes bytes"
    path.write_text(json.dumps(packet), encoding="utf-8")
    if change != "hash":
        binding["sha256"] = mod._digest(path)
    with pytest.raises(ValueError):
        mod.load_bundle(tmp_path, binding)


def test_readonly_status_no_network_no_writes(tmp_path, transport, monkeypatch):
    binding = run(tmp_path, allow_network=True)
    mod.publish_public_evidence(tmp_path, binding)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(mod, "acquire_official_report", lambda **_: pytest.fail("GET network"))
    monkeypatch.setattr(mod, "enrich_retained_company", lambda *a, **_: pytest.fail("GET writes extraction"))
    assert mod.public_evidence_status(tmp_path)["status"] == "VERIFIED"
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}


def test_api_independent_from_formal_publication_and_private_unlock(tmp_path):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.get("/api/v1/public-evidence")
    assert response.status_code == 200
    assert response.json()["reason"] == "PUBLIC_EVIDENCE_NOT_RUN"
    assert not (tmp_path / "runtime").exists()


def _rebind_test_json(root, binding, payload):
    """TEST_ONLY semantic mutations retain valid byte hashes at every edited edge."""
    path = root / binding["path"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    binding["sha256"] = mod._digest(path)


@pytest.mark.parametrize("change, error", [
    ("scope", "BUNDLE_SCOPE_INVALID"),
    ("receipt", "BUNDLE_ITEM_RECEIPT_REQUIRED"),
    ("export_facts", "FINANCIAL_EXPORT_DIFFERS_FROM_BOUND_FACTS"),
    ("export_sources", "FINANCIAL_EXPORT_DIFFERS_FROM_BOUND_FACTS"),
])
def test_rehashed_manifest_cannot_overclaim_or_change_export(tmp_path, transport, change, error):
    binding = run(tmp_path, allow_network=True)
    packet = mod.load_bundle(tmp_path, binding)
    mod.publish_public_evidence(tmp_path, binding)
    pointer_before = (tmp_path / mod.POINTER).read_bytes()
    if change == "scope":
        packet["scope"] = "ALL_MARKET"
    elif change == "receipt":
        packet["items"][0]["receipt"] = None
    else:
        export = json.loads((tmp_path / packet["financial_export"]["path"]).read_bytes())
        if change == "export_facts":
            export["annual_points"] = [{"data_point_id": "TEST_ONLY_UNBOUND_FACT"}]
        else:
            export["value_enrichment_sources"].pop()
        _rebind_test_json(tmp_path, packet["financial_export"], export)
    _rebind_test_json(tmp_path, binding, packet)
    with pytest.raises(ValueError, match=error):
        mod.load_bundle(tmp_path, binding)
    with pytest.raises(ValueError, match=error):
        mod.publish_public_evidence(tmp_path, binding)
    assert (tmp_path / mod.POINTER).read_bytes() == pointer_before
    assert mod.public_evidence_status(tmp_path)["status"] == "CONFLICT"


@pytest.mark.parametrize("part", ["fact_snapshot", "financial_export"])
@pytest.mark.parametrize("refresh", [False, True])
def test_corrupt_previous_closure_cannot_reextract_or_download(tmp_path, transport, monkeypatch, part, refresh):
    binding = run(tmp_path, allow_network=True)
    packet = mod.load_bundle(tmp_path, binding)
    mod.publish_public_evidence(tmp_path, binding)
    pointer_before = (tmp_path / mod.POINTER).read_bytes()
    bundle_before = (tmp_path / binding["path"]).read_bytes()
    ref = packet["items"][0][part] if part == "fact_snapshot" else packet[part]
    (tmp_path / ref["path"]).write_bytes(b"TEST_ONLY corrupted closure")
    monkeypatch.setattr(mod, "acquire_official_report", lambda **_: pytest.fail("corruption triggered download"))
    monkeypatch.setattr(mod, "enrich_retained_company", lambda *a, **k: pytest.fail("corruption triggered re-extraction"))
    with pytest.raises(ValueError, match="EVIDENCE_HASH_OR_PATH_INVALID"):
        run(tmp_path, folder="blocked-replay", previous_binding=binding,
            allow_network=True, refresh=refresh)
    assert not (tmp_path / "runtime/blocked-replay").exists()
    assert (tmp_path / mod.POINTER).read_bytes() == pointer_before
    assert (tmp_path / binding["path"]).read_bytes() == bundle_before
    assert mod.public_evidence_status(tmp_path)["status"] == "CONFLICT"


@pytest.mark.parametrize("change, error", [
    ("bundle_before_export", "FINANCIAL_EXPORT_SCOPE_OR_CLOCK_INVALID"),
    ("receipt_after_bundle", "BUNDLE_RECEIPT_IDENTITY_OR_CLOCK_INVALID"),
    ("facts_before_receipt", "FACT_SNAPSHOT_SCOPE_OR_CLOCK_INVALID"),
    ("facts_after_export", "FACT_SNAPSHOT_SCOPE_OR_CLOCK_INVALID"),
])
def test_rehashed_closure_rejects_inverted_nonfuture_clocks(tmp_path, transport, change, error):
    binding = run(tmp_path, allow_network=True)
    packet = mod.load_bundle(tmp_path, binding)
    item = packet["items"][0]
    if change == "bundle_before_export":
        packet["generated_at"] = "2000-01-01T00:00:00+00:00"
    elif change == "receipt_after_bundle":
        # All clocks are past: exercise ordering, not the future-date guard.
        packet["generated_at"] = "2025-12-31T00:00:00+00:00"
        export = json.loads((tmp_path / packet["financial_export"]["path"]).read_bytes())
        export["generated_at"] = packet["generated_at"]
        _rebind_test_json(tmp_path, packet["financial_export"], export)
    else:
        facts = json.loads((tmp_path / item["fact_snapshot"]["path"]).read_bytes())
        if change == "facts_before_receipt":
            facts["evaluation_at"] = "2026-01-01T00:00:00+00:00"
        else:
            export = json.loads((tmp_path / packet["financial_export"]["path"]).read_bytes())
            export["generated_at"] = "2026-01-01T00:00:02+00:00"
            _rebind_test_json(tmp_path, packet["financial_export"], export)
        _rebind_test_json(tmp_path, item["fact_snapshot"], facts)
    _rebind_test_json(tmp_path, binding, packet)
    with pytest.raises(ValueError, match=error):
        mod.load_bundle(tmp_path, binding)
