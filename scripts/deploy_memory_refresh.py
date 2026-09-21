"""One-use, hash-pinned deployment of the reviewed per-issuer memory fix."""
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path('/opt/value-investment-agent')
EXPECTED = {
    'cli.py': ('08bfefab58b6cc6c721c763edf0b8f1ea03418ef8bcd2b26d1911ef390729d89',
               '80febb2e8c89e4be9cc0c2a76313ce47c338d01ffd15f39871c7ddaaa4ebb25a'),
    'db.py': ('a7ac4a4ba2745dd99fd2b1973eaf599a0f7b26e1e3d02815f990017b746b6ced',
              '84e46b7e40094941731adb89499c9c687eb2efcf44f0b95ad8d560cdd9326f60'),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_idle_filing_service():
    state = subprocess.check_output(
        ['systemctl', 'show', 'value-investment-agent-filings.service',
         '--property=ActiveState', '--value'], universal_newlines=True).strip()
    if state not in {'inactive', 'failed'}:
        raise RuntimeError('Filing service is not idle: ' + state)


def main(expected=EXPECTED, backup_prefix='memory-refresh-'):
    with (ROOT / 'exports/market-screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_idle_filing_service()
        containers = subprocess.check_output(['podman', 'ps', '--format', '{{.Image}}'],
                                             universal_newlines=True)
        if 'value-investment-agent' in containers:
            raise RuntimeError('An application container is active; retry after it finishes')
        destination = ROOT / 'src/value_investment_agent'
        staging = ROOT / 'deploy-staging'
        for name, (old, new) in expected.items():
            if digest(destination / name) != old or digest(staging / name) != new:
                raise RuntimeError('Baseline or staged hash mismatch: ' + name)
        backup = Path(tempfile.mkdtemp(prefix=backup_prefix, dir=str(ROOT / 'deploy-backups')))
        for name in expected:
            shutil.copy2(str(destination / name), str(backup / name))
        try:
            for name in expected:
                os.replace(str(staging / name), str(destination / name))
            assert all(digest(destination / n) == h[1] for n, h in expected.items())
        except BaseException:
            for name in expected:
                shutil.copy2(str(backup / name), str(destination / name))
            raise
        print(json.dumps({'backup': str(backup), 'deployed_hashes':
                          {n: digest(destination / n) for n in expected}}))


if __name__ == '__main__':
    main()
