"""Explain consumed conditional distributions; do not forecast, value or approve."""
from decimal import Decimal, localcontext

FIELDS = ('profit', 'target_distribution', 'distribution', 'accessible_profit',
    'mandatory_cash', 'cash_distribution_limit', 'capacity_distribution_limit',
    'closing_cash', 'closing_unremitted', 'funding_shortfall')


def explain_distribution_capacity(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('EXPLICIT_ANNUAL_DISTRIBUTION_LEDGER_REQUIRED')
    with localcontext() as context:
        context.prec = 80
        years = []
        for year, row in enumerate(rows, 1):
            if not isinstance(row, dict) or type(row.get('year')) is not int or row['year'] != year:
                raise ValueError('CONTIGUOUS_MODEL_YEARS_REQUIRED')
            values = {}
            for field in FIELDS:
                value = row.get(field)
                if not isinstance(value, str):
                    raise ValueError('FINITE_DECIMAL_LEDGER_FIELD_REQUIRED: ' + field)
                try:
                    number = Decimal(value)
                except ArithmeticError as exc:
                    raise ValueError('FINITE_DECIMAL_LEDGER_FIELD_REQUIRED: ' + field) from exc
                if not number.is_finite():
                    raise ValueError('FINITE_DECIMAL_LEDGER_FIELD_REQUIRED: ' + field)
                values[field] = number
            if values['profit'] <= 0 or any(values[k] < 0 for k in FIELDS
                    if k not in {'mandatory_cash', 'closing_cash'}):
                raise ValueError('UNSUPPORTED_DISTRIBUTION_LEDGER_AMOUNT')
            limits = {'TARGET_POLICY': values['target_distribution'],
                      'CASH_LIMIT': values['cash_distribution_limit'],
                      'DISTRIBUTABLE_CAPACITY': values['capacity_distribution_limit']}
            paid = values['distribution']
            # Assert the consumed result; never choose a replacement dividend.
            if paid != min(limits.values()):
                raise ValueError('CONSUMED_DISTRIBUTION_LIMIT_MISMATCH')
            net = values['accessible_profit'] - values['mandatory_cash']
            reduction = values['target_distribution'] - paid
            years.append(dict(model_year=year, **{k: row[k] for k in FIELDS},
                net_period_resources=str(net),
                distribution_coverage_ratio=str(net / paid) if paid else None,
                target_reduction=str(reduction),
                distribution_support_from_opening_resources=str(max(Decimal(0), paid - max(Decimal(0), net))),
                operating_resource_deficit=str(max(Decimal(0), -net)),
                binding_constraints=[k for k, v in limits.items() if v == paid],
                status='FUNDING_SHORTFALL' if values['funding_shortfall'] else
                    'TARGET_CONSTRAINED' if reduction else 'TARGET_MET'))
        ratios = [Decimal(y['distribution_coverage_ratio']) for y in years
                  if y['distribution_coverage_ratio'] is not None]
        def total(field):
            return str(sum((Decimal(y[field]) for y in years), Decimal(0)))
        return dict(years=years, summary=dict(
            first_year_distribution=years[0]['distribution'],
            cumulative_distribution=total('distribution'), cumulative_profit=total('profit'),
            cumulative_distribution_support_from_opening_resources=total('distribution_support_from_opening_resources'),
            minimum_distribution_coverage_ratio=str(min(ratios)) if ratios else None,
            target_reduced_years=[y['model_year'] for y in years if Decimal(y['target_reduction']) > 0],
            opening_resources_used_years=[y['model_year'] for y in years
                if Decimal(y['distribution_support_from_opening_resources']) > 0],
            funding_shortfall_years=[y['model_year'] for y in years if Decimal(y['funding_shortfall']) > 0],
            closing_unremitted=years[-1]['closing_unremitted']))
