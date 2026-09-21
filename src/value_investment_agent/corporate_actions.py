"""Disclosure discovery only; titles cannot verify amounts or event chronology."""
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation


def extract_distribution_dates(pages: list[str]) -> list[dict]:
    """Extract tightly labelled date candidates; never approve a disclosure."""
    labels = {
        'record_date': r'股权登记日',
        'ex_date': r'除权(?:[（(]除息[）)]|除息)?日|除息日',
        'cash_payment_date': r'现金红利发放日|现金红利将于',
        'bonus_listing_date': r'新增无限售条件流通股份上市日',
    }
    rows = []
    for page, text in enumerate(pages, 1):
        lines = [unicodedata.normalize('NFKC', line).strip() for line in text.splitlines()]
        for index, line in enumerate(lines[:-1]):
            if re.sub(r'\s+', '', line) != '股份类别股权登记日最后交易日除权(息)日现金红利发放日':
                continue
            cells = lines[index + 1].split()
            if len(cells) != 5 or cells[0] != 'A股' or cells[2] not in {'-', '−', '—'}:
                continue
            parsed = []
            for field, cell in zip(('record_date', 'ex_date', 'cash_payment_date'),
                                   (cells[1], cells[3], cells[4])):
                match = re.fullmatch(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})', cell)
                if not match:
                    break
                try:
                    value = date(*map(int, match.groups())).isoformat()
                except ValueError:
                    break
                parsed.append({'field': field, 'value': value, 'page': page,
                               'matched_text': line + '\n' + lines[index + 1],
                               'method': 'exact_five_column_a_share_table', 'verified': False})
            if len(parsed) == 3:
                rows.extend(parsed)
        compact = re.sub(r'\s+', '', text)
        for field, label in labels.items():
            pattern = (rf'(?:{label})(?:为|为：|为:|：|:)?'
                       r'(?P<y>20\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日')
            for match in re.finditer(pattern, compact):
                try:
                    value = date(*(int(match[k]) for k in ('y', 'm', 'd'))).isoformat()
                except ValueError:
                    continue
                rows.append({'field': field, 'value': value, 'page': page,
                             'matched_text': match.group(), 'verified': False})
    return rows


def validate_cash_distribution(event: dict) -> Decimal:
    """Validate a reviewed gross entitlement, not its tax or portfolio treatment."""
    dates = {key: date.fromisoformat(event[key]) for key in
             ('record_date', 'ex_date', 'cash_payment_date')}
    if not dates['record_date'] < dates['ex_date'] <= dates['cash_payment_date']:
        raise ValueError('Unsupported or invalid distribution chronology')
    if event.get('amount_basis') != 'implemented_gross_entitlement':
        raise ValueError('Proposal or net amount cannot stand in for gross entitlement')
    try:
        amount = Decimal(str(event['cash_amount']))
        basis = Decimal(str(event['per_shares']))
        per_share = Decimal(str(event['cash_per_share']))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Invalid distribution amount') from exc
    if any(not x.is_finite() or x <= 0 for x in (amount, basis, per_share)):
        raise ValueError('Invalid distribution amount')
    if amount / basis != per_share:
        raise ValueError('Per-share entitlement does not match declared basis')
    if not event.get('evidence'):
        raise ValueError('Missing primary evidence')
    return per_share


def is_distribution_disclosure(title: str) -> bool:
    if not any(word in title for word in ('预案', '建议', '取消派发')) and re.search(
            r'派发20\d{2}年度末期股息(?:及公司特别股息)?(?:的)?公告$', title):
        return True
    return bool(re.search(
        r'(?:权益分派|利润分配|特别分红|红利分派).*?实施公告'
        r'(?:[（(](?:更新后|已取消|修订版|修订稿)[）)]|的更正公告)?$', title))


def distribution_title_status(title: str) -> str:
    if not is_distribution_disclosure(title):
        return 'not_distribution_disclosure'
    if '已取消' in title:
        return 'cancelled_retained_for_lineage'
    if '更正公告' in title:
        return 'correction_requires_linkage'
    if any(word in title for word in ('更新后', '修订版', '修订稿')):
        return 'revised_requires_linkage'
    return 'implementation_requires_body_verification'
