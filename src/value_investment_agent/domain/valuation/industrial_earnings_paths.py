"""Explicit commercial/loss/tax/NCI research arithmetic, not a valuation model."""
from decimal import Decimal, InvalidOperation, localcontext

from .signed_parent_profit import build_signed_parent_profit_path


COMMERCIAL_COST_FIELDS = ('cost_of_sales', 'taxes_surcharges', 'selling', 'administration', 'research')
HISTORICAL_FIELDS = frozenset((*COMMERCIAL_COST_FIELDS, 'operating_revenue', 'profit_before_tax',
    'asset_impairment', 'income_tax', 'minority_profit', 'parent_profit'))
ANNUAL_FIELDS = frozenset(('year', 'revenue_growth', 'commercial_margin', 'inventory_impairment_ratio',
    'goodwill_impairment_cny', 'other_asset_impairment_cny', 'other_pbt_cny',
    'tax_research_rate', 'signed_nci_cny'))
SCENARIOS = ('bear', 'base', 'bull')


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('Industrial research values require explicit decimals, not bool or float')
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Industrial research value is not a valid decimal') from error
    if not number.is_finite():
        raise ValueError('Industrial research values must be finite')
    return number


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def build_industrial_earnings_paths(*, historical_ttm, scenarios):
    """Compute three explicit five-year hypotheses without assuming their order.

    historical_ttm is a CNY line map with HISTORICAL_FIELDS; extra numeric lines
    may be retained but never silently substituted for required fields. Annual
    rows have exactly ANNUAL_FIELDS and consecutive integer years 1..5.
    The caller authenticates issuer, sources, periods, units and policy evidence.
    Neither historical negative NCI nor historical impairment becomes a forecast.
    """
    if not isinstance(historical_ttm, dict) or not HISTORICAL_FIELDS.issubset(historical_ttm):
        raise ValueError('Complete historical TTM commercial, PBT, loss, tax and ownership lines required')
    if any(not isinstance(key, str) or not key for key in historical_ttm):
        raise ValueError('Historical TTM requires explicit line names')
    if (not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIOS)
            or any(not isinstance(scenarios[name], list) or len(scenarios[name]) != 5
                   or any(not isinstance(row, dict) or set(row) != ANNUAL_FIELDS
                          or type(row['year']) is not int or row['year'] != index
                          for index, row in enumerate(scenarios[name], 1)) for name in SCENARIOS)):
        raise ValueError('Exactly bear/base/bull with five ordered complete annual hypotheses required')
    with localcontext() as ctx:
        ctx.prec = 48
        history = {key: _decimal(value) for key, value in historical_ttm.items()}
        revenue0 = history['operating_revenue']
        if revenue0 < 0 or any(history[key] < 0 for key in COMMERCIAL_COST_FIELDS):
            raise ValueError('Historical revenue and commercial costs must be nonnegative')
        if history['profit_before_tax']-history['income_tax']-history['minority_profit'] != history['parent_profit']:
            raise ValueError('Historical PBT/tax/signed NCI does not reconcile to parent profit')
        cost0 = sum(history[key] for key in COMMERCIAL_COST_FIELDS)
        commercial0 = revenue0-cost0
        cost_ratio0 = cost0/revenue0 if revenue0 != 0 else None
        reference = dict(scope='HISTORICAL_RECONCILIATION_NOT_NORMALIZED_OR_FUTURE_POLICY', currency='CNY',
            input_lines_cny=history, revenue_cny=revenue0, commercial_cost_cny=cost0,
            commercial_subtotal_cny=commercial0, commercial_cost_ratio=cost_ratio0,
            commercial_margin=commercial0/revenue0 if revenue0 != 0 else None,
            signed_asset_impairment_cny=history['asset_impairment'],
            other_pbt_cny=history['profit_before_tax']-commercial0-history['asset_impairment'],
            group_pbt_cny=history['profit_before_tax'], income_tax_cny=history['income_tax'],
            signed_nci_cny=history['minority_profit'], parent_profit_cny=history['parent_profit'],
            bridge_residual_cny=Decimal(0))
        output = {}
        for name in SCENARIOS:
            revenue = revenue0
            rows, taxes, pbts, ncis = [], [], [], []
            for raw in scenarios[name]:
                inputs = {key: _decimal(raw[key]) for key in sorted(ANNUAL_FIELDS) if key != 'year'}
                inputs['year'] = raw['year']
                if (inputs['revenue_growth'] <= -1 or inputs['commercial_margin'] > 1
                        or any(inputs[key] < 0 for key in ('inventory_impairment_ratio',
                            'goodwill_impairment_cny', 'other_asset_impairment_cny'))
                        or not 0 <= inputs['tax_research_rate'] <= 1):
                    raise ValueError('Unsupported growth, commercial margin, nonnegative loss or tax-rate assumption')
                previous = revenue
                revenue *= 1+inputs['revenue_growth']
                commercial = revenue*inputs['commercial_margin']
                inventory_loss = revenue*inputs['inventory_impairment_ratio']
                pre_goodwill = commercial+inputs['other_pbt_cny']-inventory_loss-inputs['other_asset_impairment_cny']
                pbt = pre_goodwill-inputs['goodwill_impairment_cny']
                tax_base = max(pre_goodwill, Decimal(0))
                tax = tax_base*inputs['tax_research_rate']
                rows.append(dict(year=raw['year'], currency='CNY', inputs=inputs,
                    opening_revenue_cny=previous, revenue_cny=revenue,
                    commercial_cost_ratio=1-inputs['commercial_margin'],
                    commercial_cost_ratio_delta=(1-inputs['commercial_margin']-cost_ratio0)
                        if cost_ratio0 is not None else None,
                    commercial_cost_cny=revenue-commercial, commercial_subtotal_cny=commercial,
                    inventory_impairment_cny=inventory_loss, goodwill_impairment_cny=inputs['goodwill_impairment_cny'],
                    other_asset_impairment_cny=inputs['other_asset_impairment_cny'], other_pbt_cny=inputs['other_pbt_cny'],
                    pre_goodwill_pbt_cny=pre_goodwill, tax_research_base_cny=tax_base,
                    tax_research_rate=inputs['tax_research_rate'], group_pbt_cny=pbt,
                    operating_bridge_residual_cny=pbt-(commercial+inputs['other_pbt_cny']-inventory_loss
                        -inputs['other_asset_impairment_cny']-inputs['goodwill_impairment_cny'])))
                pbts.append(pbt)
                taxes.append(dict(basis='amount_cny', value=tax))
                ncis.append(inputs['signed_nci_cny'])
            parent = build_signed_parent_profit_path(years=list(range(1, 6)), group_pbt_cny=pbts,
                tax_assumptions=taxes, signed_nci_cny=ncis, currency='CNY')
            for row, parent_row in zip(rows, parent['rows']):
                row.update(parent_row)
                contributions = dict(
                    commercial_subtotal_change_cny=row['commercial_subtotal_cny']-commercial0,
                    asset_impairment_change_cny=-row['inventory_impairment_cny']
                        -row['goodwill_impairment_cny']-row['other_asset_impairment_cny']-history['asset_impairment'],
                    other_pbt_change_cny=row['other_pbt_cny']-reference['other_pbt_cny'],
                    income_tax_change_cny=history['income_tax']-_decimal(row['income_tax_cny']),
                    signed_nci_change_cny=history['minority_profit']-_decimal(row['signed_nci_cny']))
                change = _decimal(row['parent_profit_cny'])-history['parent_profit']
                row['change_from_historical_parent'] = dict(contributions,
                    parent_profit_change_cny=change, residual_cny=change-sum(contributions.values()))
            output[name] = dict(rows=rows)
        return _plain(dict(status='CONDITIONAL_EARNINGS_RESEARCH_NOT_APPROVED', historical_reference=reference,
            scenarios=output, action='no_order', currency='CNY', precision=48,
            scope='EXPLICIT_COMMERCIAL_LOSS_TAX_NCI_HYPOTHESES_NOT_VALUATION',
            parent_change_comparison_scope='HISTORICAL_REPORTED_PARENT_NOT_EX_NONRECURRING_OR_NORMALIZED',
            normalized_parent_profit_cny=None, economic_approval=False,
            formulas=dict(revenue='previous_revenue*(1+revenue_growth)',
                commercial='revenue*commercial_margin', inventory_loss='revenue*inventory_impairment_ratio',
                pre_goodwill_pbt='commercial+other_pbt-inventory_loss-other_asset_loss',
                group_pbt='pre_goodwill_pbt-goodwill_loss',
                tax='max(pre_goodwill_pbt,0)*tax_research_rate',
                parent_profit='group_pbt-income_tax-signed_nci',
                historical_other_pbt='historical_PBT-historical_commercial-historical_signed_asset_impairment'),
            limitations=['Historical other PBT includes unseparated finance/credit/other contributions, not certified recurring earnings.',
                'Future losses are explicit deductions, not historical impairment addbacks or equity restoration.',
                'The five-contribution bridge compares reported parent profit only; reduced losses are not attributed to commercial improvement.',
                'Tax ignores a goodwill tax shield by research assumption, not by a tax-law conclusion; no automatic loss tax benefit.',
                'Signed NCI is supplied each year; negative NCI need not persist or converge by default.',
                'Undefined historical cost ratios at zero revenue remain null, not zero.',
                'Scenario labels follow caller hypotheses, not numerical sorting; no cash, price, valuation or approval.']))
