"""Exercise real flock contention on temporary files, stopping before collection."""
import argparse
import fcntl
from pathlib import Path
import subprocess
import tempfile
import time


def verify(path):
    script = path.read_text(encoding='utf-8')
    if 'flock -w 30 9 || {' not in script:
        raise ValueError('Unexpected lock block')
    prefix, tail = script.split('flock -w 30 9 || {', 1)
    block = tail.split('\n}', 1)[0] + '\n}'
    with tempfile.TemporaryDirectory(prefix='value-agent-lock-test-') as directory:
        lock_path = Path(directory) / 'lock'
        prefix = prefix.replace('exec 9>"$root/exports/market-screen.lock"', f'exec 9>"{lock_path}"')
        prefix = prefix.replace('exec 9>/opt/value-investment-agent/exports/market-screen.lock', f'exec 9>"{lock_path}"')
        if '/exports/market-screen.lock' in prefix:
            raise ValueError('Real lock must never be used in fixture')
        command = prefix + 'flock -w 30 9 || {' + block + '\nprintf "LOCK_ACQUIRED_TEST_ONLY\\n"\n'
        with lock_path.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            started = time.monotonic()
            result = subprocess.run(['bash', '-c', command], capture_output=True, text=True, timeout=40)
            assert time.monotonic() - started >= 29
            assert result.returncode == 75 and 'SKIPPED_LOCK_BUSY:' in result.stderr, result
            assert 'LOCK_ACQUIRED' not in result.stdout
        result = subprocess.run(['bash', '-c', command], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and 'LOCK_ACQUIRED_TEST_ONLY' in result.stdout, result
    print(path.name + ': contention=75, released=0; no collection executed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts', type=Path, nargs='+')
    for path in parser.parse_args().scripts:
        verify(path)
