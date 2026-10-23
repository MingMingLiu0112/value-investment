from datetime import date
import json

import pytest

from value_investment_agent.domain.hotspot.price_action_plan import calculate_price_levels
from value_investment_agent.application.hotspot.price_action_case import project_price_action_plan
from value_investment_agent.infrastructure.hotspot.sina_price_case import (
    collect_historical_case, load_historical_case, parse_klines,
)


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
