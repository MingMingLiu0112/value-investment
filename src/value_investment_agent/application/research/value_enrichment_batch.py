"""Execute a bounded research work queue without creating admitted facts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .value_research_queue import _canonical_hash, _load_bound
from .value_research_priority_v2 import build_value_research_priority_v2
from .value_evidence_enrichment_v1 import enrich_retained_company
from ..product.common import require_inside, write_new_json
from ...infrastructure.filings.official_pdf import download_official_pdf, validate_pdf_original
from ...infrastructure.screening.financial_export_v2 import load_retained_financial_export
from ...infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource
from ...m2_discovery_engine import _point_available_at


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
        budget: int = 2, allow_network: bool = False) -> dict:
    """Only explicit queue selections execute; results never mutate input facts."""
    root = root.resolve()
    require_inside(root, root / 'runtime', 'runtime')
    if type(allow_network) is not bool:
        raise ValueError('Public evidence network permission must be explicit boolean')
    if type(budget) is not int or not 1 <= budget <= 3:
        raise ValueError('Enrichment execution budget must be between one and three')
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
                if row.get('queue_status') == 'SELECTED_FOR_RESEARCH']
    if len({row['symbol'] for row in selected}) != len(selected):
        raise ValueError('Duplicate enrichment selection')
    points, _ = load_retained_financial_export(export, evaluation_at=now)
    output.mkdir(parents=True)
    items = []
    for row in selected[:budget]:
        symbol, period = row['symbol'], row['timing']['financial_period']
        if not isinstance(symbol, str) or not re.fullmatch(r'\d{6}', symbol):
            raise ValueError('Enrichment requires security identity')
        item = {'symbol': symbol, 'state': 'EVIDENCE_ENRICHING',
            'transitions': ['SCREENED', 'EVIDENCE_ENRICHING'], 'formal_eligibility': False}
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
            # Page text remains in the extraction cache, not the small run receipt.
            result['source_extraction'].pop('page_texts', None)
            packet = json.loads(json.dumps(result, default=str, ensure_ascii=False, allow_nan=False))
            result_path = output / (symbol + '.json')
            write_new_json(result_path, packet)
            item.update(state=result['state'], source_url=source.source_url, source_sha256=source.sha256,
                source_reused=reused, extracted_candidates=len(result['candidate_matches']),
                matched_candidates=sum(bool(match['matching_retained_fact_ids']) for match in result['candidate_matches']),
                before=result['before']['quality_status'], after=result['after']['quality_status'],
                debt_scope_status=result['debt_scope']['status'], next_action=result['next_action'],
                result_binding={'path': result_path.relative_to(root).as_posix(),
                    'sha256': hashlib.sha256(result_path.read_bytes()).hexdigest()})
            item['transitions'] += ['ORIGINAL_HASH_VERIFIED', 'CANDIDATES_EXTRACTED', 'QUALITY_REEVALUATED', result['state']]
        except Exception as error:
            # An unavailable issuer cannot suppress another independently selected issuer.
            item.update(state='DATA_UNAVAILABLE', reason=type(error).__name__ + ':' + str(error),
                next_action='REOPEN_WHEN_SOURCE_OR_SCOPE_EVIDENCE_CHANGES_NO_AUTOMATIC_RETRY')
            item['transitions'].append('DATA_UNAVAILABLE')
        items.append(item)
    result = {'schema_version': 'value-enrichment-execution-v1', 'action': 'no_order',
        'started_at': now.isoformat(), 'finished_at': datetime.now(timezone.utc).isoformat(),
        'queue_content_sha256': queue['content_sha256'], 'items': items,
        'attempted_count': len(items), 'unprocessed_selected_count': len(selected) - len(items),
        'status': 'COMPLETED_WITH_GAPS' if any(row['state'] == 'DATA_UNAVAILABLE' for row in items) else 'COMPLETED',
        'scope': 'CANDIDATE_EXTRACTION_AND_REEVALUATION_NOT_FACT_ADMISSION',
        'new_fact_approvals': 0, 'formal_eligibility': False}
    write_new_json(output / 'execution.json', result)
    return result
