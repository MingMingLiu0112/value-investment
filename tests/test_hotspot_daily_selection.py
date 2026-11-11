"""Daily ranking cannot promote stale, excluded or unknown facts to admission."""
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import pytest
from value_investment_agent.domain.hotspot.daily_selection import rank_daily_candidates, RULE_VERSION
from value_investment_agent.infrastructure.hotspot.daily_market import collect_dated_market, requested_quote_symbols
from value_investment_agent.application.hotspot.daily_selection import collect_daily_candidates, verify_daily_selection


def test_classification_uses_bounded_transport_and_retains_provider_originals(monkeypatch):
    from value_investment_agent import m2_market_data as module
    import base64
    calls = []
    class Response:
        def __init__(self, value, url):
            self.content = json.dumps(value, ensure_ascii=False).encode()
            self.url = url
        def raise_for_status(self):
            pass
        def json(self):
            return json.loads(self.content)
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, params, timeout):
            calls.append((url, params, timeout))
            if url.endswith('getHQNodes'):
                value = [None, [[None, [['<font>申万行业</font>', [['Media', '', 'sw_media']]]]]]]
            elif url.endswith('getHQNodeStockCount'):
                value = '1'
            else:
                value = [{'code': '300001', 'name': 'Company', 'trade': '10'}]
            return Response(value, url)
    monkeypatch.setattr(module.requests, 'Session', Session)
    raw, report = module.fetch_sina_industry_quotes()
    assert json.loads(raw) == report
    assert len(calls) == 3 and all(call[2] == (10, 20) for call in calls)
    assert report['rows'][0]['class'] == 'Media'
    for original in report['original_responses']:
        assert hashlib.sha256(base64.b64decode(original['raw_base64'])).hexdigest() == original['sha256']


def row(symbol, industry, change, amount, **extra):
    return dict(symbol=symbol, company_name=symbol, industry=industry, close="10",
                change_percent=str(change), amount_cny=str(amount), trade_date="2026-10-14",
                status="DATED_COMPLETED_QUOTE", **extra)


def test_current_sector_ranking_replays_without_input_order_bias():
    rows = [row("000001", "bank", 0, 100), row("300001", "media", 5, 40),
            row("300002", "media", 3, 80), row("600001", "bank", -2, 200)]
    result = rank_daily_candidates(rows, trade_date="2026-10-14", limit=2)
    assert result == rank_daily_candidates(list(reversed(rows)), trade_date="2026-10-14", limit=2)
    assert result["rule_version"] == RULE_VERSION
    assert [r["symbol"] for r in result["candidates"]] == ["300002", "300001"]
    assert all(not r["formal_eligibility"] and r["persistence"] == "UNKNOWN" for r in result["candidates"])
    assert result["market"]["regime_admission"] == "UNKNOWN"


def test_daily_candidate_pool_is_bounded_and_cross_industry():
    rows = [
        row("600001", "bank", 5, 100),
        row("600002", "bank", 4, 90),
        row("600003", "bank", 3, 80),
        row("300001", "media", 2, 70),
        row("300002", "media", 1, 60),
        row("000001", "auto", 0, 50),
    ]
    result = rank_daily_candidates(
        rows, trade_date="2026-10-14", limit=2, candidate_pool_limit=5
    )
    pool = result["candidate_pool"]
    counts = {}
    for candidate in pool:
        counts[candidate["industry"]] = counts.get(candidate["industry"], 0) + 1
    assert len(pool) == 5
    assert counts == {"bank": 2, "media": 2, "auto": 1}
    assert len({candidate["industry"] for candidate in pool}) == 3
    assert [candidate["candidate_pool_rank"] for candidate in pool] == [1, 2, 3, 4, 5]
    assert all(candidate["structure_tier"] == "UNASSESSED" for candidate in pool)


def test_stale_suspended_or_name_risk_never_becomes_candidate():
    rows = [row("300001", "media", 99, 100), row("300002", "media", 99, 0),
            row("600001", "bank", 99, 200), row("000001", "bank", 1, 100)]
    rows[0]["trade_date"] = "2026-10-13"
    rows[2]["company_name"] = "ST example"
    result = rank_daily_candidates(rows, trade_date="2026-10-14")
    assert [r["symbol"] for r in result["candidates"]] == ["000001"]
    assert len(result["excluded"]) == 3


def test_equal_strength_turnover_has_stable_symbol_tiebreak():
    rows = [row("300002", "media", 5, 10), row("300001", "media", 5, 10)]
    assert [r["symbol"] for r in rank_daily_candidates(rows, trade_date="2026-10-14")["candidates"]] == ["300001", "300002"]


