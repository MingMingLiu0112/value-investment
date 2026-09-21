"""Record local versions and a bounded read-only remote baseline for the goal."""
import hashlib
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = ['market.py', 'candidate_tracking.py', 'tracking_collection.py',
         'financial_quality.py', 'quality.py', 'valuation.py', 'reminders.py', 'quote_sessions.py']
REMOTE = '''import hashlib,json,subprocess
from pathlib import Path
from datetime import datetime,timezone
root=Path('/opt/value-investment-agent')
names=['market.py','candidate_tracking.py','tracking_collection.py','financial_quality.py','quality.py','valuation.py','reminders.py','quote_sessions.py']
versions={}
for name in names:
 p=root/'src/value_investment_agent'/name
 versions[name]=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
result={'observed_at':datetime.now(timezone.utc).isoformat(),'source_hashes':versions}
for key,cmd in [('disk',['df','-Pm','/']),('memory',['free','-m']),('services',['systemctl','show','web-app-pta.service','value-investment-agent-market-screen.service','value-investment-agent-filings.service','-p','Id','-p','ActiveState','-p','SubState','-p','MainPID','-p','ExecMainStatus']),('containers',['podman','ps','--format','{{.Names}} {{.Status}}']),('timers',['systemctl','list-timers','value-investment-agent-*','--no-pager'])]:
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
 result[key]={'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
p=root/'exports/latest.json'
result['export_sha256']=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
print(json.dumps(result))
'''


def main():
    now = datetime.now(timezone.utc)
    local = {name: hashlib.sha256((ROOT / 'src/value_investment_agent' / name).read_bytes()).hexdigest()
             for name in FILES}
    key = Path.home() / '.ssh/id_ed25519_value_investment'
    response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                               '-o', 'ProxyCommand=none', '-i', str(key), 'root@47.100.97.88',
                               '/home/admin/.pyenv/versions/3.11.9/bin/python3 -c ' + shlex.quote(REMOTE)],
                              capture_output=True, text=True, encoding='utf-8', timeout=90)
    if response.returncode:
        raise RuntimeError('Remote read-only baseline failed: ' + response.stderr)
    remote = json.loads(response.stdout)
    status = subprocess.run(['git', 'status', '--short', '--untracked-files=no'],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    receipt = json.loads((ROOT / 'runtime/excel-sync-status.json').read_text(encoding='utf-8-sig'))
    workbook = Path(receipt['workbook'])
    result = {'observed_at': now.isoformat(), 'local_source_hashes': local,
              'remote': remote, 'tracked_worktree_status': status.splitlines(),
              'last_excel_receipt': receipt,
              'canonical_workbook_sha256': hashlib.sha256(workbook.read_bytes()).hexdigest(),
              'local_payload_sha256': hashlib.sha256((ROOT / 'runtime/server-export-payload.json').read_bytes()).hexdigest(),
              'new_rule_deployed_to_server': False,
              'limitations': ['Service terminal status is not proof of every child task succeeding',
                              'No database restoration or trading strategy approval performed']}
    target = ROOT / 'runtime' / ('execution-baseline-' + now.strftime('%Y%m%dT%H%M%SZ') + '.json')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'path': str(target), **result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
