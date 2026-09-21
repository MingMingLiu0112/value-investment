"""Deploy tested cashflow source selection only while the filing service is idle."""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
live = root / 'src/value_investment_agent/candidate_review.py'
stage = root / 'exports/market-deploy/cashflow_review_ready.py'
expected = '40ec298364aa07ef1c51f1ad55bdaf3d942133208e738caa5a83fe044b612363'


def check():
    state = subprocess.check_output(['systemctl','show','value-investment-agent-filings.service',
        '-p','ActiveState','--value'],universal_newlines=True).strip()
    if state!='inactive' or hashlib.sha256(live.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Service active or production module changed')


check()
subprocess.check_call(['podman','--cgroup-manager=cgroupfs','run','--rm','--network','none',
    '--memory=128m','--memory-swap=192m','--cpus=0.5','-v',str(stage.parent)+':/staged:ro,Z',
    'value-investment-agent:latest','python','-c',
    'from pathlib import Path; compile(Path("/staged/cashflow_review_ready.py").read_bytes(),"candidate_review.py","exec")'])
backup = Path(tempfile.mkdtemp(prefix='before-cashflow-scope-',dir=root/'exports'))
shutil.copy2(live,backup/live.name)
temporary = live.with_name('.cashflow-review.py')
shutil.copy2(stage,temporary)
check()
temporary.replace(live)
print(json.dumps({'backup':str(backup),'sha256':hashlib.sha256(live.read_bytes()).hexdigest()}))
