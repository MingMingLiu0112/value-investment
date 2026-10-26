"""Printed consolidated funding rows, not verified debt or sector applicability."""
from datetime import date
from decimal import Decimal, localcontext
import re

from ...financing_table import amount_from_fragments


FUNDING_LABELS = {
    'financial_deposits_and_interbank': '\u5438\u6536\u5b58\u6b3e\u53ca\u540c\u4e1a\u5b58\u653e',
    'central_bank_borrowings': '\u5411\u4e2d\u592e\u94f6\u884c\u501f\u6b3e',
    'interbank_borrowings': '\u62c6\u5165\u8d44\u91d1',
    'repurchase_financing': '\u5356\u51fa\u56de\u8d2d\u91d1\u878d\u8d44\u4ea7\u6b3e',
}
_DATE = re.compile(r'([0-9]{4})\u5e74([0-9]{1,2})\u6708([0-9]{1,2})\u65e5')
_UNIT = re.compile(r'\u5355\u4f4d[:\uff1a](\u5343\u5143|\u4e07\u5143|\u5143)\u5e01\u79cd[:\uff1a]\u4eba\u6c11\u5e01')
_CURRENCY = re.compile(r'\u5e01\u79cd[:\uff1a]\s*([^\s]+)')
_TITLE = re.compile(r'\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868(?:[\uff08(]\u7eed[\uff09)])?')
_OTHER_STATEMENT = re.compile(r'(?:\u6bcd\u516c\u53f8|\u516c\u53f8|\u5408\u5e76)?(?:\u8d44\u4ea7\u8d1f\u503a\u8868|\u5229\u6da6\u8868|\u73b0\u91d1\u6d41\u91cf\u8868)(?:[\uff08(]\u7eed[\uff09)])?')
_NOTE = re.compile(r'(?:[0-9]{1,3}|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]+[\uff08(][0-9]{1,3}[\uff09)])')


def extract_financial_funding_observations(pages: list[str], period: str) -> list[dict]:
    """Only proven FY/H1 two-column tables; blanks are not zero/applicability.

    Identity, URL, raw hash and availability belong to the caller's source
    closure. This pure text primitive cannot authenticate them or admit facts.
    """
    if not isinstance(period, str) or not re.fullmatch(r'[0-9]{4}-(?:12-31|06-30)', period):
        raise ValueError('Explicit FY or H1 closing date required')
    current = date.fromisoformat(period)
    prior = date(current.year-1, 12, 31)
    if not isinstance(pages, list) or any(not isinstance(page, str) for page in pages):
        raise ValueError('Ordered source page texts required')
    result = []
    active = False
    source_unit = unit_page = None
    for page_number, page in enumerate(pages, 1):
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        compact = ''.join(page.split())
        if any(marker in compact for marker in ('\u8c03\u6574\u524d', '\u8c03\u6574\u540e')):
            active = False
            continue
        titles = [index for index, line in enumerate(lines) if _TITLE.fullmatch(''.join(line.split()))]
        if titles:
            active = False
            source_unit = unit_page = None
            if len(titles) != 1:
                continue
            start = titles[0]+1
            header = []
            for line in lines[start:]:
                normalized = ''.join(line.split())
                if (_OTHER_STATEMENT.fullmatch(normalized) or normalized.startswith(('\u6d41\u52a8\u8d44\u4ea7', '\u8d44\u4ea7:', '\u8d44\u4ea7\uff1a'))
                        or any(normalized.startswith(label) for label in FUNDING_LABELS.values())):
                    break
                header.append(normalized)
            header = ''.join(header)
            columns = header.split('\u9879\u76ee', 1)
            units = _UNIT.findall(header)
            if (len(columns) != 2 or len(units) != 1
                    or '\u6bcd\u516c\u53f8' in header or '\u5408\u5e76\u53ca\u516c\u53f8' in header):
                continue
            try:
                dates = [date(*map(int, groups)) for groups in _DATE.findall(columns[1])]
            except ValueError:
                continue
            if dates != [current, prior]:
                continue
            source_unit, unit_page, active = units[0], page_number, True
        elif active and '\u5355\u4f4d' in compact:
            # A continuation may repeat, but never silently change, its unit.
            if _UNIT.findall(compact) != [source_unit]:
                active = False
        if not active:
            continue
        if any(currency != '\u4eba\u6c11\u5e01' for currency in _CURRENCY.findall(page)):
            active = False
            continue
        if not titles:
            column_headers = [index for index, line in enumerate(lines)
                              if ''.join(line.split()).startswith('\u9879\u76ee')]
            if column_headers:
                column_text = ''.join(''.join(line.split()) for line in lines[column_headers[0]:])
                try:
                    dates = [date(*map(int, groups)) for groups in _DATE.findall(column_text)]
                except ValueError:
                    dates = []
                if len(column_headers) != 1 or dates != [current, prior]:
                    active = False
                    continue
        multiplier = {'\u5143': 1, '\u5343\u5143': 1000, '\u4e07\u5143': 10000}[source_unit]
        for line in lines:
            normalized = ''.join(line.split())
            if _OTHER_STATEMENT.fullmatch(normalized) and not _TITLE.fullmatch(normalized):
                active = False
                break
            for field, label in FUNDING_LABELS.items():
                # Exact label boundary excludes totals and derivative/subrows.
                match = re.fullmatch(re.escape(label)+r'(?:\s+(.*))?', line)
                if not match or not match[1]:
                    continue
                cells = match[1].split()
                if len(cells) > 1 and _NOTE.fullmatch(cells[0]):
                    cells = cells[1:]
                if not cells or all(cell in ('-', '--', '\u2014', '\u2014\u2014') for cell in cells):
                    continue
                values = [amount_from_fragments([cell]) for cell in cells]
                known = len(values) == 2 and all(value is not None for value in values)
                reason = ('TWO_EXPLICIT_PRINTED_AMOUNTS_NOT_FACT_ADMISSION' if known else
                          'SINGLE_PRINTED_AMOUNT_COLUMN_UNRESOLVED' if len(cells) == 1 else
                          'AMBIGUOUS_OR_UNSUPPORTED_AMOUNT_COLUMNS')
                with localcontext() as context:
                    context.prec = 48
                    converted = [str(Decimal(value)*multiplier) for value in values] if known else [None, None]
                result.append(dict(field_name=field, source_label=label,
                    value=converted[0], prior_value=converted[1], period_label=period,
                    prior_period_label=prior.isoformat(), unit='CNY', currency='CNY',
                    source_unit=source_unit, unit_evidence_page=unit_page,
                    statement_scope='consolidated', page=page_number, excerpt=line,
                    status='candidate_funding_scope_unverified', reason=reason))
            if re.search(r'\u8d1f\u503a(?:\u548c|\u53ca)\u6240\u6709\u8005\u6743\u76ca.*\u603b\u8ba1', normalized):
                active = False
                break
    return result


