"""Hash-guarded deployment of tested pending-record deduplication."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
root = Path('/opt/value-investment-agent')
live = root/'src/value_investment_agent/db.py'
stage = root/'exports/market-deploy/db.py'
if hashlib.sha256(live.read_bytes()).hexdigest() != 'af5e55c434e7d4b2c50067ac7ceba4dfff70fae00d246aa6e4f231e8f2d71a2a':
    raise RuntimeError('Live database module changed; refusing overwrite')
compile(stage.read_bytes(),str(live),'exec')
backup = Path(tempfile.mkdtemp(prefix='pending-dedup-backup-',dir=root/'exports'))
shutil.copy2(live,backup/live.name)
temporary = live.with_name('.pending-dedup-db.py')
shutil.copy2(stage,temporary)
temporary.replace(live)
print(json.dumps({'backup':str(backup),'sha256':hashlib.sha256(live.read_bytes()).hexdigest()}))
