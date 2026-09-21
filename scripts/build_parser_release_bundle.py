"""Build a minimal parser release from inspected production baselines."""
import ast
import hashlib
import json
from pathlib import Path


def replace_function(source, name, replacement):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('Expected exactly one function: ' + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    return ''.join(lines[:node.lineno - 1]) + replacement + '\n' + ''.join(lines[node.end_lineno:])


def function_text(source, name):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('Missing or duplicate function: ' + name)
    return ast.get_source_segment(source, nodes[0])


def build_db(production, local):
    function = function_text(production, 'store_filing_candidates')
    new_function = function_text(local, 'store_filing_candidates')
    expected = function.replace("row['excerpt'][:1000]", 'candidate_evidence_excerpt(row)')
    if ast.dump(ast.parse(expected)) != ast.dump(ast.parse(new_function)):
        raise ValueError('Unexpected candidate store change')
    helper = function_text(local, 'candidate_evidence_excerpt')
    result = replace_function(production, 'store_filing_candidates', helper + '\n\n\n' + new_function)
    compile(result, 'db.py', 'exec')
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'src/value_investment_agent'
    runtime = root / 'runtime'
    output = runtime / 'parser-release-v32-20260909'
    output.mkdir(exist_ok=False)
    baselines = {
        'db.py': runtime / 'production-db-before-v32-20260909.py',
        'candidate_review.py': runtime / 'production-candidate-review-before-v32-20260909.py',
        'filing_extract.py': runtime / 'production-filing-extract-v15-20260909.py',
    }
    files = []
    for name in ['db.py', 'candidate_review.py', 'filing_extract.py', 'combined_balance.py']:
        local = (source / name).read_text(encoding='utf-8')
        if name == 'db.py':
            content = build_db(baselines[name].read_text(encoding='utf-8'), local)
        else:
            content = local
        compile(content, name, 'exec')
        target = output / name
        target.write_text(content, encoding='utf-8', newline='\n')
        files.append({'name': name, 'before_sha256': hashlib.sha256(baselines[name].read_bytes()).hexdigest()
                      if name in baselines else None,
                      'after_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    (output / 'manifest.json').write_text(json.dumps({
        'files': files, 'production_updated': False,
        'existing_evidence_backfilled': False,
        'parser': 'filing-extract-v32-explicit-report-unit'}, indent=2), encoding='utf-8')
    print(str(output))


if __name__ == '__main__':
    main()
