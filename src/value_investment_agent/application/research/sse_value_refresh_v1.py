"""Finite public value-research refresh using existing screen, queue and tasks.

This is an application orchestrator, not a scheduler, approval or task store.
Each stage binds existing immutable outputs; one issuer failure cannot stop peers.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from ..product.common import require_inside, write_new_json
from ..portfolio.private_journal_lock import InterProcessLock, LockTimeout
from . import sse_research_pipeline_v1 as pipeline
from ..discovery import sse_main_screening as screen

VERSION = 'sse-value-auto-refresh-v1'


def _now():
    return datetime.now(timezone.utc)


def _selected(queue):
    return [r for key in ('deep_research_priority', 'evidence_enrichment_work_queue')
            for r in queue[key] if r.get('tracking_selected') is True]


def run_value_research_refresh(*, root, output_dir, source_mode='RETAINED',
        allow_network=False, tracking_budget=30, enrichment_batches=1,
        comparison_batches=1, operating_budget=0, cancelled=None, on_stage=None):
    """One explicit finite invocation. Reads never invoke this operation.

    RETAINED does not claim a fresh quote. Model calls require a nonzero explicit
    operating budget AND the existing provider authorization/daily spending cap.
    Cancellation is cooperative between stages; native task cancellation remains
    owned by its existing service. No timer, account or order interface is used.
    """
    from .value_enrichment_batch import reobserve_registered_public_adoptions
    root = Path(root).resolve()
    if source_mode not in {'RETAINED', 'FRESH', 'FINANCIAL'}:
        raise ValueError('UNKNOWN_PUBLIC_SOURCE_MODE')
    for value, lower, upper in ((tracking_budget, 1, 100), (enrichment_batches, 0, 10),
                                (comparison_batches, 1, 10), (operating_budget, 0, 3)):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError('FINITE_VALUE_RESEARCH_BUDGET_REQUIRED')
    if type(allow_network) is not bool or (source_mode != 'RETAINED' and not allow_network):
        raise ValueError('EXPLICIT_PUBLIC_NETWORK_AUTHORIZATION_REQUIRED')
    output = require_inside(root / 'runtime', Path(output_dir).resolve(), 'value refresh output')
    if output.exists():
        raise FileExistsError('FRESH_REFRESH_OUTPUT_REQUIRED')
    output.mkdir(parents=True)
    started_at = _now().isoformat()
    events, batches, reobservations, research = [], [], [], []
    latest = None
    status, stop_reason = 'PARTIAL', None

    def event(stage, state, **data):
        value = dict(stage=stage, state=state, at=_now().isoformat(), **data)
        events.append(value)
        if on_stage is not None:
            on_stage(dict(value))

    def check_cancel():
        if cancelled is not None and cancelled():
            raise InterruptedError('PUBLIC_RESEARCH_CANCELLED_BETWEEN_STAGES')

    def prepare(name, count=0):
        check_cancel()
        value = pipeline.prepare_sse_research_run(root=root, manifest_binding=source,
            output_path=output / name / 'queue.json', budget=tracking_budget,
            execution_budget=count, allow_network=allow_network and count > 0)
        return value

    # Reuse the public publication lock family; no private journal is opened.
    try:
        with InterProcessLock(root / '.tmp/sse-value-refresh.lock', timeout_seconds=2):
            check_cancel()
            event('PUBLIC_SOURCE', 'RUNNING', mode=source_mode)
            if source_mode == 'FRESH':
                screen.refresh(root=root, allow_network=allow_network,
                               comparison_batches=comparison_batches)
            elif source_mode == 'FINANCIAL':
                screen.enrich_current(root=root, allow_network=allow_network,
                                      comparison_batches=comparison_batches)
            source = json.loads((root / screen.POINTER).read_bytes())['manifest']
            if source_mode == 'RETAINED':
                previous_source = pipeline._bound(root, source)
                if ('implementation' in previous_source
                        and previous_source['implementation'] != screen.implementation()):
                    # New code replays the same immutable public inputs. Never patch
                    # a saved manifest hash or restamp its original acquisition time.
                    replay_id = output.name + '-source-reobservation'
                    rebound = screen.publish_inputs(root=root, inputs=previous_source['inputs'],
                        output=root/'runtime/sse-main-screening'/replay_id, run_id=replay_id)
                    source = rebound['manifest']
                    event('SOURCE_IMPLEMENTATION_REOBSERVATION', 'SUCCESS', source=source,
                          interpretation='SAME_RETAINED_ORIGINALS_NOT_NEW_MARKET_DATA')
            # prepare performs native verification; a pointer alone never grants validity.
            latest = prepare('initial')
            event('PUBLIC_SOURCE', 'SUCCESS', source=source,
                  freshness='RETAINED_SOURCE_NOT_TODAY_REFRESH' if source_mode == 'RETAINED'
                  else 'NEW_COLLECTION_NOT_QUOTE_OR_FACT_ADMISSION')
            queue = pipeline._bound(root, latest['queue'])
            symbols = [r['symbol'] for r in _selected(queue)]
            check_cancel()
            event('REGISTERED_FACT_REOBSERVATION', 'RUNNING')
            restored = (reobserve_registered_public_adoptions(root=root, symbols=symbols[:30],
                output_dir=output / 'reobservation', budget=3) if symbols else
                dict(status='NO_TRACKED_CANDIDATES', items=[], attempted_count=0))
            reobservations.append(restored)
            event('REGISTERED_FACT_REOBSERVATION', 'FINISHED', result=restored)
            for number in range(enrichment_batches):
                event('PUBLIC_ENRICHMENT', 'RUNNING', batch=number + 1)
                latest = prepare('batch-' + str(number + 1), 3)
                manifest = pipeline._bound(root, latest['manifest'])
                execution = pipeline._bound(root, manifest['execution'])
                batches.append(dict(manifest=latest['manifest'], execution=manifest['execution'],
                    attempted_count=execution['attempted_count'], status=execution['status']))
                event('PUBLIC_ENRICHMENT', 'FINISHED', batch=number + 1,
                      attempted_count=execution['attempted_count'], status=execution['status'])
                if not execution['attempted_count']:
                    stop_reason = 'NO_DUE_EVIDENCE_WORK_RETRY_AND_SOURCE_HISTORY_RETAINED'
                    break
            # Always consume the last batch's observations at a later cutoff.
            # This avoids the old one-invocation lag after successful acquisition.
            latest = prepare('consumption')
            queue = pipeline._bound(root, latest['queue'])
            if operating_budget:
                from .agent_review.operating_sources_v1 import build_operating_source_context
                from .agent_review.operating_task_v2 import LiveOperatingTaskService, implementation
                service = LiveOperatingTaskService(root)
                started_model_tasks = 0
                for row in _selected(queue):
                    check_cancel()
                    if started_model_tasks >= operating_budget:
                        break
                    symbol = row['symbol']
                    executed = False
                    task_id = None
                    # A partial financial packet may support explicit research questions;
                    # this does NOT mean quality/G3/valuation prerequisites have passed.
                    try:
                        context = build_operating_source_context(root=root, symbol=symbol, now=_now())
                        identity = dict(symbol=symbol, source=context['source_binding'],
                                        workflow=implementation())
                        key = 'sse-auto-' + sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                        task = service.create(symbol=symbol, request_key=key, now=_now())
                        task_id = task['task_id']
                        previous_calls = task.get('new_llm_calls', 0)
                        if task['status'] == 'QUEUED':
                            started_model_tasks += 1
                            executed = True
                            task = service.run(task_id)
                        research.append(dict(symbol=symbol, task_id=task['task_id'],
                            status=task['status'], source_binding=context['source_binding'],
                            new_llm_calls=(max(0, task.get('new_llm_calls', 0) - previous_calls) if executed else 0),
                            cumulative_task_llm_calls=task.get('new_llm_calls', 0), reused=not executed,
                            action='no_order', formal_eligibility=False))
                    except (ValueError, KeyError, TypeError, OSError, PermissionError, LockTimeout) as error:
                        event('OPERATING_RESEARCH', 'BLOCKED', symbol=symbol,
                              reason=type(error).__name__ + ':' + str(error)[:220])
                        # Inspect at most the tracked pool; a missing source cannot starve peers.
                        research.append(dict(symbol=symbol, status='BLOCKED',
                            reason=type(error).__name__ + ':' + str(error)[:220],
                            task_id=task_id, new_llm_calls=None if executed else 0,
                            call_accounting='TASK_LEDGER_RECHECK_REQUIRED' if executed else 'NO_TASK_EXECUTION',
                            action='no_order'))
            event('CONSUMPTION', 'SUCCESS', queue=latest['queue'],
                  candidate_count=queue['candidate_count'], tracking_count=queue['tracking_count'])
            # Data/candidate execution is not a completed economic investment workflow.
            status = 'PARTIAL'
    except InterruptedError as error:
        status, stop_reason = 'CANCELLED', str(error)
        event('CYCLE', 'CANCELLED', reason=stop_reason)
    except (ValueError, KeyError, TypeError, OSError, TimeoutError, LockTimeout) as error:
        status, stop_reason = 'FAILED', type(error).__name__ + ':' + str(error)[:300]
        event('CYCLE', 'FAILED', reason=stop_reason)
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
            text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    code_files = {Path(__file__).name: sha256(Path(__file__).read_bytes()).hexdigest(),
                  Path(pipeline.__file__).name: sha256(Path(pipeline.__file__).read_bytes()).hexdigest()}
    receipt = dict(started_at=started_at, code_commit=commit, implementation=code_files,
        new_llm_calls=(None if any(r.get('new_llm_calls') is None for r in research)
                       else sum(r.get('new_llm_calls', 0) for r in research)), schema_version=VERSION, cycle_id=output.name, action='no_order',
        status=status, finished_at=_now().isoformat(), source_mode=source_mode,
        network_authorized=allow_network, tracking_budget=tracking_budget,
        operating_budget=operating_budget, stages=events, batches=batches,
        reobservations=reobservations, operating_research=research,
        latest_research=latest, stop_reason=stop_reason, formal_eligibility=False,
        account_accessed=False, orders_created=0,
        scope='PUBLIC_RESEARCH_PROGRESS_NOT_ECONOMIC_OR_TRADE_APPROVAL')
    write_new_json(output / 'cycle.json', receipt)
    return receipt
