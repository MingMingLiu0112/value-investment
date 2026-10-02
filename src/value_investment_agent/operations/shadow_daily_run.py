"""Persist an isolated actual research attempt; never sign or count a session."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
import shutil

from ..application.product.common import require_inside, sha256_file, write_new_json
from ..application.product.company_research import run_company_research_for_symbol
from .shadow_daily_input import audit_shadow_daily_input, DAG_NODES


def run_isolated_daily_attempt(*, root: Path, output: Path, symbol: str,
                               event_path: Path, event_sha256: str,
                               quote_path: Path | None = None,
                               quote_sha256: str | None = None) -> dict:
    root = root.resolve()
    output = require_inside(root, output, 'isolated daily output')
    if not output.is_relative_to(root / 'runtime') or output.exists():
        raise ValueError('isolated daily output requires a new runtime directory')
    if symbol not in {'000333', '600887', '601088'}:
        raise ValueError('symbol outside authorized scope')
    if bool(quote_path) != bool(quote_sha256):
        raise ValueError('quote requires paired path/hash')
    inputs = {'event': (event_path, event_sha256)}
    if quote_path is not None:
        inputs['quote'] = (quote_path, quote_sha256)
    sources = {}
    for role, (path, digest) in inputs.items():
        source = require_inside(root, path, role)
        if sha256_file(source) != digest:
            raise ValueError(f'{role} input hash mismatch')
        sources[role] = (source, digest)
    # Exclusive directory creation prevents reruns from replacing an old attempt.
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc)
    run_id = 'isolated-daily-' + uuid4().hex
    day = started.astimezone(timezone(timedelta(hours=8))).date().isoformat()
    bindings = {}
    for role, (source, digest) in sources.items():
        target = output / (role + '.json')
        shutil.copyfile(source, target)
        if sha256_file(source) != digest or sha256_file(target) != digest:
            raise ValueError('daily source changed during snapshot')
        bindings[role] = dict(path=target.relative_to(root).as_posix(), sha256=digest,
            observed_at=started.isoformat(), original_path=source.relative_to(root).as_posix(),
            observation_basis='SNAPSHOT_ACQUISITION_ONLY_NOT_ORIGINAL_PUBLICATION')
    result = run_company_research_for_symbol(root=root, symbol=symbol)
    research = result['result']
    if research.get('status') != 'BLOCKED_BY_RESEARCH_SCHEDULER':
        raise ValueError('isolated refusal runner does not yet support an admitted research DAG')
    common = dict(action='no_order', run_id=run_id, session_date=day,
                  generated_at=datetime.now(timezone.utc).isoformat(), orders=[], broker_called=False)
    outputs = {
        'research': dict(**common, result=research, application_receipt=result['receipt'], execution_status='EXECUTED'),
        'model': dict(**common, model_validity='NOT_ESTABLISHED', price_bridge='NOT_ADMITTED',
                      execution_status='NOT_RUN_UPSTREAM_BLOCKED', valuation_result_version=None),
        'decision': dict(**common, suggested_state='NOT_READY', execution_status='NOT_RUN_UPSTREAM_BLOCKED',
                         blockers=research['blockers']),
        'portfolio': dict(**common, portfolio_gate='BLOCKED_PRIVATE_INPUT', position_guidance=None,
                          execution_status='NOT_RUN_UPSTREAM_BLOCKED'),
        'product': dict(**common, symbol=symbol, suggested_state='NOT_READY', position_guidance=None,
                        execution_status='REFUSAL_PROJECTION_ONLY', blockers=research['blockers']),
    }
    for role, value in outputs.items():
        path = output / (role + '.json')
        write_new_json(path, value)
        bindings[role] = dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path),
                              observed_at=common['generated_at'])
    completed = datetime.now(timezone.utc)
    run_receipt = dict(**common, simulation_only=False, mode='ISOLATED_NOT_PRODUCTION',
        started_at=started.isoformat(), completed_at=completed.isoformat(),
        node_sequence=['research'], planned_nodes=list(DAG_NODES),
        skipped_nodes=list(DAG_NODES[1:]), dag_execution_complete=False,
        input_hashes={role: binding['sha256'] for role, binding in bindings.items() if role in inputs},
        output_hashes={role: bindings[role]['sha256'] for role in outputs},
        verified_real_session_count=0)
    receipt_path = output / 'run_receipt.json'
    write_new_json(receipt_path, run_receipt)
    bindings['run_receipt'] = dict(path=receipt_path.relative_to(root).as_posix(),
        sha256=sha256_file(receipt_path), observed_at=completed.isoformat())
    manifest = dict(schema_version='shadow-daily-input-v1', action='no_order',
        session_date=day, generated_at=completed.isoformat(), symbols=[symbol], bindings=bindings)
    manifest_path = output / 'input.json'
    write_new_json(manifest_path, manifest)
    audit = audit_shadow_daily_input(root=root, path=manifest_path,
        expected_sha256=sha256_file(manifest_path), now=datetime.now(timezone.utc))
    write_new_json(output / 'audit.json', audit)
    report = '\n'.join(['# Isolated Daily Research Attempt', '', f'Symbol: {symbol}',
        f'Run: {run_id}', f'Observed: {completed.isoformat()}',
        f'Research: {research["status"]}', 'Decision: NOT_READY',
        'Executed: shared research scheduler; downstream nodes NOT_RUN_UPSTREAM_BLOCKED.',
        'Portfolio guidance: null; no personal input or trade approval inferred.',
        f'Input audit: {audit["input_consistency_status"]}',
        *['- ' + item for item in audit['blockers']], '',
        'Not a production Shadow session; zero real sessions; action=no_order.'])
    with (output / 'report.md').open('x', encoding='utf-8') as handle:
        handle.write(report + '\n')
    return dict(output=str(output), manifest_sha256=sha256_file(manifest_path),
        audit=audit, dag_execution_complete=False, action='no_order')
