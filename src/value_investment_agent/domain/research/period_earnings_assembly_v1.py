"""Exact calendar earnings assembly, not a forecast, cash model or admission."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
import json
import re
from zoneinfo import ZoneInfo

from ..valuation.signed_parent_profit import build_signed_parent_profit_path

VERSION = 'period-earnings-assembly-v1'
KINDS = {'REPORTED_FACT', 'DERIVED_FACT', 'FORECAST_ASSUMPTION'}
AMOUNTS = ('group_pbt_cny', 'income_tax_cny', 'signed_nci_cny')
FIELDS = {'period_start', 'period_end', 'kind', 'currency', 'scope', *AMOUNTS,
          'source_refs', 'assumption_refs'}
OPTIONAL = {'parent_profit_cny', 'available_at', 'asof', 'derivation'}


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('EXACT_CALENDAR_DATE_REQUIRED')
    return date.fromisoformat(value)


def _stamp(value):
    stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError('AWARE_ASOF_OR_AVAILABILITY_REQUIRED')
    return stamp


def _amount(value):
    # Finite plain strings; the bound leaves guard digits in the shared 48-digit arithmetic.
    if not isinstance(value, str) or len(value) > 40 or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value):
        raise ValueError('EXACT_BOUNDED_DECIMAL_AMOUNT_REQUIRED')
    return Decimal(value)


def _parent(pbt, tax, nci, year=1):
    return build_signed_parent_profit_path(years=[year], group_pbt_cny=[pbt],
        tax_assumptions=[dict(basis='amount_cny', value=tax)], signed_nci_cny=[nci], currency='CNY')['rows'][0]


def _refs(value):
    if not isinstance(value, list):
        raise ValueError('EXPLICIT_REFERENCE_LIST_REQUIRED')
    seen = set()
    for ref in value:
        if not ((isinstance(ref, str) and ref.strip()) or (isinstance(ref, dict) and ref)):
            raise ValueError('NONEMPTY_REFERENCE_REQUIRED')
        key = json.dumps(ref, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if key in seen:
            raise ValueError('DUPLICATE_REFERENCE')
        seen.add(key)


def _segment(segment, asof):
    if not isinstance(segment, dict) or not FIELDS <= set(segment) or set(segment) - FIELDS - OPTIONAL:
        raise ValueError('EXACT_SEGMENT_FIELDS_REQUIRED')
    start, end = _day(segment['period_start']), _day(segment['period_end'])
    if end < start:
        raise ValueError('INVALID_SEGMENT_PERIOD')
    if segment['currency'] != 'CNY' or segment['scope'] != 'consolidated':
        raise ValueError('CONSOLIDATED_CNY_SEGMENT_REQUIRED')
    if segment['kind'] not in KINDS:
        raise ValueError('EXPLICIT_SEGMENT_KIND_REQUIRED')
    for key in ('source_refs', 'assumption_refs'):
        _refs(segment[key])
    if segment['kind'] == 'FORECAST_ASSUMPTION':
        if not segment['assumption_refs']:
            raise ValueError('FORECAST_ASSUMPTION_REFS_REQUIRED')
    elif not segment['source_refs'] or segment['assumption_refs']:
        raise ValueError('ACTUAL_SOURCE_REFS_WITHOUT_ASSUMPTIONS_REQUIRED')
    cutoff = _stamp(asof) if asof is not None else None
    if 'asof' in segment:
        own = _stamp(segment['asof'])
        if cutoff is not None and own > cutoff:
            raise ValueError('FUTURE_SEGMENT_ASOF')
        cutoff = own
    if 'available_at' in segment:
        if cutoff is None:
            raise ValueError('ASOF_REQUIRED_FOR_AVAILABILITY')
        if _stamp(segment['available_at']) > cutoff:
            raise ValueError('SEGMENT_NOT_AVAILABLE_ASOF')
    if cutoff is not None and segment['kind'] != 'FORECAST_ASSUMPTION' and end > cutoff.astimezone(ZoneInfo('Asia/Shanghai')).date():
        raise ValueError('ACTUAL_PERIOD_AFTER_ASOF')
    values = tuple(_amount(segment[key]) for key in AMOUNTS)
    parent = _parent(*values)
    if 'parent_profit_cny' in segment and _amount(segment['parent_profit_cny']) != Decimal(parent['parent_profit_cny']):
        raise ValueError('PARENT_PROFIT_RECONCILIATION_MISMATCH')
    return start, end, values


def _merge_refs(segments, key):
    result, seen = [], set()
    for segment in segments:
        for ref in segment[key]:
            identity = json.dumps(ref, sort_keys=True, ensure_ascii=False, allow_nan=False)
            if identity not in seen:
                result.append(deepcopy(ref))
                seen.add(identity)
    return result


def subtract_same_year_ytd(actual9m, actualH1, *, asof=None):
    """Return July--September actual difference; retain both operands' provenance."""
    start9, end9, nine = _segment(actual9m, asof)
    start6, end6, half = _segment(actualH1, asof)
    year = start9.year
    if (actual9m['kind'] == 'FORECAST_ASSUMPTION' or actualH1['kind'] == 'FORECAST_ASSUMPTION'
            or start9 != date(year, 1, 1) or start6 != start9
            or end9 != date(year, 9, 30) or end6 != date(year, 6, 30)):
        raise ValueError('SAME_YEAR_ACTUAL_9M_AND_H1_REQUIRED')
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        values = tuple(a - b for a, b in zip(nine, half))
    parent = _parent(*values)
    result = dict(period_start=f'{year}-07-01', period_end=f'{year}-09-30',
        kind='DERIVED_FACT', currency='CNY', scope='consolidated',
        **dict(zip(AMOUNTS, map(str, values))), parent_profit_cny=parent['parent_profit_cny'],
        source_refs=_merge_refs([actual9m, actualH1], 'source_refs'), assumption_refs=[],
        derivation=dict(version=VERSION, formula='same_year_9m_minus_h1',
                        operands=[deepcopy(actual9m), deepcopy(actualH1)]))
    stamps = [row['available_at'] for row in (actual9m, actualH1) if 'available_at' in row]
    if len(stamps) == 2:
        result['available_at'] = max(map(_stamp, stamps)).isoformat()
    if asof is not None:
        result['asof'] = _stamp(asof).isoformat()
    return result


