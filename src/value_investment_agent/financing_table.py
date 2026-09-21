"""Extract a six-column financing-note total from pypdf layout text."""
import re
from decimal import Decimal
from .financing_rollforward import AMOUNTS, reconciles, reconciles_table

TITLE = '\u7b79\u8d44\u6d3b\u52a8\u4ea7\u751f\u7684\u5404\u9879\u8d1f\u503a\u53d8\u52a8\u60c5\u51b5'
NUMBER = re.compile(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.(?:\d{2})?')
COMPLETE_AMOUNT = re.compile(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}')


def amount_from_fragments(parts):
    if not 1 <= len(parts) <= 2:
        return None
    if any(not part or not re.fullmatch(r'-?[\d,.]+',part) for part in parts):
        return None
    if len(parts)==2 and COMPLETE_AMOUNT.fullmatch(parts[0]):
        return None
    value = ''.join(parts)
    return value.replace(',','') if COMPLETE_AMOUNT.fullmatch(value) else None


def financing_applicability(layout):
    lines = [''.join(line.split()) for line in layout.splitlines()]
    starts = [i for i,line in enumerate(lines) if line == TITLE]
    if not starts:
        return 'section_not_found'
    if len(starts)!=1:
        return 'ambiguous_section'
    markers = [line for line in lines[starts[0]+1:] if line][:1]
    if not markers:
        return 'unspecified'
    for checked in ('\uf052','\u2611','\u221a'):
        if markers[0] == '\u25a1\u9002\u7528'+checked+'\u4e0d\u9002\u7528':
            return 'declared_not_applicable'
        if markers[0] == checked+'\u9002\u7528\u25a1\u4e0d\u9002\u7528':
            return 'declared_applicable'
    return 'unspecified'


def financing_label_category(label):
    label = ''.join(label.split()).replace('（','(').replace('）',')')
    if label in ('应付股利','其他应付款-应付股利','其他应付款—应付股利'):
        return 'dividends_excluded'
    for name,category in (('短期借款','borrowings'),('长期借款','borrowings'),('银行借款','borrowings'),
                          ('应付债券','bonds'),('短期应付债券','bonds'),('租赁负债','leases')):
        if label == name or label in (name+'(含一年内到期)',name+'(含一年内到期部分)',name+'(含一年内到期的'+name+')'):
            return category
    return 'requires_note'


def extract_financing_total(layout):
    if financing_applicability(layout) == 'declared_not_applicable':
        return None
    lines = layout.splitlines()
    starts = [i for i,line in enumerate(lines) if ''.join(line.split()) == TITLE]
    if len(starts) != 1:
        return None
    start = starts[0]
    section = []
    for line in lines[start+1:]:
        if re.match(r'^\s*[（(]\s*\d+\s*[）)]',line):
            break
        section.append(line)
    compact = [''.join(line.split()) for line in section]
    if '\u5355\u4f4d\uff1a\u5143' not in compact:
        return None
    header = '\u9879\u76ee\u671f\u521d\u4f59\u989d\u672c\u671f\u589e\u52a0\u672c\u671f\u51cf\u5c11\u671f\u672b\u4f59\u989d'
    subheader = '\u73b0\u91d1\u53d8\u52a8\u975e\u73b0\u91d1\u53d8\u52a8' * 2
    if header not in compact or subheader not in compact:
        return None
    totals = [i for i,line in enumerate(section) if re.match(r'^\s*\u5408\u8ba1\s+',line)]
    if len(totals)!=1 or totals[0] <= compact.index(subheader):
        return None
    index = totals[0]
    line = section[index]
    matches = list(NUMBER.finditer(line))
    if len(matches)!=6 or re.sub(r'\s|\u5408\u8ba1','',NUMBER.sub('',line)):
        return None
    values = [m.group() for m in matches]
    incomplete = [i for i,value in enumerate(values) if value.endswith('.')]
    if incomplete:
        if index+1>=len(section):
            return None
        tails = list(re.finditer(r'\S+',section[index+1]))
        if len(tails)!=len(incomplete):
            return None
        for position,tail in zip(incomplete,tails):
            if not re.fullmatch(r'\d{2}',tail.group()) or abs(tail.end()-matches[position].end())>2:
                return None
            values[position] += tail.group()
    amounts = dict(zip(AMOUNTS,[value.replace(',','') for value in values]))
    if not reconciles(amounts):
        return None
    return {'amounts':amounts,'unit':'CNY','line_number':start+index+2,
            'excerpt':'\n'.join(section[index:index+2 if incomplete else index+1]),
            'status':'total_reconciled_components_and_scope_unverified'}


def extract_financing_components(layout):
    total = extract_financing_total(layout)
    if total is None:
        return None
    lines = layout.splitlines()
    total_index = total['line_number']-1
    anchors = list(NUMBER.finditer(lines[total_index]))
    boundaries = [max(0,anchors[0].start()-2)] + [
        (left.end()+right.start())//2 for left,right in zip(anchors,anchors[1:])]
    boundaries.append(max(len(line) for line in lines)+1)
    subheader = '\u73b0\u91d1\u53d8\u52a8\u975e\u73b0\u91d1\u53d8\u52a8'*2
    starts = [i for i,line in enumerate(lines[:total_index]) if ''.join(line.split())==subheader]
    if len(starts)!=1:
        return None
    prefixes = ('短期借款','长期借款','应付债券','短期应付债券','租赁负债',
                '其他流动负债','长期应付款','其他应付款','应付股利')
    groups = []
    for index in range(starts[0]+1,total_index):
        line = lines[index]
        if not line.strip():
            continue
        label = ''.join(line[:boundaries[0]].split())
        previous_label = ''.join(part[:boundaries[0]] for part in groups[-1][1]) if groups else ''
        parentheses_open = (previous_label.count('（')+previous_label.count('(')
                            > previous_label.count('）')+previous_label.count(')'))
        if label.startswith(prefixes) and not parentheses_open:
            groups.append((index,[]))
        if not groups:
            return None
        groups[-1][1].append(line)
    rows = []
    for index,group in groups:
        label = ''.join(''.join(line[:boundaries[0]].split()) for line in group)
        amounts = {}
        for field,left,right in zip(AMOUNTS,boundaries,boundaries[1:]):
            parts = [line[left:right].strip() for line in group if line[left:right].strip()]
            if not parts:
                amounts[field] = None
                continue
            value = amount_from_fragments(parts)
            if value is None:
                return None
            amounts[field] = value
        rows.append({'label':label,'amounts':amounts,'line_number':index+1,'excerpt':'\n'.join(group),
                     'label_category':financing_label_category(label)})
    if not rows or len({row['label'] for row in rows})!=len(rows):
        return None
    balances_agree = all(all(row['amounts'][field] is not None for row in rows) and
        sum(Decimal(row['amounts'][field]) for row in rows)==Decimal(total['amounts'][field])
        for field in ('opening','closing'))
    return {'total':total,'rows':rows,'balances_reconcile':balances_agree,
            'full_movements_reconcile':reconciles_table([r['amounts'] for r in rows],total['amounts']),
            'complete_debt_verified': False, 'status':'extracted_scope_unverified'}
