"""Dated seasonal stub plus fiscal research paths; no TTM relabel or admission."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import re

from .industrial_earnings_paths import (
    ANNUAL_FIELDS, COMMERCIAL_COST_FIELDS, HISTORICAL_FIELDS, SCENARIOS,
    _decimal, _plain, build_industrial_earnings_paths,
)
from .signed_parent_profit import build_signed_parent_profit_path


SCHEMA = 'fiscal-industrial-earnings-paths-v1'
PERIODS = {'FY2025': ('2025-01-01', '2025-12-31'),
           'H12025': ('2025-01-01', '2025-06-30'), 'H12026': ('2026-01-01', '2026-06-30')}


def _check_identity(lines):
    if lines['profit_before_tax']-lines['income_tax']-lines['minority_profit'] != lines['parent_profit']:
        raise ValueError('Fiscal PBT/tax/signed NCI/parent identity does not reconcile')
    if 'net_profit' in lines and lines['profit_before_tax']-lines['income_tax'] != lines['net_profit']:
        raise ValueError('Fiscal reported net profit does not reconcile')
    if lines['operating_revenue'] < 0 or any(lines[key] < 0 for key in COMMERCIAL_COST_FIELDS):
        raise ValueError('Unsupported fiscal revenue or commercial-cost signs')


def _period(start, end, classification, **extra):
    return dict(period_start=start, period_end=end, fiscal_year=int(end[:4]),
        full_year=start.endswith('01-01') and end.endswith('12-31'),
        classification=classification, **extra)


def build_fiscal_industrial_earnings_paths(*, historical, stub_scenarios, scenarios):
    """Three H2-2026 hypotheses, each feeding its own FY2027..2031 path.

    Caller verifies actual originals and same accounting/restatement basis.
    Five-cost allocations preserve the total and are computational references,
    not forecasts of individual cost lines or source facts.
    """
    if not isinstance(historical, dict) or set(historical) != set(PERIODS):
        raise ValueError('FY2025/H12025/H12026 originals required; no TTM input')
    metadata = {'symbol', 'period_start', 'period_end', 'scope', 'unit', 'currency', 'accounting_basis_id', 'lines'}
    identities, bases, field_sets = set(), set(), []
    for name, record in historical.items():
        if (not isinstance(record, dict) or set(record) != metadata
                or not isinstance(record['symbol'], str) or not re.fullmatch(r'[0-9]{6}', record['symbol'])
                or (record['period_start'], record['period_end']) != PERIODS[name]
                or record['scope'] != 'consolidated' or record['unit'] != 'CNY' or record['currency'] != 'CNY'
                or not isinstance(record['accounting_basis_id'], str) or not record['accounting_basis_id'].strip()
                or not isinstance(record['lines'], dict) or not HISTORICAL_FIELDS.issubset(record['lines'])
                or any(not isinstance(key, str) or not key for key in record['lines'])):
            raise ValueError('Historical fiscal dates, identity, scope/unit or lines differ')
        identities.add(record['symbol'])
        bases.add(record['accounting_basis_id'])
        field_sets.append(set(record['lines']))
    if len(identities) != 1 or len(bases) != 1 or any(keys != field_sets[0] for keys in field_sets):
        raise ValueError('Issuers, accounting/restatement bases or line sets are not comparable')
    if (not isinstance(stub_scenarios, dict) or set(stub_scenarios) != set(SCENARIOS)
            or any(not isinstance(row, dict) or set(row) != ANNUAL_FIELDS-{'year'}
                   for row in stub_scenarios.values())):
        raise ValueError('Three explicit eight-driver H2 stub hypotheses required')
    if (not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIOS)
            or any(not isinstance(rows, list) or len(rows) != 5
                   or any(not isinstance(row, dict) or set(row) != ANNUAL_FIELDS
                          or type(row['year']) is not int or row['year'] != year
                          for year, row in enumerate(rows, 2027)) for rows in scenarios.values())):
        raise ValueError('Three explicit FY2027..FY2031 paths required, not rolling years')
    with localcontext() as ctx:
        ctx.prec = 48
        values = {name: {key: _decimal(value) for key, value in record['lines'].items()}
                  for name, record in historical.items()}
        for lines in values.values():
            _check_identity(lines)
        h2 = {key: values['FY2025'][key]-values['H12025'][key] for key in values['FY2025']}
        _check_identity(h2)
        h2_cost = sum(h2[key] for key in COMMERCIAL_COST_FIELDS)
        stub_output, bases_output, references, dated = {}, {}, {}, {}
        for name in SCENARIOS:
            drivers = {key: _decimal(value) for key, value in stub_scenarios[name].items()}
            if (drivers['revenue_growth'] <= -1 or drivers['commercial_margin'] > 1
                    or any(drivers[key] < 0 for key in ('inventory_impairment_ratio',
                        'goodwill_impairment_cny', 'other_asset_impairment_cny'))
                    or not 0 <= drivers['tax_research_rate'] <= 1):
                raise ValueError('Unsupported explicit stub economics')
            revenue = h2['operating_revenue']*(1+drivers['revenue_growth'])
            commercial = revenue*drivers['commercial_margin']
            total_cost = revenue-commercial
            if h2_cost == 0 and total_cost != 0:
                raise ValueError('Zero historical H2 cost cannot define a nonzero computational cost allocation')
            # Only the sum is consumed by the existing margin-based kernel.
            # The partition is NOT an asserted forecast of the five cost lines.
            costs = {key: total_cost*h2[key]/h2_cost if h2_cost != 0 else D(0)
                     for key in COMMERCIAL_COST_FIELDS}
            if h2_cost != 0:
                last = next(key for key in reversed(COMMERCIAL_COST_FIELDS) if h2[key] > 0)
                costs[last] = total_cost-sum(value for key, value in costs.items() if key != last)
            if min(costs.values()) < 0:
                raise ValueError('Unsupported computational cost allocation rounding')
            inventory = revenue*drivers['inventory_impairment_ratio']
            losses = inventory+drivers['goodwill_impairment_cny']+drivers['other_asset_impairment_cny']
            pre_goodwill = commercial+drivers['other_pbt_cny']-inventory-drivers['other_asset_impairment_cny']
            pbt = pre_goodwill-drivers['goodwill_impairment_cny']
            tax = max(pre_goodwill, D(0))*drivers['tax_research_rate']
            parent = build_signed_parent_profit_path(years=[2026], group_pbt_cny=[pbt],
                tax_assumptions=[dict(basis='amount_cny', value=tax)],
                signed_nci_cny=[drivers['signed_nci_cny']], currency='CNY')['rows'][0]
            stub_lines = dict(costs, operating_revenue=revenue, profit_before_tax=pbt,
                asset_impairment=-losses, income_tax=tax, minority_profit=drivers['signed_nci_cny'],
                parent_profit=_decimal(parent['parent_profit_cny']))
            if 'net_profit' in h2:
                stub_lines['net_profit'] = pbt-tax
            _check_identity(stub_lines)
            fy2026 = {key: values['H12026'][key]+value for key, value in stub_lines.items()}
            _check_identity(fy2026)
            owner_steps = [dict(row, year=step) for step, row in enumerate(scenarios[name], 1)]
            # The old pure API is a three-label batch with one common reference.
            # Repeat this SAME supplied path for its required labels, selecting
            # only the owner. No parameters or additional economic paths invented.
            generated = build_industrial_earnings_paths(historical_ttm=_plain(fy2026),
                scenarios={label: deepcopy(owner_steps) for label in SCENARIOS})
            allocation_scope = 'COMPUTATIONAL_COST_PARTITION_NOT_OBSERVED_OR_COMPONENT_FORECAST'
            stub_output[name] = _period('2026-07-01', '2026-12-31', 'RESEARCH_ASSUMPTION',
                confidence='LOW', inputs=drivers, lines=stub_lines,
                seasonal_revenue_reference_cny=h2['operating_revenue'], commercial_subtotal_cny=commercial,
                inventory_impairment_cny=inventory, goodwill_impairment_cny=drivers['goodwill_impairment_cny'],
                other_asset_impairment_cny=drivers['other_asset_impairment_cny'],
                pre_goodwill_pbt_cny=pre_goodwill, tax_research_base_cny=max(pre_goodwill, D(0)),
                cost_component_scope=allocation_scope)
            bases_output[name] = _period('2026-01-01', '2026-12-31', 'MIXED_ACTUAL_H1_AND_RESEARCH_H2',
                confidence='LOW', lines=fy2026, formula='H12026 actual + same-scenario H22026 assumption',
                cost_component_scope=allocation_scope,
                unmodelled_historical_line_names=sorted(set(h2)-set(stub_lines)))
            references[name] = dict(generated['historical_reference'],
                scope='MIXED_FY2026_RESEARCH_COMPUTATIONAL_REFERENCE_NOT_TTM_OR_ACTUAL',
                cost_component_scope=allocation_scope)
            rows = []
            for year, original in enumerate(generated['scenarios'][name]['rows'], 2027):
                row = deepcopy(original)
                row['projection_step'] = row['year']
                row['year'] = row['inputs']['year'] = year
                row['change_from_fy2026_research_parent'] = row.pop('change_from_historical_parent')
                row.update(_period(f'{year}-01-01', f'{year}-12-31',
                    'RESEARCH_ASSUMPTION', confidence='LOW'))
                rows.append(row)
            dated[name] = dict(rows=rows)
        return _plain(dict(schema_version=SCHEMA, status='FISCAL_EARNINGS_RESEARCH_NOT_APPROVED_V1',
            symbol=next(iter(identities)), currency='CNY', scope='consolidated', action='no_order',
            accounting_basis_id=next(iter(bases)), historical_inputs=deepcopy(historical),
            historical_h2_2025=_period('2025-07-01', '2025-12-31',
                'DERIVED_FY_MINUS_H1_FROM_SAME_BASIS', lines=h2,
                formula='FY2025 original lines minus comparable H12025 original lines'),
            research_h2_2026=stub_output, fy2026_research_base=bases_output,
            fy2026_research_reference=references, scenarios=dated,
            parent_change_comparison_scope='SAME_SCENARIO_MIXED_FY2026_RESEARCH_PARENT_NOT_HISTORICAL_ACTUAL',
            normalized_parent_profit_cny=None, formal_eligibility=False, economic_approval=False,
            research_admitted=False, price_admitted=False, strategy_admitted=False, action_admitted=False,
            limitations=['Source/restatement comparability requires caller verification; matching basis IDs are not proof.',
                'No H1 annualization or TTM-to-FY relabeling; H2-2025 is derived, not separately reported.',
                'Each FY2026 reference combines actual H1 and same-scenario assumed H2; all later years are assumptions.',
                'Only aggregate commercial cost is forecast; component partitions are computational references, not facts.',
                'Goodwill has no tax shield by research assumption, not by tax-law conclusion.',
                'Fiscal dating grants no dividend-policy extension, cash capacity, valuation or approval.']))