def assemble_annual_earnings(*, year, period_start, period_end, segments, asof=None):
    """One model-year income row plus provenance; caller supplies ten rows/cash policy.

    annual_row is directly compatible with the explicit cash adapter once its
    separately researched cash_policy is added. No ROE/retention is calculated.
    """
    if type(year) is not int or not 1 <= year <= 10:
        raise ValueError('MODEL_YEAR_1_TO_10_REQUIRED')
    start, end = _day(period_start), _day(period_end)
    if start.day != 1 or end != date(start.year + 1, start.month, 1) - timedelta(days=1):
        raise ValueError('COMPLETE_MODEL_YEAR_REQUIRED')
    if not isinstance(segments, list) or not 1 <= len(segments) <= 366:
        raise ValueError('EXPLICIT_ORDERED_SEGMENTS_REQUIRED')
    cursor = start
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        totals = [Decimal(0), Decimal(0), Decimal(0)]
        for segment in segments:
            first, last, values = _segment(segment, asof)
            if first != cursor or last > end:
                raise ValueError('SEGMENT_GAP_OVERLAP_OR_OUTSIDE_MODEL_YEAR')
            totals = [a + b for a, b in zip(totals, values)]
            cursor = last + timedelta(days=1)
    if cursor != end + timedelta(days=1):
        raise ValueError('INCOMPLETE_MODEL_YEAR_COVERAGE')
    parent = _parent(*totals, year=year)
    annual = dict(year=year, period_start=period_start, period_end=period_end,
        period_basis='FY' if start.month == 1 else 'ROLLING_FULL_YEAR',
        scope='consolidated', currency='CNY', group_pbt_cny=str(totals[0]),
        tax_assumption=dict(basis='amount_cny', value=str(totals[1])), signed_nci_cny=str(totals[2]))
    return dict(version=VERSION, status='ARITHMETIC_COMPLETE', action='no_order',
        formal_eligibility=False, main_range_adopted=False, annual_row=annual, parent_bridge=parent,
        segments=deepcopy(segments), source_refs=_merge_refs(segments, 'source_refs'),
        assumption_refs=_merge_refs(segments, 'assumption_refs'),
        contains_forecast_assumptions=any(row['kind'] == 'FORECAST_ASSUMPTION' for row in segments),
        limitations=['References and company inputs are caller supplied, not source authentication.',
                    'Mixed actual/forecast assembly is not a reported annual fact or adopted valuation.',
                    'No cash policy, ROE, retention, annualisation or profit normalization is inferred.'])


