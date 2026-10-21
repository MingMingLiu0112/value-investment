from datetime import datetime
import hashlib
import json

import pytest

from value_investment_agent.application.hotspot.current_refresh import refresh_current_price_conditions, select_watch_candidates
from value_investment_agent.quote_sessions import CHINA
from test_daily_quote_binding import _write_bundle


@pytest.mark.parametrize("live_clock,source_seconds,expected", [
    (True, 2, "SOURCE_BOUND_OBSERVATION_ONLY"),
    (False, 2, "UNASSESSABLE"),
    (True, 10, "UNASSESSABLE"),
])
def test_continuity_uses_real_post_collection_clock_without_advancing_explicit_cutoff(
    tmp_path, monkeypatch, live_clock, source_seconds, expected,
):
    from datetime import timedelta
    from test_hotspot_current_price_case import Response, NOW
    from value_investment_agent.infrastructure.hotspot.current_price_case import collect_current_price_case
    from value_investment_agent.application.hotspot import current_refresh as module
    at = [NOW]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at[0].astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)
    bundle_path = _write_bundle(tmp_path)
    bundle = json.loads(bundle_path.read_bytes())
    source = tmp_path / "runtime/watch.json"
    source.write_text(json.dumps(dict(schema_version="hotspot-observation-report-v1", action="no_order",
        hotspot_watch_queue=[dict(symbol="600519", name="TEST_ONLY")],
        dated_quote_observations=[dict(symbol="600519", quote_date="2026-09-24",
            status="DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION")])), encoding="utf-8")

    def collect(**kwargs):
        # Reuse the refresh's retained bundle; capture() would create the same
        # fixture quote directory a second time before testing the clock.
        case = collect_current_price_case(**kwargs, now=NOW + timedelta(seconds=source_seconds),
            fetch=lambda _url, params, timeout: Response(params["scale"]))
        at[0] = NOW + timedelta(seconds=3)
        return case

    result = module.refresh_current_price_conditions(root=tmp_path, watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=lambda symbols: bundle, case_collector=collect,
        **({} if live_clock else dict(now=NOW)))
    assert result["status"] == "WRITTEN", result
    assert result["observation_continuity"]["status"] == expected, result
    if expected == "SOURCE_BOUND_OBSERVATION_ONLY":
        saved = json.loads((tmp_path / result["observation_continuity"]["path"]).read_bytes())
        assert datetime.fromisoformat(saved["evaluated_at"]) == at[0]
        assert datetime.fromisoformat(saved["items"][0]["observation"]["plan"]["data_available_at"]) == NOW + timedelta(seconds=2)
    else:
        assert result["observation_continuity"]["reason"] == "Observation unavailable at evaluation cutoff"


