"""Bounded sequential annual backfill with a host-shared lock and audit summary."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings


def main():
    import fcntl
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error('limit must be between 1 and 20')
    root = Path(__file__).resolve().parent
    with (root / 'annual-batch.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status':'already_running'}))
            return
        with connect(get_settings().database_url) as db:
            run = begin_run(db,'annual-batch-summary')
        result = execute_batch(root, args.limit)
        with connect(get_settings().database_url) as db:
            end_run(db,run,'failed' if result['failures'] else 'succeeded',result)
        print(json.dumps(result),flush=True)
        if result['failures']:
            raise SystemExit(1)


def execute_batch(root, limit):
    symbols = []
    failures = []
    completed = []
    try:
        selected = subprocess.run([sys.executable,str(root/'select_annual_batch.py'),'--limit',str(limit)],
                                  check=True,capture_output=True,text=True,timeout=60)
        symbols = json.loads(selected.stdout)['symbols']
    except (subprocess.SubprocessError, OSError, ValueError, KeyError) as error:
        return {'selected': symbols, 'completed': completed,
                'failures': [{'stage': 'select_annual_batch.py', 'error': str(error)}]}
    for symbol in symbols:
        for script, extra in [('collect_annual_samples.py',[]),('reextract_annual_samples.py',['--apply'])]:
            try:
                subprocess.run([sys.executable,str(root/script),'--symbols',symbol,*extra],
                               check=True,timeout=180)
            except (subprocess.SubprocessError, OSError) as error:
                failures.append({'symbol':symbol,'stage':script,'error':str(error)})
                break
        else:
            completed.append(symbol)
    try:
        subprocess.run([sys.executable,'-m','value_investment_agent','auto-verify-filings','--limit','100'],
                       check=True,timeout=120)
    except (subprocess.SubprocessError, OSError) as error:
        failures.append({'stage': 'auto-verify-filings', 'error': str(error)})
    return {'selected':symbols,'completed':completed,'failures':failures}


if __name__ == '__main__':
    main()
