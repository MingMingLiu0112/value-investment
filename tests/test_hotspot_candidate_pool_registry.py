"""Registry membership and metadata follow verified daily selection evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.hotspot import current_registry as module
from value_investment_agent.application.hotspot.daily_selection import verify_daily_selection
from value_investment_agent.domain.hotspot.daily_selection import rank_daily_candidates


NOW = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)


def _write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "available_at": NOW.isoformat()}


def _report(root, *, same_industry=False):
    symbols = ["600001", "600002", "600003"]
    classification = {
        "fetched_at": NOW.isoformat(),
        "rows": [{"code": symbol, "name": "Company" + symbol,
                  "class": "TEST_INDUSTRY" if same_industry else "INDUSTRY_" + symbol}
                 for symbol in symbols],
    }
    bindings = [_write(root, "runtime/classification.json", classification),
                _write(root, "runtime/calendar.json", {})]
    rows = []
    for index, symbol in enumerate(symbols):
        fields = [""] * 40
        for key, value in {1: "Company" + symbol, 2: symbol, 3: "11", 4: "10",
                           6: "100", 30: "20261014150000", 37: str(50 - index)}.items():
            fields[key] = value
        binding = _write(root, f"runtime/quote-{symbol}.txt",
                         ('v_sh' + symbol + '="' + '~'.join(fields) + '";').encode("gb18030"))
        binding["source_url"] = "https://qt.gtimg.cn/q=sh" + symbol
        bindings.append(binding)
        rows.append({"symbol": symbol, "company_name": fields[1],
                     "industry": classification["rows"][index]["class"],
                     "close": "11", "change_percent": "10.0",
                     "amount_cny": str((50 - index) * 10000), "trade_date": "2026-10-14",
                     "status": "DATED_COMPLETED_QUOTE", "sha256": binding["sha256"],
                     "source_url": binding["source_url"], "available_at": NOW.isoformat(),
                     "classification_available_at": NOW.isoformat()})
    limit = 3 if same_industry else 1
    ranking = rank_daily_candidates(rows, trade_date="2026-10-14", limit=limit, candidate_pool_limit=3)
    report = {"schema_version": "hotspot-daily-selection-v1", "action": "no_order",
              "trade_date": "2026-10-14", "limit": limit, "candidate_pool_limit": 3,
              "rows": rows, "ranking": ranking, "observation_list": ranking["candidates"],
              "candidate_pool": ranking["candidate_pool"], "hotspot_watch_queue": ranking["candidate_pool"],
              "source_bindings": bindings, "unknowns": ["TEST_ONLY_NOT_ADMISSION"]}
    verify_daily_selection(root, report)
    return report


def _register(root, report, symbol):
    binding = _write(root, "runtime/selection.json", report)
    _write(root, module.REGISTRY, {
        "schema_version": "current-price-conditions-v1", "action": "no_order",
        "watch_source_binding": binding, "watch_source_scope": "DATED_DAILY_CROSS_INDUSTRY_CANDIDATE_POOL",
        "items": [{"symbol": symbol, "company_name": "TEST_ONLY", "case_path": "runtime/case.json",
                   "case_sha256": "a" * 64}],
    })


@pytest.fixture
def case_calls(monkeypatch):
    calls = []

    def load(**kwargs):
        calls.append(kwargs["symbol"])
        return {"market_trade_date": "2026-10-14", "case_path": "runtime/case.json", "case_sha256": "a" * 64}

    monkeypatch.setattr(module, "load_current_price_case", load)
    monkeypatch.setattr(module, "project_current_price_action_plan", lambda case: {
        "signal_state": "WATCH", "opportunity_quality": {"structure_tier": "ACTIVE_ONLY"},
    })
    return calls


def test_pool_only_member_loads_exact_pool_metadata(tmp_path, case_calls):
    report = _report(tmp_path)
    member = report["candidate_pool"][1]
    assert member["symbol"] not in {row["symbol"] for row in report["observation_list"]}
    _register(tmp_path, report, member["symbol"])
    loaded = module.load_price_conditions(tmp_path, now=NOW, research_version="TEST_ONLY")
    assert loaded["status"] == "CURRENT_OBSERVATION" and loaded["blockers"] == []
    plan = loaded["items"][0]["price_action_plan"]
    assert plan["daily_selection"] == member
    assert plan["daily_selection"]["candidate_pool_rank"] == 2
    assert plan["selection_rule_version"] == report["ranking"]["rule_version"]
    assert plan["market_environment"] == report["ranking"]["market"]
    assert plan["formal_eligibility"] is False and plan["portfolio_eligibility"] is None
    assert case_calls == [member["symbol"]]


def test_outsider_remains_blocked_before_case_loading(tmp_path, case_calls):
    report = _report(tmp_path)
    _register(tmp_path, report, "600999")
    result = module.load_price_conditions(tmp_path, now=NOW, research_version=None)
    assert result["status"] == "BLOCKED" and result["items"] == []
    assert result["blockers"] == ["CURRENT_PRICE_REGISTRY_UNAVAILABLE"]
    assert case_calls == []


@pytest.mark.parametrize("change", ["metadata", "membership"])
def test_rehashed_tampered_pool_rejected_by_real_verifier(tmp_path, case_calls, change):
    report = deepcopy(_report(tmp_path))
    report["candidate_pool"] = deepcopy(report["candidate_pool"])
    symbol = report["candidate_pool"][1]["symbol"]
    if change == "metadata":
        report["candidate_pool"][1]["industry"] = "FABRICATED_INDUSTRY"
    else:
        report["candidate_pool"][1]["symbol"] = "600999"
    report["hotspot_watch_queue"] = deepcopy(report["candidate_pool"])
    with pytest.raises(ValueError, match="candidate pool mismatch"):
        verify_daily_selection(tmp_path, report)
    # Rehash the outer source, so failure must come from evidence replay.
    _register(tmp_path, report, symbol)
    result = module.load_price_conditions(tmp_path, now=NOW, research_version=None)
    assert result["status"] == "BLOCKED" and result["items"] == []
    assert case_calls == []


def test_observation_only_member_falls_back_to_observation_metadata(tmp_path, case_calls):
    report = _report(tmp_path, same_industry=True)
    member = report["observation_list"][2]
    assert member["symbol"] not in {row["symbol"] for row in report["candidate_pool"]}
    _register(tmp_path, report, member["symbol"])
    result = module.load_price_conditions(tmp_path, now=NOW, research_version=None)
    assert result["status"] == "CURRENT_OBSERVATION"
    assert result["items"][0]["price_action_plan"]["daily_selection"] == member
    assert case_calls == [member["symbol"]]