def test_verified_empty_daily_selection_retires_old_candidates_without_acquisition(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import current_refresh as module
    from value_investment_agent.application.hotspot import current_registry
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    report = dict(schema_version='hotspot-daily-selection-v1', action='no_order',
        trade_date='2026-10-14', available_at='2026-10-14T08:00:00+00:00',
        ranking={'candidates': []}, rows=[{'symbol': '600519'}], failures=[],
        observation_list=[], hotspot_watch_queue=[])
    source = runtime / 'empty.json'
    source.write_text(json.dumps(report), encoding='utf-8')
    # The daily-selection verifier owns original/ranking validation; exercise
    # the empty-result publication and retired-candidate boundary here.
    monkeypatch.setattr(module, 'verify_daily_selection', lambda *args: None)
    monkeypatch.setattr(current_registry, 'verify_daily_selection', lambda *args: None)
    config = tmp_path / 'config'
    config.mkdir()
    pointer = config / 'current-price-conditions.json'
    pointer.write_text(json.dumps(dict(items=[dict(symbol='600519', company_name='TEST_ONLY',
        case_path='runtime/old.json', case_sha256='a' * 64)],
        watch_source_binding=dict(path='runtime/old-watch.json', sha256='b' * 64),
        watch_source_scope='HISTORICAL_ONLY')), encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('Zero candidates must not request bars or quotes')
    result = refresh_current_price_conditions(root=tmp_path, watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=forbidden, case_collector=forbidden)
    assert result['status'] == 'WRITTEN' and not result['items'] and not result['failures']
    assert result['observation_continuity']['status'] == 'UNASSESSABLE'
    registered = json.loads(pointer.read_bytes())
    assert registered['items'] == [] and registered['selected_symbols'] == []
    assert registered['previous_items'][0]['symbol'] == '600519'
    loaded = current_registry.load_price_conditions(tmp_path,
        now=datetime(2026, 10, 14, 17, tzinfo=CHINA), research_version=None)
    assert loaded['status'] == 'CURRENT_EMPTY_SELECTION'
    assert loaded['selection_trade_date'] == '2026-10-14'
    assert loaded['blockers'] == []
    assert loaded['retired_warnings']


def test_bounded_fallback_does_not_claim_industry_admission():
    report = dict(hotspot_watch_queue=[], dated_quote_observations=[
        dict(symbol=symbol, status="DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION")
        for symbol in ("300308", "300750", "300502", "688825", "002384", "000333")])
    selected, scope = select_watch_candidates(report)
    assert len(selected) == 5 and selected[-1]["symbol"] == "002384"
    assert scope == "DATED_SECURITIES_WATCH_FALLBACK_NOT_INDUSTRY_CERTIFIED"
    with pytest.raises(ValueError):
        select_watch_candidates(report, limit=6)


@pytest.mark.parametrize("metadata", [{}, {"industry": None, "rank": None}])
def test_legacy_watch_candidates_allow_missing_industry_and_rank(metadata):
    selected, scope = select_watch_candidates(dict(hotspot_watch_queue=[
        dict(symbol="600519", company_name="TEST_ONLY", **metadata),
    ]))
    assert selected == [dict(symbol="600519", company_name="TEST_ONLY")]
    assert scope == "HOTSPOT_WATCH_QUEUE"


@pytest.mark.parametrize("rank", [True, False, 0, -1, "1", 1.0])
def test_watch_candidate_rejects_invalid_explicit_rank(rank):
    with pytest.raises(ValueError, match="Invalid watch rank"):
        select_watch_candidates(dict(candidate_pool=[
            dict(symbol="600519", industry="TEST_ONLY", rank=rank),
        ]))


@pytest.mark.parametrize("industry", ["", " ", 1, []])
def test_watch_candidate_rejects_invalid_explicit_industry(industry):
    with pytest.raises(ValueError, match="Invalid watch industry"):
        select_watch_candidates(dict(candidate_pool=[
            dict(symbol="600519", industry=industry, rank=1),
        ]))


@pytest.mark.parametrize("structure_priority", [False, True])
def test_quality_ranking_promotes_a_lower_ranked_candidate_and_excludes_unassessed(
    tmp_path, monkeypatch, structure_priority,
):
    from value_investment_agent.application.hotspot import current_refresh as module

    symbols = [f"60000{index}" for index in range(7, 0, -1)]
    rows = [
        dict(symbol=symbol, company_name=symbol, industry=f"industry-{index % 3}", rank=index)
        for index, symbol in enumerate(symbols, start=1)
    ]
    selected, _ = select_watch_candidates(dict(candidate_pool=rows), limit=7)
    assert selected == rows
    assert rows[0]["rank"] == 1 and rows[0]["industry"] == "industry-1"
    source = tmp_path / "runtime" / "candidate-pool.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(dict(
        observation_list=rows[:5], candidate_pool=rows, action="no_order",
    )), encoding="utf-8")
    bundle = dict(
        status="collected_not_verified",
        finished_at="2026-10-14T08:00:00+00:00",
        documents={"quote": {}},
        references={symbol: {"document_refs": {"tencent": "quote"}} for symbol in symbols},
    )
    tiers = {symbol: "ACTIVE_ONLY" for symbol in symbols[:5]}
    tiers[symbols[5]] = "STRUCTURE_QUALIFIED_OBSERVATION"
    monkeypatch.setattr(module, "parse_quote", lambda *args: dict(price="10"))
    monkeypatch.setattr(module, "evaluate_quote_session", lambda *args, **kwargs: dict(
        passed=True, status="VERIFIED", expected_session="2026-10-14",
    ))

    def collect_case(**kwargs):
        symbol = kwargs["symbol"]
        return dict(
            symbol=symbol,
            case_path=f"runtime/cases/{symbol}.json", case_sha256="a" * 64,
            signal_state="WATCH",
            opportunity_quality=dict(
                structure_tier=tiers[symbol], structure_reasons=["TEST_ONLY"],
            ),
        )

    def project_case(case):
        return dict(
            signal_state="WATCH",
            price_behavior=(dict(observation_quality="RESEARCH_ONLY", daily_trend="UPTREND")
                            if structure_priority and case["symbol"] == symbols[4] else {}),
            opportunity_quality=dict(
                structure_tier=tiers[case["symbol"]],
                structure_reasons=["TEST_ONLY"],
            ),
        )

    monkeypatch.setattr(module, "project_current_price_action_plan", project_case)

    result = refresh_current_price_conditions(
        root=tmp_path, watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=lambda selected: bundle, case_collector=collect_case,
        now=datetime(2026, 10, 14, 17, tzinfo=CHINA),
    )
    assert result["status"] == "WRITTEN"
    assert result["selection_pipeline"]["candidate_pool_count"] == 7
    assert result["selection_pipeline"]["candidate_pool_industry_count"] == 3
    assert result["selection_pipeline"]["assessed_count"] == 6
    assert result["selection_pipeline"]["failed_count"] == 1
    assert result["items"][0]["symbol"] == symbols[5]
    expected = (5, 4, 0, 1, 2) if structure_priority else (5, 0, 1, 2, 3)
    assert [item["symbol"] for item in result["items"]] == [symbols[index] for index in expected]
    assert [item["activity_rank"] for item in result["items"]] == [index + 1 for index in expected]
    assert [item["industry"] for item in result["items"]] == [
        rows[index]["industry"] for index in expected
    ]
    assert symbols[6] not in {item["symbol"] for item in result["items"]}
    assert all(item["structure_tier"] != "UNASSESSED" for item in result["items"])
    registry = json.loads((tmp_path / "config/current-price-conditions.json").read_text())
    assert registry["selected_symbols"][0] == symbols[5]
    assert registry["candidate_pool_symbols"] == symbols
    assert registry["selection_pipeline"]["candidate_pool_industry_count"] == 3
    assert registry["selection_pipeline"]["quality_counts"] == {
        "STRUCTURE_QUALIFIED_OBSERVATION": 1,
        "ACTIVE_ONLY": 5,
        "CONFLICT_OR_REJECTED": 0,
    }
    assert registry["assessed_candidates"][1]["structure_selection_evidence"]["trade_space_known"] is structure_priority
    assert registry["selection_pipeline"]["ranking_scope"] == "OBSERVATION_PRIORITY_NOT_STRATEGY_ADMISSION"