def extract_funding_cash_context(pages: list[str], period: str) -> list[dict]:
    """Adjacent research observations; no facts, debt clearance or cash access.

    A controlling depositor needs both an explicit relationship and a dated
    single-column deposit note. Cash inherits the exact statement header and
    its period across continuation pages, never the generic monetary-funds row.
    Source identity and original-byte authentication remain the caller's job.
    """
    funding = extract_financial_funding_observations(pages, period)
    closing = date.fromisoformat(period)
    result = []

    def observation(field, value, scope, page, excerpt, unit_page, **extra):
        return dict(field_name=field, value=value, period_label=period,
                    unit='CNY', currency='CNY', statement_scope=scope,
                    page=page, excerpt=excerpt, source_unit='\u5143',
                    unit_evidence_page=unit_page,
                    status='SOURCE_BOUND_RESEARCH_OBSERVATION_NOT_FACT_ADMISSION', **extra)

    deposits = [row for row in funding if row['field_name'] == 'financial_deposits_and_interbank'
                and row['value'] is not None]
    if len(deposits) == 1:
        result.append({**deposits[0], 'status': 'SOURCE_BOUND_RESEARCH_OBSERVATION_NOT_FACT_ADMISSION'})

    # Only exact mother-company relationships, not siblings labelled mother's subsidiaries.
    parties = []
    for n, page in enumerate(pages, 1):
        compact = ''.join(page.split())
        if ('\u5b58\u6b3e\u4e1a\u52a1' not in compact or '\u5173\u8054\u5173\u7cfb' not in compact
                or '\u671f\u672b\u4f59\u989d' not in compact or _UNIT.findall(compact) != ['\u5143']):
            continue
        for match in re.finditer(r'([^\s]+)\s+\u6bcd\u516c\u53f8\s+', page):
            name = match[1]
            tail = page[match.end():].split()
            amounts = []
            for token in tail:
                amount = amount_from_fragments([token])
                if amount is None:
                    break
                amounts.append(Decimal(amount))
            if len(amounts) == 4 and amounts[0] + amounts[1] - amounts[2] == amounts[3]:
                parties.append((name, n, match[0].strip(), amounts[3]))
    party_names = {name.replace('(', '\uff08').replace(')', '\uff09') for name, _, _, _ in parties}
    if len(parties) == 1 and len(party_names) == 1:
        name, relationship_page, relationship_excerpt, flow_closing = parties[0]
        normalized_name = next(iter(party_names))
        candidates = []
        for n, page in enumerate(pages, 1):
            compact = ''.join(page.split())
            if ('\u5176\u4ed6\u5173\u8054\u4ea4\u6613' not in compact
                    or '\u5b58\u6b3e\u4f59\u989d\u53ca\u5e94\u8ba1\u5229\u606f' not in compact
                    or set(_UNIT.findall(compact)) != {'\u5143'}
                    or any(c.rstrip(')\uff09') != '\u4eba\u6c11\u5e01' for c in _CURRENCY.findall(page))):
                continue
            headers = list(re.finditer(r'(?m)^\s*\u5173\u8054\u65b9[ \t]*([0-9]{4}[ \t]*\u5e74[ \t]*[0-9]{1,2}[ \t]*\u6708[ \t]*[0-9]{1,2}[ \t]*\u65e5)[ \t]*\r?$', page))
            if len(headers) != 1:
                continue
            header = headers[0]
            groups = _DATE.fullmatch(''.join(header[1].split()))
            try:
                note_date = date(*map(int, groups.groups())) if groups else None
            except ValueError:
                note_date = None
            if note_date != closing:
                continue
            for line in page[header.end():].splitlines():
                cells = line.split()
                if len(cells) != 2 or cells[0].replace('(', '\uff08').replace(')', '\uff09') != normalized_name:
                    continue
                amount = amount_from_fragments([cells[1]])
                if amount is not None and Decimal(amount) == flow_closing:
                    candidates.append(observation('controlling_group_deposits', amount,
                        'financial_subsidiary_depositor', n, line.strip(), n,
                        counterparty=name, relationship='CONTROLLING_GROUP_NOT_ISSUER_PARENT',
                        relationship_evidence=dict(page=relationship_page, excerpt=relationship_excerpt),
                        balance_basis='DEPOSITS_AND_ACCRUED_INTEREST_NOT_PRINCIPAL_ONLY'))
        if len(candidates) == 1:
            result.extend(candidates)

    active = None
    unit_page = header_page = None
    cash = {'consolidated': [], 'issuer_parent': []}
    for n, page in enumerate(pages, 1):
        compact = ''.join(page.split())
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            title = ''.join(line.split())
            if _OTHER_STATEMENT.fullmatch(title):
                active = None
                scope = {'\u5408\u5e76\u73b0\u91d1\u6d41\u91cf\u8868': 'consolidated',
                         '\u6bcd\u516c\u53f8\u73b0\u91d1\u6d41\u91cf\u8868': 'issuer_parent'}.get(title)
                header = ''.join(''.join(v.split()) for v in lines[i+1:i+9])
                expected = (f'{closing.year}\u5e74\u5ea6{closing.year-1}\u5e74\u5ea6'
                            if closing.month == 12 else
                            f'{closing.year}\u5e74\u534a\u5e74\u5ea6{closing.year-1}\u5e74\u534a\u5e74\u5ea6')
                if (scope and _UNIT.findall(header) == ['\u5143']
                        and '\u9879\u76ee' in header and expected in header
                        and not any(k in header for k in ('\u8c03\u6574\u524d', '\u8c03\u6574\u540e'))):
                    active, unit_page, header_page = scope, n, n
            if active:
                if (any(c != '\u4eba\u6c11\u5e01' for c in _CURRENCY.findall(page))
                        or (re.search(r'\u5355\u4f4d[:\uff1a]', compact)
                            and set(_UNIT.findall(compact)) != {'\u5143'})
                        or any(k in compact for k in ('\u8c03\u6574\u524d', '\u8c03\u6574\u540e'))):
                    active = None
                    continue
                match = re.fullmatch(r'\u516d\u3001\s*\u671f\u672b\u73b0\u91d1\u53ca\u73b0\u91d1\u7b49\u4ef7\u7269\u4f59\u989d\s+(\S+)\s+(\S+)', line)
                if match:
                    amounts = [amount_from_fragments([v]) for v in match.groups()]
                    if all(v is not None for v in amounts):
                        field = ('consolidated_cash_and_equivalents' if active == 'consolidated'
                                 else 'issuer_parent_cash_and_equivalents')
                        cash[active].append(observation(field, amounts[0], active, n, line,
                            unit_page, statement_header_page=header_page,
                            cash_access_status='NOT_ASSESSED_NOT_DISTRIBUTABLE_CASH'))
                    active = None
    for rows in cash.values():
        if len(rows) == 1:
            result.extend(rows)
    return result
