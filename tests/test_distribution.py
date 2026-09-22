from datetime import date
from decimal import Decimal
import json

import pytest

from value_investment_agent.distribution import (
    CAPACITY_UNKNOWN,
    CAPACITY_READY,
    DIVIDEND_APPROVED,
    DIVIDEND_ORDINARY,
    DIVIDEND_PAID,
    DIVIDEND_PROPOSED,
    DIVIDEND_RESEARCH_PARTIAL,
    DIVIDEND_SPECIAL,
    HISTORY_PARTIAL,
    HISTORY_UNKNOWN,
    SUSTAINABILITY_UNKNOWN,
    YIELD_CURRENT,
    YIELD_NORMALIZED,
    YIELD_NORMALIZED_SCENARIO,
    YIELD_READY,
    YIELD_TRAILING_PAID,
    DividendHistory,
    DividendRecord,
    DividendResearchResult,
    DistributionCapacity,
    DividendSustainabilityAssessment,
    DividendYieldSnapshot,
    build_dividend_yield_snapshot,
    build_trailing_paid_yield_snapshot,
)
from value_investment_agent.fixed_sample_admission import (
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    DECISION_PAUSE_PRODUCTION_VALUATION,
    DECISION_RESOLVE_MODEL_INPUTS,
    FixedSampleAdmissionPolicy,
    review_fixed_sample,
)
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_bridge import bridge
from value_investment_agent.quote_snapshot import QuoteSnapshot
from value_investment_agent.valuation_models.base import ValuationResult


REF = {"id": "fixture", "path": "fixtures/distribution.json", "sha256": "fixture-hash"}
QUOTE_REF = {"id": "quote", "path": "fixtures/quote.json", "sha256": "quote-hash"}


def _paid_record(symbol="600519", *, dps="1.00", fiscal="FY2024", ex=date(2026, 9, 10), pay=date(2026, 9, 12), dtype=DIVIDEND_ORDINARY):
    return DividendRecord(
        symbol=symbol,
        fiscal_period=fiscal,
        dividend_type=dtype,
        status=DIVIDEND_PAID,
        dividend_per_share=Decimal(dps),
        currency="CNY",
        announcement_date=None,
        approval_date=None,
        ex_date=ex,
        payment_date=pay,
        known_at=pay,
        share_basis="ordinary shares",
        evidence_refs=[REF],
    )


def _quote(symbol="600519", *, price="100", quote_date=date(2026, 9, 18), status="verified_close"):
    return QuoteSnapshot(
        symbol=symbol,
        quote_date=quote_date if status == "verified_close" else None,
        current_price=Decimal(price) if status == "verified_close" else None,
        status=status,
        evidence_refs=[QUOTE_REF] if status == "verified_close" else [],
    )


