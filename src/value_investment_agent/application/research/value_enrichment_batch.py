"""Execute a bounded research work queue without creating admitted facts."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .value_research_queue import _canonical_hash, _load_bound
from .value_research_priority_v2 import build_value_research_priority_v2
from .value_evidence_enrichment_v1 import (
    PUBLIC_PROFIT_VERSION, enrich_retained_company, register_enriched_research,
)
from ..product.common import require_inside, write_new_json
from ...infrastructure.filings.official_pdf import (
    download_official_pdf, validate_pdf_original, is_transient_evidence_failure,
)
from ...infrastructure.screening.financial_export_v2 import load_retained_financial_export
from ...infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource
from ...infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
from ...infrastructure.screening import value_enrichment_progress
from ...m2_discovery_engine import _point_available_at
from ...infrastructure.screening.sina_income_original import collect_sina_income_original
from ...infrastructure.filings.official_report_acquisition import acquire_official_report


def load_enrichment_research_contexts(*, root: Path, symbols, evaluation_at: datetime,
                                     _reuse=True):
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
    repository = InMemoryResearchArtifactRepository()
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
            if _reuse:
                try:
                    restored = _verified_registered_adoption(root, symbol, evaluation_at,
                                                             repository=repository)
                    if restored:
                        restored_case, restored_facts = restored[1]['case'], restored[1]['facts']
                        contexts[symbol] = dict(
                            case=replace(restored_case, as_of=evaluation_at.date(),
                                research_status='DATA_CHECK', valuation_status='NOT_ASSESSED'),
                            facts=replace(restored_facts, **updates))
                        diagnostics[symbol]['status'] = 'VERIFIED_ENRICHMENT_CONTEXT_RESTORED'
                except (ValueError, KeyError, TypeError, OSError) as error:
                    diagnostics[symbol]['reuse_status'] = 'UNVERIFIED'
                    diagnostics[symbol]['reuse_reason'] = type(error).__name__ + ':' + str(error)
        except (ValueError, KeyError, TypeError, OSError) as error:
            diagnostics[symbol] = dict(status='NO_USABLE_REGISTERED_RESEARCH_CONTEXT',
                reason=type(error).__name__ + ':' + str(error))
    return repository, contexts, diagnostics


def _context_digest(context):
    from ...research_artifact_codecs import artifact_payload
    payload = {key: artifact_payload(context[key])[1] for key in ('case', 'facts')}
    return _canonical_hash(json.loads(json.dumps(payload, default=str)))


def _new_public_candidate_context(result):
    """A deterministic facts-only baseline, not an invented thesis or model choice."""
    from datetime import date
    from ...research_case import ResearchCase
    from ...valuation_models.fcff import FinancialFacts

    symbol = result['symbol']
    stamp = datetime.fromisoformat(result['evaluation_at'])
    source = result['source_extraction']['identity']['source']
    if (not re.fullmatch(r'[0-9]{6}', symbol) or source['symbol'] != symbol
            or stamp.utcoffset() is None or result.get('action') != 'no_order'
            or not result.get('adopted_points')):
        raise ValueError('Automatic candidate context requires source-verified adoption')
    blockers = ['BUSINESS_THESIS_NOT_RESEARCHED', 'MODEL_NOT_SELECTED',
        'ECONOMIC_ASSUMPTIONS_NOT_RESEARCHED', 'FINANCIAL_COMPLETENESS_NOT_PROVEN']
    case = ResearchCase(symbol=symbol, name=result.get('company_name') or symbol,
        as_of=stamp.date(), generated_at=stamp,
        run_id='auto-public-facts:' + symbol + ':' + source['sha256'][:16],
        research_version='auto-public-facts-v1', industry='UNASSESSED',
        investment_path='UNASSESSED', thesis='Business thesis has not been researched.',
        return_driver='UNASSESSED', mispricing_hypothesis='UNASSESSED',
        financial_summary=dict(context_origin='AUTOMATIC_PUBLIC_FACTS_ONLY_V1'),
        positives=[], counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status='PARTIAL', valuation_status='NOT_ASSESSED',
        research_status='DATA_CHECK', blockers=blockers,
        evidence_refs=[dict(id='automatic-official-original', **source)],
        quote_date=None, financial_period=date.fromisoformat(source['period']),
        missing_date_reasons={'quote_date': 'No price admission from financial acquisition'})
    # The legacy carrier supports existing serialization only. Its FCFF fields
    # do not select a model or become issuer-specific research requirements.
    return dict(case=case, facts=FinancialFacts(symbol, stamp.date(), False, [], blockers))


def _retry_baseline_contexts(root, supplied, *, evaluation_at, identity_at):
    from dataclasses import replace

    def normalized(context):
        # Loader restamps the data-check date; provenance retains the registered
        # artifact's original bytes, dates and model inputs.
        return dict(case=replace(context['case'], as_of=identity_at.date()),
                    facts=replace(context['facts'], as_of=identity_at.date()))

    _, baselines, _ = load_enrichment_research_contexts(root=root, symbols=supplied,
        evaluation_at=evaluation_at, _reuse=False)
    result = {}
    for symbol, context in supplied.items():
        if symbol not in baselines:
            raise ValueError('Retry identity requires verified registered baseline: ' + symbol)
        baseline = normalized(baselines[symbol])
        supplied_digest = _context_digest(normalized(context))
        if supplied_digest != _context_digest(baseline):
            restored = _verified_registered_adoption(root, symbol, evaluation_at)
            if restored is None or supplied_digest != _context_digest(normalized(restored[1])):
                raise ValueError('Supplied research context differs from verified registered inputs: ' + symbol)
        result[symbol] = baseline
    return result


def _verified_registered_adoption(root, symbol, evaluation_at, *, repository=None, binding=None):
    """Revalidate lineage and replay registration; checkpoints grant no authority."""
    from .value_evidence_enrichment_v1 import verify_enrichment_adoption
    from ...research_artifact_repository import InMemoryResearchArtifactRepository
    from ...research_artifact_codecs import ResearchCaseCodec
    from ...research_input import facts_from_payload

    if not isinstance(symbol, str) or not re.fullmatch(r'\d{6}', symbol):
        raise ValueError('Research context requires security identity')
    root = root.resolve()
    if binding is None:
        binding = ValueEnrichmentProgress(root).registered_adoption(symbol, cutoff=evaluation_at)
    if binding is None:
        return None
    if binding.get('symbol') != symbol:
        raise ValueError('Registered adoption belongs to another security')
    export_binding = binding['financial_export']
    export = require_inside(root / 'runtime', root / export_binding['path'], 'financial export')
    summary = verify_enrichment_adoption(root=root, result_binding=binding['result_binding'],
        financial_export_path=export, financial_export_sha256=export_binding['sha256'],
        evaluation_at=evaluation_at)
    if not summary['research_inputs_updated'] or not summary['adopted_fact_count']:
        raise ValueError('No verified typed fact adoption')
    result = _load_bound(root / binding['result_binding']['path'], binding['result_binding']['sha256'])
    if (summary['symbol'] != symbol or result['symbol'] != symbol
            or result['source_extraction']['identity']['source']['symbol'] != symbol):
        raise ValueError('Registered adoption result security mismatch')
    stamp = datetime.fromisoformat(result['evaluation_at'])
    if binding.get('baseline_kind') == 'AUTOMATIC_PUBLIC_FACTS_ONLY_V1':
        baseline = _new_public_candidate_context(result)
    else:
        _, contexts, _ = load_enrichment_research_contexts(root=root, symbols=[symbol],
            evaluation_at=stamp, _reuse=False)
        baseline = contexts[symbol]
    if baseline['case'].symbol != symbol or baseline['facts'].symbol != symbol:
        raise ValueError('Registered adoption baseline security mismatch')
    if _context_digest(baseline) != binding['baseline_sha256']:
        raise ValueError('Registered enrichment baseline changed')
    points, _ = load_retained_financial_export(export, evaluation_at=stamp)
    saved = result['research_registration']
    run_id = saved['artifacts'][-1]['envelope']['run_id']
    # Reconstruct the entire registration from the current registered baseline.
    # Check all payload fields, including inherited inputs and approval flags.
    replay = register_enriched_research(result, root=root, points=points,
        repository=InMemoryResearchArtifactRepository(), **baseline, run_id=run_id)
    old = {a['envelope']['identity']['artifact_type']: a for a in saved['artifacts']}
    new = {a['envelope']['identity']['artifact_type']: a for a in replay['artifacts']}
    for kind in ('financial_facts', 'research_case'):
        expected = json.loads(new[kind]['envelope']['canonical_payload'])
        actual = json.loads(old[kind]['envelope']['canonical_payload'])
        if kind == 'research_case':
            link = expected['financial_summary']['value_enrichment']['financial_facts']
            link['artifact_id'] = saved['financial_facts_artifact_id']
            for ref in expected['evidence_refs']:
                if ref.get('id') == 'value-enrichment-financial-facts':
                    ref['artifact_id'] = saved['financial_facts_artifact_id']
        if expected != actual:
            raise ValueError('Registered enrichment differs from baseline replay: ' + kind)
    if repository is not None:
        replay = register_enriched_research(result, root=root, points=points,
            repository=repository, **baseline, run_id=run_id)
    typed = {a['envelope']['identity']['artifact_type']:
             json.loads(a['envelope']['canonical_payload']) for a in replay['artifacts']}
    context = dict(case=ResearchCaseCodec().from_payload(typed['research_case']),
                   facts=facts_from_payload(typed['financial_facts']))
    return summary, context, result


def read_verified_enrichment_progress(root: Path, symbol: str, evaluation_at: datetime) -> dict | None:
    """Bounded facts-only public supplement; never changes published economics."""
    try:
        verified = _verified_registered_adoption(root, symbol, evaluation_at)
        if verified is None:
            return None
        summary, context, result = verified
        keys = ('status', 'symbol', 'adopted_fact_count', 'research_inputs_updated',
                'quality_coverage_before', 'quality_coverage_after', 'formal_eligibility', 'action')
        metrics = [dict(field_name=point['field_name'], value=point['value'],
                        unit=point['unit'], period_label=point['period_label'])
                   for point in result['adopted_points']
                   if point['field_name'] in {'debt_ratio', 'revenue_yoy', 'net_income_yoy', 'net_income'}]
        funding = summary.get('source_financial_funding_scope')
        composition = (funding or {}).get('industrial_financing_composition') or {}
        supplement = ({'source_financial_funding_scope': funding}
                      if funding and (funding.get('required_fields') or funding.get('observations')
                                      or composition.get('status') ==
                                      'SOURCE_BOUND_PARTIAL_COMPOSITION_NOT_COMPLETE_DEBT') else {})
        if context['case'].financial_summary.get('context_origin') == 'AUTOMATIC_PUBLIC_FACTS_ONLY_V1':
            supplement.update(source_original=result['source_extraction']['identity']['source'],
                verification_methods=sorted({p['metadata']['verification_method']
                    for p in result['adopted_points'] if p.get('metadata', {}).get('verification_method')}))
        return dict({key: summary[key] for key in keys}, as_of=result['evaluation_at'],
                    verified_at=evaluation_at.isoformat(), adopted_metrics=metrics,
                    **({'context_origin': context['case'].financial_summary['context_origin']}
                       if context['case'].financial_summary.get('context_origin') else {}),
                    **supplement)
    except (ValueError, KeyError, TypeError, OSError):
        return None


def persist_verified_enrichment_adoption(*, root: Path, result: dict,
        financial_export_path: Path, financial_export_sha256: str, output_dir: Path) -> dict:
    """Persist a single real issuer through the existing result/checkpoint contract.

    Registration is rebuilt from registered inputs, never a caller's approval or
    arbitrary typed payload. This also supports explicit research outside a queue.
    """
    from copy import deepcopy
    from .value_evidence_enrichment_v1 import verify_enrichment_adoption
    root = root.resolve()
    stamp = datetime.fromisoformat(result['evaluation_at'])
    symbol = result['symbol']
    export = require_inside(root / 'runtime', financial_export_path, 'financial export')
    _load_bound(export, financial_export_sha256)
    repository, contexts, _ = load_enrichment_research_contexts(root=root, symbols=[symbol],
        evaluation_at=stamp, _reuse=False)
    automatic_context = symbol not in contexts
    baseline = _new_public_candidate_context(result) if automatic_context else contexts[symbol]
    points, _ = load_retained_financial_export(export, evaluation_at=stamp)
    packet = deepcopy(result)
    output = require_inside(root / 'runtime', output_dir, 'adoption output')
    with ValueEnrichmentProgress(root).locked() as progress:
        if output.exists():
            raise FileExistsError('Adoption requires a fresh output directory')
        packet['research_registration'] = register_enriched_research(packet, root=root,
            points=points, repository=repository, **baseline, run_id=output.name + ':' + symbol)
        packet['source_extraction'].pop('page_texts', None)
        output.mkdir(parents=True)
        result_path = output / (symbol + '.json')
        write_new_json(result_path, json.loads(json.dumps(packet, default=str)))
        result_binding = dict(path=result_path.relative_to(root).as_posix(),
                              sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())
        now = datetime.now(timezone.utc)
        summary = verify_enrichment_adoption(root=root, result_binding=result_binding,
            financial_export_path=export, financial_export_sha256=financial_export_sha256,
            evaluation_at=now)
        if not summary['research_inputs_updated'] or not summary['adopted_fact_count']:
            raise ValueError('No verified typed adoption to persist')
        adoption = dict(symbol=symbol, baseline_sha256=_context_digest(baseline),
            financial_export=dict(path=export.relative_to(root).as_posix(), sha256=financial_export_sha256))
        if automatic_context:
            adoption['baseline_kind'] = 'AUTOMATIC_PUBLIC_FACTS_ONLY_V1'
        attempt = output / (symbol + '-attempt.json')
        write_new_json(attempt, dict(symbol=symbol, state=packet['state'], result_binding=result_binding))
        progress.save(dict(key=_canonical_hash(dict(adoption=adoption, result_binding=result_binding)),
            attempt=1, retryable=False, completed_at=now.isoformat(), retry_after=now.isoformat(),
            registered_adoption=adoption, execution_binding=dict(path=attempt.relative_to(root).as_posix(),
                sha256=hashlib.sha256(attempt.read_bytes()).hexdigest())))
    return dict(summary, result_binding=result_binding)


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
    from . import income_source_correlation
    from ...infrastructure.screening import sina_income_original
    from ...infrastructure.filings import official_report_acquisition
    modules = [Path(__file__), Path(income_source_correlation.__file__), Path(value_evidence_enrichment_v1.__file__),
        Path(sina_income_original.__file__), Path(official_report_acquisition.__file__),
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


def _annual_source_for_row(root, row, points, retained_sources, *, allow_network, output, now):
    """Discover missing public originals; conflicts and damaged caches never fall back."""
    symbol, period = row['symbol'], row['timing']['financial_period']
    candidates = [point for point in points if point.get('symbol') == symbol
        and point.get('source_name') == 'CNINFO statutory disclosure'
        and point.get('period_label') == period and _point_available_at(point, now) is not None]
    sources = {(point.get('sha256'), point.get('source_url')): point for point in candidates}
    retained = retained_sources.get((symbol, period))
    if retained:
        source = RetainedAnnualSource(**retained)
        if source.symbol != symbol or source.period != period:
            raise ValueError('Declared official source identity mismatch')
        if len(sources) > 1 or any(point['sha256'] != source.sha256
                or point['source_url'] != source.source_url for point in sources.values()):
            raise ValueError('Declared official source conflicts with retained points')
        path = require_inside(root, root / source.path, 'declared official original')
        if (not path.is_file() or path.stat().st_size > 32 * 1024**2
                or hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256):
            raise ValueError('Declared official original hash mismatch or unavailable')
        acquired = datetime.fromisoformat(source.available_at)
        if acquired.utcoffset() is None or acquired > now:
            raise ValueError('Declared official original unavailable at cutoff')
        validate_pdf_original(path)
        return source, True, None
    if not sources and allow_network:
        acquisition = acquire_official_report(root=root, symbol=symbol,
            issuer_name=row.get('company_name') or symbol, period=period,
            output_dir=output / (symbol + '-official-original'), allow_network=True)
        source = RetainedAnnualSource(**acquisition['source'])
        if (source.symbol != symbol or source.period != period
                or acquisition.get('action') != 'no_order'
                or acquisition.get('formal_eligibility') is not False
                or acquisition.get('status') != 'ORIGINAL_ACQUIRED_NOT_FACT_ADMITTED'):
            raise ValueError('Discovered original identity or acquisition scope mismatch')
        receipt = output / (symbol + '-official-original') / 'receipt.json'
        return source, False, dict(path=receipt.relative_to(root).as_posix(),
            sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())
    if len(sources) != 1:
        raise ValueError('OFFICIAL_ANNUAL_SOURCE_MISSING_OR_AMBIGUOUS')
    point = next(iter(sources.values()))
    path, acquired, reused = _original(root, point, allow_network=allow_network)
    return RetainedAnnualSource(symbol, period, path.relative_to(root).as_posix(),
        point['sha256'], point['source_url'], acquired.isoformat()), reused, None


def _collect_income_supplement(root, symbol, source, points, export_payload, export_binding, output):
    from copy import deepcopy
    from dataclasses import asdict
    from decimal import Decimal
    from .income_source_correlation import correlate_income_inputs
    from ...financial_quality import _accepted

    descriptor = collect_sina_income_original(root=root, symbol=symbol,
        output_dir=output / (symbol + '-income-original'), allow_network=True)
    clock = datetime.now(timezone.utc)
    correlated = correlate_income_inputs(root, source, descriptor, evaluation_at=clock)
    added = []
    for point in correlated:
        existing = [p for p in points if p.get('symbol') == symbol
            and p.get('field_name') == point['field_name'] and p.get('period_label') == point['period_label']
            and _point_available_at(p, clock) is not None]
        if any(p.get('unit') != 'CNY' or Decimal(str(p['value'])) != Decimal(point['value'])
               or (p.get('metadata') or {}).get('statement_scope') == 'parent' for p in existing):
            raise ValueError('Income correlation conflicts with retained company inputs')
        accepted = [p for p in existing if _accepted(p)]
        if len(accepted) > 1:
            raise ValueError('Income correlation has ambiguous admitted company inputs')
        if not accepted:
            added.append(point)
    if not added:
        return points, None, []
    payload = deepcopy(export_payload)
    payload.setdefault('annual_points', []).extend(added)
    payload['value_enrichment_base_export'] = payload.get('value_enrichment_base_export') or export_binding
    declaration = asdict(source)
    declarations = {(s['symbol'], s['period']): s for s in payload.get('value_enrichment_sources', [])}
    identity = (symbol, source.period)
    if identity in declarations and declarations[identity] != declaration:
        raise ValueError('Income correlation conflicts with retained official source declaration')
    declarations[identity] = declaration
    payload['value_enrichment_sources'] = list(declarations.values())
    path = output / (symbol + '-financial-inputs.json')
    write_new_json(path, payload)
    binding = dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return [*points, *added], binding, added


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
    supplied = dict(path=export.relative_to(root).as_posix(), sha256=financial_export_sha256)
    effective = dict(path=queue['inputs']['financial_export_path'],
                     sha256=queue['inputs']['financial_export_sha256'])
    if supplied != effective and supplied != queue['inputs'].get('base_financial_export'):
        raise ValueError('Queue and enrichment financial input binding differ')
    export = require_inside(root / 'runtime', root / effective['path'], 'effective financial export')
    financial_export_sha256 = effective['sha256']
    export_payload = _load_bound(export, financial_export_sha256)
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
    history = progress.scheduling_history(cutoff=now)
    # Allocate acquisition resources fairly; this does not rank investments.
    # A new exact work key still executes fresh validation, not a cached result.
    def schedule(row):
        count = len(row['evidence_completeness']['accepted_fields'])
        completed = history.get((row['symbol'], row['timing']['financial_period']))
        return (completed is not None,
                completed or datetime.min.replace(tzinfo=timezone.utc), -count)
    selected.sort(key=schedule)
    implementation_sha256 = hashlib.sha256(Path(__file__).read_bytes() +
        Path(value_enrichment_progress.__file__).read_bytes()).hexdigest()
    points, _ = load_retained_financial_export(export, evaluation_at=now)
    retained_sources = {(s['symbol'], s['period']): s for s in export_payload.get('value_enrichment_sources', [])}
    selected_symbols = {row['symbol'] for row in selected}
    work_contexts = _retry_baseline_contexts(root,
        {symbol: context for symbol, context in research_contexts.items() if symbol in selected_symbols},
        evaluation_at=now, identity_at=datetime.fromisoformat(queue['evaluation_at']))
    output.mkdir(parents=True)
    items, skipped, lawful_sources, adopted_fact_ids, income_inputs, public_profit_inputs = [], [], [], [], [], []
    public_info = export_payload.get('public_financial_input') or {}
    public_binding = public_info.get('manifest')
    for row in selected:
        key = _work_key(root, row, points, allow_network, retry_token, work_contexts.get(row['symbol']))
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
            'attempt': previous['attempt'] + 1 if previous else 1, 'retryable': False,
            'scheduling': dict(symbol=symbol, financial_period=period,
                accepted_field_count=len(row['evidence_completeness']['accepted_fields']),
                implementation_sha256=implementation_sha256)}
        adoption = None
        item_points, item_export, added_income = points, effective, []
        try:
            source, reused, acquisition_binding = _annual_source_for_row(root, row, points,
                retained_sources, allow_network=allow_network, output=output, now=now)
            if acquisition_binding:
                item['official_acquisition'] = acquisition_binding
            result = enrich_retained_company(root, source, points,
                evaluation_at=datetime.now(timezone.utc), cache_dir=root / '.tmp/value-enrichment-extraction',
                name=row.get('company_name'), public_summary_binding=public_binding)
            if allow_network and any(p['field_name'] in {'revenue_yoy', 'net_income_yoy'}
                                     for p in result.get('sourced_arithmetic_points', [])):
                try:
                    supplemented, supplement_binding, added = _collect_income_supplement(
                        root, symbol, source, points, export_payload, effective, output)
                    if supplement_binding:
                        updated = enrich_retained_company(root, source, supplemented,
                            evaluation_at=datetime.now(timezone.utc),
                            cache_dir=root / '.tmp/value-enrichment-extraction', name=row.get('company_name'),
                            public_summary_binding=public_binding)
                        result, item_points, item_export, added_income = updated, supplemented, supplement_binding, added
                    item['income_collection'] = dict(status='SOURCE_REPLAYED', added_input_count=len(added))
                except Exception as error:
                    # Independent income failure cannot discard lawful official evidence.
                    item['income_collection'] = dict(status='UNAVAILABLE',
                        reason=type(error).__name__ + ':' + str(error), added_input_count=0)
                    item['retryable'] = is_transient_evidence_failure(error)
            automatic_context = symbol not in research_contexts and bool(result.get('adopted_points'))
            if symbol in research_contexts or automatic_context:
                if automatic_context:
                    from ...research_artifact_repository import InMemoryResearchArtifactRepository
                    context = _new_public_candidate_context(result)
                    baselines = {symbol: context}
                    if repository is None:
                        repository = InMemoryResearchArtifactRepository()
                else:
                    context = research_contexts[symbol]
                    _, baselines, _ = load_enrichment_research_contexts(root=root, symbols=[symbol],
                        evaluation_at=datetime.fromisoformat(result['evaluation_at']), _reuse=False)
                if symbol in baselines:
                    context = baselines[symbol]
                result['research_registration'] = register_enriched_research(result,
                    root=root, points=item_points,
                    repository=repository, case=context['case'], facts=context['facts'],
                    run_id=output.name + ':' + symbol)
                if (symbol in baselines and result['research_registration']['status'] == 'RESEARCH_INPUTS_UPDATED'):
                    adoption = dict(symbol=symbol, baseline_sha256=_context_digest(context),
                        financial_export=item_export)
                    if automatic_context:
                        adoption['baseline_kind'] = 'AUTOMATIC_PUBLIC_FACTS_ONLY_V1'
            # Page text remains in the extraction cache, not the small run receipt.
            result['source_extraction'].pop('page_texts', None)
            packet = json.loads(json.dumps(result, default=str, ensure_ascii=False, allow_nan=False))
            result_path = output / (symbol + '.json')
            write_new_json(result_path, packet)
            if result.get('adopted_points'):
                lawful_sources.append(packet['source_extraction']['identity']['source'])
                adopted_fact_ids.extend(p['data_point_id'] for p in result['adopted_points'])
                income_inputs.extend(added_income)
                public_profit_inputs.extend(p for p in result['adopted_points']
                    if (p.get('metadata') or {}).get('derivation_formula') == PUBLIC_PROFIT_VERSION)
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
            if item_export != effective:
                item['financial_export'] = item_export
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
                                       work_contexts.get(row['symbol'])),
            'attempt': item['attempt'], 'retryable': item['retryable'],
            'scheduling': item['scheduling'],
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'registered_adoption': adoption,
            'retry_after': (now + timedelta(seconds=60 * 2 ** (item['attempt'] - 1))).isoformat(),
            'execution_binding': {'path': checkpoint.relative_to(root).as_posix(),
                'sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest()}})
    consumption_export = None
    if lawful_sources:
        payload = json.loads(export.read_bytes())
        if income_inputs or public_profit_inputs:
            annual = payload.setdefault('annual_points', [])
            identities = {point['data_point_id']: point for point in annual}
            for point in [*income_inputs, *public_profit_inputs]:
                identity = point['data_point_id']
                if identity in identities:
                    if identities[identity] != point:
                        raise ValueError('Conflicting supplemental annual fact identity')
                    continue
                annual.append(point)
                identities[identity] = point
            payload['value_enrichment_base_export'] = payload.get('value_enrichment_base_export') or effective
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
