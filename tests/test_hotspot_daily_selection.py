"""Daily ranking cannot promote stale, excluded or unknown facts to admission."""
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import pytest
from value_investment_agent.domain.hotspot.daily_selection import rank_daily_candidates, RULE_VERSION
from value_investment_agent.infrastructure.hotspot.daily_market import collect_dated_market
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
                  rows=[quote], ranking=ranking, hotspot_watch_queue=ranking["candidates"], observation_list=ranking["candidates"],
                  source_bindings=[binding(classify_path), binding(calendar_path),
                                   {**sources[0], "path": Path(sources[0]["path"]).relative_to(tmp_path).as_posix()}])
    verify_daily_selection(tmp_path, report)
    report["rows"][0]["close"] = "99"
    report["ranking"] = rank_daily_candidates(report["rows"], trade_date="2026-10-14")
    report["hotspot_watch_queue"] = report["observation_list"] = report["ranking"]["candidates"]
    with pytest.raises(ValueError, match="original evidence"):
        verify_daily_selection(tmp_path, report)
    report["rows"][0]["close"] = "11"
    report["ranking"] = rank_daily_candidates(report["rows"], trade_date="2026-10-14")
    report["hotspot_watch_queue"] = report["observation_list"] = report["ranking"]["candidates"]
    classify_path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="original changed"):
        verify_daily_selection(tmp_path, report)


@pytest.mark.parametrize("changed_limit", [None, 20, 9, "10"])
def test_collected_explicit_pool_limit_replays_and_rejects_parameter_drift(tmp_path, changed_limit):
    from test_daily_quote_binding import _write_bundle

    now = datetime(2026, 9, 26, 9, tzinfo=timezone.utc)
    bundle = json.loads(_write_bundle(tmp_path).read_bytes())
    symbols = ["000333", *[str(number) for number in range(600519, 600530)]]
    classification = dict(
        fetched_at=now.isoformat(), source_url="https://vip.stock.finance.sina.com.cn/",
        rows=[dict(code=symbol, name="SYNTHETIC_" + symbol,
                   **{"class": "SYNTHETIC_INDUSTRY_" + symbol}) for symbol in symbols],
    )
    raw_classification = json.dumps(classification).encode("utf-8")
    assignments = []
    for symbol in symbols:
        fields = [""] * 40
        for index, value in {
            1: "SYNTHETIC_" + symbol, 2: symbol, 3: "11", 4: "10",
            6: "100", 30: "20260924150000", 37: "50",
        }.items():
            fields[index] = value
        identity = ("sz" if symbol.startswith("0") else "sh") + symbol
        assignments.append('v_' + identity + '="' + '~'.join(fields) + '";')
    raw_quotes = "\n".join(assignments).encode("gb18030")

    class Response:
        content = raw_quotes
        url = "https://qt.gtimg.cn/q=" + ",".join(
            ("sz" if symbol.startswith("0") else "sh") + symbol for symbol in symbols
        )

        def raise_for_status(self):
            pass

    class Session:
        def get(self, *args, **kwargs):
            return Response()

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
