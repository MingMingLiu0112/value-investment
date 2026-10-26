"""Bounded private MOCK review of caller-selected, existing journal facts.

No provider, current registry, filesystem output or private-input discovery.
Call behind the existing private authorization boundary; never publish the result.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from zoneinfo import ZoneInfo

from ...portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService


def _saved_judgment(trade, now):
    snapshot = trade.get("judgment_snapshot")
    if snapshot is None:
        return None, "SAVED_JUDGMENT_MISSING"
    try:
        unsigned = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
        digest = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        recorded = datetime.fromisoformat(snapshot["recorded_at"])
        plan = snapshot["plan"]
        if (snapshot.get("schema_version") != "private-recording-time-judgment-snapshot-v1"
                or snapshot.get("action") != "no_order" or digest != snapshot.get("snapshot_sha256")
                or recorded.utcoffset() is None or recorded > now
                or not trade.get("decision_id") or not trade.get("research_version")
                or snapshot.get("decision_id") != trade["decision_id"]
                or snapshot.get("research_version") != trade["research_version"]
                or plan.get("research_version") != trade["research_version"]
                or plan.get("symbol") != trade["symbol"] or plan.get("action") != "no_order"):
            return None, "SAVED_JUDGMENT_INVALID_OR_MISMATCHED"
        return deepcopy(snapshot), None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, "SAVED_JUDGMENT_INVALID_OR_MISMATCHED"


def _saved_recording_risk(snapshot, trade, records, now):
    """Read the exact prepared journal capture, never infer pretrade availability."""
    risk = (snapshot or {}).get("personal_risk_at_trade")
    if risk is None:
        return None, "RECORDING_TIME_PERSONAL_RISK_MISSING"
    try:
        revision = risk["journal_revision"]
        generated = datetime.fromisoformat(risk["generated_at"])
        verified = datetime.fromisoformat(risk["verified_at"])
        recorded = datetime.fromisoformat(snapshot["recorded_at"])
        if (type(revision) is not int or not 0 < revision < len(records)
                or risk.get("status") != "SERVER_VERIFIED_RECORDING_TIME_RISK"
                or risk.get("scope") != "RECORDING_TIME_RISK_NOT_PROVEN_PRETRADE"
                or risk.get("action") != "no_order"
                or any(risk.get(key) is not False for key in (
                    "formal_eligibility", "trade_eligible", "broker_execution_permission", "trade_time_availability_proven"))
                or snapshot.get("trade_time_availability_proven") is not False
                or snapshot.get("personal_risk_capture") != risk
                or risk.get("account_scope") != records[0]["body"]["account_scope"]
                or risk.get("journal_tip_sha256") != records[revision - 1]["record_sha256"]
                or records[revision]["kind"] != "FILL_PREPARED"
                or records[revision]["body"]["fill"].get("judgment_snapshot") != snapshot
                or records[revision]["body"]["fill"]["transaction_id"] != trade["transaction_id"]
                or risk.get("symbol") != trade["symbol"] or risk.get("strategy") != trade["sleeve"]
                or risk.get("research_version") != trade.get("research_version")
                or risk.get("publication_id") != snapshot.get("publication_id")
                or any(value.utcoffset() is None for value in (generated, verified, recorded))
                or not generated <= verified <= recorded <= now):
            raise ValueError("Invalid recording-time risk binding")
        return deepcopy(risk), None
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return None, "RECORDING_TIME_PERSONAL_RISK_INVALID"


def run_daily_retrospective_mock(*, journal: PrivateJournal, review_date: date,
                                 generated_at: datetime, max_trades: int = 20) -> dict:
    """Read an existing ledger only, reusing its hash validation and fill replay.

    MOCK describes the research workflow, never the origin of ledger facts.
    Numeric differences are observations, not inferred reasons or violations.
    Recording-time judgments cannot establish a contemporaneous approved plan.
    """
    if generated_at.utcoffset() is None or type(review_date) is not date:
        raise ValueError("Aware clock and explicit review date required")
    if review_date > generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("Future review date")
    if type(max_trades) is not int or not 1 <= max_trades <= 50:
        raise ValueError("max_trades must be between 1 and 50")
    result = dict(schema_version="daily-agent-retrospective-mock-v1", action="no_order",
        mode="MOCK", sensitivity="PRIVATE", generated_at=generated_at.isoformat(),
        review_date=review_date.isoformat(), ledger_source="MISSING_PRIVATE_INPUT",
        status="BLOCKED_PRIVATE_INPUT", items=[], approval_count=0,
        decision_changed=False, formal_eligibility=False, ledger_written=False,
        public_registry_written=False, live_provider_called=False)
    if not journal.path.is_file():
        return result
    if journal.path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Journal exceeds bounded 4 MiB input")
    before = hashlib.sha256(journal.path.read_bytes()).hexdigest()
    service = PrivatePortfolioService(journal)
    records = service.records()
    if len(records) > 2000:
        raise ValueError("Journal exceeds bounded 2000 records")
    # Only records known at the requested review clock enter the existing replay.
    for record in records:
        clock = datetime.fromisoformat(record["recorded_at"])
        if clock.utcoffset() is None or clock > generated_at:
            raise ValueError("Journal contains unavailable records at review clock")
    replayed = service._replay(records)
    if replayed is None:
        return result
    baseline = next(row["body"] for row in records if row["kind"] == "BASELINE_CONFIRMED")
    scope = baseline["account_scope"]
    test_scope = scope == "TEST_ONLY" or scope.startswith(("TEST_ONLY_", "TEST_ONLY-"))
    result.update(ledger_source="TEST_ONLY" if test_scope else
        "USER_CONFIRMED_PRIVATE_JOURNAL_NOT_BROKER_VERIFIED", account_scope=scope,
        journal_sha256=before, revision=len(records), journal_head_sha256=records[-1]["record_sha256"])
    trades = [trade for trade in replayed.trades if trade["trade_date"] == review_date.isoformat()]
    for trade in trades[:max_trades]:
        snapshot, gap = _saved_judgment(trade, generated_at)
        recording_risk, risk_gap = _saved_recording_risk(snapshot, trade, records, generated_at)
        gaps = ["TRADE_TIME_PLAN_AND_DATA_AVAILABILITY_NOT_PROVEN",
                "PERSONAL_RISK_AT_TRADE_NOT_PROVEN", "DEVIATION_REASON_NOT_RECORDED",
                "SUBSEQUENT_RISK_NOT_EVALUATED_NO_LATER_EVIDENCE"]
        if gap:
            gaps.append(gap)
        if risk_gap:
            gaps.append(risk_gap)
        if not trade.get("decision_id"):
            gaps.append("UNLINKED_FILL_NO_RESEARCH_APPROVAL_INFERRED")
        differences = []
        if snapshot:
            plan = snapshot["plan"]
            # These existing plan fields are reference levels, not execution prices.
            for field in ("entry_trigger_price", "stop_price", "exit_trigger_price",
                          "invalidation_price", "profit_review_price"):
                if plan.get(field) is None:
                    continue
                try:
                    reference = Decimal(str(plan[field]))
                    if not reference.is_finite() or reference <= 0:
                        raise ValueError("Invalid reference level")
                    differences.append(dict(field=field, saved_reference_cny=str(reference),
                        fill_minus_reference_cny=str(Decimal(trade["price_cny"]) - reference),
                        interpretation="REFERENCE_DIFFERENCE_NOT_PROVEN_PLAN_VIOLATION"))
                except (InvalidOperation, ValueError):
                    gaps.append("SAVED_REFERENCE_LEVEL_INVALID:" + field)
        result["items"].append(dict(manual_fill=deepcopy(trade), saved_judgment=snapshot,
            recording_time_personal_risk=recording_risk,
            recording_time_risk_status="AVAILABLE_RECORDING_TIME_ONLY" if recording_risk else "UNAVAILABLE",
            contemporaneous_plan=None, trade_time_availability_proven=False,
            research_approval_inferred=False, differences=differences, evidence_gaps=gaps,
            summary="MOCK review: confirmed ledger fill compared with saved recording-time judgment; human review required."))
    if hashlib.sha256(journal.path.read_bytes()).hexdigest() != before:
        raise ValueError("Journal changed during retrospective review")
    result.update(status="MOCK_DRAFT_PENDING_HUMAN_REVIEW" if trades else "NO_CONFIRMED_FILLS",
                  unprocessed_trade_count=max(0, len(trades) - max_trades))
    return result