def test_raw_quote_dates_and_values_bound_to_ranking(tmp_path):
    directory = tmp_path / "runtime" / "evidence"
    directory.mkdir(parents=True)
    fields = [""] * 40
    for key, value in {1: "Company", 2: "300001", 3: "11", 4: "10", 6: "100", 30: "20261014150000", 37: "50"}.items():
        fields[key] = value
    raw = ('v_sz300001="' + '~'.join(fields) + '";').encode("gb18030")

    class Response:
        content = raw
        url = "https://qt.gtimg.cn/q=sz300001"
        def raise_for_status(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    now = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)
    quotes, sources, failures = collect_dated_market(["300001"], directory=directory, session=Session(), clock=lambda: now)
    assert not failures and quotes[0]["amount_cny"] == "500000"
    classification = dict(fetched_at=now.isoformat(), rows=[dict(code="300001", name="Company", **{"class": "media"})])
    classify_path = directory / "classification.json"
    classify_path.write_text(json.dumps(classification), encoding="utf-8")
    calendar_path = directory / "calendar.json"
    calendar_path.write_text("{}", encoding="utf-8")
    quote = {**quotes[0], "industry": "media", "classification_available_at": now.isoformat(), "classification_effective_date": None}
    ranking = rank_daily_candidates([quote], trade_date="2026-10-14")
    def binding(path):
        return dict(path=path.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report = dict(schema_version="hotspot-daily-selection-v1", action="no_order", trade_date="2026-10-14", limit=5,
                  rows=[quote], ranking=ranking, hotspot_watch_queue=ranking["candidate_pool"], observation_list=ranking["candidates"],
                  candidate_pool=ranking["candidate_pool"], candidate_pool_limit=ranking["candidate_pool_limit"],
                  source_bindings=[binding(classify_path), binding(calendar_path),
                                   {**sources[0], "path": Path(sources[0]["path"]).relative_to(tmp_path).as_posix()}])
    verify_daily_selection(tmp_path, report)
    report["rows"][0]["close"] = "99"
    report["ranking"] = rank_daily_candidates(report["rows"], trade_date="2026-10-14")
    report["observation_list"] = report["ranking"]["candidates"]
    report["candidate_pool"] = report["hotspot_watch_queue"] = report["ranking"]["candidate_pool"]
    with pytest.raises(ValueError, match="original evidence"):
        verify_daily_selection(tmp_path, report)
    report["rows"][0]["close"] = "11"
    report["ranking"] = rank_daily_candidates(report["rows"], trade_date="2026-10-14")
    report["observation_list"] = report["ranking"]["candidates"]
    report["candidate_pool"] = report["hotspot_watch_queue"] = report["ranking"]["candidate_pool"]
    classify_path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="original changed"):
        verify_daily_selection(tmp_path, report)


