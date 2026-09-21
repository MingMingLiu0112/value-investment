"""Research candidates from explicit dated per-share tables, never approved values."""
import re
from datetime import date
from decimal import Decimal, localcontext


def extract_dated_share_counts(pages):
    """Retain explicitly dated issued-share counts, not dividend entitlement."""
    pattern = re.compile(r'截至\s*(20\d{2})\s*年\s*12\s*月\s*31\s*日[，,]?\s*'
                         r'(?:本公司|公司)\s*总股本(?:为)?\s*'
                         r'([\d,]+(?:\.\d+)?)\s*(万股|股)')
    rows = []
    for page_number, text in enumerate(pages, 1):
        for match in pattern.finditer(text):
            value = Decimal(match[2].replace(',', '')) * (10000 if match[3] == '万股' else 1)
            if value <= 0 or value != value.to_integral_value():
                continue
            rows.append({'field_name': 'ending_total_shares', 'value': str(value),
                         'unit': 'shares', 'period_label': match[1] + '-12-31',
                         'page': page_number, 'excerpt': match.group(),
                         'status': 'candidate_pending_automated_verification',
                         'equity_scope_verified': False, 'backtest_ready': False})
    return rows


def extract_summary_bvps(pages):
    """Derive research candidates, not approved ordinary-share book values."""
    return _extract_summary_bvps(pages, dated_shares=False)


def extract_linked_bvps(pages):
    """Join current equity to explicit same-period shares within one report only."""
    return _extract_summary_bvps(pages, dated_shares=True)


def _extract_summary_bvps(pages, dated_shares):
    from .filing_extract import _disclosed_amount_unit, _number_after_label
    results = []
    share_rows = extract_dated_share_counts(pages) if dated_shares else []
    for page_number, page in enumerate(pages, 1):
        if '主要会计数据' not in page or _disclosed_amount_unit(page) != ('CNY', 1):
            continue
        if any(word in page for word in ('预测', '母公司', '国际财务报告准则')):
            continue
        headers = list(re.finditer(r'(20\d{2})\s*年末\s+(20\d{2})\s*年末', page))
        if len(headers) != 1 or int(headers[0][1]) != int(headers[0][2]) + 1:
            continue
        header = headers[0]
        section = re.split(r'(?m)^\s*(?:[（(][一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+、)',
                           page[header.end():], maxsplit=1)[0]
        labels = ('归属于上市公司股东的净资产', '期末总股本')
        if dated_shares:
            labels = labels[:1]
        values = []
        for label in labels:
            pattern = r'\s*'.join(map(re.escape, label))
            if len(re.findall(pattern, section)) != 1:
                break
            value = _number_after_label(section, label, bare_footnote=False,
                                        wrapped_label=True, monetary=True)
            if value is None:
                break
            values.append(value)
        if len(values) != len(labels):
            continue
        evidence = []
        if dated_shares:
            evidence = [row for row in share_rows if row['period_label'] == header[1] + '-12-31']
            if not evidence or len({Decimal(row['value']) for row in evidence}) != 1:
                continue
            values.append((evidence[0]['value'],))
        equity, shares = (Decimal(value[0]) for value in values)
        if not equity.is_finite() or not shares.is_finite() or shares <= 0 or shares != shares.to_integral_value():
            continue
        with localcontext() as context:
            context.prec = 28
            bvps = str(equity / shares)
        results.append({'field_name': 'bvps', 'value': bvps, 'unit': 'CNY/share',
                        'period_label': header[1] + '-12-31', 'page': page_number,
                        'excerpt': header.group() + '\n' + section,
                        'derivation_formula': 'attributable_net_assets / ending_total_shares',
                        'input_values': {'attributable_net_assets_cny': str(equity),
                                         'ending_total_shares': str(shares)},
                        'status': 'candidate_pending_automated_verification',
                        'equity_scope_verified': False, 'backtest_ready': False})
        if dated_shares:
            results[-1]['share_evidence'] = evidence
            results[-1]['equity_column'] = 'current_year_first_column'
            results[-1]['comparatives_used'] = False
    return results


