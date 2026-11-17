"""Read-only registered official capital observations; never current continuity proof."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
from zoneinfo import ZoneInfo

from ..product.common import require_inside
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.official_pdf import validate_pdf_original

REGISTRY = 'config/current-capital-observations-v1.json'
VERSION = 'current-capital-observations-v1'
SOURCE_FIELDS = {'path', 'sha256', 'source_url', 'available_at', 'report_period', 'kind'}
FINANCIAL_REPORT_KINDS = frozenset({'annual', 'interim', 'q1', 'q3'})


def parse_native_capital_observation(pages, *, symbol):
    from ...infrastructure.filings.native_capital_observation_v1 import parse_native_capital_observation as parse
    return parse(pages, symbol=symbol)


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_REGISTRY_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('INVALID_SOURCE_DATE')
    return date.fromisoformat(value)


def _source(root, source, now):
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        raise ValueError('INVALID_SOURCE_FIELDS')
    name = source['path']
    if (not isinstance(name, str) or not name or Path(name).is_absolute()
            or PureWindowsPath(name).drive or '..' in PureWindowsPath(name).parts or '\\' in name):
        raise ValueError('INVALID_SOURCE_PATH')
    path = require_inside(root, root / name, 'capital original')
    if not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256']):
        raise ValueError('INVALID_SOURCE_HASH')
    if not isinstance(source['source_url'], str):
        raise ValueError('INVALID_OFFICIAL_URL')
    match = re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/(\d+)\.PDF', source['source_url'])
    if not match:
        raise ValueError('INVALID_OFFICIAL_URL')
    published, report = _day(match[1]), _day(source['report_period'])
    available = datetime.fromisoformat(source['available_at'])
    if (available.utcoffset() is None or available > now or report > published
            or published > available.astimezone(ZoneInfo('Asia/Shanghai')).date()):
        raise ValueError('INVALID_SOURCE_AVAILABILITY')
    if not isinstance(source['kind'], str) or not source['kind'].strip() or len(source['kind']) > 100:
        raise ValueError('INVALID_SOURCE_KIND')
    return path, 'cninfo:' + match[2]


def _check_bytes(path, digest):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('ORIGINAL_TOO_LARGE')
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('ORIGINAL_HASH_MISMATCH')


def _check_native_formation_dates(parsed, source, now):
    # Only formation/approval dates constrain source availability. Planned record,
    # ex-dividend, payment and effective dates may legitimately lie in the future.
    published = _day(source['source_url'].split('/')[4])
    zone = ZoneInfo('Asia/Shanghai')
    available = datetime.fromisoformat(source['available_at']).astimezone(zone).date()
    cutoff = now.astimezone(zone).date()
    for field in ('observation_date', 'report_approved_date'):
        value = parsed.get(field)
        if value is None or value == 'UNKNOWN':
            continue
        formed = _day(value)
        if formed > published or formed > available or formed > cutoff:
            raise ValueError('NATIVE_FORMATION_DATE_AFTER_SOURCE_AVAILABILITY')


def read_current_capital_observation(root, symbol, now):
    if not isinstance(symbol, str) or not re.fullmatch(r'\d{6}', symbol):
        raise ValueError('INVALID_SYMBOL')
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    root = Path(root).resolve()
    result = dict(schema_version=VERSION, symbol=symbol, status='NOT_STARTED', action='no_order',
        formal_eligibility=False, current_capital_continuity='NOT_PROVEN',
        source_bound_observations=[], source_results=[], current_financial_coverage=dict(
            status='UNKNOWN', report_periods=[], latest_report_period=None))
    try:
        registry = require_inside(root, root / REGISTRY, 'capital registry')
        if not registry.exists():
            return result
        if registry.stat().st_size > 1024 * 1024:
            raise ValueError('REGISTRY_TOO_LARGE')
        raw = registry.read_bytes()
        document = _json(raw)
        if (not isinstance(document, dict) or set(document) != {'schema_version', 'action', 'cases'}
                or document['schema_version'] != VERSION or document['action'] != 'no_order'
                or not isinstance(document['cases'], dict)):
            raise ValueError('INVALID_REGISTRY')
        for key, case in document['cases'].items():
            if (not re.fullmatch(r'\d{6}', key) or not isinstance(case, dict) or set(case) != {'sources'}
                    or not isinstance(case['sources'], list) or not 1 <= len(case['sources']) <= 100):
                raise ValueError('INVALID_REGISTRY_CASE')
        result['registry_binding'] = dict(path=REGISTRY, sha256=hashlib.sha256(raw).hexdigest())
        if symbol not in document['cases']:
            return result
        sources = document['cases'][symbol]['sources']
        # Reject every occurrence of duplicates; never choose the first/last registration.
        identities = []
        for source in sources:
            identities.append({key: source.get(key) for key in ('path', 'sha256', 'source_url')}
                              if isinstance(source, dict) else {})
        accepted = []
        for index, source in enumerate(sources):
            row = dict(source_index=index, status='UNASSESSABLE', source=deepcopy(source))
            try:
                path, source_id = _source(root, source, now)
                if any(any(identities[j].get(key) == source[key] for key in identities[index])
                       for j in range(len(sources)) if j != index):
                    raise ValueError('DUPLICATE_SOURCE')
                _check_bytes(path, source['sha256'])
                validate_pdf_original(path)
                parsed = parse_native_capital_observation(extract_pages(path), symbol=symbol)
                _check_bytes(path, source['sha256'])
                if (not isinstance(parsed, dict) or parsed.get('status') != 'VERIFIED'
                        or parsed.get('symbol') != symbol or parsed.get('report_period') != source['report_period']):
                    raise ValueError('NATIVE_OBSERVATION_NOT_VERIFIED_OR_IDENTITY_MISMATCH')
                # Manifest labels cannot turn an implementation notice into a report.
                if parsed.get('kind') != source['kind']:
                    raise ValueError('NATIVE_OBSERVATION_KIND_MISMATCH')
                _check_native_formation_dates(parsed, source, now)
                row.update(status='VERIFIED', source_id=source_id, observation=deepcopy(parsed))
                accepted.append((row, path, source['sha256']))
            except (ValueError, OSError, TypeError, KeyError, ImportError) as error:
                row['error_code'] = str(error) if isinstance(error, ValueError) else type(error).__name__
            result['source_results'].append(row)
        for row, path, digest in accepted:
            try:
                _check_bytes(path, digest)
            except (ValueError, OSError) as error:
                row.update(status='UNASSESSABLE', error_code='ORIGINAL_CHANGED_DURING_READ')
                row.pop('observation', None)
        if registry.read_bytes() != raw:
            raise ValueError('REGISTRY_CHANGED_DURING_READ')
        good = [row for row in result['source_results'] if row['status'] == 'VERIFIED']
        result['source_bound_observations'] = [deepcopy(row) for row in good]
        result['status'] = 'VERIFIED' if len(good) == len(sources) else 'PARTIAL'
        from ...infrastructure.filings import native_capital_observation_v1 as parser_module
        result['implementation_sha256'] = {
            'source_consumer': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'native_parser': hashlib.sha256(Path(parser_module.__file__).read_bytes()).hexdigest()}
        reports = [row for row in good if row['observation']['kind'] in FINANCIAL_REPORT_KINDS]
        periods = sorted({row['source']['report_period'] for row in reports})
        result['current_financial_coverage'] = dict(status='REGISTERED_SOURCES_ONLY' if reports else 'UNKNOWN',
            report_periods=periods, latest_report_period=periods[-1] if periods else None,
            complete_current_coverage=False)
        return result
    except (ValueError, OSError, TypeError, KeyError) as error:
        result.update(status='UNASSESSABLE', source_bound_observations=[], source_results=[],
                      error_code=str(error) if isinstance(error, ValueError) else type(error).__name__)
        return result