def test_dividend_record_keeps_proposal_approval_and_payment_separate():
    proposed = DividendRecord(
        symbol="600519",
        fiscal_period="FY2025",
        dividend_type=DIVIDEND_ORDINARY,
        status=DIVIDEND_PROPOSED,
        dividend_per_share=Decimal("27.993"),
        currency="CNY",
        announcement_date=date(2026, 4, 20),
        approval_date=None,
        ex_date=None,
        payment_date=None,
        known_at=date(2026, 4, 20),
        share_basis="ordinary shares",
        evidence_refs=[REF],
    )
    assert proposed.status == DIVIDEND_PROPOSED
    assert proposed.ex_date is None and proposed.payment_date is None

    approved = DividendRecord(
        symbol="600519",
        fiscal_period="FY2025",
        dividend_type=DIVIDEND_ORDINARY,
        status=DIVIDEND_APPROVED,
        dividend_per_share=Decimal("27.993"),
        currency="CNY",
        announcement_date=date(2026, 4, 20),
        approval_date=date(2026, 5, 20),
        ex_date=None,
        payment_date=None,
        known_at=date(2026, 5, 20),
        share_basis="ordinary shares",
        evidence_refs=[REF],
    )
    assert approved.status == DIVIDEND_APPROVED
    assert approved.approval_date == date(2026, 5, 20)
    assert approved.ex_date is None and approved.payment_date is None

    with pytest.raises(ValueError, match="cannot carry ex/payment"):
        DividendRecord(
            symbol="600519",
            fiscal_period="FY2025",
            dividend_type=DIVIDEND_ORDINARY,
            status=DIVIDEND_APPROVED,
            dividend_per_share=Decimal("27.993"),
            currency="CNY",
            announcement_date=date(2026, 4, 20),
            approval_date=date(2026, 5, 20),
            ex_date=date(2026, 5, 25),
            payment_date=None,
            known_at=date(2026, 5, 20),
            share_basis="ordinary shares",
            evidence_refs=[REF],
        )

    with pytest.raises(ValueError, match="ex/payment"):
        DividendRecord(
            symbol="600519",
            fiscal_period="FY2025",
            dividend_type=DIVIDEND_ORDINARY,
            status=DIVIDEND_PROPOSED,
            dividend_per_share=Decimal("27.993"),
            currency="CNY",
            announcement_date=date(2026, 4, 20),
            approval_date=None,
            ex_date=None,
            payment_date=date(2026, 5, 1),
            known_at=date(2026, 4, 20),
            share_basis="ordinary shares",
            evidence_refs=[REF],
        )

    paid = _paid_record()
    assert paid.status == DIVIDEND_PAID
    assert paid.payment_date is not None and paid.known_at >= paid.payment_date


def test_dividend_record_rejects_future_information():
    with pytest.raises(ValueError, match="known_at cannot precede"):
        DividendRecord(
            symbol="600519",
            fiscal_period="FY2025",
            dividend_type=DIVIDEND_ORDINARY,
            status=DIVIDEND_PROPOSED,
            dividend_per_share=Decimal("27.993"),
            currency="CNY",
            announcement_date=date(2026, 3, 20),
            approval_date=None,
            ex_date=None,
            payment_date=None,
            known_at=date(2026, 1, 1),
            share_basis="ordinary shares",
            evidence_refs=[REF],
        )

    future_record = _paid_record(pay=date(2026, 10, 1))
    with pytest.raises(ValueError, match="as_of"):
        DividendHistory(
            symbol="600519",
            records=(future_record,),
            as_of=date(2026, 9, 1),
            evidence_refs=[REF],
            status=HISTORY_PARTIAL,
        )


def test_dividend_history_is_fact_not_forecast():
    history = DividendHistory(
        symbol="600519",
        records=(_paid_record(), _paid_record(dps="2.00", fiscal="FY2025", dtype=DIVIDEND_SPECIAL, ex=date(2026, 9, 11), pay=date(2026, 9, 13))),
        as_of=date(2026, 9, 20),
        evidence_refs=[REF],
        status=HISTORY_PARTIAL,
        blockers=["future payment not claimed"],
    )
    policy = history.as_policy()
    assert policy["status"] == HISTORY_PARTIAL
    assert "forecast" not in json.dumps(policy, ensure_ascii=False)
    assert {record["fiscal_period"] for record in policy["records"]} == {"FY2024", "FY2025"}


def test_distribution_capacity_is_profile_aware_and_price_free():
    quality = DistributionCapacity(
        symbol="600519",
        profile_id="quality_compounder",
        as_of=date(2026, 9, 20),
        earnings_basis={"parent_net_profit_cny": Decimal("100")},
        cash_flow_basis={"parent_cfo_cny": Decimal("80")},
        maintenance_reinvestment={"parent_capex_cny": Decimal("5")},
        restricted_cash_or_upstream_constraints={"restricted_cash_cny": Decimal("10")},
        status=CAPACITY_UNKNOWN,
        blockers=["full-year remittance not disclosed"],
        evidence_refs=[REF],
    )
    policy = quality.as_policy()
    assert "price" not in json.dumps(policy, ensure_ascii=False)
    assert quality.profile_id == "quality_compounder"

    cyclical = DistributionCapacity(
        symbol="601088",
        profile_id="cyclical_cash_return",
        as_of=date(2026, 9, 20),
        cash_flow_basis={"normalized_cash_generation_cny": None},
        maintenance_reinvestment={"maintenance_capex_cny": None},
        status=CAPACITY_UNKNOWN,
        blockers=["normalized cash generation not registered"],
    )
    assert cyclical.profile_id == "cyclical_cash_return"
    assert cyclical.status == CAPACITY_UNKNOWN

    with pytest.raises(ValueError, match="known confidence"):
        DistributionCapacity(
            symbol="600519",
            profile_id="quality_compounder",
            as_of=date(2026, 9, 20),
            bear_capacity=Decimal("1"),
            base_capacity=Decimal("2"),
            bull_capacity=Decimal("3"),
            status=CAPACITY_READY,
            confidence="UNKNOWN",
            evidence_refs=[REF],
        )


