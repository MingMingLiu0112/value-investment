from pathlib import Path


def test_daily_launcher_never_rescreens_and_publishes_failure_status():
    script = (Path(__file__).parents[1]/'deploy/server/run_candidate_tracking.sh').read_text()
    assert 'screen-market' not in script
    assert 'track-candidates || status=$?' in script
    assert 'refresh-valuations || status=$?' in script
    assert script.index('export-payload') > script.index('\nfi\n')
    assert 'exit "$status"' in script
    assert '--cpus=0.5' in script and '--memory=512m' in script
    assert 'flock -w 30 9' in script and 'market-screen.lock' in script
    assert 'mv "$temporary" "$root/exports/latest.json"' in script