def _collected_report(tmp_path, *, quote_changes=None, malformed_batch=False,
                      symbol_count=12, cross_batch=False):
    from test_daily_quote_binding import _write_bundle

    now = datetime(2026, 9, 26, 9, tzinfo=timezone.utc)
    bundle = json.loads(_write_bundle(tmp_path).read_bytes())
    symbols = ["000333", *[str(number) for number in range(600519, 600518 + symbol_count)]]
    classification = dict(
        fetched_at=now.isoformat(), source_url="https://vip.stock.finance.sina.com.cn/",
        rows=[dict(code=symbol, name="SYNTHETIC_" + symbol,
                   **{"class": "SYNTHETIC_INDUSTRY_" + symbol}) for symbol in symbols],
    )
    raw_classification = json.dumps(classification).encode("utf-8")
    assignments = {}
    for symbol in symbols:
        fields = [""] * 40
        for index, value in {
            1: "SYNTHETIC_" + symbol, 2: symbol, 3: "11", 4: "10",
            6: "100", 30: "20260924150000", 37: "50",
        }.items():
            fields[index] = value
        if symbol == "600520":
            for index, value in (quote_changes or {}).items():
                fields[index] = value
        identity = ("sz" if symbol.startswith("0") else "sh") + symbol
        assignments[symbol] = 'v_' + identity + '="' + '~'.join(fields) + '";'

    class Response:
        def __init__(self, url):
            self.url = url
            requested = requested_quote_symbols(url)
            if cross_batch and len(requested) == 200:
                requested.append(symbols[-1])
            self.content = "\n".join(assignments[symbol] for symbol in requested).encode("gb18030")
            if malformed_batch:
                self.content += b" TEST_ONLY_BAD_BATCH"

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            return Response(url)

    def market_collector(requested, *, directory):
        assert requested == sorted(symbols)
        return collect_dated_market(
            requested, directory=directory, session=Session(), clock=lambda: now,
        )

    def bundle_collector(anchors):
        assert anchors == ["000333", "600519"]
        return bundle

    binding = collect_daily_candidates(
        root=tmp_path, limit=10, candidate_pool_limit=10, now=now,
        classification_collector=lambda: (raw_classification, classification),
        market_collector=market_collector, bundle_collector=bundle_collector,
    )
    path = tmp_path / binding["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
    report = json.loads(path.read_bytes())
    assert report["trade_date"] == "2026-09-24"
    assert report["limit"] == 10
    assert report["candidate_pool_limit"] == report["ranking"]["candidate_pool_limit"] == 10
    verify_daily_selection(tmp_path, report)
    return report


@pytest.mark.parametrize("changed_limit", [None, 20, 9, "10"])
def test_collected_explicit_pool_limit_replays_and_rejects_parameter_drift(tmp_path, changed_limit):
    report = _collected_report(tmp_path)
    assert report["coverage"]["dated_quotes"] == 12
    assert report["coverage"]["candidate_pool_industry_count"] == 10
    assert len(report["candidate_pool"]) == 10
    assert report["failures"] == []
    verify_daily_selection(tmp_path, report)
    if changed_limit is None:
        del report["candidate_pool_limit"]
    else:
        report["candidate_pool_limit"] = changed_limit
    with pytest.raises(ValueError, match="Daily ranking replay mismatch|candidate-pool limit"):
        verify_daily_selection(tmp_path, report)


@pytest.mark.parametrize("quote_changes", [
    {6: "0"}, {37: "0"}, {3: "0"}, {4: "0"}, {37: "NaN"}, {3: "bad"},
    {2: "600521"}, {30: "20260924145900"}, {30: "20260926180000"},
], ids=["suspended", "no-turnover", "zero-close", "zero-previous", "nonfinite",
        "bad-number", "wrong-identity", "incomplete", "future"])
def test_collection_and_verification_agree_on_invalid_quote_failures(tmp_path, quote_changes):
    report = _collected_report(tmp_path, quote_changes=quote_changes)
    assert len(report["rows"]) == 11
    assert {row["symbol"] for row in report["rows"]} == {
        "000333", *[str(number) for number in range(600519, 600530) if number != 600520]
    }
    assert [failure["symbol"] for failure in report["failures"]] == ["600520"]
    originals = {b["path"]: (tmp_path / b["path"]).read_bytes() for b in report["source_bindings"]}
    verify_daily_selection(tmp_path, report)
    # A genuine bad quote does not excuse omitting a different valid quote.
    report["rows"] = report["rows"][1:]
    ranking = rank_daily_candidates(report["rows"], trade_date=report["trade_date"],
                                    limit=report["limit"], candidate_pool_limit=10)
    report.update(ranking=ranking, observation_list=ranking["candidates"],
                  candidate_pool=ranking["candidate_pool"], hotspot_watch_queue=ranking["candidate_pool"])
    with pytest.raises(ValueError, match="valid original quotes"):
        verify_daily_selection(tmp_path, report)
    assert all((tmp_path / name).read_bytes() == raw for name, raw in originals.items())


def test_retained_malformed_batch_is_not_reinterpreted_as_valid_quotes(tmp_path):
    report = _collected_report(tmp_path, malformed_batch=True)
    assert report["rows"] == []
    assert len(report["failures"]) == 12
    assert all(failure["reason"] == "Unexpected response content" for failure in report["failures"])
    verify_daily_selection(tmp_path, report)


def test_stale_but_valid_original_quote_must_still_be_retained(tmp_path):
    report = _collected_report(tmp_path, quote_changes={30: "20260923150000"})
    assert len(report["rows"]) == 12
    assert report["failures"] == []
    assert dict(symbol="600520", reason="NOT_LATEST_COMPLETED_SESSION") in report["ranking"]["excluded"]
    verify_daily_selection(tmp_path, report)


def test_replay_keeps_original_batch_scope_and_does_not_promote_failed_batch(tmp_path):
    report = _collected_report(tmp_path, symbol_count=201, cross_batch=True)
    assert [row["symbol"] for row in report["rows"]] == ["600718"]
    assert len(report["failures"]) == 200
    assert all(failure["reason"] == "Unexpected quote assignment" for failure in report["failures"])
    assert [len(requested_quote_symbols(b["source_url"])) for b in report["source_bindings"][2:]] == [200, 1]
    verify_daily_selection(tmp_path, report)


@pytest.mark.parametrize("url", [
    "https://qt.gtimg.cn/q=", "https://qt.gtimg.cn/q=sh600519,sh600519",
    "https://qt.gtimg.cn/q=sz600519", "https://qt.gtimg.cn/q=sh600519&q=sz000333",
    "https://example.invalid/q=sh600519",
    "https://qt.gtimg.cn/q=" + ",".join(f"sh{600000+i}" for i in range(201)),
])
def test_request_batch_requires_unique_bounded_unambiguous_symbols(url):
    with pytest.raises(ValueError):
        requested_quote_symbols(url)


def test_request_symbols_outside_classification_cannot_be_hidden_as_failed_batch(tmp_path):
    report = _collected_report(tmp_path)
    report["source_bindings"][2]["source_url"] += ",sh699999"
    with pytest.raises(ValueError, match="outside classification"):
        verify_daily_selection(tmp_path, report)
