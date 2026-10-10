"""Apply only the explicit debt-scope gate to a pinned production baseline."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from install_parser_release import replace_bytes


OLD_HASH = '6b01ea1b85a61ef1b9259e51f5a56bd4d19731c0b4b968caf645b6f6ebe3c02c'
OLD = (b"            and 'complete_debt_verified' in metadata\n"
       b"            and metadata['complete_debt_verified'] is not True):")
NEW = b"            and metadata.get('complete_debt_verified') is not True):"


def patched_bytes(original):
    if hashlib.sha256(original).hexdigest() != OLD_HASH or original.count(OLD) != 1:
        raise ValueError('Production baseline changed')
    updated = original.replace(OLD, NEW)
    compile(updated, 'financial_quality.py', 'exec')
    return updated


def pta_pid():
    subprocess.run(['systemctl', 'is-active', '--quiet', 'web-app-pta'], check=True)
    pid = subprocess.check_output(['systemctl', 'show', 'web-app-pta', '-p', 'MainPID', '--value'],
                                  text=True).strip()
    if not pid.isdigit() or int(pid) <= 0:
        raise ValueError('PTA process not healthy')
    return pid


def main():
    import fcntl
    root = Path('/opt/value-investment-agent')
    stage = Path(__file__).resolve().parent
    if stage != root / 'deploy-staging/debt-scope-20260909':
        raise ValueError('Unexpected deployment stage')
    target = root / 'src/value_investment_agent/financial_quality.py'
    with (root / 'exports/market-screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before_pid = pta_pid()
        memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(memory['MemAvailable'].split()[0]) < 512 * 1024:
            raise ValueError('Insufficient available memory for bounded probe')
        # Tiny code release only; the separate 2-GiB database-backup reserve is unchanged.
        if shutil.disk_usage(root).free < 64 * 1024 * 1024:
            raise ValueError('Insufficient room for tiny code backup and receipt')
        original = target.read_bytes()
        updated = patched_bytes(original)
        after_hash = hashlib.sha256(updated).hexdigest()
        backup = stage / 'original'
        backup.mkdir(exist_ok=False)
        shutil.copy2(target, backup / target.name)
        mode = target.stat().st_mode & 0o777
        try:
            replace_bytes(target, updated, mode)
            subprocess.run(['podman', '--cgroup-manager=cgroupfs', 'run', '--rm', '--pull=never',
                '--network', 'none', '--cpus=0.5', '--memory=384m', '--memory-swap=512m',
                '-e', 'PYTHONPATH=/app/src', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                '-v', str(root / 'src') + ':/app/src:ro', '-v', str(stage) + ':/review:ro',
                '--entrypoint', 'python', 'value-investment-agent:latest',
                '/review/probe_debt_scope_gate.py', after_hash], check=True, timeout=90)
            if pta_pid() != before_pid:
                raise RuntimeError('PTA PID changed during probe; investigate before accepting release')
            if hashlib.sha256(target.read_bytes()).hexdigest() != after_hash:
                raise RuntimeError('Installed file changed')
            receipt = {'before_sha256': OLD_HASH, 'after_sha256': after_hash,
                       'installed_probe_passed': True, 'pta_main_pid': before_pid,
                       'database_written': False, 'collection_run': False,
                       'scope': 'Only missing complete_debt_verified gate changed'}
            (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        except BaseException:
            replace_bytes(target, original, mode)
            if hashlib.sha256(target.read_bytes()).hexdigest() != OLD_HASH:
                raise RuntimeError('CRITICAL rollback hash mismatch')
            raise
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
