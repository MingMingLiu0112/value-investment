from pathlib import Path


def test_annual_launcher_binds_configured_evidence_and_caps_resources():
    source = (Path(__file__).parents[1] / 'deploy/server/run_annual_backfill.sh').read_text()
    assert '-e EVIDENCE_DIRECTORY=/app/evidence' in source
    assert '"$ROOT/evidence:/app/evidence:Z"' in source
    assert '--memory=512m --memory-swap=640m --cpus=0.5' in source
    assert 'python /audit/run_annual_batch.py --limit "$LIMIT"' in source
    assert 'set -euo pipefail' in source
    assert 'exit 2' in source


def test_annual_launcher_checks_headroom_before_container_start():
    source = (Path(__file__).parents[1] / 'deploy/server/run_annual_backfill.sh').read_text()
    assert 'AVAILABLE_KB < 1048576 || DISK_KB < 2097152' in source
    assert 'resource_check_failed' in source
    assert 'filings_running_deferred' in source
    assert source.index('resource_deferred') < source.index('exec podman')