def test_unknown_sustainability_is_a_valid_fail_closed_result():
    unknown = DividendSustainabilityAssessment(
        symbol="601088",
        profile_id="cyclical_cash_return",
        as_of=date(2026, 9, 20),
        status=SUSTAINABILITY_UNKNOWN,
        coverage_context="cycle profit not normalized",
        capital_requirements="maintenance capex not registered",
        balance_sheet_pressure="not independently reconciled",
        cycle_risk="commodity cycle",
        growth_source="not identified",
        breakers=("sustained coal-price decline",),
        confidence="UNKNOWN",
        reasons=(),
        blockers=["normalized distribution capacity missing"],
        evidence_refs=[],
    )
    assert unknown.status == SUSTAINABILITY_UNKNOWN
    with pytest.raises(ValueError, match="reasons"):
        DividendSustainabilityAssessment(
            symbol="600519",
            profile_id="quality_compounder",
            as_of=date(2026, 9, 20),
            status="HIGH",
            coverage_context="history and cash coverage",
            capital_requirements="moderate",
            balance_sheet_pressure="low",
            cycle_risk="low",
            growth_source="stable",
            breakers=(),
            confidence="中",
            reasons=(),
            blockers=[],
            evidence_refs=[REF],
        )
    with pytest.raises(ValueError, match="known confidence"):
        DividendSustainabilityAssessment(
            symbol="600519",
            profile_id="quality_compounder",
            as_of=date(2026, 9, 20),
            status="HIGH",
            coverage_context="history and cash coverage",
            capital_requirements="moderate",
            balance_sheet_pressure="low",
            cycle_risk="low",
            growth_source="stable",
            breakers=(),
            confidence="UNKNOWN",
            reasons=("fixture reason",),
            blockers=[],
            evidence_refs=[REF],
        )


def test_yield_snapshot_requires_a_legal_matching_quote():
    record = _paid_record()
    snapshot = build_dividend_yield_snapshot(
        dividend=record,
        quote=_quote(),
        basis_type=YIELD_TRAILING_PAID,
        dividend_basis_period="FY2024",
        yield_type=YIELD_CURRENT,
    )
    assert snapshot.status == YIELD_READY
    assert snapshot.dividend_yield == Decimal("0.01")

    with pytest.raises(ValueError, match="securities differ"):
        build_dividend_yield_snapshot(
            dividend=record,
            quote=_quote(symbol="000333"),
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period="FY2024",
            yield_type=YIELD_CURRENT,
        )
    with pytest.raises(ValueError, match="verified close"):
        build_dividend_yield_snapshot(
            dividend=record,
            quote=_quote(status="PENDING_EXTERNAL_DATA"),
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period="FY2024",
            yield_type=YIELD_CURRENT,
        )
    with pytest.raises(ValueError, match="currencies differ"):
        build_dividend_yield_snapshot(
            dividend=record,
            quote=_quote(),
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period="FY2024",
            yield_type=YIELD_CURRENT,
            currency="USD",
        )
    with pytest.raises(ValueError, match="share bases differ"):
        build_dividend_yield_snapshot(
            dividend=record,
            quote=_quote(),
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period="FY2024",
            yield_type=YIELD_CURRENT,
            share_basis="H shares",
        )


