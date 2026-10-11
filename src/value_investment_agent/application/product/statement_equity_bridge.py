"""Reconcile a bound consolidated statement without approving future clean surplus."""
from decimal import Decimal
import re

from ...domain.valuation.equity_reconciliation import reconcile_equity_movements


_LABELS = {
    'opening': '二、本年期初余额',
    'closing': '四、本期期末余额',
    'change': '三、本期增减变动金额',
    'comprehensive': '（一）综合收益总额',
    'contribution': '（二）所有者投入和减少资本',
    'distribution': '（三）利润分配',
    'reserve': '（五）专项储备',
    'other': '（六）其他',
}


def reconcile_statement_equity(*, spec: dict, period_end: str, expected_equity: Decimal,
        current_source_id: str, pages: dict, verify_excerpt) -> dict:
    """Amounts are CNY; parent, minority and total remain separate throughout."""
    if (spec.get('schema_version') != 'consolidated-equity-statement-bridge-v1'
            or spec.get('unit') != 'CNY' or spec.get('scope') != 'consolidated_parent_attributable'
            or spec.get('period_end') != period_end or spec.get('source_id') != current_source_id
            or set(spec.get('rows', {})) != set(_LABELS)):
        raise ValueError('equity bridge identity/unit/scope/period mismatch')
    header_page = spec['header_page']
    verify_excerpt(current_source_id, header_page, '合并所有者权益变动表')
    header = ''.join(pages[current_source_id][header_page - 1].split())
    year = int(period_end[:4])
    if (period_end != f'{year}-06-30' or f'{year}年1—6月' not in header
            or '归属于母公司所有者权益' not in header
            or '少数股东权益所有者权益合计' not in header or '单位：元币种：人民币' not in header):
        raise ValueError('equity bridge statement header does not establish current consolidated columns')
    amounts = {}
    for key, label in _LABELS.items():
        row = spec['rows'][key]
        page = row['physical_page']
        if type(page) is not int or page not in {header_page, header_page + 1}:
            raise ValueError('equity bridge row must belong to the bound current statement')
        excerpt = row['evidence_excerpt']
        verify_excerpt(current_source_id, page, excerpt)
        if not ''.join(excerpt.split()).startswith(label):
            raise ValueError('equity bridge row label mismatch')
        numbers = [Decimal(value.replace(',', '')) for value in
                   re.findall(r'-?\d[\d,]*\.\d{2}', excerpt)]
        if len(numbers) < (2 if key == 'contribution' else 3):
            raise ValueError('equity bridge row lacks declared ownership columns')
        if key == 'contribution':
            if len(numbers) != 2 or numbers[0] != numbers[1]:
                raise ValueError('equity bridge contribution requires equal minority and total columns')
            # Equal observed minority/total columns prove zero parent contribution;
            # an empty PDF cell alone is never converted to a zero fact.
            parent, minority, total = numbers[1] - numbers[0], *numbers
        else:
            parent, minority, total = numbers[-3:]
        declared = row.get('parent_value')
        if declared is None or not Decimal(str(declared)).is_finite() or Decimal(str(declared)) != parent:
            raise ValueError('equity bridge amount differs from the parent subtotal column')
        if parent + minority != total:
            raise ValueError('equity bridge parent/minority/total columns do not reconcile')
        amounts[key] = dict(parent=parent, minority=minority, total=total)
    components = spec['comprehensive_components']
    profit, oci = Decimal(components['parent_profit_cny']), Decimal(components['parent_oci_cny'])
    comprehensive_numbers = [Decimal(value.replace(',', '')) for value in
        re.findall(r'-?\d[\d,]*\.\d{2}', spec['rows']['comprehensive']['evidence_excerpt'])]
    if (len(comprehensive_numbers) != 5 or comprehensive_numbers[:2] != [oci, profit]):
        raise ValueError('equity bridge profit/OCI components do not reconcile')
    calculation = reconcile_equity_movements(amounts=amounts, expected_equity=expected_equity, profit=profit, oci=oci)
    treasury = spec.get('treasury_disclosure')
    if treasury is not None:
        if ''.join(treasury.get('evidence_excerpt', '').split()) != '56、库存股□适用√不适用':
            raise ValueError('equity bridge treasury disclosure is not an explicit not-applicable statement')
        verify_excerpt(current_source_id, treasury['physical_page'], treasury['evidence_excerpt'])
        if f'{year}年半年度报告' not in ''.join(pages[current_source_id][treasury['physical_page'] - 1].split()):
            raise ValueError('equity bridge treasury disclosure is not from the current report')
    return dict(schema_version='consolidated-equity-statement-bridge-result-v1',
        status='ACCOUNTING_RECONCILED_NOT_MODEL_APPROVAL', period_end=period_end, unit='CNY',
        scope='consolidated_parent_attributable', source_id=current_source_id,
        source_rows=spec['rows'], header_page=header_page,
        treasury_disclosure=None if treasury is None else dict(**treasury,
            status='H1_DISCLOSED_NOT_APPLICABLE_NOT_CURRENT_DILUTION_APPROVAL', period_end=period_end),
        ownership_amounts={key: {scope: str(value) for scope, value in row.items()} for key, row in amounts.items()},
        **calculation,
        future_clean_surplus_assumption_approved=False, sustainable_distribution_approved=False,
        normalized_profit_approved=False, action='no_order')
