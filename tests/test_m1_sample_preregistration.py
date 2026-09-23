from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

from value_investment_agent.m1_sample_preregistration import (
    DEFAULT_PREREGISTRATION_PATH,
    load_m1_sample_preregistration,
)


def _payload() -> dict:
    return json.loads(
        DEFAULT_PREREGISTRATION_PATH.read_text(encoding="utf-8")
    )


def test_preregistration_loads_exactly_twenty_unique_companies():
    registered = load_m1_sample_preregistration()

    assert registered.as_of.isoformat() == "2026-09-23"
    assert len(registered.companies) == 20
    assert len({item.symbol for item in registered.companies}) == 20
    assert [item.symbol for item in registered.companies[:3]] == [
        "600519",
        "000333",
        "601088",
    ]


def test_preregistration_keeps_required_research_categories_visible():
    registered = load_m1_sample_preregistration()
    entries = {item.symbol: item for item in registered.companies}

    for profile_id in ("quality_compounder", "mature_manufacturing", "cyclical_cash_return"):
        assert sum(item.profile_id == profile_id for item in registered.companies) >= 2
    assert entries["600519"].profile_id == "quality_compounder"
    assert entries["000333"].profile_id == "mature_manufacturing"
    assert entries["601088"].profile_id == "cyclical_cash_return"
    assert any(
        item.selection_bucket == "PROFILE_REPLICATION"
        for item in registered.companies
    )
    assert any(
        item.selection_bucket == "UNSUPPORTED_MODEL"
        for item in registered.companies
    )
    assert any(
        item.selection_bucket == "DATA_INSUFFICIENT"
        for item in registered.companies
    )
    assert any(
        item.selection_bucket == "RISK_COUNTEREXAMPLE"
        for item in registered.companies
    )


def test_supported_profile_entries_use_the_registered_primary_model():
    registered = load_m1_sample_preregistration()

    supported = {
        "quality_compounder": "residual_income_or_equity_value",
        "mature_manufacturing": "fcff",
        "cyclical_cash_return": "cyclical_normalized",
    }
    for item in registered.companies:
        if item.profile_id == "unsupported_profile":
            assert item.primary_model is None
        else:
            assert item.primary_model == supported[item.profile_id]


def test_preregistration_contains_no_order_or_position_fields():
    payload = _payload()
    assert payload["action"] == "no_order"
    forbidden = {
        "trade_approved",
        "target_weight",
        "position_size",
        "order_quantity",
        "proposed_entry",
        "buy",
        "sell",
        "live_eligible",
    }

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def test_preregistration_rejects_duplicate_symbols():
    payload = _payload()
    payload["companies"].append(dict(payload["companies"][0]))
    with tempfile.TemporaryDirectory(prefix="m1-sample-") as directory:
        path = Path(directory) / "preregistration.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unique"):
            load_m1_sample_preregistration(path)


def test_preregistration_rejects_execution_keys_below_root():
    payload = _payload()
    payload["companies"][0]["target_weight"] = "0.10"
    with tempfile.TemporaryDirectory(prefix="m1-sample-") as directory:
        path = Path(directory) / "preregistration.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="execution keys"):
            load_m1_sample_preregistration(path)
