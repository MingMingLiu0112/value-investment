"""Connect the verified SSE screen to the existing research/enrichment lifecycle."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import inspect
import json
from uuid import uuid4
from ..portfolio.private_journal_lock import InterProcessLock

from ..product.common import require_inside, write_new_json, write_new_bytes
from .value_research_queue import _load_bound, _canonical_hash
from ...infrastructure.screening.verified_screen_cache_v1 import VerifiedScreenCache

POINTER='.tmp/sse-main-research-current.json'
VERSION='sse-research-tracking-view-v1'
_CACHE=VerifiedScreenCache()


def _binding(root,path):
    return dict(path=path.relative_to(root).as_posix(),sha256=sha256(path.read_bytes()).hexdigest())


def _bound(root,ref):
    if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:raise ValueError('EXACT_RESEARCH_ARTIFACT_BINDING_REQUIRED')
    name=Path(ref['path'])
    if name.is_absolute() or '..' in name.parts:raise ValueError('RELATIVE_RESEARCH_ARTIFACT_REQUIRED')
    path=require_inside(root/'runtime',root/name,'SSE research artifact')
    return _load_bound(path,ref['sha256'])


def implementation():
    from . import sse_research_priority_v1, value_enrichment_batch, value_evidence_enrichment_v1
    from ..discovery import sse_main_screening
    from ... import financial_quality
    from ...domain.discovery import value_candidate_selection
    from ...infrastructure.screening import value_enrichment_progress
    modules=[sse_research_priority_v1,value_enrichment_batch,value_evidence_enrichment_v1,
             sse_main_screening,financial_quality,value_candidate_selection,value_enrichment_progress]
    root=Path(__file__).resolve().parents[4]
    paths=[Path(__file__),*[Path(inspect.getfile(m)) for m in modules]]
    return {p.relative_to(root).as_posix():sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in paths}


def prepare_sse_research_run(*,root,manifest_binding,output_path,budget=30,
                             execution_budget=0,allow_network=False):
    from ..discovery.sse_main_screening import replay_research_inputs,POINTER as SCREEN_POINTER
    from .sse_research_priority_v1 import build_sse_research_priority
    from ...infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
    from .value_enrichment_batch import execute_value_enrichment_batch
    root=Path(root).resolve();now=datetime.now(timezone.utc)
    if type(execution_budget) is not int or not 0<=execution_budget<=3:raise ValueError('EXECUTION_BUDGET_0_TO_3_REQUIRED')
    if type(allow_network) is not bool or (allow_network and not execution_budget):raise ValueError('EXPLICIT_ENRICHMENT_EXECUTION_REQUIRED_FOR_NETWORK')
    current=json.loads((root/SCREEN_POINTER).read_bytes())
    if current['manifest']!=manifest_binding:raise ValueError('CURRENT_SSE_SCREEN_REQUIRED_FOR_TRACKING_PUBLICATION')
    output=require_inside(root/'runtime',Path(output_path).resolve(),'SSE queue output')
    if output.exists():raise FileExistsError('Fresh queue output required')
    folder=output.parent/(output.stem+'-inputs')
    folder.mkdir(parents=True,exist_ok=False)
    pointer=root/POINTER;previous_raw=pointer.read_bytes() if pointer.exists() else None
    previous=None
    if previous_raw:
        prior_manifest=_bound(root,json.loads(previous_raw)['manifest'])
        _bound(root,prior_manifest['queue']);previous=prior_manifest['queue']
    replay=replay_research_inputs(root=root,manifest_binding=manifest_binding,now=now)
    export=dict(replay['financial_payload']);export['points']=replay['points']
    declarations={(s['symbol'],s['period']):s for s in export.get('value_enrichment_sources',[])}
    for source in ValueEnrichmentProgress(root).completed_sources(cutoff=now):
        key=(source['symbol'],source['period'])
        if key in declarations and declarations[key]!=source:raise ValueError('CONFLICTING_COMPLETED_FINANCIAL_SOURCE')
        declarations[key]=source
    export['value_enrichment_sources']=list(declarations.values())
    export_path=folder/'financial-export.json';write_new_bytes(export_path,json.dumps(export,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'))
    export_ref=_binding(root,export_path)
    queue=build_sse_research_priority(root=root,manifest_binding=manifest_binding,
        financial_export_path=export_path,financial_export_sha256=export_ref['sha256'],
        now=now,budget=budget,previous_path=root/previous['path'] if previous else None,
        previous_sha256=previous['sha256'] if previous else None)
    write_new_json(output,queue)
    execution=None
    if execution_budget:
        execution=execute_value_enrichment_batch(root=root,queue=queue,
            financial_export_path=export_path,financial_export_sha256=export_ref['sha256'],
            output_dir=folder/'enrichment',budget=execution_budget,allow_network=allow_network)
    # Reuse the OS-backed lock on this public pointer, never an account path.
    with InterProcessLock(root/'.tmp/sse-research-publication.lock',timeout_seconds=2):
        # Source rotation or a concurrent publisher cannot silently replace a different lineage.
        if json.loads((root/SCREEN_POINTER).read_bytes())['manifest']!=manifest_binding:raise ValueError('SCREEN_CHANGED_DURING_RESEARCH_PREPARATION')
        if (pointer.read_bytes() if pointer.exists() else None)!=previous_raw:raise ValueError('RESEARCH_POINTER_CHANGED_DURING_PREPARATION')
        manifest=dict(schema_version='sse-research-run-v1',action='no_order',generated_at=now.isoformat(),
            source=manifest_binding,queue=_binding(root,output),financial_export=export_ref,
            parent_manifest=json.loads(previous_raw)['manifest'] if previous_raw else None,
            implementation=implementation(),execution=_binding(root,folder/'enrichment/execution.json') if execution else None)
        manifest_path=folder/'manifest.json';write_new_json(manifest_path,manifest)
        if previous_raw:write_new_bytes(folder/'previous-pointer.json',previous_raw)
        pending=pointer.with_name(pointer.name+'.'+uuid4().hex+'.part');pointer.parent.mkdir(exist_ok=True)
        write_new_json(pending,dict(schema_version='sse-research-pointer-v1',action='no_order',manifest=_binding(root,manifest_path)))
        pending.replace(pointer)
    return dict(action='no_order',queue=manifest['queue'],manifest=_binding(root,manifest_path),
        tracking_count=queue.get('tracking_count'),candidate_count=queue.get('candidate_count'),
        execution_status=execution['status'] if execution else 'NOT_REQUESTED')


def _latest_attempts(root,manifest):
    """Read bounded immutable run history, never the private account/task registry."""
    attempts={};seen=set()
    for _ in range(64):
        execution=manifest.get('execution')
        if execution:
            receipt=_bound(root,execution);queue=_bound(root,manifest['queue'])
            if receipt.get('queue_content_sha256')!=queue.get('content_sha256') or receipt.get('action')!='no_order':
                raise ValueError('ENRICHMENT_EXECUTION_QUEUE_BINDING_MISMATCH')
            for row in receipt.get('items',[]):
                if row['symbol'] not in attempts:attempts[row['symbol']]=dict(row,completed_at=receipt['finished_at'])
        parent=manifest.get('parent_manifest')
        if not parent:return attempts
        if parent['sha256'] in seen:raise ValueError('CYCLIC_RESEARCH_HISTORY')
        seen.add(parent['sha256']);manifest=_bound(root,parent)
    return attempts


def read_sse_research_pool(*,root,now):
    from .sse_research_priority_v1 import build_sse_research_priority
    from ..discovery.sse_main_screening import read_screen
    root=Path(root).resolve();history=False;binding=None
    try:
        if now.utcoffset() is None:raise ValueError('AWARE_READ_CUTOFF_REQUIRED')
        pointer=json.loads((root/POINTER).read_bytes())
        if pointer.get('schema_version')!='sse-research-pointer-v1' or pointer.get('action')!='no_order':raise ValueError('INVALID_SSE_RESEARCH_POINTER')
        binding=pointer['manifest'];manifest=_bound(root,binding);history=True
        if manifest['schema_version']!='sse-research-run-v1' or manifest['action']!='no_order':raise ValueError('INVALID_SSE_RESEARCH_MANIFEST')
        if manifest['implementation']!=implementation():raise ValueError('RESEARCH_IMPLEMENTATION_CHANGED_REPLAY_REQUIRED')
        when=datetime.fromisoformat(manifest['generated_at'])
        if when.utcoffset() is None or when>now:raise ValueError('FUTURE_RESEARCH_RUN')
        screen=read_screen(root=root,now=now,limit=1,status='ALL')
        if screen['status']=='UNAVAILABLE' or screen['source_refs'][0]!=manifest['source']:raise ValueError('CURRENT_SCREEN_CHANGED_OR_UNAVAILABLE_HISTORY_RETAINED')
        with _CACHE.lock:
            queue=_CACHE.get(root,binding)
            if queue is None:
                queue=_bound(root,manifest['queue']);inputs=queue['inputs']
                expected=build_sse_research_priority(root=root,manifest_binding=manifest['source'],
                    financial_export_path=root/inputs['financial_export_path'],
                    financial_export_sha256=inputs['financial_export_sha256'],now=datetime.fromisoformat(queue['evaluation_at']),
                    budget=queue['budget'],previous_path=root/inputs['previous_queue_path'] if inputs.get('previous_queue_path') else None,
                    previous_sha256=inputs.get('previous_queue_sha256'))
                if queue!=expected:raise ValueError('RESEARCH_QUEUE_REPLAY_MISMATCH')
                _CACHE.put(root,binding,queue)
        rows=[r for r in queue['deep_research_priority']+queue['evidence_enrichment_work_queue'] if r.get('tracking_selected') is True]
        items=[];attempts=_latest_attempts(root,manifest)
        for row in rows:
            completion=row['evidence_completeness']
            attempt=attempts.get(row['symbol'])
            gaps=list(row['gaps'])
            if attempt and attempt.get('reason'):gaps.insert(0,'最近补证：'+attempt['reason'])
            next_action=('进入经营与反证研究' if row in queue['deep_research_priority'] else '自动取得并核验官方年度原件；不跳过财务质量')
            stage='DEEP_RESEARCH_PENDING' if row in queue['deep_research_priority'] else 'EVIDENCE_REVIEW_PENDING'
            if attempt:
                stage=attempt['state'];next_action=attempt.get('next_action',next_action)
            items.append(dict(symbol=row['symbol'],name=row['company_name'],industry=row.get('industry') or '未提供',
                channels=row['channels'],reason='；'.join(row['screening_reasons']),
                first_seen_at=row['first_seen_at'],tracking_status=stage,
                financial_period=row['timing']['financial_period'],accepted_fields=len(completion['accepted_fields']),
                required_fields=len(completion['required_fields']),next_action=next_action,gaps=gaps))
        return dict(schema_version=VERSION,action='no_order',status='AVAILABLE',scope='SSE_MAIN_A_ONLY',
            source_status=screen['source_status'],source_available_at=queue['source_available_at'],
            generated_at=manifest['generated_at'],total_candidates=queue['candidate_count'],tracking_count=len(items),
            items=items,blockers=['RESEARCH_TRACKING_NOT_BUY_ADVICE','LONG_TERM_BUSINESS_QUALITY_NOT_YET_VERIFIED'],
            queue_binding=manifest['queue'],history_available=bool(manifest.get('parent_manifest')))
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
        return dict(schema_version=VERSION,action='no_order',status='UNAVAILABLE',scope='SSE_MAIN_A_ONLY',
            source_status='SOURCE_REVALIDATION_FAILED',source_available_at=None,generated_at=None,
            total_candidates=None,tracking_count=None,items=[],blockers=[str(error)[:180]],queue_binding=None,history_available=history)