@pytest.mark.parametrize("limit,pool", [(True, None), (0, None), (11, None), (5, 4), (5, True), (5, 31)])
def test_invalid_final_or_pool_limit_is_rejected_before_acquisition(tmp_path, limit, pool):
    with pytest.raises(ValueError, match="limit|pool"):
        refresh_current_price_conditions(root=tmp_path, watch_source_path="missing.json",
            watch_source_sha256="a" * 64, limit=limit, candidate_pool_limit=pool)


def test_structural_conflict_cannot_be_promoted_by_positive_auxiliary_evidence():
    from value_investment_agent.application.hotspot.current_refresh import final_observation_key
    active = dict(symbol="600001", activity_rank=999, structure_tier="ACTIVE_ONLY", signal_state="WATCH")
    rejected = dict(symbol="600002", activity_rank=1, structure_tier="CONFLICT_OR_REJECTED",
        signal_state="TRIGGER_REJECTED", structure_reasons=["PRIMARY_STRUCTURE_INVALIDATED"],
        structure_selection_evidence=dict(trade_space_known=True, primary_confirmed=True,
            daily_uptrend=True, auxiliary_confirmed=True))
    assert sorted([rejected, active], key=final_observation_key) == [active, rejected]
    assert rejected["structure_reasons"] == ["PRIMARY_STRUCTURE_INVALIDATED"]


