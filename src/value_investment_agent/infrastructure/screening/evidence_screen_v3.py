"""Versioned screening repair; historical M2 engines retain their exact bytes."""
from collections import defaultdict
from dataclasses import replace

from ... import m2_discovery_engine as legacy
from ...financial_quality import GENERAL_FIELDS, _accepted, evaluate_financial_quality as historical_quality
from ...m2_opportunity_discovery import coverage_signature

VERSION = 'm2-evidence-screen-v3'


def selected_period(points):
    relevant = [p for p in points if p['field_name'] in GENERAL_FIELDS]
    annual = [p for p in relevant if str(p['period_label']).endswith('-12-31')]
    return max((str(p['period_label']) for p in annual or relevant), default='')


def evaluate_financial_quality(symbol, name, sector, points, *, evaluation_date=None):
    period = selected_period(points)
    selected = [p for p in points if p['field_name'] not in GENERAL_FIELDS
                or str(p['period_label']) == period]
    result = historical_quality(symbol, name, sector, selected, evaluation_date=evaluation_date)
    if result.model_type != 'general_enterprise':
        return result
    details = dict(result.calculation_details, period=period or None,
                   period_selection_version=VERSION)
    if result.total_score is None and 'accepted_fields' in details:
        missing = [f for f in GENERAL_FIELDS if f not in details['accepted_fields']]
        older = sorted({p['field_name'] for p in points if p['field_name'] in missing
                        and str(p['period_label']) != period and _accepted(p)})
        details.update(missing_fields=missing, older_period_fields_excluded=older)
        result = replace(result, quality_status='待同报告期补证' if older else result.quality_status)
    return replace(result, calculation_details=details)


def build_discovery_receipt(**kwargs):
    """Keep thresholds and candidates; version evidence-gap accounting separately."""
    grouped = defaultdict(list)
    for point in kwargs['financial_points']:
        if legacy._point_available_at(point, kwargs['generated_at']) is not None:
            grouped[point['symbol']].append(point)
    selected = []
    for rows in grouped.values():
        period = selected_period(rows)
        selected.extend(p for p in rows if p['field_name'] not in GENERAL_FIELDS
                        or str(p['period_label']) == period)
    receipt = legacy.build_discovery_receipt(**dict(kwargs, financial_points=selected))
    official = {row.symbol: row for row in receipt.universe.records}
    policy = kwargs.get('policy') or legacy.M2ScreeningPolicy()
    quotes, _ = legacy.merge_market_snapshots(
        legacy.parse_tencent_board(kwargs['tencent_payload']),
        legacy.parse_sina_industry(kwargs['sina_payload']), official,
        quote_date=kwargs['quote_date'], price_tolerance=policy.price_tolerance)
    financial = legacy.build_financial_evidence(
        selected, {s: quotes[s].name if s in quotes else r.name for s, r in official.items()},
        {s: q.industry for s, q in quotes.items()}, evaluation_at=kwargs['generated_at'])
    quality = receipt.channel_results['quality']
    rows = tuple(replace(row, status='DATA_GAP',
                         reason='Financial evidence incomplete: ' + '; '.join(financial[row.symbol].reasons),
                         policy_version=VERSION)
                 if row.status == 'REJECTED' and row.symbol in financial
                 and financial[row.symbol].total_score is None else row
                 for row in quality.evaluations)
    channels = dict(receipt.channel_results, quality=replace(quality, evaluations=rows, rule_version=VERSION))
    return replace(receipt, rule_version=VERSION, channel_results=channels,
                   coverage_signature=coverage_signature(channels))
