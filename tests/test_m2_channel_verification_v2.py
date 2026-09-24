from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from value_investment_agent.m2_channel_verification_v2 import (
    ACTION_NO_ORDER,
    STATUS_INSUFFICIENT,
    STATUS_REJECTED,
    STATUS_VERIFIED,
    ChannelVerificationEvidenceV2,
    ChannelVerificationPolicyRule,
    VerificationCheckSpec,
    _validate_evidence_pit,
    build_m2_channel_verification_v2,
    evaluate_channel_verification,
    load_m2_channel_verification_policy_v2,
)


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 9, 23)
GENERATED_AT = datetime(2026, 9, 24, 10, 0, tzinfo=timezone(timedelta(hours=8)))


def _check(
    check_id: str,
    *,
    minimum_periods: int,
    required_fields: tuple[str, ...] = (),
    any_of_fields: tuple[str, ...] = (),
    required_metrics: tuple[str, ...] = (),
    any_of_metrics: tuple[str, ...] = (),
) -> VerificationCheckSpec:
    return VerificationCheckSpec(
        id=check_id,
        label=check_id,
        description=check_id,
        minimum_periods=minimum_periods,
        required_fields=required_fields,
        any_of_fields=any_of_fields,
        required_metrics=required_metrics,
        any_of_metrics=any_of_metrics,
    )


def _rule(
    channel: str,
    checks: tuple[VerificationCheckSpec, ...],
    *,
    normalization: tuple[str, ...] = (),
    negative_fields: tuple[str, ...] = (),
    counter_keywords: tuple[str, ...] = (),
) -> ChannelVerificationPolicyRule:
    return ChannelVerificationPolicyRule(
        channel=channel,
        policy_version="test-v2",
        profile_constraint="test",
        minimum_complete_fiscal_years=3,
        required_checks=checks,
        normalization_requirements=normalization,
        blocking_negative_fields=negative_fields,
        blocking_counter_keywords=counter_keywords,
    )


def _point(field_name: str, year: int, value: str) -> ChannelVerificationEvidenceV2:
    return ChannelVerificationEvidenceV2(
        symbol="600011",
        field_name=field_name,
        period_label=f"FY{year}",
        value=value,
        unit="CNY",
        validation_status="verified",
        source_name="test",
        source_url="https://example.invalid",
        source_sha256="a" * 64,
        published_at=None,
        fetched_at=f"{year}-12-31T12:00:00+08:00",
    )


def _dividend_rule() -> ChannelVerificationPolicyRule:
    return _rule(
        "dividend_cash_return",
        (
            _check("paid_history", minimum_periods=3, required_fields=("cash_dividend_per_share",)),
            _check("cfo", minimum_periods=3, required_fields=("operating_cash_flow",)),
            _check("fcf", minimum_periods=3, required_fields=("free_cash_flow",)),
            _check(
                "payout",
                minimum_periods=3,
                required_fields=("operating_cash_flow_to_net_income",),
                required_metrics=("declared_yield",),
            ),
            _check(
                "balance_sheet",
                minimum_periods=3,
                required_fields=("debt_ratio", "interest_bearing_debt"),
            ),
        ),
        normalization=("normalized_dividend_per_share",),
        negative_fields=("free_cash_flow", "operating_cash_flow"),
    )


def _full_dividend_evidence(free_cash_flow: str = "100") -> tuple[ChannelVerificationEvidenceV2, ...]:
    rows = []
    for year in (2023, 2024, 2025):
        rows.extend(
            [
                _point("cash_dividend_per_share", year, "0.5"),
                _point("operating_cash_flow", year, "200"),
                _point("free_cash_flow", year, free_cash_flow),
                _point("operating_cash_flow_to_net_income", year, "1.2"),
                _point("debt_ratio", year, "30"),
                _point("interest_bearing_debt", year, "10"),
                _point("normalized_dividend_per_share", year, "0.5"),
            ]
        )
    return tuple(rows)


def _evaluate(rule, evidence, market_context=None):
    return evaluate_channel_verification(
        rule,
        source_verdict="PENDING_DEEP_RESEARCH",
        evidence=evidence,
        market_context=market_context or {},
        missing_evidence=(),
        positives=(),
        counter_evidence=(),
    )


def test_dividend_negative_fcf_is_rejected():
    status, *_ = _evaluate(
        _dividend_rule(),
        _full_dividend_evidence(free_cash_flow="-1"),
        {"declared_yield": "0.08"},
    )
    assert status == STATUS_REJECTED


def test_dividend_one_year_is_insufficient_even_with_evidence():
    rule = _dividend_rule()
    one_year = tuple(item for item in _full_dividend_evidence() if item.period_label == "FY2025")
    status, *_ = _evaluate(rule, one_year, {"declared_yield": "0.08"})
    assert status == STATUS_INSUFFICIENT
    assert status != STATUS_VERIFIED


def test_special_dividend_only_is_not_normalized_verified():
    evidence = tuple(
        _point("special_dividend_per_share", year, "1")
        for year in (2023, 2024, 2025)
    )
    status, *_ = _evaluate(_dividend_rule(), evidence, {"declared_yield": "0.08"})
    assert status != STATUS_VERIFIED
    assert status == STATUS_INSUFFICIENT


