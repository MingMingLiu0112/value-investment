from pathlib import Path


def test_filing_service_uses_mounted_source_for_every_stage() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_collect_filings.source.sh').read_text(encoding='utf-8')

    assert script.count('-e PYTHONPATH=/app/src') == 10
    extraction = script.split('extract-filing-candidates-batch', maxsplit=1)[0]
    assert '-v /opt/value-investment-agent/src:/app/src:ro,Z' in extraction
    verification_block = script.split('auto-verify-filings --limit 300', maxsplit=1)[0].rsplit('podman run', maxsplit=1)[1]
    assert 'enrich-financials --limit 40' in script
    assert 'extract-filing-candidates-batch --limit 40' in script
    assert 'collect-secondary-financials --limit 120' in script
    assert 'auto-verify-filings --limit 300' in script
    assert '-v /opt/value-investment-agent/evidence:/app/evidence:ro,Z' in verification_block
    assert 'export-payload' in script
    assert 'exports/latest.json' in script


def test_growth_collection_is_bounded_and_precedes_verification():
    script = (Path(__file__).parents[1] / 'deploy/server/run_collect_filings.source.sh').read_text(encoding='utf-8')
    command = 'collect-growth-evidence --limit 5'
    assert script.count(command) == 1
    assert script.index('collect-secondary-financials') < script.index(command) < script.index('auto-verify-filings')
    block = script.split(command)[0].rsplit('podman run', 1)[1]
    for required in ('--memory=256m', '--memory-swap=384m', '--cpus=0.5',
                     '-e EVIDENCE_DIRECTORY=/app/evidence', '-e HTTPS_PROXY=',
                     '/evidence:/app/evidence:ro,Z', '/src:/app/src:ro,Z'):
        assert required in block


def test_secondary_collection_archives_outside_ephemeral_container():
    script = (Path(__file__).parents[1] / 'deploy/server/run_collect_filings.source.sh').read_text(encoding='utf-8')
    block = script.split('collect-secondary-financials --limit 120')[0].rsplit('podman run', 1)[1]
    assert '-e EVIDENCE_DIRECTORY=/app/evidence' in block
    assert '-v /opt/value-investment-agent/evidence:/app/evidence:Z' in block
    assert '/evidence:/app/evidence:ro' not in block
    assert '--memory=256m' in block


def test_filing_timer_and_service_retry_provider_failures() -> None:
    root = Path(__file__).parents[1] / 'deploy' / 'systemd'
    timer = (root / 'value-investment-agent-filings.timer').read_text(encoding='utf-8')
    service = (root / 'value-investment-agent-filings.service').read_text(encoding='utf-8')

    assert 'OnCalendar=*-*-* *:20:00 Asia/Shanghai' in timer
    assert 'Unit=value-investment-agent-filings.service' in timer
    assert 'Restart=on-failure' in service
    assert 'RestartSec=10min' in service


def test_cli_accepts_the_scheduled_filing_batch_limits() -> None:
    cli = (Path(__file__).parents[1] / 'src' / 'value_investment_agent' / 'cli.py').read_text(encoding='utf-8')

    assert "choices=range(1, 121), metavar='1-120'" in cli
    assert "choices=range(1, 41), metavar='1-40'" in cli
