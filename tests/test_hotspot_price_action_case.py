from datetime import date
import json
import os
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from value_investment_agent.domain.hotspot.price_action_plan import calculate_price_levels
from value_investment_agent.application.hotspot.price_action_case import project_price_action_plan
from value_investment_agent.infrastructure.hotspot.sina_price_case import (
    collect_historical_case, load_historical_case, parse_klines,
)


def _require_report_bound_historical_case(root, row):
    case = load_historical_case(root=root, symbol=row['symbol'], as_of=date(2026,10,21))
    if case['source_bindings'] != row['source_bindings']:
        raise ValueError('Historical case differs from sealed source bindings or acquisition times')
    return case


@pytest.mark.skipif(not os.environ.get('HOTSPOT_MISSING_WINDOW_ROOT'), reason='Explicit retrospective missing-window originals')
@pytest.mark.parametrize('symbol', ['600825', '000938', '600176', '600667', '601857'])
def test_real_missing_oct21_window_is_retrospective_not_repaired_pit(symbol):
    from value_investment_agent.domain.hotspot.confirmed_price_structure import analyze_price_behavior
    from value_investment_agent.domain.hotspot.current_price import current_signal, completed_session_bars
    from value_investment_agent.infrastructure.hotspot.sina_price_case import decode_klines
    from value_investment_agent.application.hotspot.lifecycle_review import _compare_entry_bars
    root = Path(os.environ['HOTSPOT_MISSING_WINDOW_ROOT'])
    raw = (root / 'completed-validation.json').read_bytes()
    assert sha256(raw).hexdigest() == os.environ['HOTSPOT_MISSING_WINDOW_REPORT_SHA256']
    report = json.loads(raw)
    assert report['baseline_coverage'] == dict(expected=7, replayed=3)
    assert report['contemporaneous_coverage_added'] == report['historical_pit_credit'] == 0
    assert report['strategy_validation'] == 'NOT_PROVEN' and report['action'] == 'no_order'
    row = next(item for item in report['rows'] if item['symbol'] == symbol)
    case = _require_report_bound_historical_case(root, row)
    assert case['levels'] == row['levels']
    assert analyze_price_behavior(case['bars']) == row['behavior']
    assert current_signal(case['levels'])[0] == row['retrospective_signal_state'] == 'WATCH'
    for period in ('60m', '15m'):
        binding = case['source_bindings'][period]
        original = (root / binding['path']).read_bytes()
        assert sha256(original).hexdigest() == binding['sha256']
        assert datetime.fromisoformat(binding['fetched_at']) > datetime(2026,10,21,15,tzinfo=ZoneInfo('Asia/Shanghai'))
        values = decode_klines(original)
        changed = 0
        for value in values:
            if value['day'][:10] > '2026-10-21':
                value['volume'] = '999999999'
                value['high'] = str(float(value['high']) * 100)
                changed += 1
        assert changed > 0
        altered = ('=(' + json.dumps(values) + ');').encode()
        assert parse_klines(altered, period=period, as_of=date(2026,10,21)) == case['bars'][period]
        completed_session_bars(case['bars'][period], period=period)
    future = completed_session_bars(parse_klines((root / case['source_bindings']['60m']['path']).read_bytes(),
        period='60m', as_of=date(2026,10,23)), period='60m')
    reference = _compare_entry_bars(bars=future,
        entry_at=datetime(2026,10,21,15,tzinfo=ZoneInfo('Asia/Shanghai')),
        protection=case['levels']['60m']['invalidation_price'], symbol=symbol)
    for key, value in reference.items():
        assert row['reference_only_followup'][key] == value
    assert reference['coverage'] == 'COMPLETE' and reference['inspected_bar_count'] == 8
    assert row['reference_only_followup']['reference_is_owned_entry'] is False
    assert row['reference_only_followup']['exit_review_admitted'] is False
    assert row['reference_only_followup']['price_comparability'] == 'UNKNOWN'


@pytest.mark.skipif(not os.environ.get('HOTSPOT_MISSING_WINDOW_ROOT'), reason='Explicit retrospective originals')
@pytest.mark.parametrize('change', ['future_tail_and_rehash', 'acquisition_time'])
def test_rehashed_case_cannot_replace_sealed_missing_window_sources(tmp_path, change):
    import shutil
    from datetime import timedelta
    from value_investment_agent.infrastructure.hotspot.sina_price_case import decode_klines
    root = Path(os.environ['HOTSPOT_MISSING_WINDOW_ROOT'])
    raw = (root / 'completed-validation.json').read_bytes()
    assert sha256(raw).hexdigest() == os.environ['HOTSPOT_MISSING_WINDOW_REPORT_SHA256']
    row = json.loads(raw)['rows'][0]
    relative = Path('runtime/hotspot-price-cases') / (row['symbol'] + '-2026-10-21')
    target = tmp_path / relative
    shutil.copytree(root / relative, target)
    case = json.loads((target / 'case.json').read_bytes())
    if change == 'future_tail_and_rehash':
        source = tmp_path / case['source_bindings']['60m']['path']
        values = decode_klines(source.read_bytes())
        assert any(value['day'][:10] > '2026-10-21' for value in values)
        for value in values:
            if value['day'][:10] > '2026-10-21':
                value['volume'] = '999999999'
        source.write_bytes(('=(' + json.dumps(values) + ');').encode())
        digest = sha256(source.read_bytes()).hexdigest()
        for period in ('60m', 'daily'):
            case['source_bindings'][period]['sha256'] = digest
    else:
        before = datetime.fromisoformat(case['source_bindings']['15m']['fetched_at'])
        case['source_bindings']['15m']['fetched_at'] = (before - timedelta(seconds=1)).isoformat()
    (target / 'case.json').write_text(json.dumps(case), encoding='utf-8')
    # A self-consistent replacement can replay the same cutoff, but is not the sealed source.
    load_historical_case(root=tmp_path, symbol=row['symbol'], as_of=date(2026,10,21))
    with pytest.raises(ValueError, match='sealed source bindings'):
        _require_report_bound_historical_case(tmp_path, row)


