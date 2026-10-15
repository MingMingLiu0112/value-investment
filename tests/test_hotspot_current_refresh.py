from datetime import datetime
import hashlib
import json

import pytest

from value_investment_agent.application.hotspot.current_refresh import refresh_current_price_conditions, select_watch_candidates
from value_investment_agent.quote_sessions import CHINA
from test_daily_quote_binding import _write_bundle


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


def test_refresh_archives_bundle_and_does_not_replace_registry_on_failure(tmp_path):
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
        case_collector=lambda **kwargs: dict(case_path="runtime/verified/case.json", case_sha256="a" * 64),
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
        return dict(case_path="runtime/capture-600519/case.json", case_sha256="a" * 64)

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
