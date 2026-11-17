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


def test_600519_blank_fx_stays_unassessable():
    result = read_first_research_input(root=_root(), symbol="600519",
                                       now=datetime.now(timezone.utc))
    cash = result["parent_cash_observation"]
    assert cash["status"] == "UNASSESSABLE"
    assert cash["reason"] == "PARENT_CASH_TWO_PRINTED_VALUES_REQUIRED:fx_cny"
    assert cash["ttm_flows"] == {}


def test_source_pair_selects_numbered_and_other_pair_selects_legacy(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(observation, "observe_numbered_first_input_parent_cash",
                        lambda **kwargs: called.append("numbered") or {"status": "NUMBERED"})
    monkeypatch.setattr(observation, "observe_first_input_parent_cash",
                        lambda **kwargs: called.append("legacy") or {"status": "LEGACY"})
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
    manifest["sources"][0]["sha256"] = "0" * 64
    assert run()["status"] == "LEGACY"
    assert called == ["numbered", "legacy"]


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