def extract_dated_bvps(pages):
    results = []
    date_pattern = r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    header_pattern = re.compile(r'(?:于\s*)?' + date_pattern + r'\s+(?:于\s*)?'
                                + date_pattern + r'\s*(?:[（(]重述[）)]\s*)?变化(?:\s*[（(]%[）)])?')
    row_pattern = re.compile(r'每股净资产\s+元[/／]股\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)(?:\s+.*)?')
    for page_number, page in enumerate(pages, 1):
        section = re.split(r'[八九十]+[、.]\s*境内外会计准则', page, maxsplit=1)[0]
        # Match values on the original text: whitespace separates numeric columns.
        wrapped = re.search(
            r'于\s*(20\d{2})\s*年\s*12\s*月\s*31\s*日\s*于\s*(20\d{2})\s*年\s*12\s*月\s*31\s*日'
            r'\s*变化\s*[（(]%[）)]\s*于\s*(20\d{2})\s*年\s*12\s*月\s*31\s*日'
            r'(?P<restated>\s*重述后\s+重述前(?:\s+重述后\s+重述前)?)?'
            r'\s*每股净资产[（(]元[/／]股[）)][ \t]*(?P<values>[^\r\n]+)', section)
        values = wrapped['values'].split() if wrapped else []
        restatement_groups = wrapped['restated'].count('重述后') if wrapped and wrapped['restated'] else 0
        columns_valid = (len(values) == 4 + restatement_groups
                         and all(re.fullmatch(r'\(?-?\d+(?:\.\d+)?\)?', v) for v in values))
        if (wrapped
                and columns_valid
                and int(wrapped[1]) == int(wrapped[2]) + 1 == int(wrapped[3]) + 2
                and re.search(r'[（(][一二三四五六七八九十]+[）)]\s*主要财务指标', section)
                and not any(word in section for word in ('预测', '母公司', '国际财务报告准则'))):
            results.append({'field_name': 'bvps', 'value': values[0], 'unit': 'CNY/share',
                            'period_label': wrapped[1] + '-12-31', 'page': page_number,
                            'excerpt': wrapped.group(),
                            'comparative_restatement_columns': bool(wrapped['restated']),
                            'comparative_restatement_groups': restatement_groups,
                            'status': 'candidate_pending_automated_verification',
                            'equity_scope_verified': False})
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for row_index, row_line in enumerate(lines):
            row = row_pattern.fullmatch(row_line)
            if not row:
                continue
            # Dates and the comparative restatement label may span several lines.
            header = None
            for index in range(max(0, row_index - 8), row_index):
                line = '\n'.join(lines[index:row_index])
                header = header_pattern.fullmatch(line)
                if header:
                    break
            if not header:
                continue
            if '%' in line and not re.fullmatch(
                    r'每股净资产\s+元[/／]股\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?'
                    r'\s+(?:-?\d+(?:\.\d+)?|\(\d+(?:\.\d+)?\))', row_line):
                continue
            try:
                current = date(*map(int, header.groups()[:3]))
                previous = date(*map(int, header.groups()[3:]))
            except ValueError:
                continue
            if current.month != 12 or current.day != 31 or previous != date(current.year - 1, 12, 31):
                continue
            context = '\n'.join(lines[max(0, index - 10):index])
            if not re.search(r'本集团\s*' + str(current.year) + r'\s*年度主要财务指标如下[：:]', context):
                continue
            if any(word in context for word in ('预测', '母公司', '国际财务报告准则')):
                continue
            results.append({'field_name': 'bvps', 'value': row[1], 'unit': 'CNY/share',
                            'period_label': current.isoformat(), 'page': page_number,
                            'excerpt': line + '\n' + row_line,
                            'comparative_restatement_columns': '重述' in line,
                            'status': 'candidate_pending_automated_verification',
                            'equity_scope_verified': False})
    return results
