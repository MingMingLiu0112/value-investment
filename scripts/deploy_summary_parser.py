"""Guarded deployment of the real-PDF-tested summary parser."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
live = root / 'src/value_investment_agent/filing_extract.py'
stage = root / 'exports/market-deploy/filing_extract.py'
expected = 'c5902e010f7a8c4689d322f45b4b557a01d2badcbc0de968eefe62ed049b6a6e'


def check():
    state = subprocess.check_output(['systemctl', 'show', 'value-investment-agent-filings.service',
        '-p', 'ActiveState', '--value'], universal_newlines=True).strip()
    if state != 'inactive' or hashlib.sha256(live.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Production parser changed or filing service active')


check()
subprocess.check_call(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm', '--network', 'none',
    '--memory=128m', '--memory-swap=192m', '--cpus=0.5',
    '-v', str(stage.parent) + ':/staged:ro,Z', 'value-investment-agent:latest', 'python', '-c',
    'from pathlib import Path; compile(Path("/staged/filing_extract.py").read_bytes(),"filing_extract.py","exec")'])
backup = Path(tempfile.mkdtemp(prefix='before-summary-v15-', dir=root / 'exports'))
shutil.copy2(live, backup / live.name)
temporary = live.with_name('.summary-v15.py')
shutil.copy2(stage, temporary)
check()
temporary.replace(live)
print(json.dumps({'backup': str(backup), 'sha256': hashlib.sha256(live.read_bytes()).hexdigest()}))
