"""Replay exact official income comparatives against retained structured bytes."""
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ...infrastructure.screening.value_evidence_enrichment_v1 import (
    RetainedAnnualSource, extract_retained_annual,
)

VERSION = 'official-sina-income-input-v1'
PREFIX = 'income-input:'
FIELDS = {'revenue': 'BIZINCO', 'net_income': 'PARENETP'}


def correlate_income_inputs(root: Path, source: RetainedAnnualSource,
                           secondary: dict, *, evaluation_at: datetime) -> list[dict]:
    """Admit amount agreement, never historical availability or economic approval.

    BIZINCO excludes financial income; PARENETP is attributable to the parent.
    Total revenue and total profit are deliberately not interchangeable inputs.
    """
    root = root.resolve()
    if evaluation_at.utcoffset() is None:
        raise ValueError('Income correlation cutoff must be timezone aware')
    clock = datetime.fromisoformat(secondary['acquired_at'])
    if clock.utcoffset() is None or clock > evaluation_at:
        raise ValueError('Income secondary source unavailable at cutoff')
    url = urlparse(secondary['source_url'])
    query = parse_qs(url.query)
    exchange = 'sh' if source.symbol.startswith('6') else 'sz'
    if (url.scheme != 'https' or url.hostname != 'quotes.sina.cn' or url.port
            or url.username or url.password or url.fragment
            or url.path != '/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'
            or query.get('paperCode') != [exchange + source.symbol]
            or query.get('source') != ['lrb'] or query.get('type') != ['0']):
        raise ValueError('Income secondary endpoint/security/scope mismatch')
    path = (root / secondary['path']).resolve()
    if not path.is_relative_to(root) or path.stat().st_size > 2_000_000:
        raise ValueError('Income secondary backing path/budget invalid')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != secondary['sha256']:
        raise ValueError('Income secondary backing hash mismatch')
    receipt_binding = secondary['receipt']
    receipt_path = (root / receipt_binding['path']).resolve()
    if not receipt_path.is_relative_to(root) or receipt_path.stat().st_size > 100_000:
        raise ValueError('Income acquisition receipt path/budget invalid')
    receipt_raw = receipt_path.read_bytes()
    if hashlib.sha256(receipt_raw).hexdigest() != receipt_binding['sha256']:
        raise ValueError('Income acquisition receipt hash mismatch')
    receipt = json.loads(receipt_raw)
    if any(receipt.get(key) != value for key, value in dict(
            url=secondary['source_url'], path=secondary['path'], sha256=secondary['sha256'],
            acquired_at=secondary['acquired_at'], bytes=len(raw), action='no_order').items()):
        raise ValueError('Income descriptor differs from retained acquisition receipt')
    payload = json.loads(raw)
    reports = payload['result']['data']['report_list']
    packet = extract_retained_annual(root, source, evaluation_at=evaluation_at,
                                    cache_dir=root / '.tmp/value-enrichment-extraction', verify_cache=True)
    known_at = max(clock, datetime.fromisoformat(source.available_at)).isoformat()
    points = []
    for field, code in FIELDS.items():
        candidates = [c for c in packet['income_comparatives'] if c['field_name'] == field]
        if len(candidates) != 1:
            raise ValueError('Official income comparative missing or ambiguous: ' + field)
        candidate = candidates[0]
        for period, amount in ((source.period, candidate['value']),
                               (candidate['prior_period_label'], candidate['prior_value'])):
            report = reports[period.replace('-', '')]
            if (report.get('rCurrency') != 'CNY' or report.get('rType') != '\u5408\u5e76\u671f\u672b'
                    or datetime.strptime(report['publish_date'], '%Y%m%d').date() > clock.date()):
                raise ValueError('Income secondary currency/scope/publication mismatch')
            rows = [r for r in report['data'] if r.get('item_field') == code]
            if len(rows) != 1 or rows[0].get('item_source') != 'lrb':
                raise ValueError('Income secondary item missing or ambiguous: ' + code)
            try:
                value = Decimal(str(rows[0]['item_value']))
                official = Decimal(str(amount))
                if not value.is_finite() or not official.is_finite() or value != official:
                    raise ValueError('Income secondary amount does not exactly agree: ' + field)
            except InvalidOperation as error:
                raise ValueError('Invalid income amount') from error
            binding = dict(version=VERSION, official=asdict(source), secondary=secondary,
                           field=field, period=period, value=str(official), comparative=candidate)
            digest = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
            points.append(dict(symbol=source.symbol, field_name=field, period_label=period,
                value=str(official), unit='CNY', data_point_id=PREFIX + digest,
                source_id='official-income:' + source.sha256, source_name='CNINFO statutory disclosure',
                source_url=source.source_url, source_path=source.path, sha256=source.sha256,
                available_at=known_at, fetched_at=known_at, created_at=known_at,
                validation_status='verified', human_reviewed=False,
                metadata=dict(automatic_cross_source_verification=True,
                    verification_method='official_pdf_plus_independent_structured_source',
                    statement_scope='consolidated', currency='CNY', income_source_version=VERSION,
                    income_secondary=secondary, income_official_source=asdict(source),
                    official_page=candidate['page'], official_excerpt=candidate['excerpt'],
                    secondary_item_field=code, secondary_report_period=period,
                    historical_pit_admission='NOT_ADMITTED', economic_approval=False)))
    return points


def reverify_income_inputs(root: Path, source: RetainedAnnualSource, points: list[dict], *,
                          evaluation_at: datetime) -> None:
    """Saved assurance flags are insufficient: regenerate exact source-bound rows."""
    replayed = {}
    for point in points:
        metadata = point.get('metadata') or {}
        if not (str(point.get('data_point_id', '')).startswith(PREFIX)
                or metadata.get('income_source_version') == VERSION):
            continue
        official = metadata.get('income_official_source')
        if official != asdict(source):
            raise ValueError('Correlated income official source mismatch')
        descriptor = metadata.get('income_secondary')
        key = json.dumps(descriptor, sort_keys=True)
        if key not in replayed:
            replayed[key] = {p['data_point_id']: p for p in correlate_income_inputs(
                root, source, descriptor, evaluation_at=evaluation_at)}
        if replayed[key].get(point.get('data_point_id')) != point:
            raise ValueError('Correlated income input differs from source replay')
