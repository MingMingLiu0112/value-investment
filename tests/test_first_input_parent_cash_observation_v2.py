"""Direct first-input consumer checks against retained public originals."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.product.first_research_input_view_v1 import read_first_research_input
from value_investment_agent.application.research import first_input_parent_cash_observation_v2 as observation


def _root():
    value = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not value:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for retained official-source replay")
    return Path(value).resolve(strict=True)


def test_000568_numbered_first_input_keeps_sparse_columns_unknown():
    result = read_first_research_input(root=_root(), symbol="000568",
                                       now=datetime.now(timezone.utc))
    cash = result["parent_cash_observation"]
    assert result["status"] == "SOURCE_BOUND_FIRST_INPUT_COMPILED"
    assert cash["status"] == "SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS"
    assert cash["action"] == "no_order" and cash["formal_eligibility"] is False
    assert cash["whole_statement_reconciled"] is False
    assert cash["ttm_flows"] == {}
    assert "borrowings_received_cny" in cash["unknown_fields"]["2025-12-31"]
    assert "fx_cny" in cash["unknown_fields"]["2026-06-30"]
    assert all("fx_cny" not in period["rows"] for period in cash["periods"])
    assert len(cash["source_bindings"]) == 3


def test_600519_partial_rows_keep_fx_unknown():
    result = read_first_research_input(root=_root(), symbol="600519",
                                       now=datetime.now(timezone.utc))
    cash = result["parent_cash_observation"]
    assert cash["status"] == "SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS"
    assert [len(period["rows"]) for period in cash["periods"]] == [9, 8]
    assert cash["periods"][0]["rows"]["closing_cash_and_equivalents_cny"]["columns"][0]["value"] == "84730758118.65"
    assert cash["periods"][1]["rows"]["opening_cash_and_equivalents_cny"]["columns"][0]["value"] == "84730758118.65"
    assert all("fx_cny" not in period["rows"] for period in cash["periods"])
    assert all("fx_cny" in fields for fields in cash["unknown_fields"].values())
    assert cash["whole_statement_reconciled"] is False
    assert cash["ttm_flows"] == {}


def test_source_pair_selects_numbered_partial_and_other_pair_selects_legacy(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(observation, "observe_numbered_first_input_parent_cash",
                        lambda **kwargs: called.append("numbered") or {"status": "NUMBERED"})
    monkeypatch.setattr(observation, "observe_first_input_parent_cash",
                        lambda **kwargs: called.append("legacy") or {"status": "LEGACY"})
    monkeypatch.setattr(observation, "observe_partial_first_input_parent_cash",
                        lambda **kwargs: called.append("partial") or {"status": "PARTIAL"})
    path = tmp_path / "runtime" / "manifest.json"
    path.parent.mkdir()
    manifest = {"sources": [dict(report_period=period, sha256=digest)
                            for period, digest in observation.NUMBERED_SOURCE_HASHES]}

    def run():
        raw = json.dumps(manifest).encode()
        path.write_bytes(raw)
        return observation.observe_first_input_parent_cash_by_source(
            root=tmp_path, native_facts_binding=dict(
                path="runtime/manifest.json", sha256=sha256(raw).hexdigest()),
            now=datetime.now(timezone.utc))

    assert run()["status"] == "NUMBERED"
    manifest["sources"] = [dict(report_period=period, sha256=digest)
                           for period, digest in observation.PARTIAL_SOURCE_HASHES]
    assert run()["status"] == "PARTIAL"
    manifest["sources"][0]["sha256"] = "0" * 64
    assert run()["status"] == "LEGACY"
    assert called == ["numbered", "partial", "legacy"]


def test_matching_sources_do_not_fallback_after_numbered_failure(tmp_path, monkeypatch):
    path = tmp_path / "runtime" / "manifest.json"
    path.parent.mkdir()
    raw = json.dumps({"sources": [dict(report_period=p, sha256=h)
                                   for p, h in observation.NUMBERED_SOURCE_HASHES]}).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(observation, "observe_numbered_first_input_parent_cash",
                        lambda **kwargs: {"status": "UNASSESSABLE", "reason": "SOURCE_SHA256_MISMATCH"})
    monkeypatch.setattr(observation, "observe_first_input_parent_cash",
                        lambda **kwargs: pytest.fail("legacy fallback after numbered failure"))
    result = observation.observe_first_input_parent_cash_by_source(
        root=tmp_path, native_facts_binding=dict(
            path="runtime/manifest.json", sha256=sha256(raw).hexdigest()),
        now=datetime.now(timezone.utc))
    assert result == {"status": "UNASSESSABLE", "reason": "SOURCE_SHA256_MISMATCH"}


def test_partial_parser_failure_does_not_return_verified_rows(monkeypatch):
    root = _root()
    manifest = root / "runtime/e2-first-input-600519-20261117/native-facts-20261117T062245490703Z.json"
    monkeypatch.setattr(observation, "observe_parent_cash_rows",
                        lambda **kwargs: (_ for _ in ()).throw(ValueError("PARTIAL_TABLE_DAMAGED")))
    result = observation.observe_first_input_parent_cash_by_source(
        root=root, native_facts_binding=dict(
            path=manifest.relative_to(root).as_posix(),
            sha256=sha256(manifest.read_bytes()).hexdigest()),
        now=datetime.now(timezone.utc))
    assert result["status"] == "UNASSESSABLE"
    assert result["reason"] == "PARTIAL_TABLE_DAMAGED"
    assert result["periods"] == [] and result["source_bindings"] == []
