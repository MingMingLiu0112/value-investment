from pathlib import Path

import pytest


@pytest.mark.parametrize('name', ['run_candidate_tracking.sh', 'run_market_screen.sh'])
def test_lock_contention_is_visible_failure_before_collection(name):
    script = (Path(__file__).parents[1] / 'deploy/server' / name).read_text(encoding='utf-8')
    prefix = script.split('flock -w 30 9', 1)[1].split('}', 1)[0]
    assert 'SKIPPED_LOCK_BUSY:' in prefix
    assert '>&2' in prefix
    assert 'exit 75' in prefix
    assert 'exit 0' not in prefix
    assert script.index('SKIPPED_LOCK_BUSY:') < script.index('podman')