def test_low_pe_only_is_not_value_verified():
    rule = _rule(
        "value",
        (
            _check("cash_earnings", minimum_periods=3, required_fields=("net_income", "operating_cash_flow")),
            _check("fcf", minimum_periods=3, required_fields=("free_cash_flow",)),
            _check("normalized", minimum_periods=3, required_fields=("normalized_earnings",)),
        ),
        normalization=("normalized_earnings",),
    )
    status, *_ = _evaluate(rule, (), {"pe_ttm": "4", "pb": "0.5"})
    assert status != STATUS_VERIFIED
    assert status == STATUS_INSUFFICIENT


def test_one_year_high_roe_is_not_quality_verified():
    rule = _rule(
        "quality",
        (
            _check("roe", minimum_periods=3, required_fields=("roe",)),
            _check("roic", minimum_periods=3, any_of_fields=("roic",)),
            _check(
                "cash_conversion",
                minimum_periods=3,
                required_fields=("operating_cash_flow", "operating_cash_flow_to_net_income"),
            ),
        ),
    )
    evidence = (
        _point("roe", 2025, "35"),
        _point("roic", 2025, "25"),
        _point("operating_cash_flow", 2025, "100"),
        _point("operating_cash_flow_to_net_income", 2025, "1"),
    )
    status, *_ = _evaluate(rule, evidence)
    assert status != STATUS_VERIFIED
    assert status == STATUS_INSUFFICIENT


def test_pending_with_evidence_but_missing_normalized_earnings_is_not_verified():
    rule = _rule(
        "cyclical",
        (
            _check("margin", minimum_periods=3, required_fields=("net_margin",)),
            _check("normalized", minimum_periods=3, required_fields=("normalized_earnings",)),
        ),
        normalization=("normalized_earnings",),
    )
    evidence = tuple(_point("net_margin", year, "10") for year in (2023, 2024, 2025))
    status, *_ = _evaluate(rule, evidence)
    assert len(evidence) > 0
    assert status != STATUS_VERIFIED
    assert status == STATUS_INSUFFICIENT


def test_pit_future_or_invalid_evidence_fails_closed():
    future = _point("net_income", 2025, "1")
    future = replace(
        future,
        fetched_at="2026-09-25T00:00:00+08:00",
    )
    with pytest.raises(ValueError, match="after evaluation"):
        _validate_evidence_pit((future,), generated_at=GENERATED_AT, as_of=AS_OF)

    invalid = replace(future, fetched_at="not-a-time")
    with pytest.raises(ValueError, match="invalid availability"):
        _validate_evidence_pit((invalid,), generated_at=GENERATED_AT, as_of=AS_OF)


def _require_real_artifacts() -> None:
    required = (
        "runtime/m2-ac8-research-reports-20260924-v1/report.json",
        "runtime/m2-ac9-coverage-audit-20260923-v2/report.json",
        "runtime/m2-live-20260923-v3/receipt.json",
        "runtime/m2-live-20260923-v3/retained-financial-points.json",
        "runtime/m2-live-20260923-v3/eastmoney-dividends.json",
    )
    if any(not (ROOT / item).exists() for item in required):
        pytest.skip("real M2 verification v2 inputs are not present in a clean CI checkout")


def test_real_frozen_18_leads_use_true_second_stage_semantics():
    _require_real_artifacts()
    policy = load_m2_channel_verification_policy_v2()
    assert len(policy.channel_policies) == 4
    for rule in policy.channel_policies:
        assert rule.minimum_complete_fiscal_years >= 3
        assert all(check.minimum_periods > 0 for check in rule.required_checks)

    batch = build_m2_channel_verification_v2(policy, root=ROOT, generated_at=GENERATED_AT)
    counts = batch.counts()
    assert batch.machine_status == "MACHINE_CHECKS_PASS"
    assert batch.acceptance_status == "CHECKPOINT_A_READY_FOR_HUMAN_RESUBMISSION"
    assert counts[STATUS_VERIFIED] == 0
    assert counts[STATUS_REJECTED] == 13
    assert counts[STATUS_INSUFFICIENT] == 5
    assert batch.source_binding["v1_status"] == "SEMANTICALLY_SUPERSEDED"
    assert batch.source_binding["pit_status"] == "PASS"
    assert all(item.action == ACTION_NO_ORDER for item in batch.results)
    by_symbol = {item.symbol: item for item in batch.results}
    assert by_symbol["002327"].status == STATUS_INSUFFICIENT
    assert by_symbol["002867"].status == STATUS_INSUFFICIENT
    assert by_symbol["600011"].status == STATUS_INSUFFICIENT


def test_real_hash_tamper_fails_closed():
    _require_real_artifacts()
    policy = load_m2_channel_verification_policy_v2()
    changed = replace(policy, ac8_report_sha256="b" * 64)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_m2_channel_verification_v2(changed, root=ROOT, generated_at=GENERATED_AT)