def test_yield_snapshot_rejects_point_in_time_lookahead():
    future = _paid_record(pay=date(2026, 9, 30))
    with pytest.raises(ValueError, match="quote date cannot precede"):
        build_dividend_yield_snapshot(
            dividend=future,
            quote=_quote(quote_date=date(2026, 9, 18)),
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period="FY2025",
            yield_type=YIELD_CURRENT,
        )


def test_high_current_yield_does_not_upgrade_sustainability():
    high_yield_record = _paid_record(dps="10.00")
    high_yield = build_dividend_yield_snapshot(
        dividend=high_yield_record,
        quote=_quote(price="100"),
        basis_type=YIELD_TRAILING_PAID,
        dividend_basis_period="FY2024",
        yield_type=YIELD_CURRENT,
    )
    unknown = DividendSustainabilityAssessment(
        symbol="600519",
        profile_id="quality_compounder",
        as_of=date(2026, 9, 20),
        status=SUSTAINABILITY_UNKNOWN,
        coverage_context="not complete",
        capital_requirements="not complete",
        balance_sheet_pressure="not complete",
        cycle_risk="not complete",
        growth_source="not complete",
        breakers=(),
        confidence="UNKNOWN",
        reasons=(),
        blockers=["future payout not verified"],
    )
    result = DividendResearchResult(
        symbol="600519",
        profile_id="quality_compounder",
        history=DividendHistory(
            symbol="600519",
            records=(high_yield_record,),
            as_of=date(2026, 9, 20),
            evidence_refs=[REF],
            status=HISTORY_UNKNOWN,
        ),
        capacity=DistributionCapacity(
            symbol="600519",
            profile_id="quality_compounder",
            as_of=date(2026, 9, 20),
            status=CAPACITY_UNKNOWN,
        ),
        sustainability=unknown,
        yield_snapshots=(high_yield,),
        as_of=date(2026, 9, 20),
    )
    assert high_yield.dividend_yield == Decimal("0.1")
    assert result.sustainability.status == SUSTAINABILITY_UNKNOWN
    assert result.cash_return_status == DIVIDEND_RESEARCH_PARTIAL


def test_cyclical_current_yield_and_normalized_yield_are_separate():
    current = DividendYieldSnapshot(
        symbol="601088",
        basis_type=YIELD_TRAILING_PAID,
        dividend_basis_period="FY2025",
        dividend_per_share=Decimal("2.50"),
        dividend_known_at=date(2026, 9, 1),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("50"),
        currency="CNY",
        share_basis="ordinary shares",
        dividend_yield=Decimal("0.05"),
        yield_type=YIELD_CURRENT,
        evidence_refs=[REF],
        status=YIELD_READY,
    )
    normalized = DividendYieldSnapshot(
        symbol="601088",
        basis_type=YIELD_NORMALIZED_SCENARIO,
        dividend_basis_period="through-cycle",
        dividend_per_share=Decimal("1.50"),
        dividend_known_at=date(2026, 9, 18),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("50"),
        currency="CNY",
        share_basis="ordinary shares",
        dividend_yield=Decimal("0.03"),
        yield_type=YIELD_NORMALIZED,
        evidence_refs=[REF],
        status=YIELD_READY,
    )
    assert current.yield_type != normalized.yield_type
    assert current.basis_type != normalized.basis_type
    assert current.dividend_yield > normalized.dividend_yield


def test_trailing_paid_yield_excludes_future_and_out_of_window_records():
    history = DividendHistory(
        symbol="600519",
        records=(
            _paid_record(dps="1.00", fiscal="FY2024", ex=date(2025, 8, 1), pay=date(2025, 8, 3)),
            _paid_record(dps="2.00", fiscal="FY2025", ex=date(2026, 8, 1), pay=date(2026, 8, 3)),
            _paid_record(dps="4.00", fiscal="FY2026", ex=date(2026, 10, 1), pay=date(2026, 10, 3)),
        ),
        as_of=date(2026, 10, 20),
        evidence_refs=[REF],
        status=HISTORY_PARTIAL,
    )
    snapshot = build_trailing_paid_yield_snapshot(
        history=history,
        quote=_quote(price="100", quote_date=date(2026, 9, 18)),
        as_of=date(2026, 10, 20),
    )
    assert snapshot.dividend_per_share == Decimal("2.00")
    assert snapshot.dividend_yield == Decimal("0.02")


