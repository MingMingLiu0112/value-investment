"""Deploy reviewed revenue-scope changes only when live hashes still match."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
stage = root / 'exports/market-deploy'
source = root / 'src/value_investment_agent'
names = ['candidate_review.py','quality.py','financial_quality.py','derived_financials.py','adapters.py','cli.py']
manifest = json.loads((stage / 'before-scope-manifest.json').read_text(encoding='utf-8-sig'))
for name in names:
    if hashlib.sha256((source / name).read_bytes()).hexdigest() != manifest[name]:
        raise RuntimeError(f'Live source changed: {name}')
    compile((stage / name).read_bytes(), name, 'exec')
backup = Path(tempfile.mkdtemp(prefix='revenue-scope-backup-',dir=root / 'exports'))
for name in names:
    shutil.copy2(source / name, backup / name)
for name in names:
    temporary = source / ('.scope-' + name)
    shutil.copy2(stage / name, temporary)
    temporary.replace(source / name)
print(json.dumps({'backup':str(backup),'deployed':{n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in names}}))
