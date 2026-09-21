"""Switch existing timers using backed-up systemd drop-ins; touch no other project."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path('/opt/value-investment-agent')
stage = root / 'exports/market-deploy/run_candidate_tracking.sh'
destination = root / 'deploy/server/run_candidate_tracking.sh'
subprocess.check_call(['bash', '-n', str(stage)])
units = ('value-investment-agent-market-screen', 'value-investment-agent-industry-refresh')
for unit in units:
    state = subprocess.check_output(['systemctl','show',unit+'.service','-p','ActiveState','--value'],
        universal_newlines=True).strip()
    if state not in ('inactive','failed'):
        raise RuntimeError('Refusing schedule switch during active job: '+unit)
changes = {
    Path('/etc/systemd/system/value-investment-agent-market-screen.service.d/20-daily-tracking.conf'):
        '[Service]\nExecStart=\nExecStart=/bin/bash /opt/value-investment-agent/deploy/server/run_candidate_tracking.sh\n',
    Path('/etc/systemd/system/value-investment-agent-industry-refresh.timer.d/20-monthly-screen.conf'):
        '[Timer]\nOnCalendar=\nOnCalendar=Sat *-*-01..07 10:30:00 Asia/Shanghai\n',
}
subprocess.check_call(['systemd-analyze','calendar','Sat *-*-01..07 10:30:00 Asia/Shanghai'])
backup = Path(tempfile.mkdtemp(prefix='before-tracking-schedule-',dir=str(root/'exports')))
for unit in units:
    for kind in ('service','timer'):
        original = Path('/etc/systemd/system')/(unit+'.'+kind)
        shutil.copy2(str(original),str(backup/original.name))
for path in changes:
    if path.exists():
        raise RuntimeError('Drop-in already exists; inspect before changing: '+str(path))
if destination.exists():
    shutil.copy2(str(destination),str(backup/destination.name))
shutil.copy2(str(stage),str(destination))
destination.chmod(0o755)
for path, content in changes.items():
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content)
subprocess.check_call(['systemctl','daemon-reload'])
subprocess.check_call(['systemctl','restart']+[u+'.timer' for u in units])
print(json.dumps({'backup':str(backup),'daily_tracking':'Mon-Fri 16:30 Asia/Shanghai',
    'monthly_screen':'First Saturday 10:30 Asia/Shanghai','strict_exchange_calendar':False}))
