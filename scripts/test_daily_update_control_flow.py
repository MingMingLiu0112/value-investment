"""Run the real shell script with an in-shell podman stub; no services or DB."""
import argparse
from pathlib import Path
import subprocess


def verify(script):
    stub = r'''
podman() {
  local action='' arg seen=0
  for arg in "$@"; do
    if [[ "$seen" == 1 ]]; then action="$arg"; break; fi
    if [[ "$arg" == value_investment_agent ]]; then seen=1; fi
  done
  printf 'STUB_STAGE=%s\n' "$action"
  case "$action" in
    init-db) return INIT ;;
    update) return UPDATE ;;
    quality) return QUALITY ;;
    backup) return BACKUP ;;
    *) return 99 ;;
  esac
}
'''
    scenarios = [
        ((0, 0, 0, 0), ['init-db', 'update', 'quality', 'backup'], 0, 0),
        ((7, 0, 0, 0), ['init-db', 'backup'], 7, 0),
        ((0, 8, 0, 0), ['init-db', 'update', 'backup'], 8, 0),
        ((0, 0, 9, 0), ['init-db', 'update', 'quality', 'backup'], 9, 0),
        ((0, 0, 0, 6), ['init-db', 'update', 'quality', 'backup'], 0, 6),
        ((0, 8, 0, 6), ['init-db', 'update', 'backup'], 8, 6),
    ]
    for codes, expected, data, backup in scenarios:
        prefix = stub
        for key, value in zip(('INIT', 'UPDATE', 'QUALITY', 'BACKUP'), codes):
            prefix = prefix.replace('return ' + key, 'return ' + str(value))
        result = subprocess.run(['bash', '-c', prefix + '\n' + script],
                                capture_output=True, text=True, timeout=10)
        actual = [s.partition('=')[2] for s in result.stdout.splitlines() if s.startswith('STUB_STAGE=')]
        assert actual == expected, (codes, actual, result.stderr)
        assert result.returncode == (backup or data), (codes, result)
        assert f'daily_update data_exit={data} backup_exit={backup}' in result.stdout
    print('6 real-shell control-flow scenarios passed; podman stubbed; no database writes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path)
    args = parser.parse_args()
    verify(args.script.read_text(encoding='utf-8'))
