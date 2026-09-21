"""Deploy the reviewed collector changes only against the inspected live version."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
live = root/'src/value_investment_agent/cli.py'
stage = root/'exports/market-deploy/cli.py'
expected = '683837f9c655408c3f6375828433ed5e284b2996bc45330d890d62a037ff9c81'
if hashlib.sha256(live.read_bytes()).hexdigest() != expected:
    raise RuntimeError('Live CLI changed; refusing overwrite')
compile(stage.read_bytes(),str(live),'exec')
backup = Path(tempfile.mkdtemp(prefix='short-transactions-backup-',dir=root/'exports'))
shutil.copy2(live,backup/live.name)
temporary = live.with_name('.short-transactions-cli.py')
shutil.copy2(stage,temporary)
temporary.replace(live)
print(json.dumps({'backup':str(backup),'sha256':hashlib.sha256(live.read_bytes()).hexdigest()}))
