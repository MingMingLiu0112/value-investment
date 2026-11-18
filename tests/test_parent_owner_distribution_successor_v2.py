"""Implemented owner-distribution successor contract and replay tests."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from test_parent_remaining_year_successor import case as predecessor_case_fixture
from value_investment_agent.application.research import parent_remaining_year_successor as predecessor
from value_investment_agent.application.research import parent_owner_distribution_successor_v2 as successor
from value_investment_agent.application.research.direct_owner_cash_research_v1 import _bytes

NOW = datetime(2026, 11, 18, 8, tzinfo=timezone.utc)


def write_bound(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _bytes(value)
    target.write_bytes(data)
    return {"path": path, "sha256": sha256(data).hexdigest()}


@pytest.fixture
def case(tmp_path, monkeypatch):
    root, old_spec, _ = predecessor_case_fixture.__wrapped__(tmp_path, monkeypatch)
    old_binding = write_bound(root, "runtime/TEST_ONLY-predecessor-spec.json", old_spec)
    old_built = predecessor.build_parent_remaining_year_successor(
        root=root, spec_binding=old_binding,
        output_dir=root / "runtime/TEST_ONLY-predecessor-output", now=NOW,
    )
    old_receipt_path = root / old_built["receipt_binding"]["path"]
    old_receipt_bytes = old_receipt_path.read_bytes()
    original = write_bound(root, "runtime/TEST_ONLY-distribution-original.json", {
        "classification": "FACT", "scope": successor.SCOPE, "paid_date": "2026-06-05",
    })
    reconciliation = write_bound(root, "runtime/TEST_ONLY-distribution-reconciliation.json", {
        "per_share_cny": "0.90", "eligible_shares": "10",
        "total_cny": "9.00", "currency": "CNY",
    })
    spec = {
        "schema_version": successor.SCHEMA, "action": "no_order",
        "predecessor_binding": old_built["receipt_binding"],
        "distribution_evidence": {"original": original, "reconciliation": reconciliation},
        "distribution": {
            "period_year": 2026, "paid_date": "2026-06-05", "per_share_cny": "0.90",
            "eligible_shares": "10", "total_cny": "9.00",
            "scope": successor.SCOPE, "currency": "CNY", "classification": "FACT",
        },
        "computed_at": NOW.isoformat(), "research_as_of": "2026-11-18",
        "run_id": "TEST_ONLY-owner-distribution-successor",
        "research_version": "TEST_ONLY-owner-distribution-successor-v2",
        "reasons": "TEST_ONLY paid distribution must enter first-year owner cash and clean surplus",
    }
    return root, spec, old_built, old_receipt_bytes


def test_shared_service_recalculates_three_scenarios_and_preserves_history(case):
    root, spec, old_built, old_receipt_bytes = case
    binding = write_bound(root, "runtime/TEST_ONLY-owner-distribution-spec.json", spec)
    built = successor.build_parent_owner_distribution_successor(
        root=root, spec_binding=binding,
        output_dir=root / "runtime/TEST_ONLY-owner-distribution-output", now=NOW,
    )
    replayed = successor.replay_parent_owner_distribution_successor(
        root=root, receipt_binding=built["receipt_binding"], now=NOW,
    )
    assert replayed["formal_eligibility"] is False
    assert replayed["successor_adopted"] is replayed["main_range_adopted"] is False
    assert replayed["action"] == "no_order"
    assert replayed["valuation"]["model_version"] == "direct-owner-cash-equity-v2"
    amount = Decimal(spec["distribution"]["total_cny"])
    calculations = replayed["valuation"]["assumptions"]["scenario_calculations"]
    for name in ("bear", "base", "bull"):
        first = calculations[name]["annual_rows"][0]
        assert Decimal(first["scheduled_owner_distribution_cny"]) == amount
        assert Decimal(first["total_owner_distribution_cny"]) == (
            Decimal(first["scheduled_owner_distribution_cny"])
            + Decimal(first["conditional_distribution_cny"])
        )
        assert Decimal(first["closing_cash_cny"]) == (
            Decimal(first["cash_before_distribution_cny"])
            - Decimal(first["total_owner_distribution_cny"])
        )
        assert Decimal(first["closing_distribution_capacity_cny"]) == (
            Decimal(first["scheduled_capacity_limit_cny"])
            - Decimal(first["total_owner_distribution_cny"])
        )
        assert Decimal(first["closing_book_equity_cny"]) == (
            Decimal(first["opening_book_equity_cny"])
            + Decimal(first["net_income_assumption_cny"])
            - Decimal(first["total_owner_distribution_cny"])
        )
        assert Decimal(calculations[name]["crosscheck_difference_cny"]) == 0
        assert (Decimal(calculations[name]["conditional_equity_value_cny"])
                == Decimal(calculations[name]["dividend_crosscheck_equity_value_cny"]))
        assert (Decimal(calculations[name]["conditional_equity_value_cny"])
                == Decimal(calculations[name]["residual_income_equity_value_cny"]))
        assert all(Decimal(row["scheduled_owner_distribution_cny"]) == 0
                   for row in calculations[name]["annual_rows"][1:])
    old_receipt = root / old_built["receipt_binding"]["path"]
    assert old_receipt.read_bytes() == old_receipt_bytes
    assert spec["predecessor_binding"] in replayed["source_bindings"]
    assert binding in replayed["source_bindings"]
    for evidence in spec["distribution_evidence"].values():
        assert evidence in replayed["source_bindings"]


@pytest.mark.parametrize("fault,error", [
    ("amount", "TOTAL_RECONCILIATION"),
    ("date", "AFTER_RESEARCH_AS_OF"),
    ("year", "FIRST_YEAR_MISMATCH"),
    ("scope", "SCOPE_CURRENCY_OR_CLASSIFICATION"),
    ("currency", "SCOPE_CURRENCY_OR_CLASSIFICATION"),
    ("classification", "SCOPE_CURRENCY_OR_CLASSIFICATION"),
])
def test_invalid_distribution_contract_is_rejected(case, fault, error):
    root, spec, _, _ = case
    if fault == "amount":
        spec["distribution"]["total_cny"] = "9.01"
    elif fault == "date":
        spec["distribution"]["paid_date"] = "2026-11-19"
    elif fault == "year":
        spec["distribution"]["period_year"] = 2025
    elif fault == "scope":
        spec["distribution"]["scope"] = "CONSOLIDATED"
    elif fault == "currency":
        spec["distribution"]["currency"] = "USD"
    else:
        spec["distribution"]["classification"] = "FORECAST_ASSUMPTION"
    binding = write_bound(root, "runtime/TEST_ONLY-bad-owner-distribution-spec.json", spec)
    with pytest.raises(ValueError, match=error):
        successor.build_parent_owner_distribution_successor(
            root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-bad-owner-distribution-output", now=NOW,
        )


@pytest.mark.parametrize("fault", ["spec", "evidence", "result"])
def test_hash_tampering_is_rejected(case, fault):
    root, spec, _, _ = case
    binding = write_bound(root, "runtime/TEST_ONLY-tamper-owner-distribution-spec.json", spec)
    built = successor.build_parent_owner_distribution_successor(
        root=root, spec_binding=binding,
        output_dir=root / "runtime/TEST_ONLY-tamper-owner-distribution-output", now=NOW,
    )
    target_binding = {
        "spec": binding,
        "evidence": spec["distribution_evidence"]["original"],
        "result": json.loads((root / built["receipt_binding"]["path"]).read_text(encoding="utf-8"))["result_binding"],
    }[fault]
    target = root / target_binding["path"]
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        successor.replay_parent_owner_distribution_successor(
            root=root, receipt_binding=built["receipt_binding"], now=NOW,
        )


def test_predecessor_receipt_schema_and_no_order_boundary_are_strict(case):
    root, spec, _, _ = case
    receipt_path = root / spec["predecessor_binding"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["schema_version"] = "wrong"
    spec["predecessor_binding"] = write_bound(
        root, "runtime/TEST_ONLY-wrong-predecessor.json", receipt,
    )
    binding = write_bound(root, "runtime/TEST_ONLY-wrong-predecessor-spec.json", spec)
    with pytest.raises(ValueError, match="EXACT_PREDECESSOR"):
        successor.build_parent_owner_distribution_successor(
            root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-wrong-predecessor-output", now=NOW,
        )
