"""Isolated TEST_ONLY journal regression; no real private inputs."""
from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from test_private_ledger_candidate_fill import ledger, request, confirm
from value_investment_agent.application.portfolio import judgment_snapshot
from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal
from value_investment_agent.application.research.agent_review.daily_retrospective import (
    run_daily_retrospective_mock,
)


def review(journal, **kwargs):
    return run_daily_retrospective_mock(journal=journal, review_date=date(2026, 10, 12),
        generated_at=datetime(2030, 1, 1, tzinfo=timezone.utc), **kwargs)


def test_absent_input_never_created(tmp_path):
    journal = PrivateJournal(tmp_path / "absent" / "journal.jsonl")
    assert review(journal)["status"] == "BLOCKED_PRIVATE_INPUT"
    assert not journal.path.parent.exists()


def test_only_confirmed_facts_no_approval_and_no_writes(ledger):
    body = request(ledger)
    body["fill"].pop("decision_id")
    body["fill"].pop("research_version")
    _, digest = ledger.prepare_fill(body)
    assert review(ledger.journal)["status"] == "NO_CONFIRMED_FILLS"
    confirm(ledger, digest, "confirm")
    before = ledger.journal.path.read_bytes()
    result = review(ledger.journal)
    assert result["mode"] == "MOCK" and result["ledger_source"] == "TEST_ONLY"
    item = result["items"][0]
    assert item["manual_fill"]["price_cny"] == "20"
    assert item["saved_judgment"] is None
    assert "UNLINKED_FILL_NO_RESEARCH_APPROVAL_INFERRED" in item["evidence_gaps"]
    assert result["approval_count"] == 0 and not result["formal_eligibility"]
    assert review(ledger.journal) == result
    assert ledger.journal.path.read_bytes() == before


@pytest.mark.parametrize("invalid", [False, True])
def test_saved_judgment_is_not_pretrade_knowledge(ledger, monkeypatch, invalid):
    plan = dict(symbol="600887", action="no_order", research_version="TEST_ONLY-v1",
                entry_trigger_price="19", invalidation_price="18",
                profit_review_price="24", formal_eligibility=True)
    snapshot = dict(schema_version="private-recording-time-judgment-snapshot-v1",
        action="no_order", decision_id="600887", research_version="TEST_ONLY-v1",
        recorded_at="2026-10-13T20:00:00+08:00", plan=plan)
    snapshot["snapshot_sha256"] = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if invalid:
        snapshot["plan"]["entry_trigger_price"] = "1"
    monkeypatch.setattr(judgment_snapshot, "capture_judgment_snapshot", lambda *args: snapshot)
    body = request(ledger)
    body["fill"].update(decision_id="600887", research_version="TEST_ONLY-v1")
    _, digest = ledger.prepare_fill(body, repository_root=ledger.journal.path.parent)
    confirm(ledger, digest, "confirmed")
    result = review(ledger.journal)
    item = result["items"][0]
    assert item["contemporaneous_plan"] is None
    assert not item["trade_time_availability_proven"]
    assert not item["research_approval_inferred"]
    if invalid:
        assert item["saved_judgment"] is None and not item["differences"]
    else:
        assert item["differences"][0]["fill_minus_reference_cny"] == "1"
        assert item["saved_judgment"]["plan"]["entry_trigger_price"] == "19"
        differences = {row["field"]: row for row in item["differences"]}
        assert differences["invalidation_price"]["fill_minus_reference_cny"] == "2"
        assert differences["profit_review_price"]["fill_minus_reference_cny"] == "-4"
        assert all(row["interpretation"] == "REFERENCE_DIFFERENCE_NOT_PROVEN_PLAN_VIOLATION"
                   for row in differences.values())
    assert not result["formal_eligibility"]


@pytest.mark.parametrize("scope, test_only", [
    ("TEST_ONLY", True), ("TEST_ONLY_BROWSER_TWO_SLEEVES", True),
    ("TEST_ONLY_IPS", True), ("TEST_ONLY-isolated", True),
    ("PRIVATE", False), ("PRIVATE_TEST_ONLY", False),
    ("REAL-TEST_ONLY-account", False), ("TEST_ONLYISH", False),
    ("test_only_ips", False),
])
def test_source_label_does_not_promote_mock_to_real_input(ledger, scope, test_only):
    # An account label is user-declared; it is never brokerage verification.
    records = ledger.records()
    records[0]["body"]["account_scope"] = scope
    from value_investment_agent.application.portfolio.private_portfolio_service import canonical_bytes
    record = records[0]
    record.pop("record_sha256")
    record["record_sha256"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
    ledger.journal.path.write_bytes(canonical_bytes(record) + b"\n")
    result = review(ledger.journal)
    assert result["ledger_source"] == ("TEST_ONLY" if test_only else
        "USER_CONFIRMED_PRIVATE_JOURNAL_NOT_BROKER_VERIFIED")
    assert result["account_scope"] == scope
    assert result["mode"] == "MOCK" and not result["formal_eligibility"]


@pytest.mark.parametrize("clock, allowed", [
    ("2026-10-12T15:59:59+00:00", False),
    ("2026-10-12T16:00:00+00:00", True),
    ("2026-10-13T00:00:00+08:00", True),
    ("2026-10-13T00:00:00+14:00", False),
])
def test_review_date_uses_shanghai_midnight(tmp_path, clock, allowed):
    journal = PrivateJournal(tmp_path / "missing.jsonl")
    kwargs = dict(journal=journal, review_date=date(2026, 10, 13),
                  generated_at=datetime.fromisoformat(clock))
    if allowed:
        assert run_daily_retrospective_mock(**kwargs)["status"] == "BLOCKED_PRIVATE_INPUT"
    else:
        with pytest.raises(ValueError, match="Future review date"):
            run_daily_retrospective_mock(**kwargs)
    assert not journal.path.exists()


@pytest.mark.parametrize("limit", [0, 51, True])
def test_bounds(ledger, limit):
    with pytest.raises(ValueError):
        review(ledger.journal, max_trades=limit)


def test_corrupt_journal_rejected(ledger):
    with ledger.journal.path.open("ab") as stream:
        stream.write(b"{}\n")
    with pytest.raises(ValueError):
        review(ledger.journal)


def test_unavailable_review_clock_rejected(ledger):
    with pytest.raises(ValueError, match="unavailable"):
        run_daily_retrospective_mock(journal=ledger.journal, review_date=date(2026, 10, 12),
            generated_at=datetime(2026, 10, 12, tzinfo=timezone.utc))
