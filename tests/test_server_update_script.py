from pathlib import Path


def test_daily_update_uses_mounted_source_for_every_stage() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_update.sh').read_text(encoding='utf-8')

    assert script.count('-e PYTHONPATH=/app/src') == 4
    assert script.count('-v /opt/value-investment-agent/src:/app/src:ro,Z') == 4
