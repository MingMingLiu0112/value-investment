"""Install only reviewed lock-block changes; refuse any other script drift."""
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from install_parser_release import replace_bytes


def main():
    root = Path('/opt/value-investment-agent')
    stage = Path(__file__).resolve().parent
    if stage != root / 'deploy-staging/backup-space-20260909':
        raise ValueError('Unexpected stage')
    names = ['run_candidate_tracking.sh', 'run_market_screen.sh']
    with (root / 'exports/market-screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in names:
            old = (root / 'deploy/server' / name).read_text(encoding='utf-8')
            new = (stage / name).read_text(encoding='utf-8')
            label = 'candidate tracking' if name == names[0] else 'full market screening'
            replacement = ("flock -w 30 9 || {\n  printf '%s\\n' "
                           "'SKIPPED_LOCK_BUSY: " + label + " did not run' >&2\n  exit 75\n}")
            if old.count('flock -n 9 || exit 0') != 1 or old.replace('flock -n 9 || exit 0', replacement) != new:
                raise ValueError('Unexpected production/staged drift: ' + name)
            subprocess.run(['bash', '-n', str(stage / name)], check=True)
        backup = stage / 'lock-originals'
        backup.mkdir(exist_ok=False)
        for name in names:
            shutil.copy2(root / 'deploy/server' / name, backup / name)
        changed = []
        try:
            for name in names:
                target = root / 'deploy/server' / name
                replace_bytes(target, (stage / name).read_bytes(), target.stat().st_mode & 0o777)
                changed.append(name)
                if target.read_bytes() != (stage / name).read_bytes():
                    raise ValueError('Installed content mismatch')
        except BaseException:
            for name in reversed(changed):
                saved = backup / name
                replace_bytes(root / 'deploy/server' / name, saved.read_bytes(), saved.stat().st_mode & 0o777)
            raise
        receipt = {name: hashlib.sha256((root / 'deploy/server' / name).read_bytes()).hexdigest() for name in names}
        (stage / 'lock-receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
        print(json.dumps({'installed': receipt, 'services_restarted': False}))


if __name__ == '__main__':
    main()
