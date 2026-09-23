from __future__ import annotations

from copy import deepcopy
import shutil
from pathlib import Path
import json

import pytest

from value_investment_agent.m1_distribution_package_builder import (
    build_dividend_result,
    dividend_results_by_symbol,
    load_dividend_package_attempts,
)
from value_investment_agent.m1_valuation_package_builder import (
    build_descriptor,
    load_descriptor_payloads,
)


ROOT = Path(__file__).resolve().parents[1]


def test_three_m1_dividend_packages_load_without_merging_lifecycle_states():
    attempts = load_dividend_package_attempts(ROOT)
    by_symbol = {attempt.symbol: attempt for attempt in attempts}

    assert {attempt.symbol for attempt in attempts} == {
        "000651",
        "600741",
        "600887",
    }
    assert all(attempt.error is None for attempt in attempts)
    assert all(attempt.result.action == "no_order" for attempt in attempts)
    assert all(
        attempt.result.cash_return_status == "PARTIAL"
        for attempt in attempts
    )

    yili = by_symbol["600887"].result
    yili_final = next(
        record
        for record in yili.history.records
        if record.fiscal_period == "FY2025-final"
    )
    assert yili_final.status == "proposed"
    assert yili_final.approval_date is None
    assert yili_final.ex_date is None
    assert yili_final.payment_date is None

    gree = by_symbol["000651"].result
    gree_payload = json.loads(
        (
            ROOT
            / "config"
            / "m1-distribution-packages-v1"
            / "000651-mature-manufacturing.json"
        ).read_text(encoding="utf-8")
    )
    source_ids = {source["id"] for source in gree_payload["sources"]}
    assert {
        "gree_fy2024_final_implementation",
        "gree_fy2025_interim_implementation",
        "gree_quote_20260922",
    } <= source_ids
    gree_final = next(
        record
        for record in gree.history.records
        if record.fiscal_period == "FY2025-final"
    )
    paid = [
        record
        for record in gree.history.records
        if record.status == "paid"
    ]
    assert gree_final.status == "proposed"
    assert gree_final.approval_date is None
    assert len(paid) == 2
    assert {record.fiscal_period for record in paid} == {
        "FY2024-final",
        "FY2025-interim",
    }
    assert {
        record.ex_date.isoformat() for record in paid
    } == {"2025-08-29", "2026-01-23"}
    assert {
        record.payment_date.isoformat() for record in paid
    } == {"2025-08-29", "2026-01-23"}


