"""Explicit display scope never bypasses the refresh quote/session boundary."""
from datetime import datetime
import hashlib
import json

import pytest

from test_daily_quote_binding import _write_bundle
from value_investment_agent.application.hotspot import current_refresh as module
from value_investment_agent.infrastructure.hotspot.current_price_case import (
    DISPLAY_CLOSE_SCOPE, STRICT_CLOSE_SCOPE,
)
from value_investment_agent.quote_sessions import CHINA


@pytest.fixture
def refresh_inputs(tmp_path, monkeypatch):
    bundle = json.loads(_write_bundle(tmp_path).read_bytes())
    source = tmp_path / "runtime/watch.json"
    source.write_text(json.dumps({
        "action": "no_order",
        "hotspot_watch_queue": [{"symbol": "600519", "name": "TEST_ONLY"}],
    }), encoding="utf-8")
    pointer = tmp_path / "config/current-price-conditions.json"
    pointer.parent.mkdir()
    previous = {
        "schema_version": "current-price-conditions-v1", "action": "no_order",
        "items": [], "watch_source_binding": {"path": "runtime/prior.json", "sha256": "a" * 64},
        "watch_source_scope": "HOTSPOT_WATCH_QUEUE",
    }
    pointer.write_text(json.dumps(previous), encoding="utf-8")
    monkeypatch.setattr(module, "project_current_price_action_plan", lambda case: {
        "signal_state": "WATCH",
        "opportunity_quality": {"structure_tier": "ACTIVE_ONLY", "structure_reasons": ["TEST_ONLY"]},
    })
    return tmp_path, source, bundle, pointer


def _run(inputs, case_collector, **options):
    root, source, bundle, _ = inputs
    return module.refresh_current_price_conditions(
        root=root, watch_source_path=source,
        watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bundle_collector=lambda symbols: bundle, case_collector=case_collector,
        now=datetime(2026, 9, 26, 16, 15, tzinfo=CHINA), **options,
    )


def _case():
    return {"case_path": "runtime/synthetic-case.json", "case_sha256": "b" * 64}


@pytest.mark.parametrize("explicit", [False, True])
def test_strict_default_keeps_legacy_collector_signature(refresh_inputs, explicit):
    calls = []

    # Deliberately excludes observation_scope: strict mode must preserve this seam.
    def collect(*, root, symbol, as_of, quote_bundle_path, quote_bundle_sha256):
        calls.append((symbol, as_of.isoformat()))
        return _case()

    result = _run(refresh_inputs, collect, **({"observation_scope": STRICT_CLOSE_SCOPE} if explicit else {}))
    assert calls == [("600519", "2026-09-24")]
    assert result["status"] == "WRITTEN" and not result["failures"]
    assert result["observation_scope"] == STRICT_CLOSE_SCOPE
    assert json.loads(refresh_inputs[3].read_bytes())["observation_scope"] == STRICT_CLOSE_SCOPE


def test_explicit_display_scope_reaches_collector_and_is_recorded(refresh_inputs):
    calls = []

    def collect(**kwargs):
        calls.append(kwargs)
        return _case()

    result = _run(refresh_inputs, collect, observation_scope=DISPLAY_CLOSE_SCOPE)
    assert result["status"] == "WRITTEN" and not result["failures"]
    assert len(calls) == 1
    assert calls[0]["observation_scope"] == DISPLAY_CLOSE_SCOPE
    assert calls[0]["as_of"].isoformat() == "2026-09-24"
    assert result["observation_scope"] == DISPLAY_CLOSE_SCOPE
    registered = json.loads(refresh_inputs[3].read_bytes())
    assert registered["observation_scope"] == DISPLAY_CLOSE_SCOPE
    assert registered["action"] == result["action"] == "no_order"
    archive = refresh_inputs[0] / result["bundle_path"]
    report = json.loads((archive.parent / "report.json").read_bytes())
    assert report["observations"][0]["result"]["passed"] is True
    assert report["financial_or_strategy_approval"] is False
    assert report["production_database_changed"] is False


