"""Re-run dated candidate selection from originals, never supplied buy lists.

Each decision consumes only its explicitly bound snapshot. A retrospective
manifest is not a preregistration receipt, performance test, or Shadow ledger.
"""
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

from .candidate_selection import select_current_hotspot_candidates
from .event_replay import _bound_bytes
from .strategy_execution_replay import fingerprint
from ...domain.execution.exchange_calendar import is_exchange_session, SCHEDULE_VERSION

VERSION = "hotspot-selection-history-v1"
SPEC_VERSION = "hotspot-selection-history-spec-v1"
RULE_PATHS = (
    "src/value_investment_agent/domain/hotspot/daily_selection.py",
    "src/value_investment_agent/domain/hotspot/price_action_plan.py",
    "src/value_investment_agent/domain/hotspot/confirmed_price_structure.py",
    "src/value_investment_agent/domain/hotspot/opportunity_quality.py",
    "src/value_investment_agent/domain/hotspot/current_price.py",
    "src/value_investment_agent/domain/execution/exchange_calendar.py",
    "src/value_investment_agent/application/hotspot/candidate_selection.py",
    "src/value_investment_agent/application/hotspot/daily_selection.py",
    "src/value_investment_agent/application/hotspot/current_case_review.py",
    "src/value_investment_agent/application/hotspot/price_action_case.py",
    "src/value_investment_agent/application/hotspot/current_refresh.py",
    "src/value_investment_agent/application/hotspot/selection_history.py",
    "src/value_investment_agent/infrastructure/hotspot/current_price_case.py",
    "src/value_investment_agent/infrastructure/hotspot/sina_price_case.py",
    "src/value_investment_agent/infrastructure/hotspot/daily_market.py",
    "src/value_investment_agent/m2_market_data.py",
    "src/value_investment_agent/quote_session_collection.py",
    "src/value_investment_agent/quote_session_conversion.py",
    "src/value_investment_agent/quote_sessions.py",
)


def implementation_bindings():
    checkout = Path(__file__).resolve().parents[4]
    return [dict(path=name, sha256=sha256((checkout / name).read_bytes()).hexdigest())
            for name in RULE_PATHS]


def _time(value):
    if not isinstance(value, str):
        raise ValueError("History requires an explicit ISO timestamp")
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("History cutoff requires a timezone")
    return stamp


def _sessions(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or (last - first).days > 366:
        raise ValueError("History range must be ordered and bounded to one year")
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)
            if is_exchange_session("SSE", first + timedelta(days=i))]


