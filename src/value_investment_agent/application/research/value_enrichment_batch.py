"""Execute a bounded research work queue without creating admitted facts."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .value_research_queue import _canonical_hash, _load_bound
from .value_research_priority_v2 import build_value_research_priority_v2
from .value_evidence_enrichment_v1 import enrich_retained_company, register_enriched_research
from ..product.common import require_inside, write_new_json
from ...infrastructure.filings.official_pdf import (
    download_official_pdf, validate_pdf_original, is_transient_evidence_failure,
)
from ...infrastructure.screening.financial_export_v2 import load_retained_financial_export
from ...infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource
from ...infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
from ...m2_discovery_engine import _point_available_at


def load_enrichment_research_contexts(*, root: Path, symbols, evaluation_at: datetime):
    """Load registered typed inputs only; never run approvals or select a model."""
    from dataclasses import fields, replace
    from ..product.publication_chain import bound_object
    from ..product.company_research import _package_for_symbol
    from ..product.source_bound_inputs import verify_package_local_sources
    from ..decision.artifact_bundle import ReadOnlyArtifactBundleRepository
    from ...m1_valuation_package_builder import build_descriptor
    from ...research_artifact_repository import InMemoryResearchArtifactRepository
    from ...research_artifact_codecs import ResearchCaseCodec
    from ...research_input import facts_from_payload, build_research_run_spec

    root = root.resolve()
    if evaluation_at.utcoffset() is None:
        raise ValueError('Research context cutoff must include timezone')
    registry_path = root / 'config/current-agent-research.json'
    registry = json.loads(registry_path.read_bytes()) if registry_path.is_file() else {}
    contexts, diagnostics = {}, {}
    for symbol in dict.fromkeys(symbols):
        if not isinstance(symbol, str) or not re.fullmatch(r'\d{6}', symbol):
            raise ValueError('Research context requires security identity')
        try:
            workflows = registry.get('cases', {}).get(symbol, {}).get('workflows', {})
            bindings = {json.dumps(w['workbench'], sort_keys=True): w['workbench']
                        for w in workflows.values() if w.get('workbench')}
            if bindings:
                if len(bindings) != 1:
                    raise ValueError('REGISTERED_WORKBENCH_AMBIGUOUS')
                binding = next(iter(bindings.values()))
                workbench = bound_object(root, binding)
                bundle = workbench['artifact_bundle']
                reader = ReadOnlyArtifactBundleRepository(bundle)
                typed = {}
                for row in bundle['artifacts']:
                    kind = row['identity']['artifact_type']
                    if kind not in {'research_case', 'financial_facts'}:
                        continue
                    stored = reader.load_by_id(row['artifact_id'])
                    ident = stored.envelope.identity
                    if (ident.scope_key != symbol or ident.available_at > evaluation_at
                            or (ident.as_of and ident.as_of > evaluation_at.date()) or kind in typed):
                        raise ValueError('REGISTERED_RESEARCH_IDENTITY_OR_CUTOFF_INVALID')
                    typed[kind] = stored.envelope.payload_object()
                case = ResearchCaseCodec().from_payload(typed['research_case'])
                facts = facts_from_payload(typed['financial_facts'])
                provenance = dict(kind='HASH_BOUND_TYPED_WORKBENCH_ONLY', **binding)
            else:
                package = _package_for_symbol(root, symbol, None)
                payload = json.loads(package.read_bytes())
                verify_package_local_sources(root, payload)
                spec = build_research_run_spec(build_descriptor(payload, root=root))
                if spec.available_at > evaluation_at:
                    raise ValueError('REGISTERED_PACKAGE_UNAVAILABLE_AT_CUTOFF')
                case, facts = spec.research_case, spec.facts
                provenance = dict(kind='REGISTERED_PACKAGE_TYPED_INPUTS',
                    path=package.relative_to(root).as_posix(),
                    sha256=hashlib.sha256(package.read_bytes()).hexdigest())
            if (case.symbol != symbol or facts.symbol != symbol or case.generated_at > evaluation_at
                    or case.as_of > evaluation_at.date() or facts.as_of > evaluation_at.date()):
                raise ValueError('REGISTERED_RESEARCH_IDENTITY_OR_CUTOFF_INVALID')
            # Start a separate current data-check version. Historical scenarios
            # and timing must not become a new valuation approval by inheritance.
            case = replace(case, as_of=evaluation_at.date(),
                financial_summary=dict(case.financial_summary,
                    inherited_research_as_of=case.as_of.isoformat(), enrichment_context=provenance),
                research_status='DATA_CHECK', valuation_status='NOT_ASSESSED')
            updates = dict(as_of=evaluation_at.date(), verified=False)
            names = {f.name for f in fields(facts)}
            updates.update({key: None for key in ('scenario_inputs', 'valuation_timing') if key in names})
            facts = replace(facts, **updates)
            contexts[symbol] = dict(case=case, facts=facts)
            diagnostics[symbol] = dict(status='REGISTERED_CONTEXT_LOADED', source=provenance,
                                       economic_admission='NOT_PROVEN')
        except (ValueError, KeyError, TypeError, OSError) as error:
            diagnostics[symbol] = dict(status='NO_USABLE_REGISTERED_RESEARCH_CONTEXT',
                reason=type(error).__name__ + ':' + str(error))
    return InMemoryResearchArtifactRepository(), contexts, diagnostics


def _original(root, point, *, allow_network):
    digest, url = point.get('sha256'), point.get('source_url')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('OFFICIAL_ORIGINAL_HASH_MISSING')
    parsed = urlparse(url or '')
    if (parsed.scheme != 'https' or parsed.hostname != 'static.cninfo.com.cn'
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not re.fullmatch(r'/finalpage/20\d{2}-\d{2}-\d{2}/\d+\.PDF', parsed.path)):
        raise ValueError('OFFICIAL_ORIGINAL_URL_INVALID')
    cache = require_inside(root, root / 'runtime/value-evidence-enrichment/originals', 'original cache')
    path = cache / (digest + '.pdf')
    meta_path = cache / (digest + '.json')
    if path.exists() or meta_path.exists():
        if not path.is_file() or not meta_path.is_file() or path.stat().st_size > 32 * 1024**2:
            raise ValueError('ORIGINAL_CACHE_INCOMPLETE_OR_OVERSIZED')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('ORIGINAL_CACHE_HASH_MISMATCH')
        meta = json.loads(meta_path.read_bytes())
        if meta.get('sha256') != digest or meta.get('source_url') != url:
            raise ValueError('ORIGINAL_CACHE_PROVENANCE_MISMATCH')
        acquired = datetime.fromisoformat(meta['acquired_at'])
        if acquired.utcoffset() is None or acquired > datetime.now(timezone.utc):
            raise ValueError('ORIGINAL_CACHE_CLOCK_INVALID')
        validate_pdf_original(path)
        return path, acquired, True
    if not allow_network:
        raise ValueError('ORIGINAL_NOT_CACHED_NETWORK_NOT_AUTHORIZED')
    cache.mkdir(parents=True, exist_ok=True)
    # The bounded downloader refuses redirects/HTML and caps originals at 32 MiB.
    # Immutable PDF bytes are retained even if a later parsing step fails.
    actual = download_official_pdf(url, path)
    if actual != digest:
        raise ValueError('DOWNLOADED_ORIGINAL_DIFFERS_FROM_REGISTERED_HASH')
    acquired = datetime.now(timezone.utc)
    write_new_json(meta_path, {'sha256': digest, 'source_url': url, 'acquired_at': acquired.isoformat()})
    return path, acquired, False


def execute_value_enrichment_batch(*, root: Path, queue: dict,
        financial_export_path: Path, financial_export_sha256: str, output_dir: Path,
        budget: int = 2, allow_network: bool = False, retry_token: str | None = None,
        repository=None, research_contexts: dict | None = None) -> dict:
    """Serialize writers; OS releases the lock even when a worker crashes."""
    if research_contexts and repository is None:
        raise ValueError('Research registration requires an explicit artifact repository')
    with ValueEnrichmentProgress(root).locked() as progress:
        return _execute_value_enrichment_batch(root=root, queue=queue,
            financial_export_path=financial_export_path,
            financial_export_sha256=financial_export_sha256, output_dir=output_dir,
            budget=budget, allow_network=allow_network, retry_token=retry_token, progress=progress,
            repository=repository, research_contexts=research_contexts or {})


def _work_key(root, row, points, allow_network, retry_token, context=None):
    from . import value_evidence_enrichment_v1, value_research_priority_v2
    from ...infrastructure.screening import value_evidence_enrichment_v1 as extraction
    from ...infrastructure.screening import evidence_screen_v3
    from ... import financial_quality, filing_extract
    modules = [Path(__file__), Path(value_evidence_enrichment_v1.__file__),
        Path(value_research_priority_v2.__file__), Path(extraction.__file__),
        Path(evidence_screen_v3.__file__), Path(financial_quality.__file__), Path(filing_extract.__file__)]
    company = [p for p in points if p.get('symbol') == row['symbol']]
    originals = {}
    for point in company:
        digest = point.get('sha256')
        if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest):
            for suffix in ('.pdf', '.json'):
                path = root / 'runtime/value-evidence-enrichment/originals' / (digest + suffix)
                if digest + suffix not in originals:
                    originals[digest + suffix] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        source_path = point.get('source_path') or (point.get('metadata') or {}).get('source_path')
        if source_path and str(source_path) not in originals:
            path = require_inside(root, root / source_path, 'retained fact backing')
            originals[str(source_path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    research_context = None
    if context:
        from ...research_artifact_codecs import artifact_payload
        research_context = {key: artifact_payload(context[key])[1] for key in ('case', 'facts')}
        research_context = json.loads(json.dumps(research_context, default=str))
    return _canonical_hash(dict(symbol=row['symbol'], period=row['timing']['financial_period'],
        points=company, originals=originals, network=allow_network, retry_token=retry_token,
        research_context=research_context,
        implementation=hashlib.sha256(b''.join(path.read_bytes() for path in modules)).hexdigest()))


def _execute_value_enrichment_batch(*, root, queue, financial_export_path,
        financial_export_sha256, output_dir, budget, allow_network, retry_token, progress,
        repository, research_contexts):
    """Only explicit queue selections execute; results never mutate input facts."""
    root = root.resolve()
    require_inside(root, root / 'runtime', 'runtime')
    if type(allow_network) is not bool:
        raise ValueError('Public evidence network permission must be explicit boolean')
    if type(budget) is not int or not 1 <= budget <= 3:
        raise ValueError('Enrichment execution budget must be between one and three')
    if retry_token is not None and (not isinstance(retry_token, str) or not 1 <= len(retry_token) <= 128):
        raise ValueError('retry token must be a nonempty bounded audit reason')
    if (queue.get('schema_version') != 'value-research-priority-v2'
            or queue.get('action') != 'no_order' or queue.get('admission') != 'RESEARCH_QUEUE_ONLY'
            or queue.get('content_sha256') != _canonical_hash({k: v for k, v in queue.items() if k != 'content_sha256'})):
        raise ValueError('Enrichment requires an intact research-only priority queue')
    export = require_inside(root / 'runtime', financial_export_path, 'financial export')
    _load_bound(export, financial_export_sha256)
    if (queue['inputs']['financial_export_path'] != export.relative_to(root).as_posix()
            or queue['inputs']['financial_export_sha256'] != financial_export_sha256):
        raise ValueError('Queue and enrichment financial input binding differ')
    inputs = queue['inputs']
    expected = build_value_research_priority_v2(root=root,
        report_path=root / inputs['report_path'], report_sha256=inputs['report_sha256'],
        receipt_path=root / inputs['receipt_path'], receipt_sha256=inputs['receipt_sha256'],
        budget=queue['budget'], enrichment_budget=queue['enrichment_budget'],
        financial_export_path=export, financial_export_sha256=financial_export_sha256,
        previous_path=root / inputs['previous_queue_path'] if inputs.get('previous_queue_path') else None,
        previous_sha256=inputs.get('previous_queue_sha256'))
    if expected != queue:
        raise ValueError('Priority queue differs from replayed bound inputs')
    now = datetime.now(timezone.utc)
    if datetime.fromisoformat(queue['evaluation_at']) > now:
        raise ValueError('Research queue is unavailable at execution cutoff')
    output = require_inside(root / 'runtime', output_dir, 'enrichment output')
    if output.exists():
        raise FileExistsError('Enrichment requires a fresh output directory')
    selected = [row for row in queue['evidence_enrichment_work_queue']
                if queue['enrichment_budget'] > 0
                and row.get('queue_status') in {'SELECTED_FOR_RESEARCH', 'BUDGET_DEFERRED'}]
    if len({row['symbol'] for row in selected}) != len(selected):
        raise ValueError('Duplicate enrichment selection')
    points, _ = load_retained_financial_export(export, evaluation_at=now)
    output.mkdir(parents=True)
    items, skipped, lawful_sources, adopted_fact_ids = [], [], [], []
    for row in selected:
        key = _work_key(root, row, points, allow_network, retry_token, research_contexts.get(row['symbol']))
        previous = progress.load(key)
        if previous and (not previous['retryable'] or previous['attempt'] >= 3
                or datetime.fromisoformat(previous['retry_after']) > now):
            skipped.append({'symbol': row['symbol'], 'reason': 'UNCHANGED_EVIDENCE_OR_RETRY_NOT_DUE',
                'attempt': previous['attempt'], 'last_state': previous.get('last_state'),
                'next_action': previous.get('next_action')})
            continue
        if len(items) >= budget:
            continue
        symbol, period = row['symbol'], row['timing']['financial_period']
        if not isinstance(symbol, str) or not re.fullmatch(r'\d{6}', symbol):
            raise ValueError('Enrichment requires security identity')
        item = {'symbol': symbol, 'state': 'EVIDENCE_ENRICHING',
            'transitions': ['SCREENED', 'EVIDENCE_ENRICHING'], 'formal_eligibility': False,
            'attempt': previous['attempt'] + 1 if previous else 1, 'retryable': False}
        try:
            candidates = [point for point in points if point.get('symbol') == symbol
                and point.get('source_name') == 'CNINFO statutory disclosure'
                and point.get('period_label') == period and _point_available_at(point, now) is not None]
            sources = {(point.get('sha256'), point.get('source_url')): point for point in candidates}
            if len(sources) != 1:
                raise ValueError('OFFICIAL_ANNUAL_SOURCE_MISSING_OR_AMBIGUOUS')
            point = next(iter(sources.values()))
            path, acquired, reused = _original(root, point, allow_network=allow_network)
            source = RetainedAnnualSource(symbol, period, path.relative_to(root).as_posix(),
                point['sha256'], point['source_url'], acquired.isoformat())
            result = enrich_retained_company(root, source, points,
                evaluation_at=datetime.now(timezone.utc), cache_dir=root / '.tmp/value-enrichment-extraction',
                name=row.get('company_name'))
            if symbol in research_contexts:
                context = research_contexts[symbol]
                result['research_registration'] = register_enriched_research(result,
                    root=root, points=points,
                    repository=repository, case=context['case'], facts=context['facts'],
                    run_id=output.name + ':' + symbol)
            # Page text remains in the extraction cache, not the small run receipt.
            result['source_extraction'].pop('page_texts', None)
            packet = json.loads(json.dumps(result, default=str, ensure_ascii=False, allow_nan=False))
            result_path = output / (symbol + '.json')
            write_new_json(result_path, packet)
            if result.get('adopted_points'):
                lawful_sources.append(packet['source_extraction']['identity']['source'])
                adopted_fact_ids.extend(p['data_point_id'] for p in result['adopted_points'])
            item.update(state=result['state'], source_url=source.source_url, source_sha256=source.sha256,
                source_reused=reused, extracted_candidates=len(result['candidate_matches']),
                matched_candidates=sum(bool(match['matching_retained_fact_ids']) for match in result['candidate_matches']),
                before=result['before']['quality_status'], after=result['after']['quality_status'],
                debt_scope_status=result['debt_scope']['status'], next_action=result['next_action'],
                adopted_fact_ids=[p['data_point_id'] for p in result.get('adopted_points', [])],
                research_registration_status=result.get('research_registration', {}).get('status',
                    'NOT_REQUESTED_NO_RESEARCH_CONTEXT'),
                result_binding={'path': result_path.relative_to(root).as_posix(),
                    'sha256': hashlib.sha256(result_path.read_bytes()).hexdigest()})
            item['transitions'] += ['ORIGINAL_HASH_VERIFIED', 'CANDIDATES_EXTRACTED', 'QUALITY_REEVALUATED', result['state']]
        except Exception as error:
            # An unavailable issuer cannot suppress another independently selected issuer.
            item.update(state='DATA_UNAVAILABLE', reason=type(error).__name__ + ':' + str(error),
                next_action='REOPEN_WHEN_SOURCE_OR_SCOPE_EVIDENCE_CHANGES_NO_AUTOMATIC_RETRY')
            item['transitions'].append('DATA_UNAVAILABLE')
            item['retryable'] = is_transient_evidence_failure(error)
            if item['retryable']:
                item['next_action'] = 'BOUNDED_RETRY_MAX_THREE_ATTEMPTS_WITH_BACKOFF'
        items.append(item)
        # Commit each issuer before the next one; a crash loses at most the
        # in-flight issuer. Source acquisition changes the post-attempt identity.
        checkpoint = output / (symbol + '-attempt.json')
        write_new_json(checkpoint, item)
        progress.save({'key': _work_key(root, row, points, allow_network, retry_token,
                                       research_contexts.get(row['symbol'])),
            'attempt': item['attempt'], 'retryable': item['retryable'],
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'retry_after': (now + timedelta(seconds=60 * 2 ** (item['attempt'] - 1))).isoformat(),
            'execution_binding': {'path': checkpoint.relative_to(root).as_posix(),
                'sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest()}})
    consumption_export = None
    if lawful_sources:
        payload = json.loads(export.read_bytes())
        # Preserve all source facts and their original assurance. The next
        # receipt clock must admit acquisition/review times before consumption.
        declarations = {(s['symbol'], s['period']): s for s in payload.get('value_enrichment_sources', [])}
        declarations.update({(s['symbol'], s['period']): s for s in lawful_sources})
        if len(declarations) > 128:
            raise ValueError('lawful consumption export exceeds 128-source replay budget')
        payload['value_enrichment_sources'] = list(declarations.values())
        adopted_export = output / 'lawful-consumption-financial-export.json'
        write_new_json(adopted_export, payload)
        consumption_export = {'path': adopted_export.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(adopted_export.read_bytes()).hexdigest(),
            'adopted_fact_ids': adopted_fact_ids,
            'requires_receipt_cutoff_after_source_acquisition_and_scope_review': True}
    result = {'schema_version': 'value-enrichment-execution-v1', 'action': 'no_order',
        'started_at': now.isoformat(), 'finished_at': datetime.now(timezone.utc).isoformat(),
        'queue_content_sha256': queue['content_sha256'], 'items': items,
        'attempted_count': len(items), 'unprocessed_selected_count': len(selected) - len(items) - len(skipped),
        'skipped_unchanged': skipped, 'progression': 'DURABLE_EVIDENCE_KEYED_BOUNDED_RETRY',
        'retry_token': retry_token,
        'lawful_consumption_export': consumption_export,
        'status': 'COMPLETED_WITH_GAPS' if (any(row['state'] == 'DATA_UNAVAILABLE' for row in items)
            or any(row.get('last_state') == 'DATA_UNAVAILABLE' for row in skipped)) else 'COMPLETED',
        'scope': 'SOURCE_BOUND_DERIVATION_AND_REEVALUATION_NOT_ECONOMIC_APPROVAL',
        'new_fact_approvals': 0, 'formal_eligibility': False}
    write_new_json(output / 'execution.json', result)
    return result
