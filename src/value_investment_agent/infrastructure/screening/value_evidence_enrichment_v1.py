"""Bounded retained-original extraction. Candidates never confer verification."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from ...filing_extract import ANNUAL_BACKFILL_PARSER_VERSION, extract_candidates_from_pages
from ..filings.pdf_text import extract_pages

VERSION = 'value-retained-enrichment-v1'
DEBT_LABELS = {
    'short_term_borrowings': '\u77ed\u671f\u501f\u6b3e',
    'current_portion_long_term_debt': '\u4e00\u5e74\u5185\u5230\u671f\u7684\u975e\u6d41\u52a8\u8d1f\u503a',
    'long_term_borrowings': '\u957f\u671f\u501f\u6b3e',
    'bonds_payable': '\u5e94\u4ed8\u503a\u5238',
    'lease_liabilities_noncurrent': '\u79df\u8d41\u8d1f\u503a',
    'financing_payables_noncurrent': '\u957f\u671f\u5e94\u4ed8\u6b3e',
    'other_current_financing': '\u5176\u4ed6\u6d41\u52a8\u8d1f\u503a',
    'other_noncurrent_financing': '\u5176\u4ed6\u975e\u6d41\u52a8\u8d1f\u503a',
    'other_financing_scope': '\u7b79\u8d44\u6d3b\u52a8\u4ea7\u751f\u7684\u5404\u9879\u8d1f\u503a',
}


@dataclass(frozen=True)
class RetainedAnnualSource:
    symbol: str
    period: str
    path: str
    sha256: str
    source_url: str
    available_at: str


def _inside(root: Path, path: str | Path) -> Path:
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('evidence/cache path outside repository')
    return target


_STATEMENT_TITLES = ('合并资产负债表', '母公司资产负债表', '合并利润表',
                     '母公司利润表', '合并现金流量表', '母公司现金流量表')


def _statement_lines(page: str) -> list[str]:
    lines = [line.strip() for line in page.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        match = re.fullmatch(r'\d+、\s*(' + '|'.join(_STATEMENT_TITLES) + ')', line)
        if match:
            lines[index] = match[1]
    return lines


def _raw_excerpt(text: str, compact_snippet: str) -> str:
    positions = [index for index, char in enumerate(text) if not char.isspace()]
    compact = ''.join(text[index] for index in positions)
    start = compact.index(compact_snippet)
    return text[positions[start]:positions[start + len(compact_snippet) - 1] + 1]


def _consolidated_currency_context(pages: list[str]) -> list[dict]:
    evidence = []
    # A subsidiary's functional currency is not a group presentation currency.
    pattern = re.compile(r'本(?:集团|公司)编制本财务报表时所采用的货币为([^。；;\n]+)[。；;]')
    for number, page in enumerate(pages, 1):
        for match in pattern.finditer(''.join(page.split())):
            evidence.append(dict(page=number, excerpt=_raw_excerpt(page, match[0]), currency=match[1]))
    return evidence


def _statement_unit(page: str, number: int, context: list[dict]) -> tuple:
    compact = ''.join(page.split())
    unit = re.search(r'单位[：:](百万元|万元|千元|元)', compact)
    if not unit:
        return None, None
    local = list(re.finditer(r'币种[：:]\s*([^，,。；;\s]+)', page))
    if local:
        if any(value[1] != '人民币' for value in local):
            return None, None
        currency = dict(page=number, excerpt=local[0][0], currency='人民币')
    else:
        if not context or any(item['currency'] != '人民币' for item in context):
            return None, None
        currency = context[0]
    multiplier = {'元': 1, '千元': 1000, '万元': 10000, '百万元': 1000000}[unit[1]]
    return multiplier, dict(currency_evidence_page=currency['page'],
                            currency_evidence_excerpt=currency['excerpt'],
                            unit_evidence_excerpt=_raw_excerpt(page, unit[0]))


def _issuer_legal_owner(pages: list[str]) -> dict | None:
    """A labelled legal name plus security code, never a market short name."""
    evidence = []
    for number, page in enumerate(pages[:12], 1):
        codes = list(re.finditer(r'(?:股票|证券|公司)代码[：:]?(\d{6})(?!\d)', ''.join(page.split())))
        if len({match[1] for match in codes}) != 1:
            continue
        for match in re.finditer(r'(?m)^[ \t]*(?:公司的中文名称|公司中文名称|公司中文全称)[：: \t]+([^\r\n]+)', page):
            name = ''.join(match[1].split())
            if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z（）()·]+有限公司', name):
                continue
            evidence.append(dict(legal_name=name, security_code=codes[0][1],
                legal_name_page=number, legal_name_excerpt=match[0].strip(),
                security_code_page=number, security_code_excerpt=_raw_excerpt(page, codes[0][0])))
    if not evidence or len({(e['legal_name'], e['security_code']) for e in evidence}) != 1:
        return None
    return evidence[0]


def extract_debt_balance_candidates(pages: list[str], period: str, *, balance_totals: bool = False,
                                    include_equity: bool = False) -> list[dict]:
    """Narrow two-column balance rows, kept separate from financing judgments."""
    result = []
    active = False
    multiplier = None
    unit_page = None
    currency_context = _consolidated_currency_context(pages)
    evidence = {}
    period_evidence = {}
    table_identity = {}
    legal_owner = _issuer_legal_owner(pages) if include_equity else None
    labels = dict(DEBT_LABELS)
    labels.pop('other_financing_scope')
    labels['long_term_payables_noncurrent'] = labels.pop('financing_payables_noncurrent')
    labels['other_current_liabilities'] = labels.pop('other_current_financing')
    labels['other_noncurrent_liabilities'] = labels.pop('other_noncurrent_financing')
    if balance_totals:
        labels = {'total_assets': '\u8d44\u4ea7\u603b\u8ba1', 'total_liabilities': '\u8d1f\u503a\u5408\u8ba1'}
        if include_equity:
            labels['total_equity'] = '所有者权益合计'
    amount = re.compile(r'(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)')
    for number, page in enumerate(pages, 1):
        lines = _statement_lines(page)
        closes = False
        if '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868' in lines:
            lines = lines[lines.index('合并资产负债表') + 1:]
            active = True
        stops = [i for i, line in enumerate(lines) if line in _STATEMENT_TITLES]
        if include_equity:
            stops.extend(i for i, line in enumerate(lines) if '资产负债表' in line
                and not re.fullmatch(r'(?:\d+、\s*)?合并资产负债表[（(]续[）)]', line))
        if stops:
            lines = lines[:min(stops)]
            closes = True
        compact = ''.join(''.join(lines).split())
        if '合并资产负债表' in _statement_lines(page):
            issuers = list(re.finditer(r'编制单位[：:]\s*([^\r\n]+)', '\n'.join(lines)))
            issuer = ''.join(issuers[0][1].split()) if len(issuers) == 1 else None
            table_identity = dict(statement_evidence_page=number,
                                  statement_title='合并资产负债表', issuer=issuer)
            current = f'{period[:4]}\u5e7412\u670831\u65e5'
            prior = f'{int(period[:4]) - 1}\u5e7412\u670831\u65e5'
            active = current in compact and prior in compact and compact.index(current) < compact.index(prior)
            period_evidence = dict(period_evidence_page=number,
                                   period_evidence_excerpt=_raw_excerpt(page,
                                       compact[compact.index(current):compact.index(prior)+len(prior)]) if active else '',
                                   prior_period_basis='EXPLICIT_DATES')
            header = compact.split('项目', 1)[0]
            relative = ('项目期末余额期初余额' in compact and
                        re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', header) == [current])
            if '期末余额' in compact or '期初余额' in compact:
                active = False
            if not active and relative:
                active = True
                period_evidence = dict(period_evidence_page=number,
                    period_evidence_excerpt=_raw_excerpt(page, compact[compact.index(current):
                        compact.index('项目期末余额期初余额')+len('项目期末余额期初余额')]),
                    prior_period_basis='ANNUAL_OPENING_INFERRED_NOT_EXPLICIT_SECOND_DATE')
            # Restated or grouped multi-column tables require their own parser.
            active = active and not any(word in compact for word in ('\u8c03\u6574\u524d', '\u8c03\u6574\u540e', '\u6bcd\u516c\u53f8'))
            multiplier = None
            multiplier, evidence = _statement_unit('\n'.join(lines), number, currency_context)
            if multiplier is not None:
                unit_page = number
            if include_equity:
                if not legal_owner or issuer != legal_owner['legal_name']:
                    active = False
                else:
                    owner = dict(legal_owner, compiler_name=issuer, compiler_page=number,
                        compiler_excerpt=_raw_excerpt(page, ''.join(issuers[0][0].split())))
                    table_identity['owner_evidence'] = owner
                    context = dict(table_identity, **period_evidence, **(evidence or {}), unit_page=unit_page)
                    table_identity['table_context_id'] = hashlib.sha256(
                        json.dumps(context, sort_keys=True).encode()).hexdigest()
        elif include_equity and active:
            # A continued page must not borrow its predecessor's owner, column
            # order or units after an explicit conflicting declaration.
            continued = '\n'.join(lines)
            owners = re.findall(r'编制单位[：:]\s*([^\r\n]+)', continued)
            if any(''.join(owner.split()) != table_identity.get('issuer') for owner in owners):
                active = False
            headers = [''.join(line.split()) for line in lines if line.startswith('项目')]
            expected_headers = {'项目期末余额期初余额',
                f'项目{period[:4]}年12月31日{int(period[:4])-1}年12月31日'}
            if any(header not in expected_headers for header in headers):
                active = False
            if re.search(r'(?<!编制)单位[：:]', continued):
                continued_multiplier, _ = _statement_unit(continued, number, currency_context)
                if continued_multiplier != multiplier:
                    active = False
            currencies = re.findall(r'币种[：:]\s*([^，,。；;\s]+)', continued)
            if any(currency != '人民币' for currency in currencies):
                active = False
        if not active or multiplier is None:
            if closes:
                active = False
            continue
        for line in lines:
            for field, label in labels.items():
                if not line.startswith(label):
                    continue
                values = amount.findall(line[len(label):])
                # A single printed value could be the prior-year column.
                if len(values) != 2:
                    continue
                if include_equity and not re.fullmatch(re.escape(label) + r'\s+' +
                        amount.pattern + r'\s+' + amount.pattern, line):
                    continue
                result.append(dict(field_name=field, source_label=label,
                                   value=str(Decimal(values[0].replace(',', '')) * multiplier),
                                   prior_value=str(Decimal(values[1].replace(',', '')) * multiplier),
                                   unit='CNY', currency='CNY', period_label=period,
                                   prior_period_label=str(int(period[:4])-1)+'-12-31',
                                   statement_scope='consolidated', page=number, excerpt=line,
                                   comparative_basis='as_printed_may_be_restated',
                                   unit_evidence_page=unit_page,
                                   **evidence, **period_evidence,
                                   **table_identity,
                                   status='candidate_source_unverified' if balance_totals else 'candidate_debt_scope_unverified'))
        if closes or re.search(r'\u8d1f\u503a(?:\u548c|\u53ca)\u6240\u6709\u8005\u6743\u76ca.*\u603b\u8ba1', compact):
            active = False
    return result


def extract_income_comparatives(pages: list[str], period: str) -> list[dict]:
    """Only explicitly ordered annual consolidated income columns, no summaries."""
    active, unit_page, multiplier = False, None, None
    rows = []
    currency_context = _consolidated_currency_context(pages)
    evidence = {}
    period_evidence = {}
    number = r'(-?\d[\d,]*\.\d{2})(?!\d)'
    note = (r'(?:\d{1,2}|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e]{1,6}\s*'
            r'(?:\(\s*[1-9]\d{0,2}\s*\)|\uff08\s*[1-9]\d{0,2}\s*\uff09))\s+')
    labels = {'revenue': '\u8425\u4e1a\u6536\u5165',
              'net_income': '\u5f52\u5c5e\u4e8e\u6bcd\u516c\u53f8\u80a1\u4e1c\u7684\u51c0\u5229\u6da6'}
    for page_number, page in enumerate(pages, 1):
        lines = _statement_lines(page)
        compact = ''.join(page.split())
        scan = page
        if '\u5408\u5e76\u5229\u6da6\u8868' in lines:
            current, prior = period[:4] + '\u5e74\u5ea6', str(int(period[:4]) - 1) + '\u5e74\u5ea6'
            statement_text = page.split('合并利润表', 1)[1]
            for title in _STATEMENT_TITLES:
                if title != '合并利润表':
                    statement_text = statement_text.split(title, 1)[0]
            header_compact = ''.join(statement_text.split())
            active = current in header_compact and prior in header_compact and header_compact.index(current) < header_compact.index(prior)
            multiplier, evidence = _statement_unit(statement_text, page_number, currency_context)
            period_evidence = dict(period_evidence_page=page_number,
                                   period_evidence_excerpt=_raw_excerpt(statement_text,
                                       header_compact[header_compact.index(current):
                                           header_compact.index(prior)+len(prior)]) if active else '',
                                   prior_period_basis='EXPLICIT_ANNUAL_COLUMNS')
            unit_page = page_number
            scan = page.split('\u5408\u5e76\u5229\u6da6\u8868', 1)[1]
        if any(word in compact for word in ('\u8c03\u6574\u524d', '\u8c03\u6574\u540e', '\u91cd\u8ff0')):
            active = False
        if not active or multiplier is None:
            continue
        boundaries = [scan.index(title) for title in ('\u6bcd\u516c\u53f8\u5229\u6da6\u8868',
            '\u5408\u5e76\u73b0\u91d1\u6d41\u91cf\u8868', '\u6bcd\u516c\u53f8\u73b0\u91d1\u6d41\u91cf\u8868') if title in scan]
        if boundaries:
            scan = scan[:min(boundaries)]
            active = False
        for field, label in labels.items():
            pattern = r'\s*'.join(re.escape(c) for c in label)
            # The profit note may wrap to the following line. Total net profit
            # and minority profit cannot match this attributable-profit label.
            loss = r'(?:\s*[\uff08(]\s*\u51c0\s*\u4e8f\s*\u635f\s*\u4ee5[^\uff09)]*[\uff09)])?' if field == 'net_income' else ''
            for match in re.finditer(pattern + loss + r'\s+(?:' + note + r')?' + number + r'\s+' + number, scan):
                if re.match(r'[^\S\r\n]+' + number, scan[match.end():]):
                    continue
                rows.append(dict(field_name=field, value=str(Decimal(match[1].replace(',', '')) * multiplier),
                    prior_value=str(Decimal(match[2].replace(',', '')) * multiplier),
                    unit='CNY', statement_scope='consolidated', currency='CNY',
                    period_label=period, prior_period_label=str(int(period[:4])-1)+'-12-31',
                    page=page_number, excerpt=match[0], unit_evidence_page=unit_page,
                    **evidence, **period_evidence,
                    status='SOURCE_LOCATED_NOT_INDEPENDENTLY_ADMITTED'))
    return rows


def extract_retained_annual(root: Path, source: RetainedAnnualSource, *,
                            evaluation_at: datetime, cache_dir: Path,
                            max_bytes: int = 30_000_000, max_pages: int = 600,
                            verify_cache: bool = False) -> dict:
    """Hash/clock check before cached reuse; no fetching and no source mutation."""
    if evaluation_at.tzinfo is None:
        raise ValueError('evaluation clock must be timezone aware')
    available = datetime.fromisoformat(source.available_at)
    if available.tzinfo is None or available > evaluation_at:
        raise ValueError('source unavailable at evaluation cutoff')
    if not re.fullmatch(r'\d{6}', source.symbol) or not re.fullmatch(r'\d{4}-12-31', source.period):
        raise ValueError('requires security identity and annual period')
    url = urlparse(source.source_url)
    if url.scheme != 'https' or url.hostname not in {
        'static.cninfo.com.cn', 'www.cninfo.com.cn', 'www.sse.com.cn',
        'static.sse.com.cn', 'disc.static.szse.cn', 'www.szse.cn', 'www.bse.cn',
    }:
        raise ValueError('requires an official retained filing URL')
    path = _inside(root, source.path)
    if path.stat().st_size > max_bytes:
        raise ValueError('source exceeds byte budget')
    if hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256:
        raise ValueError('retained original hash mismatch')
    cache = _inside(root, cache_dir)
    if not cache.is_relative_to((root / '.tmp').resolve()):
        raise ValueError('extraction cache must be under project .tmp')
    from ... import filing_extract
    parser_hash = hashlib.sha256(Path(__file__).read_bytes() + Path(filing_extract.__file__).read_bytes()).hexdigest()
    identity = dict(source=asdict(source), version=VERSION,
                    upstream_parser=ANNUAL_BACKFILL_PARSER_VERSION,
                    implementation_sha256=parser_hash)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cached = cache / (key + '.json')
    cached_packet = None
    if cached.exists():
        envelope = json.loads(cached.read_bytes())
        packet = envelope['packet']
        digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
        if envelope['packet_sha256'] != digest or packet['identity'] != identity:
            raise ValueError('extraction cache integrity mismatch')
        if packet['page_count'] > max_pages:
            raise ValueError('source exceeds page budget')
        if not verify_cache:
            return dict(packet, reused=True)
        cached_packet = packet
    # One extra page detects overflow without decoding an unbounded document.
    pages = extract_pages(path, limit=max_pages + 1)
    if len(pages) > max_pages:
        raise ValueError('source exceeds page budget')
    header = ''.join(''.join(pages[:3]).split())
    if source.period[:4] + '\u5e74\u5e74\u5ea6\u62a5\u544a' not in header:
        raise ValueError('original annual-report identity not found')
    opening = ''.join(''.join(pages[:12]).split())
    labelled_codes = set(re.findall(r'(?:\u80a1\u7968|\u8bc1\u5238|\u516c\u53f8)\u4ee3\u7801[:\uff1a]?(\d{6})(?!\d)', opening))
    if source.symbol not in labelled_codes:
        raise ValueError('original labelled security identity not found in first twelve pages')
    candidates = extract_candidates_from_pages(pages)
    debt_candidates = extract_debt_balance_candidates(pages, source.period)
    balance_candidates = extract_debt_balance_candidates(pages, source.period, balance_totals=True)
    reconciliation_candidates = extract_debt_balance_candidates(
        pages, source.period, balance_totals=True, include_equity=True)
    searches = {}
    for field, label in DEBT_LABELS.items():
        hits = []
        for page_number, page in enumerate(pages, 1):
            compact = ''.join(page.split())
            start = compact.find(label)
            if start >= 0:
                hits.append(dict(page=page_number, excerpt=compact[max(0, start - 120):start + 700]))
            if len(hits) == 12:
                break
        searches[field] = dict(hits=hits, status='CANDIDATE_REQUIRES_SCOPE_VALIDATION'
                               if hits else 'NOT_LOCATED_NOT_ZERO')
    packet = dict(identity=identity, page_count=len(pages), page_texts=pages, candidates=candidates,
                  debt_balance_candidates=debt_candidates,
                  balance_total_candidates=balance_candidates,
                  balance_reconciliation_candidates=reconciliation_candidates,
                  income_comparatives=extract_income_comparatives(pages, source.period),
                  debt_searches=searches, verification_created=False,
                  action='no_order', reused=False)
    if cached_packet is not None:
        if cached_packet != packet:
            raise ValueError('extraction cache differs from original re-extraction')
        return dict(packet, reused=True)
    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
    cached.write_text(json.dumps(dict(packet=packet, packet_sha256=digest),
                                ensure_ascii=False, indent=2), encoding='utf-8')
    return packet
