"""Deploy growth verification only against the reviewed production module."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
source = root/'src/value_investment_agent'
stage = root/'exports/market-deploy'
expected = 'd63d7bd5423efcb28b63d163c3c199eab1aa26cb46223b972baf9e91d73bc012'
if hashlib.sha256((source/'candidate_review.py').read_bytes()).hexdigest() != expected:
    raise RuntimeError('Candidate reviewer changed; refusing overwrite')
if (source/'growth_evidence.py').exists():
    raise RuntimeError('Growth module already exists; inspect before replacing')
names = ['growth_evidence.py','candidate_review.py']
for name in names:
    compile((stage/name).read_bytes(),name,'exec')
backup = Path(tempfile.mkdtemp(prefix='growth-gate-backup-',dir=root/'exports'))
shutil.copy2(source/'candidate_review.py',backup/'candidate_review.py')
for name in names:
    temporary = source/('.growth-'+name)
    shutil.copy2(stage/name,temporary)
    temporary.replace(source/name)
print(json.dumps({'backup':str(backup),'hashes':{n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in names}}))