@pytest.mark.parametrize("scope", ["DISPLAY", "TEST_ONLY", "", None, True])
def test_unsupported_scope_fails_before_acquisition_or_any_file_mutation(refresh_inputs, scope):
    root, source, _, _ = refresh_inputs
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid scope must fail before acquisition")

    with pytest.raises(ValueError, match="[Ss]cope"):
        module.refresh_current_price_conditions(
            root=root, watch_source_path=source,
            watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            bundle_collector=forbidden, case_collector=forbidden, observation_scope=scope,
        )
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("failure", ["calendar", "stale-session", "selection-session", "collector"])
def test_display_failure_preserves_prior_registry(refresh_inputs, monkeypatch, failure):
    _, source, bundle, pointer = refresh_inputs
    previous = pointer.read_bytes()
    calls = []
    if failure == "calendar":
        bundle["references"]["600519"]["document_refs"]["calendar_documents"] = []
    elif failure == "selection-session":
        report = json.loads(source.read_bytes())
        report.update(schema_version="hotspot-daily-selection-v1", trade_date="2026-09-23")
        source.write_text(json.dumps(report), encoding="utf-8")
        # Original selection verification is separate; retain real B1 evaluation here.
        monkeypatch.setattr(module, "verify_daily_selection", lambda *args: None)

    def collect(**kwargs):
        calls.append(kwargs)
        if failure == "collector":
            raise ValueError("TEST_ONLY incomplete bars")
        pytest.fail("Session rejection must precede case acquisition")

    if failure == "stale-session":
        root = refresh_inputs[0]
        result = module.refresh_current_price_conditions(
            root=root, watch_source_path=source,
            watch_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            bundle_collector=lambda symbols: bundle, case_collector=collect,
            now=datetime(2026, 9, 28, 17, tzinfo=CHINA), observation_scope=DISPLAY_CLOSE_SCOPE,
        )
    else:
        result = _run(refresh_inputs, collect, observation_scope=DISPLAY_CLOSE_SCOPE)
    assert result["status"] == "BLOCKED" and result["items"] == []
    assert result["failures"]
    if failure in {"calendar", "stale-session"}:
        assert result["failures"][0]["reason"].startswith("B1 rejected:")
    elif failure == "selection-session":
        assert "Selection session and price session differ" in result["failures"][0]["reason"]
    else:
        assert result["failures"][0]["reason"] == "TEST_ONLY incomplete bars"
    assert len(calls) == (1 if failure == "collector" else 0)
    assert pointer.read_bytes() == previous
    assert (refresh_inputs[0] / result["bundle_path"]).is_file()


@pytest.mark.parametrize("scope", [STRICT_CLOSE_SCOPE, DISPLAY_CLOSE_SCOPE])
def test_cli_forwards_selected_scope_without_acquiring_candidates(tmp_path, monkeypatch, capsys, scope):
    from scripts.current import refresh_current_price_conditions as cli

    calls = []
    monkeypatch.setattr(cli, "collect_daily_candidates", lambda **kwargs: pytest.fail("Explicit watch supplied"))

    def capture(**kwargs):
        calls.append(kwargs)
        return {"status": "WRITTEN", "action": "no_order", "observation_scope": kwargs["observation_scope"]}

    monkeypatch.setattr(cli, "refresh_current_price_conditions", capture)
    args = ["--root", str(tmp_path), "--watch-source", "runtime/synthetic-watch.json",
            "--watch-source-sha256", "a" * 64]
    if scope == DISPLAY_CLOSE_SCOPE:
        args += ["--observation-scope", scope]
    assert cli.main(args) == 0
    assert calls[0]["observation_scope"] == scope
    assert json.loads(capsys.readouterr().out)["observation_scope"] == scope


def test_cli_unsupported_scope_rejects_before_any_acquisition(tmp_path, monkeypatch):
    from scripts.current import refresh_current_price_conditions as cli

    def forbidden(**kwargs):
        pytest.fail("Argparse must reject unsupported scope first")

    monkeypatch.setattr(cli, "collect_daily_candidates", forbidden)
    monkeypatch.setattr(cli, "refresh_current_price_conditions", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main(["--root", str(tmp_path), "--observation-scope", "TEST_ONLY"])
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())