COMPONENT_FIELDS = ('revenue', 'cost', 'surcharges', 'selling', 'admin', 'research', 'pre_tax_profit')
POINT_DRIVERS = ('volume_change', 'realization_mix_change', 'unit_cost_change',
                 'fixed_cogs_share', 'opex_change', 'surcharge_ratio', 'other_pretax_cny')


def _operating_period(start, end):
    if start.day != 1 or start.year != end.year:
        raise ValueError('EXACT_QUARTER_H1_OR_FY_REQUIRED')
    if start.month in (1, 4, 7, 10):
        next_month = start.month + 3
        following = date(start.year + (next_month > 12), (next_month - 1) % 12 + 1, 1)
        if end == following - timedelta(days=1):
            return 'Q' + str((start.month - 1) // 3 + 1)
    if start.month == 1 and end == date(start.year, 6, 30):
        return 'H1'
    if start.month == 1 and end == date(start.year, 12, 31):
        return 'FY'
    raise ValueError('EXACT_QUARTER_H1_OR_FY_REQUIRED')


def project_operating_period(baseline_component_rows, explicit_point_drivers, targetperiod):
    """One explicit operating point, not a corner search or a valuation.

    Each baseline row: field/value/period_start/period_end/kind/currency/scope/
    source_refs/assumption_refs; optional available_at/asof/derivation. Seven
    unique actual components are required, including the signed historical PBT.
    Drivers: seven POINT_DRIVERS as decimal strings plus source_refs and
    assumption_refs; optional rationale. targetperiod: period_start/period_end,
    optional asof. A derived Q4 must already be FY-minus-9M, never H1 divided by 2.
    """
    if (not isinstance(targetperiod, dict) or not {'period_start', 'period_end'} <= set(targetperiod)
            or set(targetperiod) - {'period_start', 'period_end', 'asof'}):
        raise ValueError('EXPLICIT_TARGET_PERIOD_REQUIRED')
    target_start, target_end = (_day(targetperiod[k]) for k in ('period_start', 'period_end'))
    target_kind = _operating_period(target_start, target_end)
    asof = targetperiod.get('asof')
    if asof is not None:
        _stamp(asof)
    if not isinstance(baseline_component_rows, list) or len(baseline_component_rows) != 7:
        raise ValueError('SEVEN_UNIQUE_ACTUAL_COMPONENTS_REQUIRED')
    row_fields = {'field', 'value', 'period_start', 'period_end', 'kind', 'currency', 'scope',
                  'source_refs', 'assumption_refs'}
    values, periods = {}, set()
    for row in baseline_component_rows:
        if (not isinstance(row, dict) or not row_fields <= set(row)
                or set(row) - row_fields - {'available_at', 'asof', 'derivation'}):
            raise ValueError('EXACT_BASELINE_COMPONENT_FIELDS_REQUIRED')
        field = row['field']
        if not isinstance(field, str) or field not in COMPONENT_FIELDS or field in values:
            raise ValueError('SEVEN_UNIQUE_ACTUAL_COMPONENTS_REQUIRED')
        if row['kind'] not in {'REPORTED_FACT', 'DERIVED_FACT'}:
            raise ValueError('ACTUAL_BASELINE_COMPONENT_REQUIRED')
        first, last = _day(row['period_start']), _day(row['period_end'])
        periods.add((first, last))
        if row['currency'] != 'CNY' or row['scope'] != 'consolidated':
            raise ValueError('CONSOLIDATED_CNY_SEGMENT_REQUIRED')
        _refs(row['source_refs'])
        _refs(row['assumption_refs'])
        if not row['source_refs'] or row['assumption_refs']:
            raise ValueError('ACTUAL_SOURCE_REFS_WITHOUT_ASSUMPTIONS_REQUIRED')
        cutoff = _stamp(asof) if asof is not None else None
        if 'asof' in row:
            own = _stamp(row['asof'])
            if cutoff is not None and own > cutoff:
                raise ValueError('FUTURE_SEGMENT_ASOF')
            cutoff = own
        if 'available_at' in row:
            if cutoff is None:
                raise ValueError('ASOF_REQUIRED_FOR_AVAILABILITY')
            if _stamp(row['available_at']) > cutoff:
                raise ValueError('SEGMENT_NOT_AVAILABLE_ASOF')
        if cutoff is not None and last > cutoff.astimezone(ZoneInfo('Asia/Shanghai')).date():
            raise ValueError('ACTUAL_PERIOD_AFTER_ASOF')
        values[field] = _amount(row['value'])
    if len(periods) != 1:
        raise ValueError('BASELINE_COMPONENT_PERIOD_MISMATCH')
    start, end = next(iter(periods))
    if (_operating_period(start, end) != target_kind or target_start != date(start.year+1, start.month, 1)
            or (target_end.month, target_end.day) != (end.month, end.day)):
        raise ValueError('NEXT_YEAR_SAME_OPERATING_PERIOD_REQUIRED')
    if values['revenue'] <= 0 or any(values[k] < 0 for k in COMPONENT_FIELDS if k not in {'pre_tax_profit', 'revenue'}):
        raise ValueError('NONNEGATIVE_BASELINE_COSTS_POSITIVE_REVENUE_REQUIRED')
    required = set(POINT_DRIVERS) | {'source_refs', 'assumption_refs'}
    if (not isinstance(explicit_point_drivers, dict) or not required <= set(explicit_point_drivers)
            or set(explicit_point_drivers) - required - {'rationale'}):
        raise ValueError('EXPLICIT_SEVEN_POINT_DRIVERS_REQUIRED')
    for key in ('source_refs', 'assumption_refs'):
        _refs(explicit_point_drivers[key])
    if not explicit_point_drivers['assumption_refs']:
        raise ValueError('POINT_ASSUMPTION_REFS_REQUIRED')
    d = {key: _amount(explicit_point_drivers[key]) for key in POINT_DRIVERS}
    if any(d[key] < -1 for key in ('volume_change', 'realization_mix_change', 'unit_cost_change', 'opex_change')):
        raise ValueError('NEGATIVE_REVENUE_OR_COST_MULTIPLIER')
    if any(not 0 <= d[key] <= 1 for key in ('fixed_cogs_share', 'surcharge_ratio')):
        raise ValueError('INVALID_FIXED_SHARE_OR_SURCHARGE_RATIO')
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        revenue = values['revenue'] * (1+d['volume_change']) * (1+d['realization_mix_change'])
        cost = values['cost'] * (d['fixed_cogs_share'] + (1-d['fixed_cogs_share'])*(1+d['volume_change'])) * (1+d['unit_cost_change'])
        opex = sum(values[k] for k in ('selling', 'admin', 'research')) * (1+d['opex_change'])
        surcharges = revenue * d['surcharge_ratio']
        pbt = revenue - cost - opex - surcharges + d['other_pretax_cny']
    return dict(version=VERSION, status='POINT_ARITHMETIC_COMPLETE', action='no_order',
        formal_eligibility=False, main_range_adopted=False, kind='FORECAST_ASSUMPTION',
        currency='CNY', scope='consolidated', period_start=targetperiod['period_start'],
        period_end=targetperiod['period_end'], period_basis=target_kind,
        group_pbt_cny=str(pbt), income_tax_cny=None, signed_nci_cny=None,
        components=dict(revenue_cny=str(revenue), cogs_cny=str(cost), opex_cny=str(opex),
            surcharges_cny=str(surcharges), other_pretax_cny=str(d['other_pretax_cny'])),
        baseline_component_rows=deepcopy(baseline_component_rows), drivers=deepcopy(explicit_point_drivers),
        source_refs=_merge_refs([*baseline_component_rows, explicit_point_drivers], 'source_refs'),
        assumption_refs=deepcopy(explicit_point_drivers['assumption_refs']),
        limitations=['Single explicit point, not a probability or a jointly inferred scenario.',
            'Negative projected PBT is retained; income tax and signed NCI require separate explicit inputs.',
            'Derived historical components are caller supplied; no mechanical H1 split or source authentication.',
            'Activity covers revenue scope; realization includes product/channel mix; cost level applies to all COGS.',
            'Fixed share is a sensitivity assumption; other pretax is not presumed recurring income.'])
