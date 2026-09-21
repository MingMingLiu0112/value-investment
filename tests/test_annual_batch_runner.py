import importlib.util
from pathlib import Path
import subprocess

import pytest


spec = importlib.util.spec_from_file_location(
    'annual_batch_runner', Path(__file__).parents[1] / 'scripts' / 'run_annual_batch.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('stage', ['selection', 'collection', 'verification', None])
def test_batch_keeps_completed_companies_and_stage_failures(monkeypatch, stage):
    def run(command, **kwargs):
        if 'select_annual_batch.py' in command[1]:
            if stage == 'selection':
                raise subprocess.TimeoutExpired(command, 60)
            return subprocess.CompletedProcess(command, 0, '{"symbols":["000551","000563"]}')
        if (stage == 'collection' and 'collect_annual_samples.py' in command[1]
                and '000551' in command):
            raise subprocess.CalledProcessError(1, command)
        if stage == 'verification' and 'auto-verify-filings' in command:
            raise subprocess.TimeoutExpired(command, 120)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, 'run', run)
    result = runner.execute_batch(Path('/audit'), 5)
    expected = [] if stage == 'selection' else ['000563'] if stage == 'collection' else ['000551', '000563']
    assert result['completed'] == expected
    assert len(result['failures']) == (0 if stage is None else 1)
    if stage == 'verification':
        assert result['failures'][0]['stage'] == 'auto-verify-filings'
