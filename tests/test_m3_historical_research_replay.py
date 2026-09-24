from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from value_investment_agent.m3_historical_research_replay import (
    ACTION_NO_ORDER,
    REPLAY_NAMESPACE,
    REPLAY_SCHEMA,
    RULE_REGISTRATION_CONTEMPORANEOUS,
    RULE_REGISTRATION_EVIDENCE_KINDS,
    HistoricalEvidenceReference,
    HistoricalResearchReplay,
    HistoricalRuleBinding,
    ThenKnownFinancialFacts,
    ThenKnownQuote,
)


SYMBOL = "600519"
REPLAY_DATE = date(2024, 6, 21)
GENERATED_AT = datetime(2026, 9, 24, 2, 0, tzinfo=timezone.utc)
CN_TZ = timezone(timedelta(hours=8))


def _ref(kind: str, available_at: datetime | None = None) -> HistoricalEvidenceReference:
    return HistoricalEvidenceReference(
        ref_id=f"ref-{kind}",
        kind=kind,
        path=f"fixtures/{kind}.json",
        sha256="a" * 64,
        source_url=f"https://example.test/{kind}",
        available_at=available_at or datetime(2024, 1, 1, tzinfo=CN_TZ),
        role="fixture evidence",
    )


def _facts() -> ThenKnownFinancialFacts:
    return ThenKnownFinancialFacts(
        symbol=SYMBOL,
        period_label="2023-12-31",
        source_id="cninfo:fixture",
        published_at=datetime(2024, 4, 3, tzinfo=CN_TZ),
        parent_profit_cny=Decimal("74734071550.75"),
        ending_issued_shares=Decimal("1256197800"),
        reported_basic_eps=Decimal("59.49"),
        source_ref=_ref("annual_filing", datetime(2024, 4, 4, tzinfo=CN_TZ)),
    )


def _quote() -> ThenKnownQuote:
    return ThenKnownQuote(
        symbol=SYMBOL,
        quote_date=REPLAY_DATE,
        close_cny=Decimal("1471.00"),
        source_ref=_ref("prices", datetime(2024, 6, 21, 15, 0, tzinfo=CN_TZ)),
    )


def _rule() -> HistoricalRuleBinding:
    return HistoricalRuleBinding(
        rule_version="moutai-pe-mid-paper-contract-v2-2025-extension",
        model_scope="relative_pe_research_only",
        registered_at=datetime(2026, 9, 12, 5, 27, 47, tzinfo=timezone.utc),
        rule_registration_status="RETROSPECTIVE_RESEARCH_EXTENSION",
        entry_margin=Decimal("0.30"),
        research_quantity=100,
        exit_rule="close exceeds that day's median-relative value",
    )


def _replay(**changes) -> HistoricalResearchReplay:
    payload = {
        "replay_id": "fixture-replay-v1",
        "schema_version": REPLAY_SCHEMA,
        "namespace": REPLAY_NAMESPACE,
        "symbol": SYMBOL,
        "replay_date": REPLAY_DATE,
        "generated_at": GENERATED_AT,
        "source_receipt": {"input_sha256": "b" * 64},
        "then_known_facts": _facts(),
        "then_known_filings": (_ref("distribution"),),
        "then_known_quote": _quote(),
        "rule": _rule(),
        "source_decision_state": "proposed_entry",
        "source_decision_action": "propose_entry_review",
        "final_decision": "WAIT",
        "blockers": (
            "relative_pe_research_only_not_intrinsic_valuation",
            "retrospective_rule_not_contemporaneous",
            "valuation_approved_false",
            "no_human_research_approval",
            "positive_price_review_not_eligible",
        ),
        "valuation_approved": False,
        "trade_approved": False,
        "positive_price_review_eligible": False,
        "future_facts_used": False,
        "future_rule_version_used": True,
        "action": ACTION_NO_ORDER,
    }
    payload.update(changes)
    return HistoricalResearchReplay(**payload)


def test_historical_replay_is_wait_namespace_and_no_order():
    replay = _replay()

    assert replay.namespace == REPLAY_NAMESPACE
    assert replay.final_decision == "WAIT"
    assert replay.valuation_approved is False
    assert replay.trade_approved is False
    assert replay.positive_price_review_eligible is False
    assert replay.action == ACTION_NO_ORDER
    assert "relative_pe_research_only_not_intrinsic_valuation" in replay.blockers
    assert len(replay.replay_sha256) == 64


def test_historical_replay_rejects_positive_review_claim():
    with pytest.raises(ValueError, match="cannot produce a positive BUY_REVIEW"):
        _replay(final_decision="BUY_REVIEW")

    with pytest.raises(ValueError, match="not price-review eligible"):
        _replay(positive_price_review_eligible=True)


def test_historical_replay_rejects_valuation_or_trade_approval():
    with pytest.raises(ValueError, match="cannot approve valuation or trade"):
        _replay(valuation_approved=True)
    with pytest.raises(ValueError, match="cannot approve valuation or trade"):
        _replay(trade_approved=True)


def test_historical_replay_rejects_future_facts():
    with pytest.raises(ValueError, match="cannot use future facts"):
        _replay(future_facts_used=True)


