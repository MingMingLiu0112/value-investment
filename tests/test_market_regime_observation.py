from datetime import datetime, timezone

from value_investment_agent.application.market_regime import observe_market_regime


CUTOFF = datetime(2026, 10, 12, tzinfo=timezone.utc)


def snapshot(day, changes, amounts, *, digest="a" * 64):
    return dict(action="no_order", session_date=day,
                available_at=f"{day}T08:00:00+00:00", universe_id="fixed-a-share-subset-v1",
                source_sha256=digest,
                rows=[dict(code=code, changepercent=str(change), amount=str(amount))
                      for code, change, amount in zip(("000001", "600000"), changes, amounts)])


def test_dated_breadth_and_prior_turnover_are_descriptive_only():
    result = observe_market_regime([
        snapshot("2026-10-08", (1, -1), (40, 60)),
        snapshot("2026-10-09", (2, 0), (75, 75))], cutoff=CUTOFF)
    assert result["status"] == "OBSERVED"
    assert result["market_breadth_ratio"] == "0.5"
    assert result["turnover_change_ratio"] == "0.5"
    assert result["turnover_baseline_sessions"] == ["2026-10-08"]
    assert result["regime"] == "UNKNOWN"
    assert result["action"] == "no_order" and result["position_guidance"] is None


def test_distinct_sessions_required_and_dates_never_inferred():
    one = snapshot("2026-10-09", (1, -1), (40, 60))
    assert observe_market_regime([one], cutoff=CUTOFF)["status"] == "UNKNOWN"
    assert observe_market_regime([one, one], cutoff=CUTOFF)["reason"] == "DUPLICATE_SESSION_DATE"
    del one["session_date"]
    assert observe_market_regime([one], cutoff=CUTOFF)["reason"] == "SESSION_DATE_MISSING_OR_INVALID"


def test_incomplete_or_incomparable_evidence_fails_closed():
    first = snapshot("2026-10-08", (1, -1), (40, 60))
    second = snapshot("2026-10-09", (2, 0), (75, 75))
    second["rows"][1]["code"] = "300001"
    assert observe_market_regime([first, second], cutoff=CUTOFF)["reason"] == "MEMBERSHIP_CHANGED"
    second["rows"][1]["code"] = "600000"
    second["available_at"] = "2026-10-13T00:00:00+00:00"
    assert observe_market_regime([first, second], cutoff=CUTOFF)["reason"] == "SOURCE_NOT_AVAILABLE_AT_CUTOFF"
    second["available_at"] = "2026-10-09T08:00:00+00:00"
    first["rows"][0]["amount"] = "0"
    first["rows"][1]["amount"] = "0"
    assert observe_market_regime([first, second], cutoff=CUTOFF)["reason"] == "ZERO_PRIOR_TURNOVER"