def test_two_m1_dividend_packages_preserve_fact_policy_forecast_layers():
    attempts = load_dividend_package_attempts(ROOT)
    by_symbol = {attempt.symbol: attempt for attempt in attempts}

    yili = by_symbol["600887"].result
    yili_final = next(
        record
        for record in yili.history.records
        if record.fiscal_period == "FY2024-final"
    )
    yili_interim = next(
        record
        for record in yili.history.records
        if record.fiscal_period == "FY2025-interim"
    )
    assert yili_final.status == "paid"
    assert yili_final.ex_date.isoformat() == "2025-06-06"
    assert yili_final.payment_date.isoformat() == "2025-06-06"
    assert yili_interim.status == "paid"
    assert yili_interim.ex_date.isoformat() == "2025-12-17"
    assert yili_interim.payment_date.isoformat() == "2025-12-17"
    assert {
        snapshot.yield_type
        for snapshot in yili.yield_snapshots
    } == {"current", "normalized"}
    assert next(
        snapshot
        for snapshot in yili.yield_snapshots
        if snapshot.basis_type == "trailing_paid"
    ).status == "READY"
    assert next(
        snapshot
        for snapshot in yili.yield_snapshots
        if snapshot.yield_type == "normalized"
    ).status == "NOT_READY"
    assert "special_dividend_observation" in yili.capacity.capital_allocation_context
    assert "no forward payout forecast" in yili.sustainability.coverage_context

    huayu = by_symbol["600741"].result
    huayu_final = next(
        record
        for record in huayu.history.records
        if record.fiscal_period == "FY2024-final"
    )
    assert huayu_final.status == "paid"
    assert huayu_final.ex_date.isoformat() == "2025-07-25"
    assert huayu_final.payment_date.isoformat() == "2025-07-25"
    assert next(
        snapshot
        for snapshot in huayu.yield_snapshots
        if snapshot.basis_type == "declared"
    ).status == "READY"
    assert next(
        snapshot
        for snapshot in huayu.yield_snapshots
        if snapshot.yield_type == "normalized"
    ).status == "NOT_READY"
    assert "special_dividend_observation" in huayu.capacity.capital_allocation_context
    assert "no forward payout forecast" in huayu.sustainability.coverage_context

    gree = by_symbol["000651"].result
    gree_trailing = next(
        snapshot
        for snapshot in gree.yield_snapshots
        if snapshot.basis_type == "trailing_paid"
    )
    gree_declared = next(
        snapshot
        for snapshot in gree.yield_snapshots
        if snapshot.basis_type == "declared"
    )
    assert gree_trailing.status == "READY"
    assert str(gree_trailing.dividend_per_share) == "3.00"
    assert str(gree_trailing.dividend_yield) == "0.07857517024620220010476689366"
    assert gree_declared.status == "READY"
    assert str(gree_declared.dividend_per_share) == "2.00"
    assert next(
        snapshot
        for snapshot in gree.yield_snapshots
        if snapshot.yield_type == "normalized"
    ).status == "NOT_READY"
    assert "special_dividend_observation" in gree.capacity.capital_allocation_context
    assert "no forward payout forecast" in gree.sustainability.coverage_context


def test_valuation_descriptor_attaches_the_matching_dividend_package():
    descriptor = build_descriptor(
        load_descriptor_payloads(ROOT)["600887"],
        root=ROOT,
    )

    assert descriptor.distribution_result is not None
    assert descriptor.distribution_result.symbol == "600887"
    assert descriptor.distribution_result.sustainability.status == "LOW"
    assert descriptor.distribution_result.cash_return_status == "PARTIAL"
    assert descriptor.distribution_result.action == "no_order"


def test_dividend_package_rejects_changed_source_hash():
    package_path = (
        ROOT
        / "config"
        / "m1-distribution-packages-v1"
        / "600741-mature-manufacturing.json"
    )
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    payload = deepcopy(payload)
    payload["sources"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="source hash changed"):
        build_dividend_result(payload, root=ROOT)


def test_dividend_package_rejects_an_order_like_action():
    package_path = (
        ROOT
        / "config"
        / "m1-distribution-packages-v1"
        / "600887-quality-compounder.json"
    )
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    payload = deepcopy(payload)
    payload["action"] = "buy"

    with pytest.raises(ValueError, match="no_order"):
        build_dividend_result(payload, root=ROOT)


def test_dividend_results_by_symbol_rejects_duplicate_symbols(tmp_path):
    package_dir = tmp_path / "config" / "m1-distribution-packages-v1"
    package_dir.mkdir(parents=True)
    source = (
        ROOT
        / "runtime"
        / "valuation-research"
        / "china-cost-of-equity-m1-20260923"
        / "evidence.json"
    )
    package = json.loads(
        (
            ROOT
            / "config"
            / "m1-distribution-packages-v1"
            / "600741-mature-manufacturing.json"
        ).read_text(encoding="utf-8")
    )
    source_target = (
        tmp_path
        / "runtime"
        / "valuation-research"
        / "china-cost-of-equity-m1-20260923"
        / "evidence.json"
    )
    source_target.parent.mkdir(parents=True)
    shutil.copyfile(source, source_target)
    package["sources"] = [
        {
            "id": "temp_source",
            "kind": "valuation_reference",
            "location": str(source_target.relative_to(tmp_path)).replace("\\", "/"),
            "sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(),
        }
    ]
    for index in range(2):
        (package_dir / f"{index}.json").write_text(
            json.dumps(package, ensure_ascii=False),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="Duplicate"):
        dividend_results_by_symbol(tmp_path)