def test_historical_replay_policy_does_not_contain_order_fields():
    text = __import__("json").dumps(_replay().as_policy(), ensure_ascii=False)

    assert "target_weight" not in text
    assert "position_size" not in text
    assert "order_quantity" not in text
    assert "sell" not in text.lower()


def test_retrospective_rule_must_mark_future_rule_version():
    with pytest.raises(ValueError, match="must mark future_rule_version_used"):
        _replay(future_rule_version_used=False)


def test_contemporaneous_rule_cannot_be_registered_after_replay_date():
    evidence = HistoricalEvidenceReference(
        ref_id="rule-evidence-v1",
        kind="versioned_file",
        path="fixtures/rule-v1.json",
        sha256="c" * 64,
        source_url="https://example.test/rule-v1.json",
        available_at=datetime(2024, 6, 1, tzinfo=CN_TZ),
        role="contemporaneous rule registration evidence",
    )
    rule = HistoricalRuleBinding(
        rule_version="contemporaneous-v1",
        model_scope="relative_pe_research_only",
        registered_at=datetime(2024, 6, 22, tzinfo=CN_TZ),
        rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
        entry_margin=Decimal("0.30"),
        research_quantity=100,
        exit_rule="close exceeds that day's median-relative value",
        registration_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match="cannot postdate the replay date"):
        _replay(rule=rule, future_rule_version_used=False)


def test_contemporaneous_rule_rejects_future_rule_flag():
    evidence = HistoricalEvidenceReference(
        ref_id="rule-evidence-v1",
        kind="versioned_file",
        path="fixtures/rule-v1.json",
        sha256="c" * 64,
        source_url="https://example.test/rule-v1.json",
        available_at=datetime(2024, 6, 1, tzinfo=CN_TZ),
        role="contemporaneous rule registration evidence",
    )
    rule = HistoricalRuleBinding(
        rule_version="contemporaneous-v1",
        model_scope="relative_pe_research_only",
        registered_at=datetime(2024, 6, 20, tzinfo=CN_TZ),
        rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
        entry_margin=Decimal("0.30"),
        research_quantity=100,
        exit_rule="close exceeds that day's median-relative value",
        registration_evidence=(evidence,),
    )

    with pytest.raises(ValueError, match="cannot use a future rule version"):
        _replay(rule=rule, future_rule_version_used=True)


def test_contemporaneous_rule_before_replay_date_is_valid():
    evidence = HistoricalEvidenceReference(
        ref_id="rule-evidence-v1",
        kind="versioned_file",
        path="fixtures/rule-v1.json",
        sha256="c" * 64,
        source_url="https://example.test/rule-v1.json",
        available_at=datetime(2024, 6, 1, tzinfo=CN_TZ),
        role="contemporaneous rule registration evidence",
    )
    rule = HistoricalRuleBinding(
        rule_version="contemporaneous-v1",
        model_scope="relative_pe_research_only",
        registered_at=datetime(2024, 6, 20, tzinfo=CN_TZ),
        rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
        entry_margin=Decimal("0.30"),
        research_quantity=100,
        exit_rule="close exceeds that day's median-relative value",
        registration_evidence=(evidence,),
    )

    replay = _replay(rule=rule, future_rule_version_used=False)

    assert replay.rule.is_retrospective_rule is False
    assert replay.future_rule_version_used is False
    assert replay.rule.as_policy()["registration_evidence"][0]["id"] == "rule-evidence-v1"


def test_contemporaneous_rule_requires_dated_source_evidence():
    with pytest.raises(ValueError, match="requires dated source evidence"):
        HistoricalRuleBinding(
            rule_version="contemporaneous-v1",
            model_scope="relative_pe_research_only",
            registered_at=datetime(2024, 6, 20, tzinfo=CN_TZ),
            rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
            entry_margin=Decimal("0.30"),
            research_quantity=100,
            exit_rule="close exceeds that day's median-relative value",
        )


def test_contemporaneous_rule_rejects_undated_or_postdated_evidence():
    late = HistoricalEvidenceReference(
        ref_id="rule-evidence-late",
        kind="publication",
        path="fixtures/rule-late.json",
        sha256="d" * 64,
        source_url="https://example.test/rule-late.json",
        available_at=datetime(2024, 6, 21, tzinfo=CN_TZ),
        role="late rule evidence",
    )
    with pytest.raises(ValueError, match="cannot postdate"):
        HistoricalRuleBinding(
            rule_version="contemporaneous-v1",
            model_scope="relative_pe_research_only",
            registered_at=datetime(2024, 6, 20, tzinfo=CN_TZ),
            rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
            entry_margin=Decimal("0.30"),
            research_quantity=100,
            exit_rule="close exceeds that day's median-relative value",
            registration_evidence=(late,),
        )

    unsupported = _ref("prices")
    with pytest.raises(ValueError, match="independently dated source"):
        HistoricalRuleBinding(
            rule_version="contemporaneous-v1",
            model_scope="relative_pe_research_only",
            registered_at=datetime(2024, 6, 20, tzinfo=CN_TZ),
            rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
            entry_margin=Decimal("0.30"),
            research_quantity=100,
            exit_rule="close exceeds that day's median-relative value",
            registration_evidence=(unsupported,),
        )

    assert RULE_REGISTRATION_EVIDENCE_KINDS == {
        "archived_document",
        "publication",
        "source_commit",
        "versioned_file",
    }
