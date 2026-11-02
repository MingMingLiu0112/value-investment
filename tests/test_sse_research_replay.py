"""TEST_ONLY offline replay: real compiler, explicit pins, no current publication."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from value_investment_agent.application.discovery import sse_main_screening as app
from test_sse_main_screening import inputs, NOW
from test_m2_opportunity_discovery import _tencent_payload, _sina_payload, _dividend_payload


def write(root, name, payload):
    path = root / "runtime/sse-main-screening/TEST_ONLY-replay" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(app._bytes(payload))
    return app._binding(root, path)


def save(root, source_inputs):
    screen, receipt = app.compile_inputs(root=root, inputs=source_inputs, now=NOW, run_id="TEST_ONLY")
    manifest = dict(schema_version=app.VERSION, scope=app.SCOPE, action="no_order",
        run_id="TEST_ONLY", generated_at=NOW.isoformat(), implementation=app.implementation(),
        inputs=source_inputs, result=write(root, "screening.json", screen),
        receipt=write(root, "receipt.json", receipt))
    binding = write(root, "manifest.json", manifest)
    return binding, manifest, screen, receipt


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def no_io(*args, **kwargs):
    raise AssertionError("Replay must not write, publish or make network requests")


def block_io(monkeypatch):
    monkeypatch.setattr(app, "write_new_bytes", no_io)
    monkeypatch.setattr(app, "publish_inputs", no_io)
    monkeypatch.setattr(app.sources, "collect_inputs", no_io)
    monkeypatch.setattr(requests.sessions.Session, "request", no_io)


def test_explicit_replay_ignores_current_pointer_preserves_payload_and_no_io(inputs, monkeypatch):
    root, source_inputs, payload = inputs
    payload["financial"]["public_financial_input"] = dict(
        period="2025-12-31", summary_binding=dict(path="TEST_ONLY/public-summary.json", sha256="b"*64))
    payload["financial"]["TEST_ONLY_metadata"] = {"retain": ["original"]}
    binding, manifest, screen, receipt = save(root, source_inputs)
    pointer = root / app.POINTER
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_bytes(b"TEST_ONLY deliberately invalid current pointer")
    before = snapshot(root)
    block_io(monkeypatch)
    result = app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)
    assert set(result) == {"screen", "receipt", "points", "financial_payload"}
    assert result["screen"] == screen and result["receipt"] == receipt
    assert result["points"] == payload["financial"]["points"]
    assert result["financial_payload"] == payload["financial"]
    assert result["screen"]["formal_eligibility"] is result["screen"]["buy_eligible"] is False
    assert before == snapshot(root)
    result["points"][0]["metadata"]["TEST_ONLY_mutation"] = True
    result["financial_payload"]["TEST_ONLY_metadata"]["retain"].append("changed")
    assert "TEST_ONLY_mutation" not in payload["financial"]["points"][0]["metadata"]
    assert payload["financial"]["TEST_ONLY_metadata"]["retain"] == ["original"]
    assert "TEST_ONLY_mutation" not in result["financial_payload"]["points"][0]["metadata"]


def test_capture_merged_points_before_engine_preserves_legacy_return(inputs, monkeypatch):
    root, source_inputs, payload = inputs
    period = payload["financial"]["points"][0]["period_label"]
    payload["financial"]["public_financial_input"] = dict(period=period, manifest={"TEST_ONLY": True})
    payload["financial"]["points"] = [p for p in payload["financial"]["points"]
                                     if p["field_name"] not in {"cash", "net_margin"}]
    original = deepcopy(payload["financial"])
    source_inputs["financial_supplement"] = dict(path="runtime/TEST_ONLY-statements.json", sha256="b"*64)
    ref = dict(path="runtime/TEST_ONLY-original.json", sha256="c"*64,
               source_url="https://datacenter-web.eastmoney.com/api/data/v1/get",
               acquired_at="2026-11-02T05:00:00+00:00")
    supplement = dict(status="COMPLETE", period=period, available_at=ref["acquired_at"],
        balance={"600001": dict(raw=dict(MONETARYFUNDS=123, TOTAL_ASSETS=1000, TOTAL_LIABILITIES=200),
                                source_ref=ref)}, income={}, cashflow={})
    monkeypatch.setattr(app.three_statements, "load", lambda *a, **kw: deepcopy(supplement))
    source_inputs["sina_supplements"] = [dict(path="runtime/TEST_ONLY-sina.json", sha256="d"*64)]
    secondary = dict(symbols={"600001": dict(period=period)}, available_at=ref["acquired_at"], errors=[])
    monkeypatch.setattr(app.sina_source, "load", lambda *a, **kw: deepcopy(secondary))
    secondary_point = dict(symbol="600001", field_name="net_margin", period_label=period,
        value="12", unit="percent", currency="CNY", validation_status="unverified",
        available_at=ref["acquired_at"], fetched_at=ref["acquired_at"], created_at=ref["acquired_at"],
        source_id="TEST_ONLY_SECONDARY", metadata=dict(statement_scope="consolidated",
                                                     automatic_cross_source_verification=False))
    monkeypatch.setattr(app, "sina_observations", lambda _: [deepcopy(secondary_point)])
    capture = {}
    native_build = app.build_discovery_receipt
    def build(**kwargs):
        assert capture["points"] == kwargs["financial_points"]
        assert capture["points"] is not kwargs["financial_points"]
        assert capture["financial_payload"] == original
        return native_build(**kwargs)
    expected = app.compile_inputs(root=root, inputs=source_inputs, now=NOW, run_id="TEST_ONLY")
    monkeypatch.setattr(app, "build_discovery_receipt", build)
    actual = app.compile_inputs(root=root, inputs=source_inputs, now=NOW, run_id="TEST_ONLY",
                                _research_capture=capture)
    assert actual == expected and len(actual) == 2
    cash = next(p for p in capture["points"] if p["field_name"] == "cash")
    assert cash["value"] == "123" and cash["validation_status"] == "unverified"
    assert secondary_point in capture["points"]
    assert capture["financial_payload"] == original
    assert not any(p["field_name"] in {"cash", "net_margin"} for p in original["points"])


@pytest.mark.parametrize("key,value,error", [
    ("schema_version", "old", "INVALID_SCOPED_SCREEN_MANIFEST"),
    ("scope", "ALL_A", "INVALID_SCOPED_SCREEN_MANIFEST"),
    ("action", "buy", "INVALID_SCOPED_SCREEN_MANIFEST"),
    ("implementation", {}, "SCREEN_IMPLEMENTATION_CHANGED_REPLAY_REQUIRED"),
    ("generated_at", "2026-11-02T06:00:00", "FUTURE_SCREEN_MANIFEST"),
    ("generated_at", "2099-01-01T00:00:00+00:00", "FUTURE_SCREEN_MANIFEST"),
])
def test_manifest_contract_rejected_before_compile(inputs, monkeypatch, key, value, error):
    root, source_inputs, _ = inputs
    _, manifest, _, _ = save(root, source_inputs)
    manifest[key] = value
    binding = write(root, "manifest.json", manifest)
    monkeypatch.setattr(app, "compile_inputs", no_io)
    with pytest.raises(ValueError, match=error):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)


@pytest.mark.parametrize("artifact", ["result", "receipt"])
def test_rehashed_stored_artifact_must_equal_actual_recomputation(inputs, artifact):
    root, source_inputs, _ = inputs
    _, manifest, _, _ = save(root, source_inputs)
    stored = app._read(root, manifest[artifact], result_artifact=artifact == "result")
    stored["TEST_ONLY_forged"] = True
    manifest[artifact] = write(root, "screening.json" if artifact == "result" else "receipt.json", stored)
    binding = write(root, "manifest.json", manifest)
    with pytest.raises(ValueError, match="SCREEN_"+("RESULT" if artifact == "result" else "RECEIPT")+"_REPLAY_MISMATCH"):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)


@pytest.mark.parametrize("artifact", ["manifest", "result", "receipt"])
def test_hash_damage_rejected(inputs, artifact):
    root, source_inputs, _ = inputs
    binding, manifest, _, _ = save(root, source_inputs)
    target = binding if artifact == "manifest" else manifest[artifact]
    path = root / target["path"]
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="SCREEN_SOURCE_HASH_MISMATCH"):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)


def test_naive_now_and_invalid_binding_rejected(inputs):
    root, source_inputs, _ = inputs
    binding, _, _, _ = save(root, source_inputs)
    with pytest.raises(ValueError, match="AWARE_RESEARCH_REPLAY_CUTOFF_REQUIRED"):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="EXACT_SCREEN_BINDING_REQUIRED"):
        app.replay_research_inputs(root=root, manifest_binding={**binding, "current": True}, now=NOW)


def test_manifest_changed_during_compile_cannot_return_stale_capture(inputs, monkeypatch):
    root, source_inputs, _ = inputs
    binding, _, _, _ = save(root, source_inputs)
    native = app.compile_inputs
    def changed(**kwargs):
        result = native(**kwargs)
        path = root / binding["path"]
        path.write_bytes(path.read_bytes()+b" ")
        return result
    monkeypatch.setattr(app, "compile_inputs", changed)
    with pytest.raises(ValueError, match="SCREEN_SOURCE_HASH_MISMATCH"):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)


def test_native_sources_1700_all_points_and_budget_candidates_no_pages(tmp_path, monkeypatch):
    # Synthetic full-count official response, native source hash verification and compiler.
    # Only the separately covered public-financial provenance verifier is a TEST_ONLY stub.
    root = tmp_path
    symbols = [str(600000+n) for n in range(1000)] + [str(601000+n) for n in range(700)]
    stamp = "2026-11-02T03:00:00+00:00"
    raw_official = dict(result=[dict(A_STOCK_CODE=s, SEC_NAME_CN="测试制造"+s,
                                    LIST_DATE="2000-01-01") for s in symbols],
                        pageHelp=dict(total=1700))
    raw_binding = dict(write(root, "official.raw.json", raw_official), fetched_at=stamp)
    official = app.sources._official(app._bytes(raw_official), stamp)
    tencent = dict(fetched_at=stamp, rows=[dict(_tencent_payload()["rows"][0],
                       code="sh"+s, name="测试制造"+s) for s in symbols])
    sina = dict(fetched_at=stamp, rows=[dict(_sina_payload()["rows"][0],
                    code=s, name="测试制造"+s) for s in symbols])
    dividend = dict(_dividend_payload(), fetched_at=stamp)
    points = [dict(symbol=s, field_name="cash", value="100", unit="CNY", currency="CNY",
                   period_label="2025-12-31", available_at=stamp, created_at=stamp, fetched_at=stamp,
                   validation_status="unverified", source_id="TEST_ONLY",
                   metadata=dict(statement_scope="consolidated", automatic_cross_source_verification=False))
              for s in symbols]
    financial = dict(points=points, public_financial_input=dict(period="2025-12-31",
                     summary_binding=dict(path="TEST_ONLY-public-summary.json", sha256="e"*64)))
    payload = dict(official=official, tencent=tencent, sina=sina, dividend=dividend, financial=financial)
    refs = {role: dict(write(root, role+".json", value), fetched_at=stamp)
            for role, value in payload.items()}
    refs["official"].update(raw=raw_binding, request_identity=deepcopy(app.sources.REQUEST))
    source_inputs = dict(schema_version=app.sources.VERSION, scope=app.SCOPE, action="no_order",
                         status="COMPLETE_INPUTS", started_at=stamp,
                         finished_at="2026-11-02T03:01:00+00:00", inputs=refs)
    calls = []
    monkeypatch.setattr(app, "verify_public_supplement", lambda **kw: calls.append(kw["payload"]))
    binding, _, _, _ = save(root, source_inputs)
    before = snapshot(root)
    block_io(monkeypatch)
    result = app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)
    assert len(calls) == 2
    assert len(result["screen"]["rows"]) == len(result["points"]) == 1700
    assert {p["symbol"] for p in result["points"]} == set(symbols)
    assert result["financial_payload"] == financial
    budget = [r for r in result["screen"]["rows"]
              if any(e["status"] == "BUDGET_EXCLUDED" for e in r["channel_evaluations"])]
    assert len(budget) > 100
    assert all(r["status"] == "CANDIDATE" for r in budget)
    assert set(r["symbol"] for r in budget) <= {p["symbol"] for p in result["points"]}
    assert before == snapshot(root)
    # Revalidation is cold: a prior successful result never bypasses original hashes.
    damaged = root / refs["financial"]["path"]
    damaged.write_bytes(damaged.read_bytes()+b" ")
    with pytest.raises(ValueError, match="source hash mismatch"):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)


def test_implementation_change_during_replay_rejected(inputs, monkeypatch):
    root, source_inputs, _ = inputs
    binding, _, _, _ = save(root, source_inputs)
    native = app.implementation
    calls = []
    def changing():
        calls.append(True)
        value = native()
        # Before compilation and in the compiled result stay identical;
        # the final check detects the implementation replacement.
        if len(calls) >= 3:
            value["TEST_ONLY_CHANGED_MODULE"] = "0"*64
        return value
    monkeypatch.setattr(app, "implementation", changing)
    with pytest.raises(ValueError, match="SCREEN_IMPLEMENTATION_CHANGED_DURING_REPLAY"):
        app.replay_research_inputs(root=root, manifest_binding=binding, now=NOW)
