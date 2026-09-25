from pathlib import Path


def test_find_percent_tokens_are_escaped_for_systemd():
    unit = (Path(__file__).parents[1] / 'deploy/server/value-investment-agent-restore-drill.service').read_text(encoding='utf-8')
    assert '%%T@ %%p' in unit
    assert '/bin/bash -e -o pipefail -c' in unit
    assert ' -lc ' not in unit
    assert 'head -n1' not in unit  # Avoid SIGPIPE from early pipeline exit.
    assert 'test -n "$$latest"' in unit


def test_restore_runner_uses_fixed_source_and_bounded_resources():
    script = (Path(__file__).parents[1] / 'deploy/server/run_restore_drill.sh').read_text(encoding='utf-8')
    assert '-e PYTHONPATH=/app/src' in script
    assert '-v /opt/value-investment-agent/src:/app/src:ro,Z' in script
    assert script.count('--cpus=0.5') == 2
    assert 'for attempt in {1..60}' in script
    assert 'if [[ "$ready" != true ]]' in script
    assert "trap 'podman rm -f value-investment-restore-postgres" in script
    assert 'localhost/value-investment-agent:pg16-tools python' in script
    assert 'restore-postgres.env' in script
    assert 'RESTORE_POSTGRES_PASSWORD' in script
    assert 'postgres.env' not in script.replace('restore-postgres.env', '')
    assert 'M6_RESTORE_ATTEMPT_STARTED_AT' in script


def test_restore_service_has_bounded_total_deadline():
    unit = (Path(__file__).parents[1] / 'deploy/server/value-investment-agent-restore-drill.service').read_text(encoding='utf-8')
    assert 'TimeoutStartSec=4h15min' in unit
