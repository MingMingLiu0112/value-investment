"""Hash-guarded single-file recovery deployment with a retained rollback copy."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
live = root / 'src/value_investment_agent/candidate_review.py'
stage = root / 'exports/market-deploy/candidate_review.py'
expected = 'ffcc1ca935510b3b09f778d7693e70671f0cfd0d09655b242c1a3677dcddbbf8'
if hashlib.sha256(live.read_bytes()).hexdigest() != expected:
    raise RuntimeError('Live candidate review changed; deployment aborted')
compile(stage.read_bytes(), str(live), 'exec')
backup = Path(tempfile.mkdtemp(prefix='reverification-backup-', dir=root / 'exports'))
shutil.copy2(live, backup / live.name)
temporary = live.with_name('.reverification-candidate_review.py')
shutil.copy2(stage, temporary)
temporary.replace(live)
print(json.dumps({'backup':str(backup),'sha256':hashlib.sha256(live.read_bytes()).hexdigest()}))
