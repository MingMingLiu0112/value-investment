"""Install two reviewed backup fixes without starting services or a real dump."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from install_parser_release import replace_bytes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old_backup_hash')
    parser.add_argument('old_shell_hash')
    parser.add_argument('new_backup_hash')
    parser.add_argument('new_shell_hash')
    args = parser.parse_args()
    root = Path('/opt/value-investment-agent')
    stage = Path(__file__).resolve().parent
    if stage != root / 'deploy-staging/backup-space-20260909':
        raise ValueError('Unexpected staging directory')
    pairs = [(root / 'src/value_investment_agent/backup.py', stage / 'backup.py', args.old_backup_hash, args.new_backup_hash),
             (root / 'deploy/server/run_update.sh', stage / 'run_update.sh', args.old_shell_hash, args.new_shell_hash)]
    with (root / 'exports/market-screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for target, source, old_hash, new_hash in pairs:
            if sha(target) != old_hash or sha(source) != new_hash:
                raise ValueError('File changed: ' + str(target))
        compile((stage / 'backup.py').read_bytes(), 'backup.py', 'exec')
        subprocess.run(['bash', '-n', str(stage / 'run_update.sh')], check=True)
        saved = stage / 'originals'
        saved.mkdir(exist_ok=False)
        for target, _, _, _ in pairs:
            shutil.copy2(target, saved / target.name)
        changed = []
        try:
            for target, source, _, expected in pairs:
                replace_bytes(target, source.read_bytes(), target.stat().st_mode & 0o777)
                changed.append(target)
                if sha(target) != expected:
                    raise ValueError('Installed hash mismatch')
            subprocess.run(['/home/admin/.pyenv/versions/3.11.9/bin/python3',
                str(stage / 'test_daily_update_control_flow.py'), str(pairs[1][0])], check=True, timeout=90)
        except BaseException:
            for target in reversed(changed):
                original = saved / target.name
                replace_bytes(target, original.read_bytes(), original.stat().st_mode & 0o777)
            if any(sha(target) != old for target, _, old, _ in pairs):
                raise RuntimeError('CRITICAL: rollback hash mismatch')
            raise
        receipt = {'installed': True, 'real_backup_started': False, 'services_restarted': False,
                   'files': [{'path': str(t), 'sha256': sha(t)} for t, _, _, _ in pairs]}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
