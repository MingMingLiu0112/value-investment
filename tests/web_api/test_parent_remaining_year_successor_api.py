"""TEST_ONLY public successor dispatch and isolation; no economic acceptance."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from value_investment_agent.application.product import first_research_input_view_v1 as view
from value_investment_agent.application.product import parent_remaining_year_successor_view as successor_view
from value_investment_agent.application.research import parent_remaining_year_alignment as successor_alignment
from web_api.test_held_continuity_api import client_for


NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def bound(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(json.dumps(value, sort_keys=True).encode())
    return {"path": path, "sha256": sha256(target.read_bytes()).hexdigest()}


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def case(root):
    predecessor = {"path": "runtime/TEST_ONLY-prior.json", "sha256": "a" * 64}
    spec = bound(root, "runtime/TEST_ONLY-spec.json", dict(
        period_end="2026-09-30", research_as_of="2026-11-18",
        computed_at=NOW.isoformat(), scenarios={name: {"field_provenance": {}}
                                              for name in ("bear", "base", "bull")}))
    receipt = bound(root, "runtime/TEST_ONLY-receipt.json", dict(
        schema_version="parent-remaining-year-successor-receipt-v1",
        symbol="600887", action="no_order", spec_binding=spec,
        predecessor_binding=predecessor, input_descriptor_sha256="d" * 64))
    bound(root, view.REGISTRY, dict(schema_version=view.SCHEMA,
        action="no_order", cases={"600887": {"receipt": receipt}}))
    rows = [{"year": 2026, "policy": {"operating_cash": "100"}}]
    result = dict(symbol="600887", action="no_order", formal_eligibility=False,
        successor_adopted=False, main_range_adopted=False,
        predecessor_binding=predecessor, input_descriptor_sha256="d" * 64,
        research_case={"symbol": "600887"}, valuation={"bear_value": "1",
        "base_value": "2", "bull_value": "3"},
        compiled={"scenarios": {name: {"calculation": {"annual_rows": rows}}
                                for name in ("bear", "base", "bull")},
                  "assumptions": {}},
        annual_recalculations={name: {"full_year": {"cfo": {
            "fact_9m": "40", "forecast_q4": "60", "total": "100",
            "fact_classification": "FACT",
            "forecast_classification": "FORECAST_ASSUMPTION"}}}
                               for name in ("bear", "base", "bull")},
        research_result={"blockers": ["ECONOMIC_RESEARCH_NOT_APPROVED"]},
        source_bindings=[], package={"sources": []})
    return receipt, result


def test_successor_api_keeps_full_conditional_research_and_blocks_f2(tmp_path, monkeypatch):
    receipt, result = case(tmp_path)
    calls = []
    monkeypatch.setattr(successor_view, "replay_parent_remaining_year_successor",
        lambda **kwargs: (calls.append(kwargs), deepcopy(result))[1])
    monkeypatch.setattr(view, "replay_first_research_input", lambda **_:
        (_ for _ in ()).throw(AssertionError("v1 replay must not see successor")))
    alignment_calls = []
    monkeypatch.setattr(successor_alignment, "read_parent_remaining_year_alignment",
        lambda **kwargs: (alignment_calls.append(kwargs), dict(
            schema_version="parent-remaining-year-alignment-v1",
            status="BLOCKED", reason_codes=["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"],
            research_artifact_kind="PARENT_REMAINING_YEAR_SUCCESSOR_RECEIPT",
            receipt_binding=receipt, candidate_binding=receipt,
            input_descriptor_sha256="d" * 64, checks=[], evidence_bindings=[],
            currentpricecomparison=False, formal_eligibility=False,
            action="no_order"))[1])
    client, _ = client_for(tmp_path, tmp_path / "TEST_ONLY-private.jsonl", monkeypatch)
    before = files(tmp_path)
    assert client.get("/api/v1/private/portfolio/held-continuity").status_code == 401
    response = client.get("/api/v1/first-research-inputs/600887")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "SOURCE_BOUND_FIRST_INPUT_COMPILED"
    assert body["receipt_binding"] == receipt
    assert body["predecessor_binding"] == result["predecessor_binding"]
    assert body["annual_ledgers"]["base"]["rows"][0]["policy"]["operating_cash"] == "100"
    assert body["annual_recalculations"]["base"]["full_year"]["cfo"]["fact_9m"] == "40"
    assert body["valuation"]["base_value"] == "2"
    assert body["direct_cash_alignment"]["reason_codes"] == [
        "EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]
    assert body["e2_quote_alignment"]["quote_usable_for_e2_research"] is False
    assert body["condition_price"] is None and body["current_price"] is None
    assert body["formal_eligibility"] is False and body["action"] == "no_order"
    assert len(calls) == 1 and calls[0]["receipt_binding"] == receipt
    assert len(alignment_calls) == 1 and alignment_calls[0]["receipt_binding"] == receipt
    assert files(tmp_path) == before


def test_unknown_receipt_schema_never_falls_through_to_v1(tmp_path, monkeypatch):
    receipt, _ = case(tmp_path)
    changed = json.loads((tmp_path / receipt["path"]).read_text())
    changed["schema_version"] = "TEST_ONLY-unknown-receipt"
    replacement = bound(tmp_path, "runtime/TEST_ONLY-unknown.json", changed)
    bound(tmp_path, view.REGISTRY, dict(schema_version=view.SCHEMA,
        action="no_order", cases={"600887": {"receipt": replacement}}))
    monkeypatch.setattr(view, "replay_first_research_input", lambda **_:
        (_ for _ in ()).throw(AssertionError("unknown receipt reached v1")))
    before = files(tmp_path)
    result = view.read_first_research_input(root=tmp_path, symbol="600887", now=NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["reason"] == "FIRST_INPUT_RECEIPT_SCHEMA_UNSUPPORTED"
    assert files(tmp_path) == before


def test_successor_symbol_and_hash_fail_closed(tmp_path, monkeypatch):
    receipt, result = case(tmp_path)
    monkeypatch.setattr(successor_view, "replay_parent_remaining_year_successor",
        lambda **_: deepcopy(result))
    result["symbol"] = "000333"
    before = files(tmp_path)
    rejected = view.read_first_research_input(root=tmp_path, symbol="600887", now=NOW)
    assert rejected["status"] == "UNASSESSABLE"
    assert rejected["formal_eligibility"] is False
    assert files(tmp_path) == before
    result["symbol"] = "600887"
    (tmp_path / receipt["path"]).write_bytes(b"TEST_ONLY changed receipt")
    before = files(tmp_path)
    rejected = view.read_first_research_input(root=tmp_path, symbol="600887", now=NOW)
    assert rejected["status"] == "UNASSESSABLE"
    assert "changed" in rejected["reason"]
    assert files(tmp_path) == before