def _bars():
    return [dict(time=f"2026-10-{day:02}", open="10", close="10",
                 high=str(10 + day / 100), low="9", volume="100")
            for day in range(7, 13)]


def test_prior_five_levels_are_replayable_and_not_an_order():
    levels = calculate_price_levels(_bars(), period="daily")
    assert levels["entry_trigger_price"] == "10.11"
    assert levels["invalidation_price"] == "9"
    assert levels["risk_reward_ratio"] is None
    assert levels["action"] == "no_order"
    assert not levels["breakout_observed"]


def test_insufficient_duplicate_and_bad_ohlc_fail_closed():
    with pytest.raises(ValueError, match="Six"):
        calculate_price_levels(_bars()[:5], period="60m")
    repeated = _bars()
    repeated[-1]["time"] = repeated[-2]["time"]
    with pytest.raises(ValueError, match="unique"):
        calculate_price_levels(repeated, period="daily")
    invalid = _bars()
    invalid[-1]["high"] = "8"
    with pytest.raises(ValueError, match="OHLC"):
        calculate_price_levels(invalid, period="daily")


def test_provider_symbol_and_cutoff_are_enforced():
    with pytest.raises(ValueError, match="JSONP"):
        parse_klines(b"{}", period="60m", as_of=date(2026, 10, 13))


@pytest.mark.parametrize("raw,reason", [
    (b"", "JSONP"),
    (b"=([]);", "No bars"),
    (b"=([broken]);", "Expecting value"),
    (("=(" + json.dumps([{}] * 2501) + ");").encode(), "kline rows"),
])
def test_shared_decoder_preserves_existing_empty_corrupt_and_size_boundaries(raw, reason):
    with pytest.raises(ValueError, match=reason):
        parse_klines(raw, period="60m", as_of=date(2026, 10, 13))


def test_capture_keeps_original_hash_and_rejects_duplicate_case(tmp_path):
    class Response:
        def __init__(self, period):
            self.url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/=/"
                        f"CN_MarketDataService.getKLineData?symbol=sz000651&scale={period}&ma=no")
            rows = [dict(day=f"2026-10-{day:02} {clock}", open="10", close="10",
                         high="11", low="9", volume="100", amount="1000")
                    for day in range(8, 14)
                    for clock in ("10:30:00", "11:30:00", "14:00:00", "15:00:00")]
            self.content = ("/*provider*/\n=(" + json.dumps(rows) + ");").encode()

        def raise_for_status(self):
            return None

    result = collect_historical_case(
        root=tmp_path, symbol="000651", as_of=date(2026, 10, 13),
        fetch=lambda _url, params, timeout: Response(params["scale"]),
    )
    assert result["action"] == "no_order"
    assert result["signal_state"] == "HISTORICAL_OBSERVATION_NOT_ADMITTED"
    plan = project_price_action_plan(result)
    assert plan["entry_trigger_price"] == result["levels"]["60m"]["entry_trigger_price"]
    assert plan["invalidation_price"] == result["levels"]["60m"]["invalidation_price"]
    assert plan["action_eligibility"] is False and plan["risk_reward_ratio"] is None
    assert plan["add_trigger_price"] is None and plan["exit_trigger_price"] is None
    assert set(result["source_bindings"]) == {"daily", "60m", "15m"}
    from hashlib import sha256
    for source in result["source_bindings"].values():
        assert sha256((tmp_path / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    loaded = load_historical_case(root=tmp_path, symbol="000651",
                                  as_of=date(2026, 10, 13))
    assert loaded["bar_timezone"] == "Asia/Shanghai"
    assert {k: v for k, v in loaded.items() if k != "bar_timezone"} == result
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    client = TestClient(create_app(tmp_path))
    listing = client.get("/api/v1/historical-price-cases").json()
    assert listing["status"] == "HISTORICAL_NOT_CURRENT"
    assert listing["items"][0]["symbol"] == "000651"
    detail = client.get("/api/v1/historical-price-case/000651/2026-10-13").json()
    assert detail["levels"] == result["levels"]
    assert detail["price_action_plan"] == plan
    case_path = tmp_path / "runtime/hotspot-price-cases/000651-2026-10-13/case.json"
    original_case = case_path.read_bytes()
    altered = json.loads(original_case)
    altered["blockers"] = []
    case_path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="contract"):
        load_historical_case(root=tmp_path, symbol="000651",
                             as_of=date(2026, 10, 13))
    case_path.write_bytes(original_case)
    binding = case_path.parent / "close-crosscheck.json"
    binding.write_text(json.dumps({"manifest_path": "runtime/missing.json",
                                   "manifest_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_historical_case(root=tmp_path, symbol="000651",
                             as_of=date(2026, 10, 13))
    binding.unlink()
    raw_source = tmp_path / result["source_bindings"]["15m"]["path"]
    raw_source.write_bytes(raw_source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        load_historical_case(root=tmp_path, symbol="000651",
                             as_of=date(2026, 10, 13))
    assert client.get("/api/v1/historical-price-case/000651/2026-10-13").json()["status"] == "UNAVAILABLE"
    with pytest.raises(FileExistsError):
        collect_historical_case(root=tmp_path, symbol="000651",
                                as_of=date(2026, 10, 13), fetch=lambda *_a, **_k: None)
