"""E2 quote compatibility is independent of a legacy candidate's broken package."""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from types import SimpleNamespace

from value_investment_agent.application.product import quote_bridge
from value_investment_agent.application.product.first_input_quote_alignment_v1 import (
    read_first_input_quote_alignment,
)
from value_investment_agent.quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE


NOW = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)


def _case(root, *, cutoff="2026-11-17"):
    bundle = root / "runtime/quotes/bundle.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text(json.dumps({"finished_at": "2026-11-17T08:30:00+00:00",
                                  "references": {"600519": {}}, "documents": {}}), encoding="utf-8")
    pointer = root / quote_bridge.POINTER_PATH
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"schema_version": quote_bridge.POINTER_SCHEMA,
        "action": "no_order", "quotes": {"600519": {
            "quote_bundle": "runtime/quotes/bundle.json",
            "quote_bundle_sha256": sha256(bundle.read_bytes()).hexdigest(),
            "research_package": "runtime/legacy/missing-and-invalid.json",
            "research_package_sha256": "0" * 64}}}), encoding="utf-8")
    research = {"status": "SOURCE_BOUND_FIRST_INPUT_COMPILED", "symbol": "600519",
                "action": "no_order", "formal_eligibility": False,
                "research_as_of": cutoff,
                "input_computed_at": "2026-11-17T08:40:00+00:00",
                "receipt_binding": {"path": "runtime/e2/receipt.json", "sha256": "a" * 64}}
    return bundle, research


def test_new_e2_cutoff_uses_verified_close_without_inheriting_invalid_legacy_package(tmp_path, monkeypatch):
    bundle, research = _case(tmp_path)
    monkeypatch.setattr(quote_bridge, "quote_snapshot_from_bundle_file", lambda *a, **k:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE, quote_date=date(2026, 11, 17),
                        current_price="1457.70", blockers=[], evidence_refs=[]))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = read_first_input_quote_alignment(root=tmp_path, symbol="600519",
                                               first_input=research, now=NOW)
    assert result["status"] == "QUOTE_VERIFIED_FOR_RESEARCH_INPUT"
    assert result["quote_usable_for_e2_research"] is True
    assert result["quote_source_verified"] is True
    assert result["display_price"] == "1457.70"
    assert result["current_valuation_comparable"] is False
    assert result["condition_price"] is None and result["action"] == "no_order"
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    bundle.write_bytes(b"tampered")
    damaged = read_first_input_quote_alignment(root=tmp_path, symbol="600519",
                                                first_input=research, now=NOW)
    assert damaged["status"] == "UNASSESSABLE"
    assert damaged["quote_usable_for_e2_research"] is False


def test_quote_after_e2_cutoff_cannot_be_used_for_that_research(tmp_path, monkeypatch):
    _, research = _case(tmp_path, cutoff="2026-11-16")
    monkeypatch.setattr(quote_bridge, "quote_snapshot_from_bundle_file", lambda *a, **k:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE, quote_date=date(2026, 11, 17),
                        current_price="1457.70", blockers=[], evidence_refs=[]))
    result = read_first_input_quote_alignment(root=tmp_path, symbol="600519",
                                               first_input=research, now=NOW)
    assert result["status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert result["quote_usable_for_e2_research"] is False
    assert result["current_valuation_comparable"] is False


def test_same_day_quote_collected_after_e2_computation_requires_new_revalidation(tmp_path, monkeypatch):
    _, research = _case(tmp_path)
    research["input_computed_at"] = "2026-11-17T06:26:35+00:00"
    monkeypatch.setattr(quote_bridge, "quote_snapshot_from_bundle_file", lambda *a, **k:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE, quote_date=date(2026, 11, 17),
                        current_price="1457.70", blockers=[], evidence_refs=[]))
    result = read_first_input_quote_alignment(root=tmp_path, symbol="600519",
                                               first_input=research, now=NOW)
    assert result["status"] == "QUOTE_AFTER_E2_RESEARCH_SNAPSHOT"
    assert result["quote_source_verified"] is True
    assert result["quote_usable_for_e2_research"] is False
    assert result["display_price"] == "1457.70"
    assert result["current_valuation_comparable"] is False