def replay_selection_history(*, root: Path, specification: dict, now: datetime) -> dict:
    """Reproduce all snapshot members and retain gaps; no source writes.

    The specification itself is content-fingerprinted as a retrospective
    experiment input. Its declared registration time never proves independent
    preregistration. Missing sessions invalidate membership transitions.
    """
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Timezone-aware evaluation clock required")
    fields = {"schema_version", "namespace", "action", "registered_at", "start_date",
              "end_date", "rule_bindings", "snapshots"}
    if (not isinstance(specification, dict) or set(specification) != fields
            or specification["schema_version"] != SPEC_VERSION
            or specification["namespace"] not in {"ACTUAL", "TEST_ONLY"}
            or specification["action"] != "no_order"):
        raise ValueError("Exact selection-history specification required; supplied orders are not supported")
    before = implementation_bindings()
    if specification["rule_bindings"] != before:
        raise ValueError("Historical rule binding differs from executing implementation")
    registered = _time(specification["registered_at"])
    if registered > now:
        raise ValueError("Future history specification")
    expected = _sessions(specification["start_date"], specification["end_date"])
    if not expected or _time(expected[-1] + "T15:00:00+08:00") > now:
        raise ValueError("History range has no completed calendar coverage")
    snapshots = specification["snapshots"]
    if not isinstance(snapshots, list) or len(snapshots) > len(expected):
        raise ValueError("Bounded one-snapshot-per-session history required")
    indexed = {}
    for item in snapshots:
        if (not isinstance(item, dict) or set(item) !=
                {"session", "decision_at", "watch_binding", "case_bindings"}
                or item["session"] not in expected or item["session"] in indexed
                or not isinstance(item["case_bindings"], dict)):
            raise ValueError("Duplicate, out-of-window or malformed history snapshot")
        if _time(item["decision_at"]) > now:
            raise ValueError("Future historical decision")
        indexed[item["session"]] = item
    root = root.resolve()
    rows, previous, bindings = [], None, []
    previous_contract = None
    for session in expected:
        item = indexed.get(session)
        if item is None:
            rows.append(dict(session=session, status="MISSING_SESSION", selection=None,
                membership_change=None, blockers=["CONTEMPORANEOUS_SNAPSHOT_MISSING"]))
            previous = None
            previous_contract = None
            continue
        selection = select_current_hotspot_candidates(root=root, now=_time(item["decision_at"]),
            watch_binding=item["watch_binding"], case_bindings=item["case_bindings"], limit=30)
        coverage = selection.get("coverage", {})
        complete = (selection.get("status") == "RESEARCH_SELECTION_REPLAYED"
            and selection.get("data_status") == "CURRENT" and selection.get("trade_date") == session
            and coverage.get("market_securities", 0) > 0
            and coverage.get("unknown") == 0 and coverage.get("omitted_by_limit") == 0)
        selected = {row["symbol"] for row in selection["shortlist"]}
        change = None
        contract = None
        if complete:
            watch = json.loads(_bound_bytes(root, item["watch_binding"]))
            contract = dict(activity_rule=selection["activity_rule_version"],
                structure_rule=selection["structure_rule_version"],
                membership_source="candidate_pool" if "candidate_pool" in watch else "observation_list",
                candidate_pool_rule=selection.get("candidate_pool_rule"),
                display_limit=watch["limit"], candidate_pool_limit=watch.get("candidate_pool_limit"))
        if complete and previous is not None and contract == previous_contract:
            change = dict(entered=sorted(selected - previous), left=sorted(previous - selected),
                scope="RESEARCH_POOL_MEMBERSHIP_NOT_BUY_OR_EXIT")
        rows.append(dict(session=session, decision_at=item["decision_at"],
            status="REPLAYED" if complete else "INCOMPLETE_OR_INVALID",
            selection=selection, selection_contract=contract, membership_change=change,
            transition_status="COMPARABLE" if change is not None else "NO_COMPARABLE_PREVIOUS_SESSION",
            blockers=[] if complete else ["SOURCE_DATE_OR_STRUCTURE_COVERAGE_NOT_PROVEN"]))
        previous = selected if complete else None
        previous_contract = contract if complete else None
        if complete:
            bindings.extend(selection["source_bindings"])
    # Check source bytes and implementation again after the whole computation.
    for binding in bindings:
        _bound_bytes(root, {key: binding[key] for key in ("path", "sha256")})
    if implementation_bindings() != before:
        raise ValueError("Rule implementation changed during history replay")
    result = dict(schema_version=VERSION, action="no_order", namespace=specification["namespace"],
        evaluated_at=now.isoformat(), specification_sha256=fingerprint(specification),
        implementation_bindings=before, calendar_version=SCHEDULE_VERSION,
        start_date=specification["start_date"], end_date=specification["end_date"],
        expected_sessions=len(expected), replayed_sessions=sum(r["status"] == "REPLAYED" for r in rows),
        missing_sessions=[r["session"] for r in rows if r["status"] == "MISSING_SESSION"],
        invalid_or_incomplete_sessions=[r["session"] for r in rows if r["status"] == "INCOMPLETE_OR_INVALID"],
        rows=rows, status="REPLAYED" if all(r["status"] == "REPLAYED" for r in rows) else "PARTIAL",
        declared_registration_precedes_decisions=bool(snapshots) and all(
            registered <= _time(x["decision_at"]) for x in snapshots),
        registration_assurance="DECLARED_TIMESTAMP_NOT_INDEPENDENT_PREREGISTRATION_PROOF",
        metrics_scope="DATED_UNIVERSE_AND_STRUCTURE_REPLAY_NOT_EXECUTION_OR_WALK_FORWARD",
        strict_pit_admitted=False, strict_oos_admitted=False, strategy_validation="NOT_PROVEN",
        elapsed_real_shadow_sessions=0, formal_eligibility=False, trade_eligible=False,
        limitations=["Coverage is the retained provider universe, not certified all-market completeness",
            "Historical industry effective dates remain unproved",
            "No fold training, independent OOS, corporate-action or execution validation inferred",
            "Leaving a candidate pool never requests selling an owned position"])
    result["content_sha256"] = fingerprint(result)
    return result
