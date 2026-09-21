"""Explicit current-maturity note components; unknown cells are never zero."""
from decimal import Decimal
import re

from .financing_table import amount_from_fragments


TITLE = '一年内到期的非流动负债'
CATEGORIES = {
    '一年内到期的长期借款': 'current_borrowings',
    '一年内到期的租赁负债': 'current_leases',
    '一年内到期的应付债券': 'current_bonds',
    '一年内到期的长期应付款': 'current_payables_require_terms',
    '一年内到期的远期外汇合约': 'derivatives_separate_scope',
}


def extract_current_maturities(cells, context):
    lines = [''.join(line.split()) for line in context.splitlines() if line.strip()]
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r'\d+[、.．]' + TITLE, line)]
    if len(starts) != 1:
        return None
    suffix = lines[starts[0] + 1:]
    if suffix and re.fullmatch(r'[\uf052\u2611\u221a]适用□不适用', suffix[0]):
        suffix = suffix[1:]
    unit = re.fullmatch(r'单位：(元|千元)(?:币种：人民币)?', suffix[0]) if len(suffix) == 1 else None
    if unit is None:
        return None
    multiplier = Decimal(1000) if unit[1] == '千元' else Decimal(1)
    if len(cells) < 3 or cells[0] is None:
        return None
    source_cells = cells
    header = [''.join((x or '').split()) for x in cells[0]]
    # A known nine-grid PDF layout has three semantic columns and explicit
    # merged-cell placeholders. Never drop all blanks: some are missing amounts.
    if header in (['', '项目', '', '', '期末余额', '', '', '期初余额', ''],
                  ['', '项目', '', '', '期末余额', '', '期初余额', '']):
        normalized = []
        for row in cells[1:]:
            placeholders = (4, 5, 7, 8) if len(header) == 9 else (4, 5, 7)
            if len(row) != len(header) or any(row[i] is not None for i in placeholders):
                return None
            if row[0] == '' and row[2] == '':
                label = row[1]
            elif row[0] and row[1] is None and row[2] is None:
                label = row[0]
            else:
                return None
            normalized.append([label, row[3], row[6]])
        cells = [['项目', '期末余额', '期初余额']] + normalized
    if [''.join((x or '').split()) for x in cells[0]] != ['项目', '期末余额', '期初余额']:
        return None
    rows = []
    for index, raw in enumerate(cells[1:], 1):
        if len(raw) != 3 or any(x is None for x in raw):
            return None
        label = ''.join(raw[0].split())
        if not label:
            return None
        amounts = {}
        for field, cell in zip(('closing', 'opening'), raw[1:]):
            parts = cell.split()
            value = None if not parts or parts == ['-'] else amount_from_fragments(parts)
            if value is None and len(parts) == 1 and re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)', parts[0]):
                value = parts[0].replace(',', '')
            if parts and parts != ['-'] and (value is None or Decimal(value) < 0):
                return None
            if value is not None and multiplier != 1:
                value = str(Decimal(value) * multiplier)
            amounts[field] = value
        rows.append({'label': label, 'amounts': amounts, 'raw_cells': source_cells[index],
                     'category': CATEGORIES.get(label, 'requires_note_classification')})
    if rows[-1]['label'] != '合计' or any(r['label'] == '合计' for r in rows[:-1]):
        return None
    if len({r['label'] for r in rows}) != len(rows):
        return None
    total = rows.pop()
    checks = {}
    for field in ('closing', 'opening'):
        checks[field] = (total['amounts'][field] is not None
            and all(r['amounts'][field] is not None for r in rows)
            and sum(Decimal(r['amounts'][field]) for r in rows) == Decimal(total['amounts'][field]))
    return {'rows': rows, 'total': {**total, 'unit': 'CNY'}, 'reconciliation': checks,
            'context': context, 'complete_debt_verified': False,
            'source_unit': 'CNY_thousand' if multiplier == 1000 else 'CNY',
            'normalization_multiplier': str(multiplier),
            'parser': 'current_maturity_cells_v3_explicit_units', 'status': 'research_components_scope_unverified'}


def extract_current_maturity_continuation(cells, next_cells, context, tail, prefix):
    """Join adjacent ruled tables only when no intervening content is present."""
    header = ['项目', '期末余额', '期初余额']
    if not cells or cells[0] != header or any(len(r) != 3 for r in cells):
        return None
    if any(''.join((r[0] or '').split()) == '合计' for r in cells[1:]):
        return None
    tail_lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if len(tail_lines) != 1 or not re.fullmatch(r'\d+', tail_lines[0]):
        return None
    prefix_lines = [''.join(line.split()) for line in prefix.splitlines() if line.strip()]
    if len(prefix_lines) != 1 or not re.fullmatch(r'[^\d]+公司20\d{2}年年度报告(?:全文)?', prefix_lines[0]):
        return None
    if not next_cells or any(len(r) != 3 for r in next_cells):
        return None
    following = next_cells[1:] if next_cells[0] == header else next_cells
    if not following or not ''.join((following[0][0] or '').split()).startswith('一年内到期的'):
        return None
    result = extract_current_maturities(cells + following, context)
    if result:
        result.update(previous_table_cells=cells, continuation_table_cells=next_cells,
                      previous_page_tail=tail, next_page_prefix=prefix,
                      parser='current_maturity_cells_v2_adjacent_continuation')
    return result


def extract_borderless_current_maturities(header, boxes, words, context):
    """Use the observed ruled header geometry for a same-page unruled body."""
    if header != ['项目', '期末余额', '期初余额'] or len(boxes) != 3 or any(b is None for b in boxes):
        return None
    if any(b[0] >= b[2] or b[1] >= b[3] for b in boxes):
        return None
    if any(abs(boxes[i][2] - boxes[i + 1][0]) > 0.5 for i in (0, 1)):
        return None
    if any(abs(b[1] - boxes[0][1]) > 0.5 or abs(b[3] - boxes[0][3]) > 0.5 for b in boxes):
        return None
    lines = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if not word['text'].strip():
            continue
        if word['top'] < boxes[0][3] - 0.5:
            return None
        if not lines or abs(word['top'] - lines[-1][0]['top']) > 1.5:
            lines.append([])
        lines[-1].append(word)
    cells = [header]
    retained = []
    for line in lines:
        parts = [[], [], []]
        for word in sorted(line, key=lambda w: w['x0']):
            columns = [i for i, box in enumerate(boxes)
                       if word['x0'] >= box[0] - 0.5 and word['x1'] <= box[2] + 0.5]
            if len(columns) != 1:
                return None
            parts[columns[0]].append(word['text'])
        label = ''.join(parts[0]).replace(' ', '')
        if label != '合计' and not label.startswith('一年内到期的'):
            return None
        cells.append([label, ' '.join(parts[1]), ' '.join(parts[2])])
        retained.extend(line)
        if label == '合计':
            result = extract_current_maturities(cells, context)
            if result:
                result.update(header_cell_boxes=boxes, body_words=retained,
                              parser='current_maturity_geometry_v1_same_page')
            return result
    return None
