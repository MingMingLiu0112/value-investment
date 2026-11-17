"""TEST_ONLY source replay and existing native conditions, no live requests."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json

import pytest

from test_intraday_plan_observation import plan, bind
from value_investment_agent.application.hotspot.intraday_completed_plan import project_completed_plan
from value_investment_agent.application.hotspot.intraday_bar_observation import project_intraday_bar_observation
from value_investment_agent.infrastructure.hotspot.sina_price_case import ENDPOINT


NOW = datetime.fromisoformat("2026-09-28T10:55:00+08:00")


def documents(price="14", now=NOW):
    result = {}
    for period, end in (("60m", "10:30:00"), ("15m", "10:45:00")):
        row = dict(day="2026-09-28 " + end, open=price, high=price, low=price,
                   close=price, volume="100", amount="1400")
        result[period] = raw_document(period, [row], now)
    return result


def raw_document(period, rows, now):
    raw = ("/*TEST_ONLY*/=(" + json.dumps(rows) + ");").encode()
    return dict(raw_base64=base64.b64encode(raw).decode(), sha256=hashlib.sha256(raw).hexdigest(),
        source_url=ENDPOINT + f"?symbol=sh600519&scale={period[:-1]}&ma=no&datalen=8",
        http_status=200, fetched_at=(now - timedelta(seconds=1)).isoformat())


def qualified(plan):
    candidate = deepcopy(plan)
    candidate["opportunity_quality"]["structure_tier"] = "STRUCTURE_QUALIFIED_OBSERVATION"
    return bind(candidate)


def test_completed_confirmation_exact_source_contract_and_deterministic_replay(plan):
    binding, docs = qualified(plan), documents()
    before = deepcopy((binding, docs))
    result = project_completed_plan(binding, docs, now=NOW)
    assert result["status"] == "WAITING_CONFIRMATION", result
    assert result["price_conditions_observed"] is True
    assert result["structure_confirmation"] is False
    assert "PRIOR_FIVE_VOLUME_RULE" in result["pending_confirmations"]
    assert result == project_completed_plan(binding, docs, now=NOW)
    assert (binding, docs) == before
    assert len(result["evidence"]) == 2
    for period, item in result["periods"].items():
        o = item["source_result"]["observation"]
        assert o["completed"] is True and o["period"] == period
        assert o["raw_sha256"] == docs[period]["sha256"]
        assert o["adjustment_basis"] == "UNADJUSTED"
        assert Decimal(o["close"]) == 14 and o["volume"] == "100"
        assert datetime.fromisoformat(o["bar_end"]) - datetime.fromisoformat(o["bar_start"]) == timedelta(minutes=int(period[:-1]))
        assert o["source_at"] == o["bar_end"]
        assert item["document"] == docs[period]
        assert item["states"][0]["state"]["status"] == "CONDITION_REVIEW"
    assert result["action"] == "no_order"
    assert result["eligibility"] is result["formal_eligibility"] is result["m5_admitted"] is False
    restarted = project_completed_plan(binding, docs, previous=json.loads(json.dumps(result)), now=NOW)
    assert restarted == result


def test_entry_needs_both_periods_and_existing_structure_quality(plan):
    unqualified = deepcopy(plan)
    unqualified["opportunity_quality"]["structure_tier"] = "ACTIVE_ONLY"
    assert project_completed_plan(bind(unqualified), documents(), now=NOW)["status"] == "WAITING_CONFIRMATION"
    docs = documents()
    docs["15m"] = documents(str(plan["entry_trigger_price"]))["15m"]
    assert project_completed_plan(qualified(plan), docs, now=NOW)["status"] == "WAITING_CONFIRMATION"


def test_invalidation_is_observation_risk_even_with_other_period_missing(plan):
    docs = documents(str(Decimal(plan["invalidation_price"]) - 1))
    del docs["15m"]
    result = project_completed_plan(qualified(plan), docs, now=NOW)
    assert result["status"] == "RISK_REVIEW"
    assert result["formal_eligibility"] is False


@pytest.mark.parametrize("defect", ["missing", "bad-hash", "http-error", "stale-receipt",
    "stale-bar", "wrong-period", "wrong-symbol", "collection-error", "bad-ohlc", "adjusted"])
def test_bad_period_preserved_and_never_confirms(plan, defect):
    docs = documents()
    doc = docs["15m"]
    if defect == "missing":
        del docs["15m"]
    elif defect == "bad-hash":
        doc["sha256"] = "0" * 64
    elif defect == "http-error":
        doc["http_status"] = 503
    elif defect == "stale-receipt":
        doc["fetched_at"] = (NOW - timedelta(seconds=121)).isoformat()
    elif defect == "stale-bar":
        docs["15m"] = documents(now=NOW.replace(hour=11, minute=10))["15m"]
    elif defect == "wrong-period":
        doc["source_url"] = doc["source_url"].replace("scale=15", "scale=60")
    elif defect == "wrong-symbol":
        doc["source_url"] = doc["source_url"].replace("sh600519", "sz000333")
    elif defect == "collection-error":
        doc["error"] = "SOURCE_REQUEST_FAILED"
    elif defect == "adjusted":
        doc["adjustment"] = "FORWARD_ADJUSTED"
    else:
        docs["15m"] = raw_document("15m", [dict(day="2026-09-28 10:45:00", open="14",
            high="12", low="10", close="14", volume="100", amount="1400")], NOW)
    before = deepcopy(docs)
    result = project_completed_plan(qualified(plan), docs, now=NOW)
    assert result["status"] == "INSUFFICIENT_DATA", result
    assert result["periods"]["15m"]["document"] == docs.get("15m")
    assert docs == before


def test_live_partial_bar_is_excluded_from_completed_plan_state(plan):
    docs = documents()
    rows = json.loads(base64.b64decode(docs["15m"]["raw_base64"]).decode().split("=(")[1][:-2])
    rows.append({**rows[-1], "day": "2026-09-28 11:00:00"})
    docs["15m"] = raw_document("15m", rows, NOW)
    result = project_completed_plan(qualified(plan), docs, now=NOW)
    assert result["status"] == "WAITING_CONFIRMATION"
    assert all(row["state"]["last_bar_end"] != "2026-09-28T03:00:00+00:00"
               for row in result["periods"]["15m"]["states"])


def test_separate_bar_age_keeps_receipt_limit_and_defaults_compatible():
    doc = documents()["60m"]
    kwargs = dict(symbol="600519", period="60m", now=NOW, max_age=timedelta(seconds=120))
    assert project_intraday_bar_observation(doc, **kwargs)["reason"] == "STALE_COMPLETED_BAR"
    assert project_intraday_bar_observation(doc, **kwargs, max_bar_age=timedelta(seconds=3720))["observation"]
    doc["fetched_at"] = (NOW - timedelta(seconds=121)).isoformat()
    assert project_intraday_bar_observation(doc, **kwargs, max_bar_age=timedelta(seconds=3720))["observation"] is None
    with pytest.raises(ValueError):
        project_intraday_bar_observation(doc, **kwargs, max_bar_age=timedelta(0))


@pytest.mark.parametrize("period,end,limit", [("60m", "10:30:00", 3599), ("15m", "10:45:00", 1020)])
def test_exact_bar_age_boundary_and_one_second_past(period, end, limit):
    end_at = datetime.fromisoformat("2026-09-28T" + end + "+08:00")
    for extra, accepted in ((0, True), (1, False)):
        now = end_at + timedelta(seconds=limit + extra)
        doc = documents(now=now)[period]
        result = project_intraday_bar_observation(doc, symbol="600519", period=period,
            now=now, max_age=timedelta(seconds=120), max_bar_age=timedelta(seconds=limit))
        assert (result["observation"] is not None) is accepted


def test_missing_collection_recovers_and_same_bar_conflict_is_retained(plan):
    binding = qualified(plan)
    initial = project_completed_plan(binding, {}, now=NOW)
    assert initial["status"] == "INSUFFICIENT_DATA"
    recovered = project_completed_plan(binding, documents(), previous=initial, now=NOW)
    assert recovered["status"] == "WAITING_CONFIRMATION"
    conflict = project_completed_plan(binding, documents("15"), previous=recovered, now=NOW)
    assert conflict["status"] == "INSUFFICIENT_DATA"
    assert all(p["status"] == "INSUFFICIENT_DATA" for p in conflict["periods"].values())
    assert all(p["reason"] == "CONFLICTING_REPEATED_OBSERVATION" for p in conflict["periods"].values())
    assert all(p["document"] for p in conflict["periods"].values())


def test_strict_invalidation_threshold_and_session_boundaries(plan):
    binding = qualified(plan)
    at_threshold = project_completed_plan(binding, documents(str(plan["invalidation_price"])), now=NOW)
    assert at_threshold["status"] == "WAITING_CONFIRMATION"
    for now in (NOW.replace(hour=12), NOW.replace(day=27)):
        result = project_completed_plan(binding, documents(), now=now)
        assert result["status"] == "INSUFFICIENT_DATA"


def test_binding_tamper_expiry_previous_and_unaware_clocks_fail_closed(plan):
    binding = qualified(plan)
    bad = deepcopy(binding)
    bad["plan"]["entry_trigger_price"] = "999"
    with pytest.raises(ValueError):
        project_completed_plan(bad, documents(), now=NOW)
    with pytest.raises(ValueError):
        project_completed_plan(binding, documents(), now=NOW.replace(tzinfo=None))
    result = project_completed_plan(binding, documents(), now=NOW)
    result["status"] = "RISK_REVIEW"
    with pytest.raises(ValueError):
        project_completed_plan(binding, documents(), previous=result, now=NOW)
    expired = project_completed_plan(binding, documents(), now=NOW.replace(hour=15, minute=0))
    assert expired["status"] == "INSUFFICIENT_DATA"
    assert all(p["reason"] == "PLAN_REFERENCE_EXPIRED" for p in expired["periods"].values())
