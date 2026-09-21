"""Deploy two reviewed modules with live-hash guard and rollback copies."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

root = Path('/opt/value-investment-agent')
source = root / 'src/value_investment_agent'
expected = {
    'valuation.py': 'c29ba446f825ab15e084c6bf671a781f52aa5811e3b453658593afaae7ecf186',
    'quality.py': '7fe8e4513e75ad8c158e778a3a2bd793c10be9d9fb4ca6b598f8f12547438b17',
}
for name, digest in expected.items():
    if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('Live module changed: ' + name)
    compile((root / 'exports' / ('lineage-' + name)).read_bytes(), name, 'exec')
backup = Path(tempfile.mkdtemp(prefix='valuation-lineage-backup-', dir=root / 'exports'))
for name in expected:
    shutil.copy2(source / name, backup / name)
try:
    for name in expected:
        temporary = source / ('.lineage-' + name)
        shutil.copy2(root / 'exports' / ('lineage-' + name), temporary)
        temporary.replace(source / name)
except Exception:
    for name in expected:
        shutil.copy2(backup / name, source / name)
    raise
print(json.dumps({'backup': str(backup), 'deployed': {
    name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in expected}}))