def _admission_fixture(result):
    validity = ModelValidity(
        model_id="fixture-v1",
        symbol=result.symbol,
        model_as_of=date(2026, 9, 18),
        valid_from=date(2026, 9, 18),
        last_material_event_check=date(2026, 9, 18),
        financial_statement_changed=False,
        capital_structure_changed=False,
        material_event_found=False,
        status="VALID",
        blockers=[],
        evidence_refs=[REF],
    )
    bridge_result = bridge(
        result,
        validity,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    return {
        "version": "fixture-v1",
        "result": json.loads(result.to_json()),
        "price_bridge": json.loads(bridge_result.to_json()),
        "model_validity": json.loads(validity.to_json()),
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def _partial_distribution_result(symbol, profile_id):
    return DividendResearchResult(
        symbol=symbol,
        profile_id=profile_id,
        history=DividendHistory(
            symbol=symbol,
            records=(),
            as_of=date(2026, 9, 20),
            evidence_refs=[REF],
            status=HISTORY_UNKNOWN,
        ),
        capacity=DistributionCapacity(
            symbol=symbol,
            profile_id=profile_id,
            as_of=date(2026, 9, 20),
            status=CAPACITY_UNKNOWN,
        ),
        sustainability=DividendSustainabilityAssessment(
            symbol=symbol,
            profile_id=profile_id,
            as_of=date(2026, 9, 20),
            status=SUSTAINABILITY_UNKNOWN,
            coverage_context="partial",
            capital_requirements="partial",
            balance_sheet_pressure="partial",
            cycle_risk="partial",
            growth_source="partial",
            breakers=(),
            confidence="UNKNOWN",
            reasons=(),
            blockers=[],
            evidence_refs=[],
        ),
        yield_snapshots=(),
        as_of=date(2026, 9, 20),
    )


def _profile_valuation_payload(symbol, profile_id):
    model_type = {
        "quality_compounder": "residual_income_or_equity_value",
        "mature_manufacturing": "FCFF",
        "cyclical_cash_return": "cyclical_normalized",
    }[profile_id]
    result = ValuationResult(
        symbol=symbol,
        model_type=model_type,
        valuation_date=date(2026, 9, 18),
        bear_value=None,
        base_value=None,
        bull_value=None,
        confidence="低",
        assumptions={},
        sensitivities=[],
        evidence_refs=[REF],
        blockers=["fixture scenarios not available"],
        status="not_ready",
        model_version="fixture-v1",
    )
    return _admission_fixture(result)


def test_three_profiles_share_one_typed_distribution_contract():
    specs = (
        ("600519", "quality_compounder", DECISION_CONTINUE_CONDITIONAL_MODEL),
        ("000333", "mature_manufacturing", DECISION_RESOLVE_MODEL_INPUTS),
        ("601088", "cyclical_cash_return", DECISION_PAUSE_PRODUCTION_VALUATION),
    )
    research_records = []
    valuation_payloads = {}
    policies = {}
    distribution_results = {}
    for symbol, profile_id, decision in specs:
        research_records.append(
            {
                "case": {"symbol": symbol, "evidence_refs": [REF]},
                "gate": {
                    "results": {
                        "G0_证据门": True,
                        "G1_财务门": True,
                        "G2_商业论点门": True,
                        "G3_估值门": False,
                    },
                    "blockers": ["fixture valuation not ready"],
                    "conclusion": "估值未就绪",
                },
            }
        )
        valuation_payloads[symbol] = _profile_valuation_payload(symbol, profile_id)
        policies[symbol] = FixedSampleAdmissionPolicy(
            profile_id=profile_id,
            decision=decision,
            decision_reason="fixture decision",
            cash_return_status="PARTIAL",
            cash_return_explanation="fixture fallback",
            admission_evidence=("research case",),
            required_evidence=("future input",),
        )
        distribution_results[symbol] = _partial_distribution_result(symbol, profile_id)

    review = review_fixed_sample(
        research_records=research_records,
        valuation_payloads=valuation_payloads,
        policies=policies,
        as_of=date(2026, 9, 20),
        distribution_results=distribution_results,
    )
    companies = {company.symbol: company for company in review.companies}
    assert review.production_valuation_available is False
    assert set(companies) == {symbol for symbol, _, _ in specs}
    for symbol, profile_id, _ in specs:
        company = companies[symbol]
        assert company.cash_return_status == DIVIDEND_RESEARCH_PARTIAL
        assert company.cash_return_result is distribution_results[symbol]
        assert company.cash_return_result.profile_id == profile_id
        assert company.action == "no_order"
        assert company.as_policy()["cash_return_research"]["profile_id"] == profile_id


def test_fixed_sample_consumes_a_typed_cash_return_result():
    result = ValuationResult(
        symbol="600519",
        model_type="residual_income_or_equity_value",
        valuation_date=date(2026, 9, 18),
        bear_value=Decimal("400"),
        base_value=Decimal("500"),
        bull_value=Decimal("600"),
        confidence="低",
        assumptions={},
        sensitivities=[],
        evidence_refs=[REF],
        blockers=[],
        status="conditional_research_only",
        model_version="fixture-v1",
    )
    record = _paid_record()
    distribution = DividendResearchResult(
        symbol="600519",
        profile_id="quality_compounder",
        history=DividendHistory(
            symbol="600519",
            records=(record,),
            as_of=date(2026, 9, 20),
            evidence_refs=[REF],
            status=HISTORY_UNKNOWN,
        ),
        capacity=DistributionCapacity(
            symbol="600519",
            profile_id="quality_compounder",
            as_of=date(2026, 9, 20),
            status=CAPACITY_UNKNOWN,
        ),
        sustainability=DividendSustainabilityAssessment(
            symbol="600519",
            profile_id="quality_compounder",
            as_of=date(2026, 9, 20),
            status=SUSTAINABILITY_UNKNOWN,
            coverage_context="partial",
            capital_requirements="partial",
            balance_sheet_pressure="partial",
            cycle_risk="partial",
            growth_source="partial",
            breakers=(),
            confidence="UNKNOWN",
            reasons=(),
            blockers=["future payout not verified"],
        ),
        yield_snapshots=(),
        as_of=date(2026, 9, 20),
    )
    review = review_fixed_sample(
        research_records=[
            {
                "case": {"symbol": "600519", "evidence_refs": [REF]},
                "gate": {
                    "results": {
                        "G0_证据门": True,
                        "G1_财务门": True,
                        "G2_商业论点门": True,
                        "G3_估值门": True,
                    },
                    "blockers": [],
                    "conclusion": "研究与估值已就绪",
                },
            }
        ],
        valuation_payloads={"600519": _admission_fixture(result)},
        policies={
            "600519": FixedSampleAdmissionPolicy(
                profile_id="quality_compounder",
                decision="CONTINUE_CONDITIONAL_MODEL",
                decision_reason="conditional model",
                cash_return_status="PARTIAL",
                cash_return_explanation="manual fallback",
                admission_evidence=("research case",),
                required_evidence=("formal approval",),
            )
        },
        as_of=date(2026, 9, 20),
        distribution_results={"600519": distribution},
    )
    company = review.companies[0]
    assert company.cash_return_status == DIVIDEND_RESEARCH_PARTIAL
    assert company.cash_return_result is distribution
    policy = company.as_policy()
    assert policy["cash_return_research"]["history"]["status"] == HISTORY_UNKNOWN
    assert policy["action"] == "no_order"
    assert json.dumps(policy, ensure_ascii=False).find("cash_return_research") != -1
