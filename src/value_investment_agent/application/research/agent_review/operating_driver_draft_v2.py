"""Unapproved operating driver drafts; economic arithmetic belongs to the domain bridge."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, InvalidOperation
import hashlib
import json

from . import operating_draft_v1 as v1
from ....infrastructure.agent_runtime.provider import LLMResponse
from ....domain.research.operating_driver_bridge_v1 import DRIVERS

DRIVER_CONTRACT_VERSION = 'operating-drivers-v2'
PROMPT_VERSION = 'operating-driver-prompts-v2-calendar-locked-citations'
ROLES = v1.ROLES
CAPITAL = ('investment', 'funding_access', 'terminal')
SCENARIOS = ('bear', 'base', 'bull')


def _bridge():
    from ....domain.research import operating_driver_bridge_v1
    return operating_driver_bridge_v1


def legacy_context(context):
    """Only period_basis is bridge metadata; v1 still rejects other extra fields."""
    result = deepcopy(context)
    for row in result['evidence']:
        row.pop('period_basis', None)
    return result


def _prompt_basis(basis):
    return dict(baselines={period: {key: deepcopy(row[key]) for key in (
        'fields', 'period_basis', 'other_pretax_cny', 'pretax_margin') if key in row}
        for period, row in basis['baselines'].items()},
        comparisons=[{key: deepcopy(row[key]) for key in ('field', 'current_period', 'prior_period',
            'current_value', 'prior_value', 'change_ratio', 'status') if key in row}
            for row in basis['comparisons'] if row['field'] in {
                'revenue', 'cost', 'selling', 'admin', 'research', 'pre_tax_profit'}],
        gaps=deepcopy(basis.get('gaps', {})))


def _prompt_bridge(bridge):
    return dict(inputs={name: {key: {field: row[field] for field in ('lower', 'upper', 'rationale')}
            for key, row in path['drivers'].items()} for name, path in bridge['inputs'].items()},
        paths={name: dict(growth_range=deepcopy(path['growth_range']),
            margin_range=deepcopy(path['margin_range']), comparison_basis=path['comparison_basis'],
            baseline_period=path['baseline']['period']) for name, path in bridge['paths'].items()},
        thresholds=[{key: row[key] for key in ('scenario', 'metric', 'direction', 'threshold')}
                    for row in bridge['thresholds']])


def calendar_plan(basis, context):
    as_of = v1._day(context['as_of'])
    available = {period: row for period, row in basis['baselines'].items()
                 if v1._day(period) <= as_of}
    if not available:
        raise ValueError('VERIFIED_BASELINE_REQUIRED')
    period = max(available)
    kind = available[period]['period_basis']
    if kind not in {'FY', 'H1'}:
        raise ValueError('VERIFIED_BASELINE_REQUIRED')
    year = as_of.year + 1
    return dict(baseline_period=period, period_start=f'{year}-01-01',
                period_end=f'{year}-06-30' if kind == 'H1' else f'{year}-12-31')


def _schema(plan, *, evidence_ids=None):
    old = v1._schema('FUNDAMENTAL', evidence_ids=evidence_ids)
    assumption = deepcopy(old['properties']['scenarios']['properties']['base']['items'])
    assumption['properties']['dimension']['enum'] = list(CAPITAL)
    driver = dict(type='object', additionalProperties=False,
        required=['lower', 'upper', 'rationale', 'evidence_ids'], properties=dict(
            lower={'type': 'string'}, upper={'type': 'string'}, rationale={'type': 'string'},
            evidence_ids={'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': {'type': 'string'}}))
    path = dict(type='object', additionalProperties=False,
        required=['baseline_period', 'period_start', 'period_end', 'drivers', 'capital_assumptions'],
        properties=dict(baseline_period={'type': 'string'}, period_start={'type': 'string'},
            period_end={'type': 'string'}, drivers=dict(type='object', additionalProperties=False,
                required=list(DRIVERS), properties={key: deepcopy(driver) for key in DRIVERS}),
            capital_assumptions=dict(type='array', minItems=3, maxItems=3, items=assumption)))
    for key, value in plan.items():
        path['properties'][key]['const'] = value
    return dict(type='object', additionalProperties=False, required=['business_drivers', 'operating_paths'],
        properties=dict(business_drivers=deepcopy(old['properties']['business_drivers']),
            operating_paths=dict(type='object', additionalProperties=False,
                required=list(SCENARIOS), properties={key: deepcopy(path) for key in SCENARIOS})))


def build_request(role, context, max_completion_tokens=4096, fundamental_draft=None):
    legacy = legacy_context(context)
    if role != 'FUNDAMENTAL':
        proposal = None
        if fundamental_draft is not None:
            if fundamental_draft.get('driver_contract_version') != DRIVER_CONTRACT_VERSION:
                raise ValueError('Current driver contract required')
            proposal = {key: deepcopy(value) for key, value in fundamental_draft.items()
                        if key not in {'driver_bridge', 'driver_contract_version'}}
        request = v1.build_request(role, legacy, max_completion_tokens, fundamental_draft=proposal)
        if fundamental_draft is not None:
            bridge = fundamental_draft['driver_bridge']
            user = request.user + '\nUNTRUSTED_NEW_DRIVER_BRIDGE:\n' + v1._canonical(_prompt_bridge(bridge))
            user += '\n仅结构化threshold为判定，文本不能代替。驱动为本次条件假设，不是原始证据或批准。'
            if len(user) > 64000:
                raise ValueError('Source plus driver proposal exceeds bounded prompt')
            request = replace(request, user=user)
        return request
    request = v1.build_request(role, legacy, max_completion_tokens, fundamental_draft=fundamental_draft)
    basis = _bridge().build_basis(context)
    plan = calendar_plan(basis, context)
    user = request.user + '\nDETERMINISTIC_DRIVER_BASIS:\n' + v1._canonical(_prompt_basis(basis))
    user += '\nLOCKED_CALENDAR_PLAN (copy these exact three values in every path):\n' + v1._canonical(plan)
    if len(user) > 64000:
        raise ValueError('Source plus driver basis exceeds bounded prompt')
    return replace(request, output_schema=_schema(plan, evidence_ids=v1._context(legacy)), user=user,
        system=request.system + '\n' + PROMPT_VERSION + ': Return operating_paths, not scenarios. '
        'Supply exactly seven bounded operating drivers per path: volume_change, realization_mix_change, '
        'unit_cost_change, fixed_cogs_share, opex_change, surcharge_ratio, other_pretax_cny. '
        'Changes and shares are decimal ratios; other_pretax_cny is CNY. Explain each assumption '
        'concisely: business_drivers at most 2 statements; statement text at most 400 characters. '
        'Each rationale must be at most 40 Chinese characters, including capital assumptions. '
        'Prefer only 1-3 necessary original evidence IDs per item. Keep UNKNOWN reasons short '
        'and avoid repeated template text. Every capital assumption, including UNKNOWN, must cite '
        'at least one exact original evidence ID. For UNKNOWN, cite the closest disclosed context '
        'and explain what it does not establish. An empty array is invalid. Preserve all seven drivers and all three capital items '
        'in each scenario; return complete JSON within the existing completion budget. '
        'with original evidence IDs. Do not emit growth or profit-margin assumptions: the domain '
        'bridge derives them from these drivers. The server selects the latest complete baseline '
        'and locks the next calendar year full FY/H1 period (for example H1 2026 to H1 2027). '
        'Copy LOCKED_CALENDAR_PLAN exactly; never use as_of as period_start or choose other dates. '
        'All three scenarios MUST share the identical baseline_period, period_start and period_end; '
        'never choose different FY/H1 bases across scenarios. Capital '
        'assumptions contain only investment, funding_access and terminal; UNKNOWN with null '
        'bounds remains valid. investment and funding_access periods must match the operating path. '
        'terminal may and preferably should use an independent farther-future period for economic '
        'persistence; it is not current-period profit and does not enter the driver bridge arithmetic. '
        'Do not force a quantified long-term terminal assumption without evidence. '
        'volume_change is a sales activity index covering the revenue scope, '
        'not tonnes of one liquor category. realization_mix_change includes price, product and '
        'channel mix, not proof of pricing power. unit_cost_change acts on all COGS in this formula '
        'and means overall cost-level change. fixed_cogs_share is only a baseline COGS sensitivity '
        'split assumption. OPEX is selling plus administrative plus R&D expense. surcharge_ratio '
        'means taxes and surcharges, not income tax. other_pretax_cny is a residual, not presumed '
        'recurring earnings. The 128 independent corner combinations form a stress envelope, '
        'not probabilities. Growth is relative_to_baseline, not an asserted forecast-year YoY. '
        'Baseline FY/H1 period_basis must match the forecast end type. '
        'These conditional paths are not a valuation or an admitted range.')


def _payload(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 64000:
        raise ValueError('Bounded JSON response required')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate response JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError('Exact operating driver fields required')


def validate_response(response_or_text, role, context, generated_at):
    legacy_source = legacy_context(context)
    if role != 'FUNDAMENTAL':
        return v1.validate_response(response_or_text, role, legacy_source, generated_at)
    ids = v1._context(legacy_source)
    text = response_or_text.text if isinstance(response_or_text, LLMResponse) else response_or_text
    payload = _payload(text)
    _exact(payload, ('business_drivers', 'operating_paths'))
    _exact(payload['operating_paths'], SCENARIOS)
    scenario_periods = set()
    for path in payload['operating_paths'].values():
        _exact(path, ('baseline_period', 'period_start', 'period_end', 'drivers', 'capital_assumptions'))
        for key in ('baseline_period', 'period_start', 'period_end'):
            v1._day(path[key])
        scenario_periods.add(tuple(path[key] for key in ('baseline_period', 'period_start', 'period_end')))
    if len(scenario_periods) != 1:
        raise ValueError('SCENARIO_BASIS_MISMATCH')
    bridge = _bridge()
    basis = bridge.build_basis(context)
    plan = calendar_plan(basis, context)
    if any(any(path[key] != value for key, value in plan.items())
           for path in payload['operating_paths'].values()):
        raise ValueError('CALENDAR_PLAN_MISMATCH')
    derived, scenarios = {}, {}
    for name in SCENARIOS:
        path = payload['operating_paths'][name]
        _exact(path, ('baseline_period', 'period_start', 'period_end', 'drivers', 'capital_assumptions'))
        if v1._day(path['baseline_period']) > v1._day(context['as_of']):
            raise ValueError('Future operating baseline forbidden')
        start, end = v1._day(path['period_start']), v1._day(path['period_end'])
        if start <= v1._day(context['as_of']) or end < start:
            raise ValueError('Explicit future forecast period required')
        _exact(path['drivers'], DRIVERS)
        for driver in path['drivers'].values():
            _exact(driver, ('lower', 'upper', 'rationale', 'evidence_ids'))
            v1._text(driver['rationale'])
            refs = driver['evidence_ids']
            if (not isinstance(refs, list) or not 1 <= len(refs) <= 8
                    or any(not isinstance(ref, str) for ref in refs)
                    or len(set(refs)) != len(refs) or not set(refs) <= ids):
                raise ValueError('Unknown/missing/duplicate driver evidence citation')
            bounds = []
            for value in (driver['lower'], driver['upper']):
                if not isinstance(value, str) or not 1 <= len(value) <= 64:
                    raise ValueError('Finite decimal driver bounds required')
                try:
                    number = Decimal(value)
                except InvalidOperation as error:
                    raise ValueError('Invalid driver number') from error
                if not number.is_finite() or abs(number) > Decimal('1e18'):
                    raise ValueError('Nonfinite/unbounded driver')
                bounds.append(number)
            if bounds[0] > bounds[1]:
                raise ValueError('Driver lower exceeds upper')
        capital = path['capital_assumptions']
        if (not isinstance(capital, list) or len(capital) != 3
                or any(not isinstance(row, dict) or not isinstance(row.get('dimension'), str) for row in capital)
                or {row['dimension'] for row in capital} != set(CAPITAL)):
            raise ValueError('Exactly three capital assumptions required')
        if any(row.get('period_start') != path['period_start'] or row.get('period_end') != path['period_end']
               for row in capital if row['dimension'] != 'terminal'):
            raise ValueError('Investment and funding access must match operating path period')
        calculated = bridge.calculate_path(basis, path)
        derived[name] = calculated
        rows = []
        for dimension, key in (('growth', 'growth_range'), ('profit', 'margin_range')):
            bounds = calculated[key]
            rows.append(dict(dimension=dimension, period_start=path['period_start'],
                period_end=path['period_end'], classification='FORECAST', lower=bounds['lower'],
                upper=bounds['upper'], unit='ratio',
                rationale=('growth=R/R0-1；relative_to_baseline，非自动认定同比。' if dimension == 'growth'
                           else 'pretax_margin=(R-COGS-OPEX-surcharges+other_pretax)/R；other非默认经常收益。')
                          + '独立角点包络，非概率、预测批准或已采纳主区间；原始依据见evidence_ids。',
                evidence_ids=calculated['evidence_ids']))
        scenarios[name] = rows + deepcopy(capital)
    legacy = v1._canonical(dict(business_drivers=payload['business_drivers'], scenarios=scenarios))
    response = replace(response_or_text, text=legacy) if isinstance(response_or_text, LLMResponse) else legacy
    result = v1.validate_response(response, role, legacy_source, generated_at)
    result['response_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
    result['driver_contract_version'] = DRIVER_CONTRACT_VERSION
    result['driver_bridge'] = dict(version='operating-driver-bridge-v1', basis=basis,
        inputs=deepcopy(payload['operating_paths']), paths=derived,
        thresholds=bridge.build_thresholds(derived), action='no_order')
    return result
