"""Persist an isolated actual research attempt; never sign or count a session."""
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from uuid import uuid4
import shutil
import json

from ..application.product.common import require_inside, sha256_file, write_new_json
from ..application.product.company_research import run_company_research_for_symbol, ResearchInputValidationError
from .shadow_daily_input import audit_shadow_daily_input, DAG_NODES
from ..pre_decision_eligibility import pre_decision_eligibility_from_payload
from ..investment_decision import DecisionEvidenceBundle, evaluate_investment_decision, MinimalPortfolioPreconditions
from ..application.product.event_followup import read_event_followup
from ..application.product.daily_event_input import project_daily_event_input
from ..application.portfolio.daily_risk_rehearsal import evaluate_daily_risk_rehearsal
from ..presentation.read_models.shadow_daily_review import render_shadow_company_review


def run_isolated_daily_attempt(*, root: Path, output: Path, symbol: str,
                               event_path: Path, event_sha256: str,
                               quote_path: Path | None = None,
                               quote_sha256: str | None = None,
                               package_path: Path | None = None,
                               package_sha256: str | None = None,
                               schedule_request_path: Path | None = None,
                               schedule_request_sha256: str | None = None,
                               followup_path: Path | None = None,
                               followup_sha256: str | None = None,
                               simulated_portfolio_path: Path | None = None,
                               simulated_portfolio_sha256: str | None = None,
                               reviews_path: Path | None = None,
                               reviews_sha256: str | None = None) -> dict:
    root = root.resolve()
    output = require_inside(root, output, 'isolated daily output')
    if not output.is_relative_to(root / 'runtime') or output.exists():
        raise ValueError('isolated daily output requires a new runtime directory')
    if symbol not in {'000333', '600887', '601088'}:
        raise ValueError('symbol outside authorized scope')
    if bool(quote_path) != bool(quote_sha256):
        raise ValueError('quote requires paired path/hash')
    for label, path, digest in (
        ('package', package_path, package_sha256),
        ('schedule request', schedule_request_path, schedule_request_sha256),
        ('event followup', followup_path, followup_sha256),
        ('simulated portfolio', simulated_portfolio_path, simulated_portfolio_sha256),
        ('research reviews', reviews_path, reviews_sha256),
    ):
        if bool(path) != bool(digest):
            raise ValueError(f'{label} requires paired path/hash')
    if schedule_request_path is not None and package_path is None:
        raise ValueError('schedule request requires an explicit source-bound package')
    if reviews_path is not None and package_path is None:
        raise ValueError('research reviews require an explicit source-bound package')
    inputs = {'event': (event_path, event_sha256)}
    if quote_path is not None:
        inputs['quote'] = (quote_path, quote_sha256)
    research_inputs = {}
    for role, path, digest in (
        ('valuation_package', package_path, package_sha256),
        ('schedule_request', schedule_request_path, schedule_request_sha256),
        ('research_reviews', reviews_path, reviews_sha256),
    ):
        if path is not None:
            research_inputs[role] = (path, digest)
    sources = {}
    for role, (path, digest) in (inputs | research_inputs).items():
        source = require_inside(root, path, role)
        if sha256_file(source) != digest:
            raise ValueError(f'{role} input hash mismatch')
        sources[role] = (source, digest)
    event = json.loads(sources['event'][0].read_text(encoding='utf-8'))
    if not isinstance(event, dict) or event.get('symbol') != symbol:
        raise ValueError('event input issuer mismatch or missing symbol')
    followup = None
    if followup_path is not None:
        followup = read_event_followup(root=root,
            cutoff=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date(),
            path=followup_path, expected_sha256=followup_sha256)
        if followup['symbol'] != symbol:
            raise ValueError('event followup issuer mismatch')
        raw_followup = json.loads(require_inside(root, followup_path, 'event followup').read_text(encoding='utf-8'))
        if raw_followup['event_scan']['sha256'] != event_sha256:
            raise ValueError('event followup must bind the acquired event scan')
    # Exclusive directory creation prevents reruns from replacing an old attempt.
    output.mkdir(parents=True, exist_ok=False)
    if followup is not None:
        target = output / 'event_followup.json'
        shutil.copyfile(followup_path, target)
        if sha256_file(target) != followup_sha256:
            raise ValueError('event followup changed during snapshot')
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
    shared_args = dict(root=root, symbol=symbol)
    if package_path is not None:
        shared_args['package_path'] = output / 'valuation_package.json'
        shared_args.update(event_path=output / 'event.json', event_sha256=event_sha256)
        if quote_path is not None:
            shared_args.update(quote_path=output / 'quote.json', quote_sha256=quote_sha256)
    if schedule_request_path is not None:
        request = json.loads((output / 'schedule_request.json').read_text(encoding='utf-8'))
        shared_args.update(schedule_request=request,
                           schedule_request_sha256=schedule_request_sha256)
    if reviews_path is not None:
        shared_args.update(reviews_path=output / 'research_reviews.json', reviews_sha256=reviews_sha256)
    try:
        result = run_company_research_for_symbol(**shared_args)
    except ResearchInputValidationError as error:
        result = dict(result=dict(schema_version='generic-company-research-result-v1',
            symbol=symbol, action='no_order', status='REJECTED_BY_INPUT_VALIDATION',
            blockers=[str(error)], failure_phase='DESCRIPTOR_BEFORE_REOPEN_CONSUMPTION'),
            receipt=dict(action='no_order', status='FAILED_INPUT_VALIDATION',
                         input_sha256={}, reopen_consumed=False))
    if event.get('schema_version') == 'm1-event-scan-v1':
        raw_target = output / 'event-original.json'
        shutil.copyfile(output / 'event.json', raw_target)
        daily_event = project_daily_event_input(root=root, path=raw_target,
            expected_sha256=event_sha256, symbol=symbol, now=datetime.now(timezone.utc))
        # Research uses the original M1 scan; the consumer uses its explicit projection.
        projected = output / 'daily-event.json'
        write_new_json(projected, daily_event)
        bindings['event'].update(path=projected.relative_to(root).as_posix(),
                                 sha256=sha256_file(projected))
    for role in research_inputs:
        if sha256_file(output / (role + '.json')) != bindings[role]['sha256']:
            raise ValueError('shared research input changed during execution')
    research_bindings = {role: bindings.pop(role) for role in research_inputs}
    for role, binding in research_bindings.items():
        binding['consumption_status'] = (
            'BOUND_IN_SHARED_APPLICATION_RECEIPT'
            if result['receipt'].get('input_sha256', {}).get(role) == binding['sha256']
            else 'SNAPSHOTTED_NOT_CONSUMED_BY_SHARED_RESEARCH'
        )
    research = result['result']
    if research.get('action') != 'no_order' or research.get('symbol') != symbol:
        raise ValueError('shared research returned an unsafe or mismatched result')
    common = dict(action='no_order', run_id=run_id, session_date=day,
                  generated_at=datetime.now(timezone.utc).isoformat(), orders=[], broker_called=False)
    outputs = {
        'research': dict(**common, result=research, application_receipt=result['receipt'],
                        research_input_bindings=research_bindings, execution_status='EXECUTED'),
        'model': dict(**common, model_validity='NOT_ESTABLISHED', price_bridge='NOT_ADMITTED',
                      execution_status='NOT_RUN_UPSTREAM_BLOCKED', valuation_result_version=None),
        'decision': dict(**common, suggested_state='NOT_READY', execution_status='NOT_RUN_UPSTREAM_BLOCKED',
                         blockers=research['blockers']),
        'portfolio': dict(**common, portfolio_gate='BLOCKED_PRIVATE_INPUT', position_guidance=None,
                          execution_status='NOT_RUN_UPSTREAM_BLOCKED'),
        'product': dict(**common, symbol=symbol, suggested_state='NOT_READY', position_guidance=None,
                        execution_status='REFUSAL_PROJECTION_ONLY', blockers=research['blockers']),
    }
    executed = ['research']
    if research.get('status') not in {'BLOCKED_BY_RESEARCH_SCHEDULER', 'REJECTED_BY_INPUT_VALIDATION'}:
        if research.get('status') not in {'COMPLETED', 'COMPLETED_WITH_BLOCKERS', 'UNSUPPORTED'}:
            raise ValueError('unknown shared research outcome')
        outputs['model'].update(
            model_validity=research.get('model_validity'), price_bridge=research.get('price_bridge'),
            valuation_result=research.get('valuation'),
            execution_status='SHARED_RESEARCH_OUTPUT_NOT_INDEPENDENT_RECALCULATION',
            source_research_run_id=research.get('run_id'))
        for node, key in (('model_validity', 'model_validity'), ('price_bridge', 'price_bridge')):
            if research.get(key) is not None:
                executed.append(node)
        predecision = research.get('pre_decision_eligibility')
        if predecision is not None:
            typed = pre_decision_eligibility_from_payload(predecision)
            if typed.symbol != symbol or typed.decision_as_of != date.fromisoformat(day):
                outputs['decision']['blockers'] = ['PREDECISION_NOT_SAME_SESSION']
            else:
                # No buy/add intent is inferred from a research result.
                bundle = DecisionEvidenceBundle(bundle_id=run_id, symbol=symbol,
                    decision_as_of=typed.decision_as_of, rule_version='m3-decision-v1',
                    artifact_refs=(), evidence_refs=typed.evidence_refs)
                review = evaluate_investment_decision(predecision=typed, bundle=bundle,
                    decision_as_of=typed.decision_as_of, decision_intent=None)
                outputs['decision'].update(review=review.as_policy(),
                    suggested_state=review.status, blockers=list(review.blockers),
                    execution_status='EXECUTED_SHARED_DECISION_REVIEW')
                executed.append('decision_gate')
        else:
            outputs['decision']['blockers'] = ['PREDECISION_INPUT_NOT_ESTABLISHED']
        outputs['product'].update(suggested_state=outputs['decision']['suggested_state'],
            blockers=outputs['decision']['blockers'], execution_status='RESEARCH_RESULT_PROJECTION_ONLY')
    outputs['product']['source_anchored_explanation'] = followup
    if simulated_portfolio_path is not None:
        assessment = evaluate_daily_risk_rehearsal(root=root,
            path=simulated_portfolio_path, expected_sha256=simulated_portfolio_sha256,
            now=datetime.now(timezone.utc), assessment_id=run_id + '-simulated-risk')
        source = require_inside(root, simulated_portfolio_path, 'simulated portfolio input')
        snapshot = output / 'simulated-portfolio-input.json'
        shutil.copyfile(source, snapshot)
        if sha256_file(snapshot) != simulated_portfolio_sha256:
            raise ValueError('simulated portfolio changed during snapshot')
        assessment['input_path'] = snapshot.relative_to(root).as_posix()
        outputs['portfolio'].update(assessment,
            portfolio_gate='SIMULATED_RISK_ONLY_NOT_PERSONAL_CAPACITY',
            execution_status='EXECUTED_EXISTING_RISK_ENGINE')
        outputs['product']['simulated_portfolio_review'] = assessment
        executed.append('portfolio_gate')
    else:
        preconditions = MinimalPortfolioPreconditions.missing()
        capacity_allowed = preconditions.allows_positive_review()
        outputs['portfolio'].update(
            portfolio_preconditions=preconditions.as_policy(),
            personal_capacity_confirmed=capacity_allowed,
            blockers=list(preconditions.blockers),
            execution_status='EXECUTED_EXISTING_PORTFOLIO_PRECONDITIONS')
        executed.append('portfolio_gate')
    executed.append('product')
    dag_execution_complete = executed == list(DAG_NODES)
    # Output observations must follow every calculation represented in the packet.
    generated_at = datetime.now(timezone.utc).isoformat()
    common['generated_at'] = generated_at
    for role, value in outputs.items():
        value['generated_at'] = generated_at
        path = output / (role + '.json')
        write_new_json(path, value)
        bindings[role] = dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path),
                              observed_at=common['generated_at'])
    completed = datetime.now(timezone.utc)
    run_receipt = dict(**common, simulation_only=simulated_portfolio_path is not None, mode='ISOLATED_NOT_PRODUCTION',
        started_at=started.isoformat(), completed_at=completed.isoformat(),
        node_sequence=executed, planned_nodes=list(DAG_NODES),
        skipped_nodes=[node for node in DAG_NODES if node not in executed],
        dag_execution_complete=dag_execution_complete,
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
    card_path = output / 'company-card.md'
    with card_path.open('x', encoding='utf-8') as handle:
        handle.write(render_shadow_company_review(research=outputs['research'],
            model=outputs['model'], decision=outputs['decision'],
            product=outputs['product'], audit=audit))
    report = '\n'.join(['# Isolated Daily Research Attempt', '', f'Symbol: {symbol}',
        f'Run: {run_id}', f'Observed: {completed.isoformat()}',
        f'Research: {research["status"]}', f'Decision: {outputs["decision"]["suggested_state"]}',
        'Executed: ' + ', '.join(executed),
        'Explicit research inputs: ' + (', '.join(research_bindings) or 'none; default package selection remains subject to shared scheduler'),
        *[f'- {role}: {binding["consumption_status"]}; SHA-256 {binding["sha256"]}'
          for role, binding in research_bindings.items()],
        'Explicit package runs pass quote/event snapshots to shared descriptor validation; scheduler refusal does not consume them. No automatic materiality approval.',
        'Skipped: ' + ', '.join(node for node in DAG_NODES if node not in executed),
        'Portfolio guidance: null; no personal input or trade approval inferred.',
        f'Input audit: {audit["input_consistency_status"]}',
        *['- ' + item for item in audit['blockers']], '',
        'Not a production Shadow session; zero real sessions; action=no_order.'])
    with (output / 'report.md').open('x', encoding='utf-8') as handle:
        handle.write(report + '\n')
    return dict(output=str(output), manifest_sha256=sha256_file(manifest_path),
        audit=audit, company_card=str(card_path),
        dag_execution_complete=dag_execution_complete, action='no_order')
