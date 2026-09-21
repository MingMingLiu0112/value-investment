"""Install a hash-pinned single adapter with rollback on installed probe failure."""
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from install_parser_release import replace_bytes

root = Path('/opt/value-investment-agent')
stage = Path(__file__).resolve().parent
if stage != root / 'deploy-staging/cash-units-20260909':
    raise ValueError('Unexpected stage')
old_hash, new_hash = sys.argv[1:]
target = root / 'src/value_investment_agent/adapters.py'
source = stage / 'adapters.py'
with (root / 'exports/market-screen.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if hashlib.sha256(target.read_bytes()).hexdigest() != old_hash or hashlib.sha256(source.read_bytes()).hexdigest() != new_hash:
        raise ValueError('Production or staged file changed')
    compile(source.read_bytes(), 'adapters.py', 'exec')
    backup = stage / 'adapter-original'
    backup.mkdir(exist_ok=False)
    shutil.copy2(target, backup / 'adapters.py')
    mode = target.stat().st_mode & 0o777
    try:
        replace_bytes(target, source.read_bytes(), mode)
        subprocess.run(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm',
            '--network', 'none', '--cpus=0.5', '--memory=384m', '--memory-swap=512m',
            '-e', 'PYTHONPATH=/app/src', '-v', str(root / 'src') + ':/app/src:ro',
            '-v', str(stage) + ':/review:ro', '--entrypoint', 'python',
            'value-investment-agent:latest', '/review/probe_single_cash_adapter.py', new_hash],
            check=True, timeout=90)
    except BaseException:
        replace_bytes(target, (backup / 'adapters.py').read_bytes(), mode)
        if hashlib.sha256(target.read_bytes()).hexdigest() != old_hash:
            raise RuntimeError('CRITICAL rollback hash mismatch')
        raise
    result = {'installed_sha256': new_hash, 'probe_passed': True,
              'network_collection': False, 'database_written': False}
    (stage / 'adapter-receipt.json').write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps(result))
