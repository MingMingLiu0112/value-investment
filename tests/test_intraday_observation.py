"""TEST_ONLY retained dual-source bytes, no source collection or activation."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib

import pytest

from test_quote_sessions import evidence
from value_investment_agent.application.hotspot.intraday_conditions import evaluate_intraday_condition
from value_investment_agent.application.hotspot.intraday_observation import project_intraday_observation


NOW = datetime.fromisoformat("2026-10-16T10:30:05+08:00")
AGE = timedelta(seconds=30)


def identity(document):
    return hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"]
                          + "\n" + document["sha256"]).encode()).hexdigest()


def bundle(now=NOW, symbol="600519", *, source_at=None):
    source_at = source_at or now - timedelta(seconds=5)
    data = evidence(price=60, day=source_at.strftime("%Y-%m-%d"),
                    clock=source_at.strftime("%H:%M:%S"), symbol=symbol)
    documents, references = {}, {}
    for provider in ("tencent", "sina"):
        doc = data[provider]
        doc.update(fetched_at=(now - timedelta(seconds=3)).isoformat(), http_status=200)
        key = identity(doc)
        documents[key], references[provider] = doc, key
    venue = "SSE" if symbol.startswith("6") else "SZSE"
    return dict(version="quote-session-collection-v1", started_at=(now - timedelta(seconds=4)).isoformat(),
        finished_at=(now - timedelta(seconds=2)).isoformat(), documents=documents,
        references={symbol: dict(symbol=symbol, calendar_exchange=venue,
                                 document_refs={**references, "calendar_documents": []})})


def doc(data, provider="tencent", symbol="600519"):
    return data["documents"][data["references"][symbol]["document_refs"][provider]]


def rekey(data, provider="tencent", symbol="600519"):
    refs = data["references"][symbol]["document_refs"]
    old = refs[provider]
    document = data["documents"].pop(old)
    document["sha256"] = hashlib.sha256(base64.b64decode(document["raw_base64"])).hexdigest()
    key = identity(document)
    data["documents"][key], refs[provider] = document, key


def field(data, provider, index, value):
    document = doc(data, provider)
    raw = base64.b64decode(document["raw_base64"]).decode("gb18030")
    before, quoted, after = raw.split('"')
    separator = "~" if provider == "tencent" else ","
    fields = quoted.split(separator)
    fields[index] = value
    document["raw_base64"] = base64.b64encode((before + '"' + separator.join(fields) + '"' + after).encode("gb18030")).decode()
    rekey(data, provider)


def project(data, *, now=NOW, symbol="600519", max_age=AGE):
    return project_intraday_observation(data, symbol=symbol, now=now, max_age=max_age)


@pytest.mark.parametrize("symbol", ["600519", "000333"])
def test_retained_bytes_to_quote_adapter_without_admission_or_mutation(symbol):
    data = bundle(symbol=symbol)
    original = deepcopy(data)
    result = project(data, symbol=symbol)
    assert result["status"] == "QUOTE_VERIFIED"
    o = result["observation"]
    assert o["source_url"] == doc(data, symbol=symbol)["source_url"]
    assert o["evidence_refs"][0]["sha256"] == doc(data, symbol=symbol)["sha256"]
    assert o["cross_check_evidence_refs"][0]["provider"] == "sina"
    assert o["completed"] is False and o["period"] == "quote"
    condition = dict(strategy="HOTSPOT_SATELLITE", symbol=symbol,
        venue="SSE" if symbol.startswith("6") else "SZSE", condition_id="TEST_ONLY_above",
        rule_version="TEST_ONLY_explicit_v1", source_id=o["source_id"], source_url=o["source_url"],
        input_kind="QUOTE", period="quote", operator="GT", threshold="59", action="no_order")
    adapted = evaluate_intraday_condition(condition, o, previous=None, now=NOW, max_age=AGE, namespace="SIMULATED")
    assert adapted.state["status"] == "STRUCTURE_OBSERVATION"
    assert len(adapted.events) == 1
    assert not adapted.admitted and not adapted.eligibility and not adapted.b1_eligible
    assert not result["admitted"] and not result["eligibility"] and not result["b1_eligible"]
    assert data == original
    o["evidence_refs"][0]["sha256"] = "mutated return"
    assert data == original


@pytest.mark.parametrize("failure", ["hash", "document_id", "symbol", "reference_symbol", "venue",
    "missing_provider", "http_status", "future_source", "source_after_receipt", "future_received",
    "stale", "naive_receipt", "zero_volume_tx", "zero_volume_sina", "abnormal_sina", "bad_volume",
    "price_conflict", "tiny_price_conflict", "bad_source_url", "bundle_clock", "missing_raw"])
def test_invalid_retained_source_never_produces_observation(failure):
    data = bundle()
    if failure == "hash":
        doc(data)["raw_base64"] = base64.b64encode(b"changed").decode()
    elif failure == "document_id":
        doc(data)["fetched_at"] = NOW.isoformat()
    elif failure == "symbol":
        field(data, "tencent", 2, "000001")
    elif failure == "reference_symbol":
        data["references"]["600519"]["symbol"] = "000001"
    elif failure == "venue":
        data["references"]["600519"]["calendar_exchange"] = "SZSE"
    elif failure == "missing_provider":
        data["references"]["600519"]["document_refs"]["sina"] = None
    elif failure == "http_status":
        doc(data)["http_status"] = 503
    elif failure == "future_source":
        field(data, "tencent", 30, "20261016103100")
    elif failure == "source_after_receipt":
        field(data, "tencent", 30, "20261016103003")
    elif failure == "future_received":
        doc(data)["fetched_at"] = (NOW + timedelta(seconds=1)).isoformat()
        rekey(data)
    elif failure == "stale":
        field(data, "tencent", 30, "20261016102900")
    elif failure == "naive_receipt":
        doc(data)["fetched_at"] = "2026-10-16T10:30:02"
        rekey(data)
    elif failure == "zero_volume_tx":
        field(data, "tencent", 6, "0")
    elif failure == "zero_volume_sina":
        field(data, "sina", 8, "0")
    elif failure == "abnormal_sina":
        field(data, "sina", 32, "01")
    elif failure == "bad_volume":
        field(data, "sina", 8, "not-numeric")
    elif failure in {"price_conflict", "tiny_price_conflict"}:
        field(data, "sina", 3, "60.01" if failure == "price_conflict" else "60.000000001")
    elif failure == "bad_source_url":
        doc(data)["source_url"] = "https://foreign.invalid/q=sh600519"
        rekey(data)
    elif failure == "bundle_clock":
        data["finished_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif failure == "missing_raw":
        doc(data).pop("raw_base64")
    result = project(data)
    assert result["status"] == "STALE_OR_UNAVAILABLE"
    assert result["observation"] is None and result["reason"]
    if "price_conflict" in failure:
        assert result["reason"] == "CROSS_SOURCE_PRICE_CONFLICT"


@pytest.mark.parametrize("stamp", ["2026-10-16T12:00:05+08:00", "2026-10-16T09:29:05+08:00",
    "2026-10-16T15:01:05+08:00", "2026-10-17T10:30:05+08:00", "2026-10-01T10:30:05+08:00",
    "2027-01-04T10:30:05+08:00"])
def test_lunch_holiday_weekend_closed_and_uncovered_sessions_fail_closed(stamp):
    now = datetime.fromisoformat(stamp)
    result = project(bundle(now), now=now)
    assert result["status"] == "STALE_OR_UNAVAILABLE" and result["observation"] is None


def test_older_cross_check_clock_is_preserved_as_conservative_freshness():
    data = bundle()
    field(data, "sina", 31, "10:29:50")
    result = project(data)
    assert result["status"] == "QUOTE_VERIFIED"
    o = result["observation"]
    assert o["source_at"] == o["provider_source_at"]["sina"]
    assert o["source_at"] < o["provider_source_at"]["tencent"]
    assert project(data, max_age=timedelta(seconds=10))["reason"] == "STALE_QUOTE"


@pytest.mark.parametrize("max_age", [timedelta(0), timedelta(seconds=-1), None, 30])
def test_explicit_freshness_policy_required(max_age):
    with pytest.raises(ValueError):
        project(bundle(), max_age=max_age)


def test_failed_bridge_passes_no_quote_to_adapter():
    data = bundle()
    field(data, "sina", 3, "61")
    result = project(data)
    c = dict(strategy="HOTSPOT_SATELLITE", symbol="600519", venue="SSE", condition_id="TEST_ONLY",
        rule_version="TEST_ONLY_v1", source_id="tencent", source_url=doc(data)["source_url"],
        input_kind="QUOTE", period="quote", operator="GT", threshold="59", action="no_order")
    adapted = evaluate_intraday_condition(c, result["observation"], previous=None,
        now=NOW, max_age=AGE, namespace="SIMULATED")
    assert adapted.state["status"] == "STALE_OR_UNAVAILABLE"
    assert [e.event_type for e in adapted.events] == ["SOURCE_SCAN_FAILED"]


@pytest.mark.parametrize("provider", ["tencent", "sina"])
@pytest.mark.parametrize("failure", ["hash", "identity", "future", "receipt_future", "receipt_naive"])
def test_each_provider_must_independently_pass_raw_and_clock_validation(provider, failure):
    data = bundle()
    document = doc(data, provider)
    if failure == "hash":
        document["raw_base64"] = base64.b64encode(b"forged bytes").decode()
    elif failure == "identity":
        raw = base64.b64decode(document["raw_base64"]).replace(b"sh600519", b"sh600000")
        document["raw_base64"] = base64.b64encode(raw).decode()
        rekey(data, provider)
    elif failure == "future":
        field(data, provider, 30 if provider == "tencent" else 31,
              "20261016103100" if provider == "tencent" else "10:31:00")
    else:
        document["fetched_at"] = ((NOW + timedelta(seconds=1)).isoformat()
                                  if failure == "receipt_future" else "2026-10-16T10:30:02")
        rekey(data, provider)
    result = project(data)
    assert result["observation"] is None and result["status"] == "STALE_OR_UNAVAILABLE"


def test_observation_window_cannot_reuse_prior_day_or_lunch_source_even_with_large_max_age():
    for source_at in (NOW - timedelta(days=1), NOW.replace(hour=12, minute=59, second=59)):
        now = NOW if source_at.date() != NOW.date() else NOW.replace(hour=13, minute=0)
        result = project(bundle(now, source_at=source_at), now=now, max_age=timedelta(days=2))
        assert result["status"] == "STALE_OR_UNAVAILABLE" and result["observation"] is None
