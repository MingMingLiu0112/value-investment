"""Research-only parsing of ruled PDF cells; blanks never become zero."""
from decimal import Decimal
import re

from .financing_rollforward import AMOUNTS, reconciles, reconciles_table
from .financing_table import TITLE, amount_from_fragments, financing_label_category


def extract_financing_cells(cells, context):
    compact = ''.join(context.split())
    units = re.findall(r'单位：((?:千)?元)(?:币种：人民币)?$', compact)
    if TITLE not in compact or len(units) != 1:
        return None
    multiplier = Decimal(1000) if units[0] == '千元' else Decimal(1)
    if len(cells) < 4:
        return None
    headers = [[''.join(c.split()) for c in row if c and c.strip()] for row in cells[:2]]
    if headers != [['项目', '期初余额', '本期增加', '本期减少', '期末余额'],
                   ['现金变动', '非现金变动', '现金变动', '非现金变动']]:
        return None
    rows = []
    for index, raw in enumerate(cells[2:], 3):
        # PDF merged-cell placeholders are None; empty actual cells stay present.
        values = [cell for cell in raw if cell is not None]
        if len(values) != 7:
            return None
        label = ''.join(values[0].split())
        if not label or (label == '合计' and index != len(cells)):
            return None
        amounts = {}
        for field, cell in zip(AMOUNTS, values[1:]):
            parts = cell.split()
            if parts == ['-']:
                amounts[field] = None
                continue
            # PDF line wrapping can separate a unary minus inside one ruled cell.
            if 2 <= len(parts) <= 3 and parts[0] == '-' and re.match(r'^\d', parts[1]):
                parts = ['-' + parts[1], *parts[2:]]
            amount = amount_from_fragments(parts) if parts else None
            if (amount is None and multiplier == 1000 and len(parts) == 1
                    and re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)', parts[0])):
                amount = parts[0].replace(',', '')
            if parts and amount is None:
                return None
            if amount is not None and multiplier != 1:
                amount = str(Decimal(amount) * multiplier)
            amounts[field] = amount
        rows.append({'label': label, 'amounts': amounts, 'raw_cells': raw,
                     'table_row': index, 'label_category': financing_label_category(label)})
    if rows[-1]['label'] != '合计' or len({r['label'] for r in rows}) != len(rows):
        return None
    total = rows.pop()
    if not reconciles(total['amounts']):
        return None
    balances = all(all(row['amounts'][field] is not None for row in rows) and
                   sum(Decimal(row['amounts'][field]) for row in rows) == Decimal(total['amounts'][field])
                   for field in ('opening', 'closing'))
    return {'total': {**total, 'unit': 'CNY'}, 'rows': rows,
            'source_unit': 'CNY_thousand' if multiplier == 1000 else 'CNY',
            'normalization_multiplier': str(multiplier),
            'balances_reconcile': balances,
            'full_movements_reconcile': reconciles_table([r['amounts'] for r in rows], total['amounts']),
            'complete_debt_verified': False,
            'status': 'extracted_scope_unverified', 'parser': 'ruled_financing_cells_v3_wrapped_sign'}
