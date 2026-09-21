"""Deploy the reviewed tracking delta only; retain all prior modules for rollback."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
live = root / 'src/value_investment_agent'
stage = root / 'exports/market-deploy'
expected = {
    'db.py': 'ff162c8b41adf49907605a0cfa874e76e63242e5a80106185df6b11f97bc0348',
    'cli.py': '30701c348810f530454e89bc51f8677d0b9ded3e64a07095024fd3140ff8d6a0',
    'market.py': 'aa8116edcf440a29d0ad463fca2804d49123d483a94dea51e3ec499bccdca9d9',
    'candidate_tracking.py': None, 'tracking_collection.py': None,
}


def check():
    for service in ('filings', 'market-screen', 'update'):
        state = subprocess.check_output(['systemctl', 'show',
            'value-investment-agent-' + service + '.service', '-p', 'ActiveState', '--value'],
            universal_newlines=True).strip()
        if state not in ('inactive', 'failed'):
            raise RuntimeError('Busy service: ' + service + ' ' + state)
    for name, digest in expected.items():
        path = live / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual != digest:
            raise RuntimeError('Unexpected production module: ' + name)


check()
subprocess.check_call(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm',
    '--memory=128m', '--cpus=0.5', '--network=none', '-v', str(stage) + ':/staged:ro,Z',
    '--entrypoint', 'python', 'value-investment-agent:latest', '-c',
    'from pathlib import Path; names=' + repr(list(expected)) +
    '; [compile((Path("/staged")/n).read_bytes(),n,"exec") for n in names]'])
backup = Path(tempfile.mkdtemp(prefix='before-daily-tracking-', dir=str(root / 'exports')))
for name, digest in expected.items():
    if digest:
        shutil.copy2(str(live / name), str(backup / name))
check()
# Install new dependencies before the entry points that import them.
for name in ('candidate_tracking.py', 'tracking_collection.py', 'market.py', 'db.py', 'cli.py'):
    temporary = live / ('.tracking-' + name)
    shutil.copy2(str(stage / name), str(temporary))
    temporary.replace(live / name)
print(json.dumps({'backup': str(backup), 'deployed': {
    n: hashlib.sha256((live/n).read_bytes()).hexdigest() for n in expected}}))
