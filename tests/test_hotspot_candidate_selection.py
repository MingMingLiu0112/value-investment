"""Research selection replays original market facts and completed structure."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot import candidate_selection as module
from value_investment_agent.domain.hotspot.daily_selection import rank_daily_candidates
from value_investment_agent.quote_sessions import CHINA
from test_hotspot_current_price_case import capture, NOW


def _write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    return dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _fixture(root, count=8, zero_turnover=False):
    case = capture(root)
    symbols = ["600519", *[f"300{i:03}" for i in range(1, count)]]
    source_url = "https://qt.gtimg.cn/q=" + ",".join(
        ("sh" if symbol.startswith("6") else "sz") + symbol for symbol in symbols)
    raw, rows = [], []
    at = NOW.isoformat()
    for i, symbol in enumerate(symbols):
        amount = 0 if zero_turnover else 100-i
        fields = [""] * 40
        for key, value in {1: symbol, 2: symbol, 3: "12.34", 4: "12", 6: "100",
                           30: "20260924150000", 37: str(amount)}.items():
            fields[key] = value
        raw.append(f'v_{"sh" if symbol.startswith("6") else "sz"}{symbol}="' + "~".join(fields) + '";')
        rows.append(dict(symbol=symbol, company_name=symbol, industry=f"sector-{i%4}",
            close="12.34", change_percent=str((Decimal("12.34")/12-1)*100),
            amount_cny=str(Decimal(amount)*10000), trade_date="2026-09-24",
            status="DATED_COMPLETED_QUOTE", available_at=at,
            classification_available_at=at, classification_effective_date=None,
            source_url=source_url))
    quote = _write(root, "runtime/selection/quotes.txt", "".join(raw).encode("gb18030"))
    for row in rows:
        row["sha256"] = quote["sha256"]
    classification = _write(root, "runtime/selection/classification.json",
        dict(fetched_at=at, rows=[dict(code=row["symbol"], name=row["symbol"],
                                      **{"class": row["industry"]}) for row in rows]))
    # Collection retains suspended originals as failures, not successful quotes.
    failures = [dict(symbol=row["symbol"], reason="Invalid or suspended quote")
                for row in rows] if zero_turnover else []
    if zero_turnover:
        rows = []
    close = case["current_reference_close"]
    calendar = dict(path=close["bundle_path"], sha256=close["bundle_sha256"])
    ranking = rank_daily_candidates(rows, trade_date="2026-09-24", limit=5,
                                    candidate_pool_limit=max(5, count))
    report = dict(schema_version="hotspot-daily-selection-v1", action="no_order",
        trade_date="2026-09-24", available_at=at, limit=5, rows=rows, ranking=ranking,
        observation_list=ranking["candidates"], candidate_pool=ranking["candidate_pool"],
        candidate_pool_limit=max(5, count), hotspot_watch_queue=ranking["candidate_pool"],
        failures=failures,
        source_bindings=[dict(classification, available_at=at), dict(calendar, available_at=at),
                         dict(quote, available_at=at, source_url=source_url)])
    watch = _write(root, "runtime/selection/report.json", report)
    binding = dict(path=case["case_path"], sha256=case["case_sha256"])
    _write(root, "config/current-price-conditions.json",
        dict(schema_version="current-price-conditions-v1", action="no_order",
             watch_source_binding=watch, items=[], assessed_candidates=[
                 dict(symbol="600519", case_path=binding["path"], case_sha256=binding["sha256"])],
             previous_items=[dict(symbol="999999", case_path="DO_NOT_LOAD")]))
    return watch, binding, report, case


def test_full_pool_not_five_displayed_names_and_no_missing_is_failure(tmp_path):
    _fixture(tmp_path)
    report = module.select_current_hotspot_candidates(root=tmp_path, now=NOW)
    assert report["status"] == "RESEARCH_SELECTION_REPLAYED", report
    assert report["coverage"] == dict(market_securities=8, candidate_pool=8, evaluated=8,
        omitted_by_limit=0, industries=4, bound_cases=1, structure_verified=1,
        selected=0, excluded=0, pending_confirmation=1, unknown=7)
    assert len(report["items"]) == 8 and report["shortlist"] == []
    missing = [row for row in report["items"] if row["symbol"] != "600519"]
    assert all(row["selection_status"] == row["structure_status"] == "UNKNOWN" for row in missing)
    assert all(row["missing_periods"] == ["daily", "60m", "15m"] for row in missing)
    assert all(row["action"] == "no_order" and row["formal_eligibility"] is False for row in report["items"])


def test_explicit_immutable_bindings_and_cutoff_replay_identically(tmp_path):
    watch, case, _, _ = _fixture(tmp_path)
    default = module.select_current_hotspot_candidates(root=tmp_path, now=NOW)
    explicit = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={"600519": case})
    assert default["items"] == explicit["items"]
    assert explicit == module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={"600519": case})
    assert "registry_binding" not in explicit


@pytest.mark.parametrize("limit", [0, 31, True, 1.2])
def test_invalid_limits(tmp_path, limit):
    with pytest.raises(ValueError):
        module.select_current_hotspot_candidates(root=tmp_path, now=NOW, limit=limit)


def test_naive_clock_rejected(tmp_path):
    with pytest.raises(ValueError):
        module.select_current_hotspot_candidates(root=tmp_path, now=datetime(2026, 10, 23))


def test_missing_registry_and_malformed_contract_fail_closed(tmp_path):
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW)
    assert result["status"] == "UNASSESSABLE" and not result["shortlist"]
    _write(tmp_path, "config/current-price-conditions.json", {"action": "order"})
    assert module.select_current_hotspot_candidates(root=tmp_path, now=NOW)["data_status"] == "INVALID"


@pytest.mark.parametrize("connected", [True, False])
def test_root_permissions_are_strict_false_even_without_personal_risk_evaluation(tmp_path, connected):
    if connected:
        _fixture(tmp_path)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW)
    assert result["formal_eligibility"] is False
    assert result["portfolio_eligibility"] is False
    assert result["personal_risk_evaluated"] is False
    assert result["current_pit"] is False
    assert result["action"] == "no_order"


@pytest.mark.parametrize("kind", ["watch", "quote", "classification", "calendar", "rank"])
def test_changed_market_provenance_never_selects(tmp_path, kind):
    watch, case, report, _ = _fixture(tmp_path)
    if kind == "rank":
        report["ranking"]["candidate_pool"][0]["rank"] = 999
        watch = _write(tmp_path, watch["path"], report)
    else:
        binding = watch if kind == "watch" else report["source_bindings"][{
            "classification": 0, "calendar": 1, "quote": 2}[kind]]
        path = tmp_path / binding["path"]
        path.write_bytes(path.read_bytes() + b" ")
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={"600519": case})
    assert result["status"] == "UNASSESSABLE" and result["items"] == []


@pytest.mark.parametrize("damage", ["trim_rows", "empty_rows", "missing_pool", "null_pool"])
def test_rebound_report_cannot_hide_valid_original_quotes_or_downgrade_v3(tmp_path, damage):
    watch, _, report, _ = _fixture(tmp_path)
    originals = {b["path"]: (tmp_path / b["path"]).read_bytes() for b in report["source_bindings"]}
    if damage == "trim_rows":
        report["rows"] = report["rows"][:1]
    elif damage == "empty_rows":
        report["rows"] = []
    # Use the default limit so a missing pool cannot fail merely on limit drift.
    report["candidate_pool_limit"] = 10
    ranking = rank_daily_candidates(report["rows"], trade_date=report["trade_date"],
                                    limit=report["limit"], candidate_pool_limit=10)
    report.update(ranking=ranking, observation_list=ranking["candidates"],
                  candidate_pool=ranking["candidate_pool"], hotspot_watch_queue=ranking["candidate_pool"])
    if damage in {"missing_pool", "null_pool"}:
        report["hotspot_watch_queue"] = report["observation_list"]
        if damage == "missing_pool":
            del report["candidate_pool"]
        else:
            report["candidate_pool"] = None
    watch = _write(tmp_path, watch["path"], report)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={})
    assert result["status"] == "UNASSESSABLE", result
    assert result["data_status"] == "INVALID"
    assert result["items"] == result["shortlist"] == []
    assert "HOTSPOT_SELECTION_SOURCE_INVALID" in result["blockers"]
    assert all((tmp_path / name).read_bytes() == raw for name, raw in originals.items())


@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize("damage", [None, "trim_rows", "empty_rows"])
def test_explicit_legacy_version_keeps_scope_but_cannot_omit_originals(tmp_path, version, damage):
    watch, _, report, _ = _fixture(tmp_path)
    if damage == "trim_rows":
        report["rows"] = report["rows"][:1]
    elif damage == "empty_rows":
        report["rows"] = []
    ranking = rank_daily_candidates(report["rows"], trade_date=report["trade_date"], limit=report["limit"])
    ranking["rule_version"] = "hotspot-dated-sector-liquidity-ranking-" + version
    for key in ("candidate_pool", "candidate_pool_limit", "candidate_pool_rule"):
        ranking.pop(key)
        report.pop(key, None)
    if version == "v1":
        for item in ranking["candidates"]:
            for key in ("activity_tier", "activity_reason", "structure_tier", "structure_reason"):
                item.pop(key)
    report.update(ranking=ranking, observation_list=ranking["candidates"], hotspot_watch_queue=ranking["candidates"])
    watch = _write(tmp_path, watch["path"], report)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={})
    if damage is None:
        assert result["status"] == "RESEARCH_SELECTION_REPLAYED", result
        assert result["activity_rule_version"] == ranking["rule_version"]
        assert result["coverage"]["candidate_pool"] == 5
    else:
        assert result["status"] == "UNASSESSABLE", result
        assert "valid original quotes" in result["diagnostic"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("version", [None, "hotspot-dated-sector-liquidity-ranking-v0"])
def test_legacy_fallback_requires_an_explicit_supported_version(tmp_path, version):
    watch, _, report, _ = _fixture(tmp_path)
    report.pop("candidate_pool")
    report["hotspot_watch_queue"] = report["observation_list"]
    if version is None:
        report["ranking"].pop("rule_version")
    else:
        report["ranking"]["rule_version"] = version
    watch = _write(tmp_path, watch["path"], report)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={})
    assert result["status"] == "UNASSESSABLE"
    assert "Unsupported daily ranking rule version" in result["diagnostic"]


@pytest.mark.parametrize("kind", ["hash", "wrong_symbol", "date", "uncompleted", "future"])
def test_bad_structure_is_unknown_not_structural_exclusion(tmp_path, kind):
    watch, binding, _, case = _fixture(tmp_path)
    symbol = "600519"
    if kind == "hash":
        path = tmp_path / case["source_bindings"]["15m"]["path"]
        path.write_bytes(path.read_bytes() + b" ")
    elif kind == "wrong_symbol":
        symbol = "300001"
    else:
        if kind == "date":
            case["market_trade_date"] = "2026-09-23"
        elif kind == "future":
            case["source_bindings"]["15m"]["fetched_at"] = "2026-10-23T17:00:00+08:00"
        else:
            case["bars"]["15m"].pop()
        # Stored loader metadata is not part of original immutable case.
        for key in ("case_path", "case_sha256", "verified_available_at"):
            case.pop(key, None)
        binding = _write(tmp_path, binding["path"], case)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={symbol: binding})
    row = next(item for item in result["items"] if item["symbol"] == symbol)
    assert row["selection_status"] == "UNKNOWN" and row["data_status"] == "INVALID"
    assert row["entry_condition"] is row["invalidation_condition"] is None
    assert not result["shortlist"]


def test_mixed_pool_or_external_path_rejected(tmp_path):
    watch, case, _, _ = _fixture(tmp_path)
    for binding, cases in [(watch, {"000999": case}),
                           ({"path": "../outside.json", "sha256": "0"*64}, {})]:
        result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
            watch_binding=binding, case_bindings=cases)
        assert result["status"] == "UNASSESSABLE"


def test_future_watch_cutoff_rejected(tmp_path):
    watch, case, report, _ = _fixture(tmp_path)
    report["available_at"] = "2026-10-23T17:00:00+08:00"
    watch = _write(tmp_path, watch["path"], report)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={"600519": case})
    assert result["status"] == "UNASSESSABLE"


def test_expired_watch_kept_as_unknown_never_uses_old_prices(tmp_path):
    _fixture(tmp_path)
    result = module.select_current_hotspot_candidates(root=tmp_path,
        now=datetime(2026, 9, 28, 16, tzinfo=CHINA))
    assert result["data_status"] == "STALE", result
    assert result["coverage"]["unknown"] == 8
    assert result["shortlist"] == []
    assert all(row["entry_condition"] is None for row in result["items"])


def test_limit_reports_omitted_pool_members(tmp_path):
    _fixture(tmp_path)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW, limit=3)
    assert result["coverage"]["candidate_pool"] == 8
    assert result["coverage"]["evaluated"] == 3
    assert result["coverage"]["omitted_by_limit"] == 5


def test_verified_zero_candidate_pool_is_legal(tmp_path):
    watch, _, _, _ = _fixture(tmp_path, zero_turnover=True)
    result = module.select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=watch, case_bindings={})
    assert result["status"] == "RESEARCH_SELECTION_REPLAYED", result
    assert result["coverage"]["candidate_pool"] == 0
    assert result["items"] == result["shortlist"] == []
    assert result["activity_exclusions"] == []
    assert len(result["data_failures"]) == 8


@pytest.mark.parametrize("tier,status", [
    ("STRUCTURE_QUALIFIED_OBSERVATION", "SELECTED"),
    ("CONFLICT_OR_REJECTED", "EXCLUDED"),
    ("ACTIVE_ONLY", "PENDING_CONFIRMATION"),
])
def test_projection_uses_existing_tier_without_reimplementing_rules(tmp_path, monkeypatch, tier, status):
    _fixture(tmp_path)
    project = module.project_current_price_action_plan

    def override(case):
        plan = project(case)
        plan["opportunity_quality"]["structure_tier"] = tier
        return plan

    monkeypatch.setattr(module, "project_current_price_action_plan", override)
    report = module.select_current_hotspot_candidates(root=tmp_path, now=NOW)
    row = next(item for item in report["items"] if item["symbol"] == "600519")
    assert row["selection_status"] == status
    assert bool(report["shortlist"]) == (status == "SELECTED")
    assert row["entry_condition"]["personal_permission"] is False
    assert row["invalidation_condition"]["price"] is not None
    assert row["formal_eligibility"] is False


def test_real_retained_watch_pool_replay_is_read_only():
    root = Path("D:/GPTProject/value-investment/.tmp/dual1")
    if not (root / module.REGISTRY).is_file():
        pytest.skip("Optional local retained source checkout")
    raw = (root / module.REGISTRY).read_bytes()
    registry = json.loads(raw)
    report = module._read(root, registry["watch_source_binding"])
    cutoff = max(datetime.fromisoformat(report["available_at"]),
                 datetime.fromisoformat(registry["completed_at"]))
    # completed_at belongs to the quote bundle, not later minute collection.
    for item in registry.get("assessed_candidates", []) + registry["items"]:
        case = json.loads((root / item["case_path"]).read_bytes())
        cutoff = max(cutoff, *(datetime.fromisoformat(source["fetched_at"])
                              for source in case["source_bindings"].values()))
    result = module.select_current_hotspot_candidates(root=root, now=cutoff)
    assert result["status"] == "RESEARCH_SELECTION_REPLAYED", result
    assert result["coverage"]["candidate_pool"] > 5
    assert result["coverage"]["evaluated"] > 5
    assert result["coverage"]["bound_cases"] > 5
    assert result["coverage"]["structure_verified"] > 5
    assert sum(result["coverage"][key] for key in (
        "selected", "excluded", "pending_confirmation", "unknown")) == len(result["items"])
    assert (root / module.REGISTRY).read_bytes() == raw
    assert result == module.select_current_hotspot_candidates(root=root, now=cutoff)
