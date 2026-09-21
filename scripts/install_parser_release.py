"""Install a pinned four-file release; restore originals if installed replay fails."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


NAMES = {'db.py', 'candidate_review.py', 'filing_extract.py', 'combined_balance.py'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def replace_bytes(path, content, mode):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.parser-release-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def install(bundle, target, backup, verify):
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    files = manifest['files']
    if len(files) != 4 or {r['name'] for r in files} != NAMES:
        raise ValueError('Unexpected release scope')
    for row in files:
        if digest(target / row['name']) != row['before_sha256']:
            raise ValueError('Production changed: ' + row['name'])
        if digest(bundle / row['name']) != row['after_sha256']:
            raise ValueError('Bundle changed: ' + row['name'])
        compile((bundle / row['name']).read_bytes(), row['name'], 'exec')
    backup.mkdir(exist_ok=False)
    for row in files:
        old = target / row['name']
        if old.exists():
            shutil.copy2(old, backup / row['name'])
    shutil.copy2(bundle / 'manifest.json', backup / 'manifest.json')
    changed = []
    try:
        for row in files:
            old = target / row['name']
            mode = old.stat().st_mode & 0o777 if old.exists() else 0o644
            replace_bytes(old, (bundle / row['name']).read_bytes(), mode)
            changed.append(row)
        for row in files:
            if digest(target / row['name']) != row['after_sha256']:
                raise ValueError('Installed hash mismatch')
        verify()
    except BaseException:
        for row in reversed(changed):
            old = target / row['name']
            if row['before_sha256'] is None:
                old.unlink()
            else:
                saved = backup / row['name']
                replace_bytes(old, saved.read_bytes(), saved.stat().st_mode & 0o777)
        if any(digest(target / r['name']) != r['before_sha256'] for r in files):
            raise RuntimeError('CRITICAL: rollback hash mismatch')
        raise
    return {'installed': True, 'installed_replay_passed': True,
            'backup': str(backup), 'files': files, 'database_written': False}


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('backup', type=Path)
    args = parser.parse_args()
    root = Path('/opt/value-investment-agent')
    bundle = args.bundle.resolve()
    backup = args.backup.resolve()
    if bundle.parent != root / 'deploy-staging' or backup.parent != root / 'deploy-staging':
        raise ValueError('Release paths must remain in project staging')
    command = ['podman', '--cgroup-manager=cgroupfs', 'run', '--rm', '--network', 'host',
               '--cpus=0.5', '--memory=384m', '--memory-swap=512m', '-e', 'PYTHONPATH=/app/src',
               '-v', str(root / 'src') + ':/app/src:ro',
               '-v', str(root / 'evidence') + ':/app/evidence:ro',
               '-v', str(bundle) + ':/review:ro', '--entrypoint', 'python',
               'value-investment-agent:latest', '/review/probe_parser_release.py', '/review',
               '/review/candidate-release-plan-20260908T210613655180Z.json',
               '/review/candidate-release-inventory-20260908T210112717345Z.json', '--installed']
    def verify():
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=240)
        print(result.stdout, flush=True)
    with (root / 'exports/market-screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = install(bundle, root / 'src/value_investment_agent', backup, verify)
        (backup / 'receipt.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
