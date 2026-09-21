"""Narrow transposed financing-note balance extraction, scope never approved."""
import re
from decimal import Decimal


def _total_movements(text, opening, closing):
    labels = ('筹资活动产生的现金流量净额', '本年支付的借款利息',
              '本年计提的利息', '其他非现金变动(i)')
    number = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
    token = r'(?:' + number + r'|\(' + number + r'\)|-)'
    compact = re.sub(r'筹资活动产生的现金流量\s+净额', labels[0], text)
    lines = [line.strip() for line in compact.splitlines() if line.strip()]
    if len(lines) != len(labels):
        return {'status': 'unsupported_movements', 'reconciles': False}
    totals = []
    for label, line in zip(labels, lines):
        expression = (r'^' + r'\s*'.join(re.escape(c) for c in label)
                      + r'\s+' + r'\s+'.join(['(' + token + ')'] * 4) + r'$')
        match = re.fullmatch(expression, line)
        if not match or match[4] == '-':
            return {'status': 'unknown_movement_total', 'reconciles': False}
        value = match[4].replace(',', '')
        totals.append(-Decimal(value[1:-1]) if value.startswith('(') else Decimal(value))
    agrees = Decimal(opening) + sum(totals) == Decimal(closing)
    return {'status': 'total_reconciled' if agrees else 'total_mismatch',
            'reconciles': agrees, 'signed_totals_thousand_cny': list(map(str, totals))}


def extract_transposed_balances(layout):
    title = '筹资活动产生的各项负债的变动情况'
    if layout.count(title) != 1:
        return None
    before, section = layout.split(title)
    context = ''.join(before.split())
    if ('金额单位为人民币千元' not in context
            or '合并财务报表项目附注' not in context
            or any(label in context for label in ('母公司财务报表', '母公司报表', '预测'))):
        return None
    section = re.split(r'\n\s*\(i\)', section, maxsplit=1)[0]
    compact = ''.join(section.split())
    if not compact.startswith('银行借款及其他应付债券租赁负债(含一年内到期)(含一年内到期)(含一年内到期)合计'):
        return None
    number = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
    pattern = (r'^\s*(20\d{2})\s*年\s*12\s*月\s*31\s*日\s+'
               + r'\s+'.join(['(' + number + ')'] * 4) + r'\s*$')
    matches = list(re.finditer(pattern, section, re.MULTILINE))
    if len(matches) != 2 or int(matches[1][1]) != int(matches[0][1]) + 1:
        return None
    balances = []
    for match in matches:
        values = [Decimal(v.replace(',', '')) for v in match.groups()[1:]]
        if sum(values[:3]) != values[3]:
            return None
        balances.append({'period': match[1] + '-12-31',
                         'values_thousand_cny': [str(v) for v in values],
                         'total_cny': str(values[3] * 1000), 'excerpt': match.group().strip()})
    movements = section[matches[0].end():matches[1].start()].strip()
    movement_check = _total_movements(movements, balances[0]['values_thousand_cny'][3],
                                     balances[1]['values_thousand_cny'][3])
    return {'columns': ['bank_borrowings_and_other', 'bonds', 'leases', 'total'],
            'statement_scope': 'consolidated_note_explicit',
            'current_portions_included': True, 'balances': balances,
            'movements_raw': movements, 'total_movement_check': movement_check,
            'balances_reconcile': True, 'full_movements_reconcile': False,
            'complete_debt_verified': False, 'status': 'balances_only_scope_unverified'}
