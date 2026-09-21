"""Guarded single-module deployment of reviewed bank table parsing fixes."""
from pathlib import Path
import hashlib
import json
import shutil
import tempfile

root = Path('/opt/value-investment-agent')
source = root / 'src/value_investment_agent/institution_metrics.py'
stage = root / 'exports/institution-v9.py'
expected = '50bc6123204fe9b297ace98f940236e656d14566a54c5e870b4bf260fb103c04'
if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
    raise RuntimeError('Live institution parser changed; refuse deployment')
compile(stage.read_bytes(), str(source), 'exec')
backup = Path(tempfile.mkdtemp(prefix='institution-v9-backup-', dir=root / 'exports'))
shutil.copy2(source, backup / source.name)
temporary = source.with_name('.institution-v9.py')
shutil.copy2(stage, temporary)
temporary.replace(source)
print(json.dumps({'backup': str(backup), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}))
