"""Describe dated market breadth and turnover without admitting a trade signal."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


SCHEMA = "market-regime-observation-v1"


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Metric requires an explicit decimal")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid decimal metric") from error
    if not result.is_finite():
        raise ValueError("Nonfinite metric")
    return result


def _unknown(reason, dates=()):
    return dict(schema_version=SCHEMA, status="UNKNOWN", regime="UNKNOWN",
                reason=reason, session_dates=list(dates), market_breadth_ratio=None,
                turnover_change_ratio=None, action="no_order",
                scope="OBSERVATION_ONLY", position_guidance=None)


def observe_market_regime(snapshots, *, cutoff, minimum_sessions=2):
    """Use complete, explicitly dated M2-style rows from one fixed universe.

    Each snapshot has session_date, available_at, universe_id, source_sha256,
    and rows with unique code, changepercent and amount (CNY). Collection
    timestamps and per-row ticktime never establish a trading session.
    """
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() is None:
        raise ValueError("cutoff requires a timezone-aware timestamp")
    if type(minimum_sessions) is not int or minimum_sessions < 2:
        raise ValueError("minimum_sessions must be at least two")
    if not isinstance(snapshots, (list, tuple)) or len(snapshots) > 30:
        raise ValueError("snapshots must be a bounded sequence")
    sessions = {}
    universe = None
    members = None
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or snapshot.get("action") != "no_order":
            return _unknown("UNSUPPORTED_SNAPSHOT")
        day = snapshot.get("session_date")
        try:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                return _unknown("SESSION_DATE_MISSING_OR_INVALID")
            available = datetime.fromisoformat(snapshot["available_at"])
            if available.utcoffset() is None or available > cutoff:
                return _unknown("SOURCE_NOT_AVAILABLE_AT_CUTOFF")
        except (KeyError, TypeError, ValueError):
            return _unknown("SOURCE_TIME_MISSING_OR_INVALID")
        digest = snapshot.get("source_sha256")
        identity = snapshot.get("universe_id")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or not isinstance(identity, str) or not identity.strip()):
            return _unknown("SOURCE_OR_UNIVERSE_UNBOUND")
        if day in sessions:
            return _unknown("DUPLICATE_SESSION_DATE", sorted(sessions))
        if universe is not None and identity != universe:
            return _unknown("UNIVERSE_CHANGED", sorted(sessions))
        universe = identity
        rows = snapshot.get("rows")
        if not isinstance(rows, list) or not rows:
            return _unknown("ROWS_MISSING", sorted(sessions))
        seen = set()
        advances = 0
        turnover = Decimal(0)
        try:
            for row in rows:
                code = row["code"]
                if not isinstance(code, str) or not code or code in seen:
                    return _unknown("DUPLICATE_OR_INVALID_MEMBER", sorted(sessions))
                seen.add(code)
                change = _decimal(row["changepercent"])
                amount = _decimal(row["amount"])
                if amount < 0:
                    return _unknown("NEGATIVE_TURNOVER", sorted(sessions))
                advances += change > 0
                turnover += amount
        except (KeyError, TypeError, ValueError):
            return _unknown("INCOMPLETE_MARKET_ROWS", sorted(sessions))
        if members is not None and seen != members:
            return _unknown("MEMBERSHIP_CHANGED", sorted(sessions))
        members = seen
        sessions[day] = dict(advances=advances, count=len(seen), turnover=turnover,
                             source_sha256=digest)
    dates = sorted(sessions)
    if len(dates) < minimum_sessions:
        return _unknown("INSUFFICIENT_DISTINCT_SESSIONS", dates)
    current = sessions[dates[-1]]
    prior = [sessions[day] for day in dates[-minimum_sessions:-1]]
    baseline = sum((item["turnover"] for item in prior), Decimal(0)) / len(prior)
    if baseline <= 0:
        return _unknown("ZERO_PRIOR_TURNOVER", dates)
    breadth = Decimal(current["advances"]) / current["count"]
    return dict(schema_version=SCHEMA, status="OBSERVED", regime="UNKNOWN",
                reason="DESCRIPTIVE_METRICS_ONLY", session_dates=dates,
                universe_id=universe, member_count=current["count"],
                market_breadth_ratio=str(breadth),
                turnover_change_ratio=str(current["turnover"] / baseline - 1),
                turnover_baseline_sessions=dates[-minimum_sessions:-1],
                source_sha256_by_date={day: sessions[day]["source_sha256"] for day in dates},
                action="no_order", scope="OBSERVATION_ONLY", position_guidance=None)