def test_injected_quality_cannot_short_circuit_case_recalculation(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import current_refresh as module

    source = tmp_path / "runtime" / "candidate-pool.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(dict(
        observation_list=[dict(symbol="600001", company_name="TEST", industry="TEST", rank=1)],
        candidate_pool=[dict(symbol="600001", company_name="TEST", industry="TEST", rank=1)],
        action="no_order",
    )), encoding="utf-8")
    bundle = dict(
        status="collected_not_verified",
        finished_at="2026-10-14T08:00:00+00:00",
        documents={"quote": {}},
        references={"600001": {"document_refs": {"tencent": "quote"}}},
    )
    monkeypatch.setattr(module, "parse_quote", lambda *args: dict(price="10"))
    monkeypatch.setattr(module, "evaluate_quote_session", lambda *args, **kwargs: dict(
        passed=True, status="VERIFIED", expected_session="2026-10-14",
    ))

    result = refresh_current_price_conditions(
        root=tmp_path,
        watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=lambda selected: bundle,
        case_collector=lambda **kwargs: dict(
            case_path="runtime/cases/600001.json",
            case_sha256="a" * 64,
            signal_state="WATCH",
            opportunity_quality=dict(
                structure_tier="STRUCTURE_QUALIFIED_OBSERVATION",
                structure_reasons=["INJECTED_WITHOUT_BARS"],
            ),
        ),
        now=datetime(2026, 10, 14, 17, tzinfo=CHINA),
    )
    assert result["items"] == []
    assert result["selection_pipeline"]["failed_count"] == 1
    assert "case" not in result or result.get("status") != "WRITTEN"


