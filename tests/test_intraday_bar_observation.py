"""Synthetic retained Sina bytes; no market collection or authorization."""
import base64
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json

import pytest

from value_investment_agent.application.hotspot.intraday_bar_observation import project_intraday_bar_observation
from value_investment_agent.application.hotspot.intraday_conditions import CHINA, evaluate_intraday_condition
from value_investment_agent.infrastructure.hotspot.sina_price_case import ENDPOINT, parse_klines


NOW = datetime.fromisoformat("2026-10-16T10:30:05+08:00")
AGE = timedelta(seconds=30)


def row(stamp="2026-10-16 10:30:00", **changes):
    return {"day": stamp, "open": "10", "high": "12", "low": "9", "close": "11",
            "volume": "100", "amount": "1100", **changes}


def document(*, rows=None, symbol="600519", period="60m", now=NOW):
    raw = ("/*TEST_ONLY*/\n=(" + json.dumps([row()] if rows is None else rows) + ");").encode()
    market = ("sh" if symbol.startswith("6") else "sz") + symbol
    return {"raw_base64": base64.b64encode(raw).decode(), "sha256": hashlib.sha256(raw).hexdigest(),
            "source_url": ENDPOINT + f"?symbol={market}&scale={period[:-1]}&ma=no&datalen=100",
            "http_status": 200, "fetched_at": (now - timedelta(seconds=1)).isoformat()}


def project(doc, *, symbol="600519", period="60m", now=NOW, max_age=AGE):
    return project_intraday_bar_observation(doc, symbol=symbol, period=period, now=now, max_age=max_age)


@pytest.mark.parametrize("symbol,period", [("600519", "15m"), ("000333", "60m"), ("300364", "15m")])
def test_raw_bridge_to_real_adapter_is_completed_single_provider_only(symbol, period):
    doc = document(symbol=symbol, period=period)
    before = deepcopy(doc)
    result = project(doc, symbol=symbol, period=period)
    assert result["status"] == "COMPLETED_BAR_VERIFIED", result
    observation = result["observation"]
    assert observation["price"] == "11"
    assert observation["source_at"] == observation["bar_end"] == "2026-10-16T02:30:00+00:00"
    assert observation["received_at"] == "2026-10-16T02:30:04+00:00"
    assert observation["evidence_refs"][0]["sha256"] == doc["sha256"]
    assert "INTRADAY_SINGLE_PROVIDER" in result["blockers"]
    assert result["formal_eligibility"] is result["admitted"] is result["b1_eligible"] is False
    c = {"strategy": "HOTSPOT_SATELLITE", "symbol": symbol,
         "venue": "SSE" if symbol.startswith("6") else "SZSE", "condition_id": "TEST_ONLY_BAR",
         "rule_version": "TEST_ONLY_v1", "source_id": "sina", "source_url": doc["source_url"],
         "input_kind": "COMPLETED_BAR", "period": period, "operator": "GT", "threshold": "10",
         "action": "no_order"}
    evaluated = evaluate_intraday_condition(c, observation, previous=None, now=NOW,
        max_age=AGE, namespace="SIMULATED")
    assert evaluated.state["status"] == "CONDITION_REVIEW"
    assert len(evaluated.events) == 1 and evaluated.admitted is evaluated.eligibility is False
    assert doc == before


@pytest.mark.parametrize("change", [
    {"sha256": "0" * 64}, {"http_status": 404}, {"http_status": True}, {"raw_base64": "!!"},
    {"fetched_at": "2026-10-16T10:30:06+08:00"}, {"fetched_at": "2026-10-16T10:30:04"},
    {"fetched_at": "2026-10-16T10:29:00+08:00"},
    {"source_url": ENDPOINT + "?symbol=sz000333&scale=60&ma=no"},
    {"source_url": ENDPOINT + "?symbol=sh600519&scale=15&ma=no"},
    {"source_url": ENDPOINT + "?symbol=sh600519&symbol=sh600519&scale=60&ma=no"},
    {"source_url": ENDPOINT + "?symbol=sh600519&scale=60&ma=no&filter=partial"},
    {"source_url": ENDPOINT + "?symbol=sh600519&scale=60&ma=no&datalen=0"},
    {"source_url": ENDPOINT.replace("https:", "http:") + "?symbol=sh600519&scale=60&ma=no"},
    {"source_url": ENDPOINT.replace("quotes.sina.cn", "user@quotes.sina.cn") + "?symbol=sh600519&scale=60&ma=no"},
    {"source_url": ENDPOINT + "?symbol=sh600519&scale=60&ma=no#fake"},
    {"source_url": ENDPOINT.replace("/cn/api/", "/fake/") + "?symbol=sh600519&scale=60&ma=no"},
])
def test_source_identity_hash_and_receipt_tampering_rejected(change):
    result = project({**document(), **change})
    assert result["status"] == "STALE_OR_UNAVAILABLE"
    assert result["observation"] is None


