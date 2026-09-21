"""Deploy the audited payables modules only while filing collection is idle."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path('/opt/value-investment-agent')
LIVE = ROOT / 'src/value_investment_agent'
STAGE = ROOT / 'exports/market-deploy'
FILES = {
    'adapters.py': ('payables_adapters.py', '01eeb8d7709b70f412928fe77d79a0bb2898112d593724229082ecbf56470de6'),
    'filing_extract.py': ('payables_parser.py', '9906e358858c63522cbdc59b66faf24ef63006cc6330354e3232482797073a48'),
    'candidate_review.py': ('payables_candidate_review.py', '492c6c49dc3baeaee3560a94b7f37242edcc2f168fd0e284d77b262c33049b8a'),
    'payables_evidence.py': ('payables_evidence.py', None),
}


def idle():
    state = subprocess.check_output(['systemctl', 'show', 'value-investment-agent-filings.service',
        '-p', 'ActiveState', '--value'], universal_newlines=True).strip()
    if state != 'inactive':
        raise RuntimeError('Filing service is not idle: ' + state)


idle()
for filename, (staged, expected) in FILES.items():
    target = LIVE / filename
    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    if actual != expected:
        raise RuntimeError('Production module changed: ' + filename)
subprocess.check_call(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm',
    '--network', 'none', '--memory=128m', '--memory-swap=192m', '--cpus=0.5',
    '-v', str(STAGE) + ':/staged:ro,Z', 'value-investment-agent:latest',
    'python', '-c', 'import pathlib,sys; [compile(pathlib.Path(p).read_bytes(),p,"exec") for p in sys.argv[1:]]',
    *['/staged/' + staged for staged, _ in FILES.values()]])
backup = Path(tempfile.mkdtemp(prefix='before-payables-gate-', dir=ROOT / 'exports'))
for filename in FILES:
    if (LIVE / filename).exists():
        shutil.copy2(LIVE / filename, backup / filename)
idle()
installed = []
try:
    # Install the dependency before the module that imports it.
    for filename in ('payables_evidence.py', 'adapters.py', 'filing_extract.py', 'candidate_review.py'):
        idle()
        staged = FILES[filename][0]
        temporary = LIVE / ('.payables-' + filename)
        shutil.copy2(STAGE / staged, temporary)
        temporary.replace(LIVE / filename)
        installed.append(filename)
except Exception:
    for filename in reversed(installed):
        previous = backup / filename
        if previous.exists():
            shutil.copy2(previous, LIVE / filename)
        else:
            (LIVE / filename).unlink()
    raise
print(json.dumps({'backup': str(backup), 'installed': {
    filename: hashlib.sha256((LIVE / filename).read_bytes()).hexdigest() for filename in installed}}))
