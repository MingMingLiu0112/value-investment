from pathlib import Path

import pytest

from value_investment_agent.historical_validation import (
    ACTION_NO_ORDER,
    ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH,
    ADMITTED_FOR_STRICT_REPLAY,
    NOT_ADMITTED,
    NOT_PIT_SAFE,
    PIT_CONSERVATIVE,
    PIT_NOT_PROVEN,
    PIT_UNSUPPORTED,
    PIT_VERIFIED,
    RETROSPECTIVE_POLICY_REPLAY,
    RULE_CONTEMPORANEOUS,
    RULE_RETROSPECTIVE,
    STRICT_CONTEMPORANEOUS_REPLAY,
    SURVIVORSHIP_CONTROLLED,
    SURVIVORSHIP_UNRESOLVED,
    ExecutionContract,
    EvidenceReference,
    HistoricalValidationAdmission,
    PitAssessment,
)


def assessment(status=PIT_VERIFIED, name="dimension"):
    if status in (PIT_VERIFIED, PIT_CONSERVATIVE):
        return PitAssessment(status, f"{name} evidence", evidence_refs=("evidence",))
    return PitAssessment(
        status,
        f"{name} cannot be proven",
        blockers=(f"{name}_blocker",),
    )


def execution(status=PIT_VERIFIED):
    return ExecutionContract(
        signal_to_fill="next_session_open",
        settlement="T+1",
        board_lot=100,
        cash_policy="cash only",
        suspension_policy="suspended sessions block fills",
        price_limit_policy="missing limits block fills",
        liquidity_policy="daily bars are explicit research assumptions",
        corporate_action_policy="record-date entitlement and no double count",
        fee_policy="dated fees plus declared commission scenario",
        status=status,
        evidence_refs=("evidence",) if status in (PIT_VERIFIED, PIT_CONSERVATIVE) else (),
        blockers=() if status in (PIT_VERIFIED, PIT_CONSERVATIVE) else ("execution_blocker",),
    )


def admission(**overrides):
    values = {
        "admission_id": "test-admission",
        "symbol": "600519",
        "scope": "single_security_historical_validation",
        "window_start": "2015-01-05",
        "window_end": "2015-01-30",
        "information_cutoff_policy": "available_at <= decision_at",
        "rule_version": "test-rule-v1",
        "rule_registration_status": RULE_CONTEMPORANEOUS,
        "rule_evidence_refs": ("evidence",),
        "facts_pit": assessment(name="facts"),
        "assumptions_pit": assessment(name="assumptions"),
        "valuation_pit": assessment(name="valuation"),
        "quote_pit": assessment(name="quote"),
        "corporate_actions_pit": assessment(name="corporate"),
        "fees_pit": assessment(name="fees"),
        "execution_contract": execution(),
        "portfolio_context": assessment(name="portfolio"),
        "benchmark_contract": assessment(name="benchmark"),
        "universe_pit": assessment(name="universe"),
        "survivorship_status": SURVIVORSHIP_CONTROLLED,
        "approved_value_model_sessions": 1,
        "blockers": (),
        "evidence_refs": (
            EvidenceReference("evidence", "test", "docs/test.md", "0" * 64),
            EvidenceReference("rule-evidence", "test-rule", "docs/test-rule.md", "1" * 64),
        ),
        "action": ACTION_NO_ORDER,
    }
    values.update(overrides)
    if "blockers" not in overrides:
        unproven = any(
            item.status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN)
            for item in (
                values["facts_pit"],
                values["assumptions_pit"],
                values["valuation_pit"],
                values["quote_pit"],
                values["corporate_actions_pit"],
                values["fees_pit"],
                values["portfolio_context"],
                values["benchmark_contract"],
                values["universe_pit"],
            )
        ) or values["execution_contract"].status in (PIT_UNSUPPORTED, PIT_NOT_PROVEN)
        if (
            values["approved_value_model_sessions"] == 0
            or values["survivorship_status"] != SURVIVORSHIP_CONTROLLED
            or unproven
        ):
            values["blockers"] = ("test_blocker",)
    return HistoricalValidationAdmission(**values)


def test_complete_contemporaneous_chain_is_the_only_strict_classification():
    result = admission()
    assert result.classification == STRICT_CONTEMPORANEOUS_REPLAY
    assert result.admission_status == ADMITTED_FOR_STRICT_REPLAY
    assert result.action == ACTION_NO_ORDER


def test_retrospective_rule_is_policy_replay_not_strict_pit():
    result = admission(rule_registration_status=RULE_RETROSPECTIVE)
    assert result.classification == RETROSPECTIVE_POLICY_REPLAY
    assert result.admission_status == ADMITTED_FOR_RETROSPECTIVE_POLICY_RESEARCH


def test_missing_valuation_cannot_be_hidden_by_a_complete_rule():
    result = admission(
        valuation_pit=assessment(PIT_UNSUPPORTED, name="valuation"),
        approved_value_model_sessions=0,
    )
    assert result.classification == NOT_PIT_SAFE
    assert result.admission_status == NOT_ADMITTED


def test_unresolved_survivorship_fails_closed_even_when_other_evidence_is_present():
    result = admission(survivorship_status=SURVIVORSHIP_UNRESOLVED)
    assert result.classification == NOT_PIT_SAFE
    assert result.admission_status == NOT_ADMITTED


@pytest.mark.parametrize("dimension", ["quote_pit", "benchmark_contract", "universe_pit"])
def test_unproven_critical_dimension_fails_closed(dimension):
    result = admission(**{dimension: assessment(PIT_NOT_PROVEN, name=dimension)})
    assert result.classification == NOT_PIT_SAFE
    assert result.admission_status == NOT_ADMITTED


def test_conservative_fee_and_execution_bounds_are_allowed_but_still_explicit():
    result = admission(
        fees_pit=assessment(PIT_CONSERVATIVE, name="fees"),
        execution_contract=execution(PIT_CONSERVATIVE),
    )
    assert result.classification == STRICT_CONTEMPORANEOUS_REPLAY
    assert result.as_dict()["execution_contract"]["status"] == PIT_CONSERVATIVE


def test_same_close_execution_is_rejected():
    with pytest.raises(ValueError, match="next-session-open"):
        ExecutionContract(
            signal_to_fill="same_close",
            settlement="T+1",
            board_lot=100,
            cash_policy="cash only",
            suspension_policy="block",
            price_limit_policy="block",
            liquidity_policy="research assumption",
            corporate_action_policy="record-date",
            fee_policy="dated",
            status=PIT_VERIFIED,
            evidence_refs=("evidence",),
        )


def test_absolute_evidence_path_is_rejected():
    with pytest.raises(ValueError):
        EvidenceReference("bad", "test", str(Path("C:/secret")), "0" * 64)


def test_admission_requires_an_explicit_blocker_when_not_pit_safe():
    with pytest.raises(ValueError, match="explicit blocker"):
        admission(approved_value_model_sessions=0, blockers=())


def test_builder_keeps_the_first_600519_case_at_not_pit_safe():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "build_moutai_historical_validation_admission.py"
    spec = importlib.util.spec_from_file_location("historical_validation_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result, manifest = module.build_admission(Path(__file__).resolve().parents[1])
    assert result.symbol == "600519"
    assert result.classification == NOT_PIT_SAFE
    assert result.admission_status == NOT_ADMITTED
    assert result.approved_value_model_sessions == 0
    assert result.execution_contract.signal_to_fill == "next_session_open"
    assert result.execution_contract.settlement == "T+1"
    assert manifest["action"] == ACTION_NO_ORDER
    assert manifest["canonical_sha256"]
