"""Versioned D2 source composition; official PDF bytes are replayed in place."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import (
    operating_q3_issuer_plan_loader_v8_600519 as loader,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 11, 14, 0, tzinfo=timezone.utc)


def _base(**kwargs):
    binding = kwargs.get("binding")
    if binding is not None and binding != {"path": "old.json", "sha256": "a" * 64}:
        raise ValueError("BASE_BINDING_CHANGED")
    return dict(symbol="600519", source_binding={"path": "old.json", "sha256": "a" * 64},
        snapshot_fingerprint="b" * 64, evidence=[{"id": "old"}],
        action="no_order", formal_eligibility=False)


def test_separate_plan_source_bound_without_changing_old_evidence(monkeypatch):
    monkeypatch.setattr(loader.prior, "load_current", _base)
    result = loader.load_current(root=ROOT, symbol="600519", now=NOW)
    replay = loader.load_current(root=ROOT, symbol="600519", now=NOW,
        binding=result["source_binding"])
    assert result == replay
    assert result["evidence"] == [{"id": "old"}]
    assert result["issuer_dividend_plan"]["fiscal_years"] == [2024, 2025, 2026]
    assert result["issuer_dividend_plan"]["available_at"] <= NOW.isoformat()
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


def test_changed_plan_binding_rejected(monkeypatch):
    monkeypatch.setattr(loader.prior, "load_current", _base)
    result = loader.load_current(root=ROOT, symbol="600519", now=NOW)
    result["source_binding"]["plan_original"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="V8_ISSUER_PLAN_SOURCE_CHANGED"):
        loader.load_current(root=ROOT, symbol="600519", now=NOW,
            binding=result["source_binding"])


def test_future_plan_and_other_symbol_rejected(monkeypatch):
    monkeypatch.setattr(loader.prior, "load_current", _base)
    with pytest.raises(ValueError, match="NOT_YET_ACQUIRED"):
        loader.load_current(root=ROOT, symbol="600519",
            now=datetime(2024, 8, 10, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="SYMBOL_NOT_SUPPORTED"):
        loader.load_current(root=ROOT, symbol="600887", now=NOW)
