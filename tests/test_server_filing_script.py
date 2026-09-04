from pathlib import Path


def test_filing_service_uses_mounted_source_for_every_stage() -> None:
    script = (Path(__file__).parents[1] / 'deploy' / 'server' / 'run_collect_filings.source.sh').read_text(encoding='utf-8')

    assert script.count('-e PYTHONPATH=/app/src') == 6
    extraction = script.split('extract-filing-candidates-batch', maxsplit=1)[0]
    assert '-v /opt/value-investment-agent/src:/app/src:ro,Z' in extraction
