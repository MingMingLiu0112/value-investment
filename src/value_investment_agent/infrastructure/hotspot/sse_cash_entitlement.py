"""Explicit SSE gross entitlement, not an ex-reference price or full action chain."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re

from .cash_implementation import _compact, _pdf, revision_warning
from .cash_implementation_v2 import _exact_security_header
from .related_disclosure_identity import _page_texts
from ...quote_sessions import CHINA
from ..evidence.historical_price_correspondence import require_inside, sha256_file


def _body_payment_date_review(pages, payment_date):
    sections = re.findall(r'四、分配实施办法(.*?)五、有关咨询办法', ''.join(_page_texts(pages)))
    unknown = dict(status='UNKNOWN', reason='SUPPORTED_BODY_PAYMENT_SENTENCE_NOT_ESTABLISHED',
        declared_dates=[], absence_of_conflict_proven=False)
    if len(sections) != 1:
        return unknown
    body = sections[0]
    day = r'(20\d{2})年(\d{1,2})月(\d{1,2})日'
    mentions = re.findall(r'(?:现金)?红利发放日(?:\(|为|:)' + day, body)
    dates = [date(*map(int, values)).isoformat() for values in mentions]
    if any(value != payment_date for value in dates):
        raise ValueError('Body payment date conflicts with cash date table')
    supported = re.findall(r'(?:^|。)已办理指定交易的(?:投资者|股东)可于红利发放日\('
        + day + r'\)在其指定的证券营业部领取现金红利[,，]', body)
    if (not dates or len(supported) != len(dates)
            or body.count('红利发放日') != len(dates)):
        return dict(unknown, declared_dates=dates)
    return dict(status='EXPLICIT_SUPPORTED_SENTENCE_MATCHES_TABLE', declared_dates=dates,
        absence_of_conflict_proven=False,
        scope='SUPPORTED_PAYMENT_SENTENCE_ONLY_NOT_ALL_SEMANTIC_DATE_CLAIMS')


def parse_sse_cash_entitlement(pages, *, symbol):
    if not isinstance(symbol, str) or re.fullmatch(r'\d{6}', symbol) is None:
        raise ValueError('Six-digit issuer required')
    if not pages or len(pages) > 16 or any(not p.strip() for p in pages):
        raise ValueError("Complete readable cash original required")
    text = ''.join(_page_texts(pages))
    if len(text) > 120000 or not _exact_security_header(_compact(pages[0]), symbol):
        raise ValueError("Exact issuer header required")
    if (revision_warning(pages) or "权益分派实施公告" not in _compact(pages[0])
            or "差异化分红送转:否" not in text
            or any(token in text for token in ("送红股", "转增股本", "配股", "拆股", "合股", "股份转换"))):
        raise ValueError("Unsupported action or amendment")
    found = [(1, m[1]) for m in re.finditer(r"(?:\(三\)|3\.)分配方案:(.*?)三、相关日期", text)]
    if len(found) != 1:
        raise ValueError("Unique complete scheme required")
    number = r"((?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?)"
    both = re.fullmatch(r"本次利润分配以方案实施前的公司总股本" + number
            + r"股为基数,向全体股东每股派发现金红利人民币" + number
            + r"元\(含税\),共计派发现金红利人民币" + number
            + r"元\(含税\)。其中:A股普通股股份数为" + number
            + r"股,本次派发A股现金红利人民币" + number
            + r"元\(含税\)。公司已派发20\d{2}年中期现金红利每股人民币" + number
            + r"元\(含税\),连同本次现金红利分配,20\d{2}年全年现金红利为每股人民币" + number
            + r"元\(含税\),20\d{2}年全年现金红利总额为人民币" + number + r"元\(含税\)。", found[0][1])
    if both is None:
        raise ValueError("Explicit A-share subtotal and RMB complete scheme required")
    total_shares, cash, total_all, eligible, total, interim, annual, annual_total = [
        Decimal(v.replace(',', '')) for v in both.groups()]
    if (total_shares < eligible or total_shares != total_shares.to_integral_value()
                or min(total_shares, total_all, interim, annual, annual_total) <= 0
                or cash + interim != annual
                or (total_shares * cash).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != total_all
                or (total_shares * annual).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != annual_total):
        raise ValueError('All-share and A-share declared cash bases conflict')
    if len(set(re.findall(r'(20\d{2})年(?:中期|全年)', found[0][1]))) != 1:
        raise ValueError('Interim and annual periods conflict')
    share_scope = 'EXPLICIT_A_SUBTOTAL_WITH_SEPARATE_ALL_SHARE_TOTAL'
    all_share_terms = dict(total_shares=str(total_shares), current_total_gross_cash_cny=str(total_all))
    if (min(eligible, cash, total) <= 0 or eligible != eligible.to_integral_value()
            or (eligible * cash).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != total):
        raise ValueError("Gross cash arithmetic mismatch")
    header = re.findall(r"A股每股现金红利(?:人民币)?([0-9.]+)元", _compact(pages[0]))
    if len(header) != 1 or Decimal(header[0]) != cash:
        raise ValueError("Header and gross entitlement disagree")
    table_header = r"股份类别股权登记日最后交易日除权\(息\)日现金红利发放日"
    day = r"(20\d{2})/(\d{1,2})/(\d{1,2})"
    tables = re.findall(table_header + r"A股" + day + r"[-—]" + day + day, text)
    rows = re.findall(r'A股' + day + r'[-—]' + day + day, text)
    if (not tables or len(tables) != text.count('股份类别股权登记日最后交易日')
            or len(set(tables)) != 1 or rows != tables
            or len(re.findall(r'A股20\d{2}/', text)) != len(rows)):
        raise ValueError("Missing or conflicting complete cash date tables")
    values = tables[0]
    dates = {key: date(*map(int, values[i:i+3])).isoformat() for key, i in (
        ('record_date', 0), ('ex_date', 3), ('cash_payment_date', 6))}
    footer = re.search(r"董事会(20\d{2})年(\d{1,2})月(\d{1,2})日$", text)
    identity = re.findall(r"公告编号:((?:临)?20\d{2}-\d+)", _compact(pages[0]))
    if footer is None or len(identity) != 1:
        raise ValueError("Unique dated issuer declaration required")
    published = date(*map(int, footer.groups())).isoformat()
    if not published <= dates['record_date'] < dates['ex_date'] == dates['cash_payment_date']:
        raise ValueError("Cash chronology conflict")
    payment_review = _body_payment_date_review(pages, dates['cash_payment_date'])
    return dict(parser_version='sse-explicit-a-subtotal-gross-cash-v1', symbol=symbol,
        announcement_number=identity[0], published_date=published, **dates,
        eligible_a_shares=str(eligible), gross_cash_per_eligible_a_share=str(cash),
        declared_total_gross_cash_cny=str(total), share_scope=share_scope, all_share_terms=all_share_terms,
        scheme_pages=[i for i, p in enumerate(_page_texts(pages), 1)
            if any(token in p for token in ('分配方案:', '连同本次现金红利分配'))],
        source_pages=list(range(1, len(pages) + 1)),
        body_payment_date_review=payment_review,
        reference_deduction_per_total_a_share=None, amendment_chain_verified=False,
        scope='DECLARED_GROSS_ENTITLEMENT_NOT_PRICE_REFERENCE_OR_ACCOUNT_RECEIPT', action='no_order')


def load_sse_cash_entitlement(*, root, binding, symbol, now):
    binding = dict(binding)
    pages, available = _pdf(root, binding, now)
    terms = parse_sse_cash_entitlement(pages, symbol=symbol)
    provider_date = date.fromisoformat(binding['url'].split('/finalpage/')[1].split('/')[0])
    if (not date.fromisoformat(terms['published_date']) <= provider_date <= date.fromisoformat(terms['record_date'])
            or date.fromisoformat(terms['cash_payment_date']) > now.astimezone(CHINA).date()):
        raise ValueError("Declared cash source unavailable")
    if sha256_file(require_inside(root, root / binding['path'], 'cash original')) != binding['sha256']:
        raise ValueError("Cash original changed during read")
    return dict(terms=terms, source_binding=binding, acquired_at=available.isoformat(),
        provider_url_date=provider_date.isoformat(), signature_date_is_not_provider_publication_date=True,
        historical_availability_proven=False, price_comparability='UNKNOWN', action='no_order')