@pytest.mark.parametrize('tier,state,expected', [
    ('STRUCTURE_QUALIFIED_OBSERVATION', 'TRIGGER_OBSERVED', 'STRUCTURE_QUALIFIED_OBSERVATION'),
    ('CONFLICT_OR_REJECTED', 'TRIGGER_REJECTED', 'CONFLICT_OR_REJECTED'),
])
def test_retired_candidate_preserves_valid_quality_without_fresh_assessment(tmp_path, monkeypatch, tier, state, expected):
    from value_investment_agent.application.hotspot import current_registry
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'bundle.json').write_text(json.dumps(dict(finished_at='2026-10-14T16:00:00+08:00')), encoding='utf-8')
    (runtime / 'case.json').write_text(json.dumps(dict(
        current_reference_close=dict(bundle_path='runtime/bundle.json'),
        source_bindings=dict(primary=dict(fetched_at='2026-10-14T16:00:00+08:00')))), encoding='utf-8')
    def binding(name, symbol):
        path = runtime / name
        path.write_text(json.dumps(dict(observation_list=[dict(symbol=symbol)])), encoding='utf-8')
        return dict(path=path.relative_to(tmp_path).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    current = binding('current.json', '300059')
    previous = binding('previous.json', '601318')
    config = tmp_path / 'config'
    config.mkdir()
    def item(symbol, source=None):
        result = dict(symbol=symbol, company_name=symbol, case_path='runtime/case.json',
                      case_sha256='a' * 64)
        if source:
            result.update(watch_source_binding=source, watch_source_scope='HOTSPOT_WATCH_QUEUE')
        return result
    (config / 'current-price-conditions.json').write_text(json.dumps(dict(
        schema_version='current-price-conditions-v1', action='no_order',
        watch_source_binding=current, watch_source_scope='HOTSPOT_WATCH_QUEUE',
        items=[item('300059')], previous_items=[item('601318', previous)])), encoding='utf-8')
    monkeypatch.setattr(current_registry, 'load_current_price_case',
                        lambda **kwargs: dict(symbol=kwargs['symbol'], case_path='runtime/case.json',
                                              case_sha256='a' * 64))
    monkeypatch.setattr(current_registry, 'project_current_price_action_plan',
                        lambda case: dict(signal_state=state, action_intent='OPEN',
                                        market_trade_date='2026-10-14', expires_after_session='2026-10-15',
                                          opportunity_quality=dict(structure_tier=tier,
                                                                   structure_reasons=['ORIGINAL_REASON'])))
    loaded = current_registry.load_price_conditions(tmp_path,
        now=datetime(2026, 10, 14, 17, tzinfo=CHINA), research_version=None)
    assert loaded['status'] == 'CURRENT_OBSERVATION', loaded
    retired = next(row['price_action_plan'] for row in loaded['items'] if row['symbol'] == '601318')
    assert retired['candidate_lifecycle'] == 'PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY'
    assert retired['opportunity_quality']['structure_tier'] == expected
    assert retired['retained_observation_valid'] is True
    assert retired['signal_state'] == state
    assert retired['opportunity_quality']['structure_reasons'] == ['ORIGINAL_REASON']


def test_refresh_archives_bundle_and_does_not_replace_registry_on_failure(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import current_refresh as module
    bundle_path = _write_bundle(tmp_path)
    bundle = json.loads(bundle_path.read_bytes())
    source = tmp_path / "runtime/watch.json"
    source.write_text(json.dumps(dict(hotspot_watch_queue=[dict(symbol="600519", name="test")])), encoding="utf-8")
    config = tmp_path / "config"
    config.mkdir()
    pointer = config / "current-price-conditions.json"
    pointer.write_bytes(b"existing")
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        raise ValueError("source incomplete")

    monkeypatch.setattr(
        module,
        "project_current_price_action_plan",
        lambda case: dict(
            signal_state="WATCH",
            opportunity_quality=dict(
                structure_tier="ACTIVE_ONLY",
                structure_reasons=["STRUCTURE_CONFIRMATION_PENDING"],
            ),
        ),
    )

    result = refresh_current_price_conditions(root=tmp_path, watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=lambda symbols: bundle, case_collector=capture,
        now=datetime(2026, 9, 26, 16, 15, tzinfo=CHINA))
    assert result["status"] == "BLOCKED" and result["failures"][0]["reason"] == "source incomplete"
    assert calls[0]["as_of"].isoformat() == "2026-09-24"
    assert pointer.read_bytes() == b"existing"
    assert (tmp_path / result["bundle_path"]).is_file()
    result = refresh_current_price_conditions(root=tmp_path, watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=lambda symbols: bundle,
        case_collector=lambda **kwargs: dict(
            case_path="runtime/verified/case.json", case_sha256="a" * 64,
            signal_state="WATCH",
            opportunity_quality=dict(
                structure_tier="ACTIVE_ONLY",
                structure_reasons=["STRUCTURE_CONFIRMATION_PENDING"],
            ),
        ),
        now=datetime(2026, 9, 26, 16, 15, tzinfo=CHINA))
    assert result["status"] == "WRITTEN"
    assert json.loads(pointer.read_bytes())["items"][0]["case_sha256"] == "a" * 64


def test_cli_default_binding_and_pair_failure(tmp_path, monkeypatch, capsys):
    from scripts.current import refresh_current_price_conditions as cli
    binding = dict(path="runtime/published/report.json", sha256="b" * 64)
    monkeypatch.setattr(cli, "collect_daily_candidates", lambda **kwargs: binding)
    captured = {}

    def refresh(**kwargs):
        captured.update(kwargs)
        return dict(status="WRITTEN", action="no_order")
    monkeypatch.setattr(cli, "refresh_current_price_conditions", refresh)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    assert cli.main([]) == 0
    assert captured["root"] == tmp_path
    assert captured["watch_source_path"].as_posix() == binding["path"]
    assert captured["watch_source_sha256"] == binding["sha256"]
    capsys.readouterr()
    assert cli.main(["--root", str(tmp_path), "--watch-source", "runtime/report.json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_current_binding_checks_actual_report_role(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import current_refresh as module
    monkeypatch.setattr(module, "load_current_chain", lambda root: dict(model=dict(
        product_extensions=dict(hotspot_report=dict(path="runtime/report.json", sha256="b" * 64)))))
    monkeypatch.setattr(module, "bound_object", lambda root, binding: dict(schema_version="wrong", action="no_order"))
    with pytest.raises(ValueError, match="not a hotspot"):
        module.current_watch_binding(tmp_path)


@pytest.mark.parametrize("replace_fails", [False, True])
def test_partial_failure_retains_evidence_and_cleans_temporary_pointer(tmp_path, monkeypatch, replace_fails):
    from value_investment_agent.application.hotspot import current_refresh as module
    original_bundle = _write_bundle(tmp_path)
    bundle = json.loads(original_bundle.read_bytes())
    source = tmp_path / "runtime/watch.json"
    source.write_text(json.dumps(dict(hotspot_watch_queue=[dict(symbol="600519"), dict(symbol="600887")])), encoding="utf-8")
    config = tmp_path / "config"
    config.mkdir()
    pointer = config / "current-price-conditions.json"
    pointer.write_bytes(b"old-pointer")

    def capture(**kwargs):
        folder = tmp_path / "runtime" / ("capture-" + kwargs["symbol"])
        folder.mkdir()
        (folder / "original.jsonp").write_bytes(b"retained-original")
        if kwargs["symbol"] == "600887":
            raise ValueError("Incomplete 15m session")
        return dict(
            case_path="runtime/capture-600519/case.json", case_sha256="a" * 64,
            signal_state="WATCH",
            opportunity_quality=dict(
                structure_tier="ACTIVE_ONLY",
                structure_reasons=["STRUCTURE_CONFIRMATION_PENDING"],
            ),
        )

    monkeypatch.setattr(
        module,
        "project_current_price_action_plan",
        lambda case: dict(
            signal_state="WATCH",
            opportunity_quality=dict(
                structure_tier="ACTIVE_ONLY",
                structure_reasons=["STRUCTURE_CONFIRMATION_PENDING"],
            ),
        ),
    )

    if replace_fails:
        def reject_replace(*args):
            raise OSError("atomic replace failed")
        monkeypatch.setattr(module.os, "replace", reject_replace)
    kwargs = dict(root=tmp_path, watch_source_path=source,
                  watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  bundle_collector=lambda symbols: bundle, case_collector=capture,
                  now=datetime(2026, 9, 26, 16, 15, tzinfo=CHINA))
    if replace_fails:
        with pytest.raises(OSError, match="atomic replace"):
            refresh_current_price_conditions(**kwargs)
        assert pointer.read_bytes() == b"old-pointer"
    else:
        result = refresh_current_price_conditions(**kwargs)
        assert result["status"] == "WRITTEN"
        assert [item["symbol"] for item in result["items"]] == ["600519"]
        assert result["failures"][0]["symbol"] == "600887"
        assert [item["symbol"] for item in json.loads(pointer.read_bytes())["items"]] == ["600519"]
    assert not list(config.glob(".current-price-conditions-*.json"))
    assert (tmp_path / "runtime/capture-600887/original.jsonp").read_bytes() == b"retained-original"
    assert not (tmp_path / "runtime/capture-600887/case.json").exists()
    assert list((tmp_path / "runtime/hotspot-current-refresh").glob("*/bundle.json"))
