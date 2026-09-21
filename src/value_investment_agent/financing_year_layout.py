"""Bounded year-heading financing table research; no debt scope approval."""
import re
from decimal import Decimal

from .financing_rollforward import AMOUNTS, reconciles
from .financing_table import TITLE, financing_label_category

TOKEN = re.compile(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}|(?<!\S)-(?!\S)')


def extract_year_financing(layout):
    lines = layout.splitlines()
    compact = [''.join(s.split()) for s in lines]
    if compact.count(TITLE) != 1:
        return None
    start = compact.index(TITLE)
    if '（除特别注明外，金额单位为人民币元）' not in compact[:start]:
        return None
    section = []
    for line in lines[start + 1:]:
        if re.match(r'^\s*[（(]\s*\d+\s*[）)]', line):
            break
        if line.strip():
            section.append(line)
    if len(section) < 4 or ''.join(section[0].split()) != '项目年初数本年增加本年减少年末数':
        return None
    if ''.join(section[1].split()) != '现金变动非现金变动现金变动非现金变动':
        return None
    rows = []
    for line in section[2:]:
        matches = list(TOKEN.finditer(line))
        if not matches:
            # This exact known continuation must stay attached to its row.
            if rows and rows[-1]['label'] == '一年内到期的' and line.strip() == '非流动负债':
                rows[-1]['label'] += '非流动负债'
                rows[-1]['excerpt'] += '\n' + line
                continue
            return None
        if len(matches) != 6:
            return None
        label = ''.join(line[:matches[0].start()].split())
        remainder = TOKEN.sub('', line[matches[0].start():])
        if not label or remainder.strip() or not re.fullmatch(r'[\u4e00-\u9fff]+', label):
            return None
        amounts = dict(zip(AMOUNTS, [None if m.group() == '-' else m.group().replace(',', '') for m in matches]))
        rows.append({'label': label, 'amounts': amounts, 'excerpt': line,
                     'label_category': financing_label_category(label)})
    if not rows or rows[-1]['label'] != '合计' or len({r['label'] for r in rows}) != len(rows):
        return None
    total = rows.pop()
    if not rows or any(r['label'] == '合计' for r in rows) or not reconciles(total['amounts']):
        return None
    balances = all(all(r['amounts'][f] is not None for r in rows)
                   and sum(Decimal(r['amounts'][f]) for r in rows) == Decimal(total['amounts'][f])
                   for f in ('opening', 'closing'))
    return {'rows': rows, 'total': {**total, 'unit': 'CNY'}, 'balances_reconcile': balances,
            'full_movements_reconcile': False, 'complete_debt_verified': False,
            'status': 'extracted_scope_unverified', 'parser': 'year-heading-financing-v1'}