@pytest.mark.parametrize("rows", [
    [row("2026-10-16 10:29:00")], [row("2026-10-16 12:00:00")],
    [row("2026-10-16 10:30:00.000001")], [row("2026-10-16T10:30:00+08:00")],
    [row("2026-10-19 10:30:00")], [row("2026-10-15 15:00:00")],
    [row(), row()], [row(), row("2026-10-16 09:45:00")],
    [row(close="NaN")], [row(high="8")], [row(volume="0")], [row(amount="0")],
    [row(low="0")], [],
])
def test_incomplete_future_stale_off_grid_and_invalid_bars_never_fall_back(rows):
    result = project(document(rows=rows))
    assert result["status"] == "STALE_OR_UNAVAILABLE", result
    assert result["observation"] is None


def test_live_partial_bar_is_preserved_but_never_used_as_the_completed_bar():
    result = project(document(rows=[row(), row("2026-10-16 11:30:00")]))
    assert result["status"] == "COMPLETED_BAR_VERIFIED"
    assert result["observation"]["bar_end"] == "2026-10-16T02:30:00+00:00"
    assert result["observation"]["close"] == "11"
    assert result["observation"]["completed"] is True


@pytest.mark.parametrize("stamp", ["2026-10-16T12:00:00+08:00", "2026-10-16T09:29:00+08:00",
    "2026-10-16T15:01:00+08:00", "2026-10-17T10:30:05+08:00", "2026-10-01T10:30:05+08:00",
    "2027-01-04T10:30:05+08:00"])
def test_lunch_closed_holiday_and_uncovered_calendar_fail_closed(stamp):
    now = datetime.fromisoformat(stamp)
    assert project(document(now=now), now=now)["observation"] is None


def test_receipt_before_bar_end_and_fresh_receipt_of_old_bar_rejected():
    result = project({**document(), "fetched_at": "2026-10-16T10:29:59+08:00"})
    assert result["observation"] is None
    later = NOW + timedelta(minutes=1)
    result = project(document(now=later), now=later)
    assert result["reason"] == "STALE_COMPLETED_BAR"
    assert result["observation"] is None


def test_close_endpoint_can_be_observed_at_exact_close_not_during_lunch_receipt():
    now = NOW.replace(hour=15, minute=0, second=0)
    doc = document(rows=[row("2026-10-16 15:00:00")], now=now)
    doc["fetched_at"] = now.isoformat()
    assert project(doc, now=now)["status"] == "COMPLETED_BAR_VERIFIED"
    now = NOW.replace(hour=13, minute=0, second=1)
    doc = document(rows=[row("2026-10-16 11:30:00")], now=now)
    doc["fetched_at"] = "2026-10-16T12:59:59+08:00"
    assert project(doc, now=now, max_age=timedelta(hours=2))["observation"] is None


def test_default_historical_parser_retains_exact_full_close_output_and_does_not_mutate_raw():
    rows = [row("2026-10-16 " + clock) for clock in ("10:30:00", "11:30:00", "14:00:00", "15:00:00")]
    raw = base64.b64decode(document(rows=rows)["raw_base64"])
    before = bytes(raw)
    expected = [{"time": item["day"], **{key: item[key] for key in
        ("open", "high", "low", "close", "volume", "amount")}} for item in rows]
    assert parse_klines(raw, period="60m", as_of=date(2026, 10, 16)) == expected
    assert raw == before
    partial = base64.b64decode(document()["raw_base64"])
    with pytest.raises(ValueError, match="completed final bar"):
        parse_klines(partial, period="60m", as_of=date(2026, 10, 16))
    assert parse_klines(partial, period="60m", as_of=date(2026, 10, 16), completed_through=NOW) == expected[:1]


def test_explicit_parser_cutoff_requires_aware_same_date_exchange_clock():
    raw = base64.b64decode(document()["raw_base64"])
    for clock in (NOW.replace(tzinfo=None), NOW + timedelta(days=1)):
        with pytest.raises(ValueError):
            parse_klines(raw, period="60m", as_of=date(2026, 10, 16), completed_through=clock)


def test_explicit_parser_cutoff_drops_only_the_live_partial_bar():
    rows = [row("2026-10-16 10:30:00"), row("2026-10-16 11:30:00")]
    raw = base64.b64decode(document(rows=rows)["raw_base64"])
    cutoff = datetime(2026, 10, 16, 10, 31, tzinfo=CHINA)
    parsed = parse_klines(raw, period="60m", as_of=date(2026, 10, 16),
                          completed_through=cutoff)
    assert [item["time"] for item in parsed] == ["2026-10-16 10:30:00"]


@pytest.mark.parametrize("changes", [{"now": NOW.replace(tzinfo=None)}, {"max_age": timedelta(0)},
    {"symbol": "60051\uff11"}, {"symbol": "800001"}, {"period": "daily"}])
def test_bad_caller_contract_rejected(changes):
    with pytest.raises(ValueError):
        project(document(), **changes)
