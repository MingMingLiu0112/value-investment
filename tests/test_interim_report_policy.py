from datetime import date

import pytest

from value_investment_agent.interim_report_policy import (
    CLASSIFICATION_CONFIDENCE_MODIFIER,
    CLASSIFICATION_HARD_BLOCKER,
    INTERIM_REPORT_POLICY_SCHEMA,
    classify_unaudited_interim_report,
    interim_report_policy_from_payload,
)


PERIOD = date(2026, 6, 30)


def test_verified_unaudited_interim_is_a_confidence_modifier_by_default():
    policy = classify_unaudited_interim_report(
        symbol="600519",
        report_period=PERIOD,
        source_verified=True,
        evidence_refs=({"id": "interim-pdf"},),
    )

    assert policy.classification == CLASSIFICATION_CONFIDENCE_MODIFIER
    assert policy.previous_classification == CLASSIFICATION_HARD_BLOCKER
    assert policy.blockers == ()
    assert policy.action == "no_order"


def test_unverified_source_remains_a_hard_blocker():
    policy = classify_unaudited_interim_report(
        symbol="600519",
        report_period=PERIOD,
        source_verified=False,
    )

    assert policy.classification == CLASSIFICATION_HARD_BLOCKER
    assert "interim_source_not_verified" in policy.blockers


@pytest.mark.parametrize(
    ("flag", "blocker"),
    (
        ("has_reported_conflict", "reported_data_conflict"),
        ("has_subsequent_correction", "subsequent_correction"),
        ("has_scope_mismatch", "scope_mismatch"),
        ("has_audit_qualification", "audit_qualification_evidence"),
        ("has_material_accounting_uncertainty", "material_accounting_uncertainty"),
    ),
)
def test_known_conflict_classes_escalate_to_hard_blocker(flag: str, blocker: str):
    policy = classify_unaudited_interim_report(
        symbol="600519",
        report_period=PERIOD,
        source_verified=True,
        **{flag: True},
    )

    assert policy.classification == CLASSIFICATION_HARD_BLOCKER
    assert blocker in policy.blockers
    assert policy.action == "no_order"


def test_policy_round_trip_preserves_the_versioned_reclassification():
    policy = classify_unaudited_interim_report(
        symbol="600519",
        report_period=PERIOD,
        source_verified=True,
        previous_classification=CLASSIFICATION_HARD_BLOCKER,
        evidence_refs=({"id": "interim-pdf"},),
    )
    payload = policy.as_policy()
    restored = interim_report_policy_from_payload(payload)

    assert payload["schema_version"] == INTERIM_REPORT_POLICY_SCHEMA
    assert restored == policy
    assert restored.as_policy() == payload


def test_illegal_identity_or_order_semantics_fail_closed():
    with pytest.raises(ValueError, match="symbol"):
        classify_unaudited_interim_report(
            symbol="bad",
            report_period=PERIOD,
            source_verified=True,
        )
    with pytest.raises(ValueError, match="no_order"):
        from value_investment_agent.interim_report_policy import (
            InterimReportPolicyDecision,
        )

        InterimReportPolicyDecision(
            symbol="600519",
            report_period=PERIOD,
            source_verified=True,
            has_reported_conflict=False,
            has_subsequent_correction=False,
            has_scope_mismatch=False,
            has_audit_qualification=False,
            has_material_accounting_uncertainty=False,
            classification=CLASSIFICATION_CONFIDENCE_MODIFIER,
            previous_classification=CLASSIFICATION_HARD_BLOCKER,
            policy_reason="policy correction",
            action="order",
        )
