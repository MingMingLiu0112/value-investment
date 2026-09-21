"""Guarded single-module deployment of distinct provider indicator scopes."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
live = root / 'src/value_investment_agent/adapters.py'
stage = root / 'exports/market-deploy/roe_adapters.py'
expected = '195a94b9fb49efbf47b254b4efbf1d70dde378b0795d09cac062f9332d81aab4'


def check():
    state = subprocess.check_output(['systemctl', 'show', 'value-investment-agent-filings.service',
        '-p', 'ActiveState', '--value'], universal_newlines=True).strip()
    if state != 'inactive' or hashlib.sha256(live.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Service active or production adapter changed')


check()
subprocess.check_call(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm',
    '--network', 'none', '--memory=128m', '--memory-swap=192m', '--cpus=0.5',
    '-v', str(stage.parent) + ':/staged:ro,Z', 'value-investment-agent:latest',
    'python', '-c', 'from pathlib import Path; compile(Path("/staged/roe_adapters.py").read_bytes(),"adapters.py","exec")'])
backup = Path(tempfile.mkdtemp(prefix='before-roe-scope-', dir=root / 'exports'))
shutil.copy2(live, backup / live.name)
temporary = live.with_name('.roe-adapters.py')
shutil.copy2(stage, temporary)
check()
temporary.replace(live)
print(json.dumps({'backup': str(backup), 'sha256': hashlib.sha256(live.read_bytes()).hexdigest()}))
