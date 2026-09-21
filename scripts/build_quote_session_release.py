"""Prepare a minimal release; preserve the production archive helper exactly."""
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = {'tracking_collection.py': '1c8f08a0d20fcce3d1e390e46d25ae774b2ab58502c3e917700d5716439882d6',
       'candidate_tracking.py': 'fd872149462dc69eb568468096edc158aa5571a623b1cbbb046b9c9b68311019',
       'quote_sessions.py': None, 'quote_session_collection.py': None}


def function_source(source, name):
    matches = [node for node in ast.parse(source).body
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError('Expected exactly one archive helper')
    return ast.get_source_segment(source, matches[0])


def main():
    baseline = (ROOT / 'runtime/session-collection-production-baseline-20260909.py').read_bytes()
    if hashlib.sha256(baseline).hexdigest() != OLD['tracking_collection.py']:
        raise ValueError('Downloaded production baseline hash changed')
    stage = ROOT / 'runtime/quote-session-release-20260909'
    stage.mkdir(exist_ok=False)
    files = []
    for name, old_hash in OLD.items():
        source = (ROOT / 'src/value_investment_agent' / name).read_text(encoding='utf-8')
        if name == 'tracking_collection.py':
            current = function_source(source, 'archive_snapshot')
            original = function_source(baseline.decode('utf-8'), 'archive_snapshot')
            if source.count(current) != 1:
                raise ValueError('Ambiguous archive helper replacement')
            source = source.replace(current, original, 1)
            assert function_source(source, 'archive_snapshot') == original
        raw = source.encode('utf-8')
        compile(raw, name, 'exec')
        (stage / name).write_bytes(raw)
        files.append({'name': name, 'expected_production_sha256': old_hash,
                      'new_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    result = {'files': files, 'status': 'prepared_not_deployed',
              'production_archive_helper_preserved': True,
              'required_before_install': ['pinned live baseline comparison',
                  'isolated PostgreSQL shared-document export test',
                  'offline import/quote replay with bounded existing container',
                  'shared lock, rollback and PTA identity verification'],
              'limitations': ['SZSE calendar only; SSE and BSE remain blocked',
                  'No successful production dated quote run yet',
                  'Do not lower evidence disk reserve to make a run pass']}
    (stage / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'path': str(stage), **result}, indent=2))


if __name__ == '__main__':
    main()
