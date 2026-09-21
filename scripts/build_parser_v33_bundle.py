"""Build v33 from the installed v32 baseline and a pinned real-PDF case."""
import hashlib
import json
from pathlib import Path
import shutil

from value_investment_agent.filing_extract import ANNUAL_BACKFILL_PARSER_VERSION, extract_candidates


def main():
    root = Path(__file__).resolve().parents[1]
    runtime = root / 'runtime'
    baseline = runtime / 'parser-release-v32-20260909'
    manifest = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
    pdf = runtime / '600496-2025-annual-debt-review.pdf'
    packet = extract_candidates(pdf)
    expected_hash = '7063bee136b03667ca138335ce8ac0950406762e64b707f5771483b239d4fa03'
    if packet['sha256'] != expected_hash:
        raise ValueError('Real PDF changed')
    rows = [r for r in packet['candidates'] if r['field_name'] == 'current_portion_long_term_debt']
    if len(rows) != 1 or rows[0]['value'] != '468249668.22' or rows[0]['page'] != 80:
        raise ValueError('Real PDF regression failed')
    if 'PDF第81页' not in rows[0]['excerpt']:
        raise ValueError('Continuation evidence missing')
    output = runtime / 'parser-release-v33-20260909'
    output.mkdir(exist_ok=False)
    files = []
    for row in manifest['files']:
        name = row['name']
        old = (baseline / name).read_bytes()
        if hashlib.sha256(old).hexdigest() != row['after_sha256']:
            raise ValueError('Baseline changed: ' + name)
        content = ((root / 'src/value_investment_agent' / name).read_bytes()
                   if name == 'filing_extract.py' else old)
        compile(content, name, 'exec')
        (output / name).write_bytes(content)
        files.append({'name': name, 'before_sha256': row['after_sha256'],
                      'after_sha256': hashlib.sha256(content).hexdigest()})
    plan_name = 'candidate-release-plan-20260908T210613655180Z.json'
    plan = json.loads((runtime / plan_name).read_text(encoding='utf-8'))
    plan['parser'] = ANNUAL_BACKFILL_PARSER_VERSION
    (output / plan_name).write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    shutil.copy2(runtime / 'candidate-release-inventory-20260908T210112717345Z.json', output)
    shutil.copy2(root / 'scripts/probe_parser_release.py', output)
    manifest = {'files': files, 'parser': ANNUAL_BACKFILL_PARSER_VERSION,
                'database_written': False, 'regression_cases': [{
                    'path': '/app/evidence/600496/2025-12-31-annual.pdf',
                    'sha256': expected_hash, 'field_name': 'current_portion_long_term_debt',
                    'value': '468249668.22', 'page': 80, 'excerpt_contains': 'PDF第81页'}]}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
