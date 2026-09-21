"""Install a four-file pinned release under the shared lock with rollback."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone


NAMES = {'tracking_collection.py', 'candidate_tracking.py', 'quote_sessions.py', 'quote_session_collection.py'}


def replace(path, raw, mode):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.session-release-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def pta_pid():
    subprocess.run(['systemctl', 'is-active', '--quiet', 'web-app-pta'], check=True)
    pid = subprocess.check_output(['systemctl', 'show', 'web-app-pta', '-p', 'MainPID', '--value'], text=True).strip()
    if not pid.isdigit() or int(pid) <= 0:
        raise ValueError('PTA is not healthy')
    return pid


def main():
    import fcntl
    root = Path('/opt/value-investment-agent')
    stage = Path(__file__).resolve().parent
    if stage != root / 'deploy-staging/quote-session-20260909':
        raise ValueError('Unexpected deployment stage')
    manifest = json.loads((stage / 'manifest.json').read_text())
    rows = manifest['files']
    if len(rows) != 4 or {row['name'] for row in rows} != NAMES:
        raise ValueError('Unexpected release file set')
    target = root / 'src/value_investment_agent'
    with (root / 'exports/market-screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before_pid = pta_pid()
        memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(memory['MemAvailable'].split()[0]) < 512 * 1024:
            raise ValueError('Insufficient memory for bounded offline probe')
        if shutil.disk_usage(root).free < 64 * 1024 * 1024:
            raise ValueError('Insufficient room for tiny source backup; evidence reserve unchanged')
        original, updated, modes = {}, {}, {}
        for row in rows:
            path = target / row['name']
            original[row['name']] = path.read_bytes() if path.exists() else None
            actual = hashlib.sha256(original[row['name']]).hexdigest() if path.exists() else None
            if actual != row['expected_production_sha256']:
                raise ValueError('Production baseline changed: ' + row['name'])
            raw = (stage / row['name']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['new_sha256']:
                raise ValueError('Stage hash changed: ' + row['name'])
            compile(raw, str(path), 'exec')
            updated[row['name']] = raw
            modes[row['name']] = path.stat().st_mode & 0o777 if path.exists() else 0o644
        backup = stage / 'originals'
        backup.mkdir(exist_ok=False)
        for name, raw in original.items():
            if raw is not None:
                (backup / name).write_bytes(raw)
        changed = []
        try:
            for name, raw in updated.items():
                replace(target / name, raw, modes[name])
                changed.append(name)
            result = subprocess.run(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm', '--pull=never',
                '--network', 'none', '--cpus=0.5', '--memory=384m', '--memory-swap=512m',
                '-e', 'PYTHONPATH=/app/src', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                '-v', str(root / 'src') + ':/app/src:ro', '-v', str(stage) + ':/review:ro',
                '--entrypoint', 'python', 'value-investment-agent:latest', '/review/probe_quote_session_offline.py'],
                check=True, capture_output=True, text=True, timeout=90)
            proof = json.loads(result.stdout)
            if pta_pid() != before_pid:
                raise RuntimeError('PTA identity changed during release')
            for row in rows:
                if hashlib.sha256((target / row['name']).read_bytes()).hexdigest() != row['new_sha256']:
                    raise RuntimeError('Installed source changed during probe')
            receipt = {'installed_at': datetime.now(timezone.utc).isoformat(), 'files': rows,
                       'installed_probe': proof, 'pta_main_pid': before_pid,
                       'production_data_written': False, 'dated_collection_run': False,
                       'calendar_scope': 'SZSE only; other venues remain blocked'}
            (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        except BaseException:
            for name in reversed(changed):
                if original[name] is None:
                    if hashlib.sha256((target / name).read_bytes()).hexdigest() != hashlib.sha256(updated[name]).hexdigest():
                        raise RuntimeError('Changed new file cannot be safely rolled back: ' + name)
                    (target / name).unlink()
                else:
                    replace(target / name, original[name], modes[name])
            raise
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
