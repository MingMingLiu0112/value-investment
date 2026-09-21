"""Publish explicit group-prose parser after guarding the reviewed v9 baseline."""
from pathlib import Path
import hashlib
import json
import shutil
import tempfile

root = Path('/opt/value-investment-agent')
source = root / 'src/value_investment_agent/institution_metrics.py'
stage = root / 'exports/institution-v10.py'
expected = 'b32246b8105ba054204750014117d2fc4d71e8e7277ec053e3cf05db53906525'
if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
    raise RuntimeError('Live parser changed; refuse deployment')
compile(stage.read_bytes(), str(source), 'exec')
backup = Path(tempfile.mkdtemp(prefix='institution-v10-backup-', dir=root / 'exports'))
shutil.copy2(source, backup / source.name)
temporary = source.with_name('.institution-v10.py')
shutil.copy2(stage, temporary)
temporary.replace(source)
print(json.dumps({'backup': str(backup), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}))
