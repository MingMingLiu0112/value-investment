from pathlib import Path


def test_daily_update_uses_mounted_source_for_every_stage() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_update.sh').read_text(encoding='utf-8')

    assert script.count('-e PYTHONPATH=/app/src') == 4
    assert script.count('-v /opt/value-investment-agent/src:/app/src:ro,Z') == 4
    assert 'localhost/value-investment-agent:pg16-tools python -m value_investment_agent backup' in script


def test_market_screen_uses_mounted_source_for_every_stage() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_market_screen.sh').read_text(encoding='utf-8')

    assert script.count('-e PYTHONPATH=/app/src') == 4
    assert script.count('-v /opt/value-investment-agent/src:/app/src:ro,Z') == 4
    assert 'value_investment_agent init-db' not in script
    assert 'refresh-security-universe' in script
