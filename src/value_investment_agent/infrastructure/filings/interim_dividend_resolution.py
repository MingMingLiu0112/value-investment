"""Read an exact interim dividend vote from a shareholder resolution original."""
from datetime import date
import re
import unicodedata


_DAY = r"(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日"
_VOTES = r"(\d[\d,]*)\s+\d+\.\d+\s+(\d[\d,]*)\s+\d+\.\d+\s+(\d[\d,]*)\s+\d+\.\d+"


def parse_interim_dividend_resolution(pages, *, symbol, published):
    """Identify the approved agenda item, without inferring amount or payment."""
    return _parse_dividend_resolution(pages, symbol=symbol, published=published, annual=False)


def parse_annual_dividend_resolution(pages, *, symbol, published):
    """Verify the annual vote independently of proposal amount and payment."""
    return _parse_dividend_resolution(pages, symbol=symbol, published=published, annual=True)


def _parse_dividend_resolution(pages, *, symbol, published, annual):
    prefix = "ANNUAL" if annual else "INTERIM"
    period = "度" if annual else "中期"
    if not pages or len(pages) > 16 or any(not page.strip() for page in pages):
        raise ValueError(prefix + "_DIVIDEND_RESOLUTION_INCOMPLETE")
    pages = [unicodedata.normalize("NFKC", page) for page in pages]
    compact = lambda text: re.sub(r"\s+", "", text)
    cover = compact(pages[0])
    meeting_type = r"年?度股东(?:大会|会)" if annual else r"[第0-9一二三四五六七八九十]+次临时股东(?:大会|会)"
    title = re.search(r"(20[0-9]{2})年" + meeting_type + "决议公告", cover)
    code = re.findall(r"证券代码:([0-9]{6})", cover)
    meeting = re.findall(r"股东(?:大会|会)召开的时间:" + _DAY, cover)
    footer = re.search(r"董事会" + _DAY + r"(?:[0-9]{1,3})?$", compact(pages[-1]))
    attendees = re.findall(r"(?m)出席会议的股东所持有表决权的股份总数\s*\(股\)\s*([0-9,]+)[ \t]*$", pages[0].replace("\r", "\n"))
    if annual and title and code == [symbol] and footer and not meeting and not attendees:
        return _parse_numbered_annual_resolution(pages, symbol=symbol, published=published,
                                                 fiscal_year=int(title[1]), footer=footer)
    if not title or code != [symbol] or len(meeting) != 1 or not footer or len(attendees) != 1:
        raise ValueError(prefix + "_DIVIDEND_RESOLUTION_IDENTITY_UNVERIFIED")
    held = date(*map(int, meeting[0]))
    if held.year != int(title[1]) + int(annual) or not held <= date(*map(int, footer.groups())) <= published:
        raise ValueError(prefix + "_DIVIDEND_RESOLUTION_CHRONOLOGY_UNVERIFIED")

    items = []
    for physical_page, page in enumerate(pages, 1):
        for block in re.split(r"\d+\s*[、.]\s*议案名称\s*:", page):
            agenda = re.match(r"\s*《([^》]{1,120})》\s*审议结果\s*:\s*([^\s]+)", block)
            if not agenda:
                continue
            proposal = re.fullmatch(r"(?:公司)?(?:关于)?(20[0-9]{2})年" + period + r"利润分配预案(?:的议案)?", compact(agenda[1]))
            if proposal:
                items.append((physical_page, agenda, proposal, block))
    if len(items) != 1:
        raise ValueError(prefix + "_DIVIDEND_RESOLUTION_AGENDA_UNVERIFIED")
    page, agenda, proposal, block = items[0]
    rows = re.findall(r"(?m)^\s*A\s*股\s+" + _VOTES + r"\s*$", block)
    if int(proposal[1]) != int(title[1]) or agenda[2] != "通过" or len(rows) != 1:
        raise ValueError(prefix + "_DIVIDEND_RESOLUTION_PASS_UNVERIFIED")
    yes, no, abstain = (int(value.replace(",", "")) for value in rows[0])
    total = int(attendees[0].replace(",", ""))
    if yes + no + abstain != total or yes * 2 <= total:
        raise ValueError(prefix + "_DIVIDEND_RESOLUTION_VOTES_NOT_RECONCILED")
    return dict(symbol=symbol, fiscal_year=int(title[1]), meeting_date=held.isoformat(),
                published_date=published.isoformat(), physical_page=page,
                yes_votes=yes, no_votes=no, abstentions=abstain, decision="APPROVED",
                implementation_verified=False, payment_verified=False, action="no_order")


def _parse_numbered_annual_resolution(pages, *, symbol, published, fiscal_year, footer):
    """Verify the annual agenda and full vote counts in the numbered SZSE layout."""
    text = re.sub(r"\s+", "", "".join(pages))
    cover = re.sub(r"\s+", "", pages[0])
    meeting = re.findall(r"会议召开日期和时间:.*?现场会议时间:" + _DAY, cover)
    attendees = re.findall(
        r"股东出席的总体情况:通过现场和网络投票的股东[\d,]+人,代表股份([\d,]+)股", text,
    )
    if len(meeting) != 1 or len(attendees) != 1:
        raise ValueError("ANNUAL_DIVIDEND_RESOLUTION_IDENTITY_UNVERIFIED")
    held = date(*map(int, meeting[0]))
    if held.year != fiscal_year + 1 or not held <= date(*map(int, footer.groups())) <= published:
        raise ValueError("ANNUAL_DIVIDEND_RESOLUTION_CHRONOLOGY_UNVERIFIED")
    pattern = (
        r"\d+\.00《(20\d{2})年度利润分配方案》表决结果:审议通过。总表决情况:"
        r"同意([\d,]+)股,占出席会议所有股东所持股份的\d+\.\d+%;"
        r"反对([\d,]+)股,占出席会议所有股东所持股份的\d+\.\d+%;"
        r"弃权([\d,]+)股(?:\([^)]*\))?,占出席会议所有股东所持股份的\d+\.\d+%。"
    )
    votes = re.findall(pattern, text)
    agenda_pages = [i for i, page in enumerate(pages, 1)
                    if re.search(r"\d+\.00《20\d{2}年度利润分配方案》", re.sub(r"\s+", "", page))]
    if len(votes) != 1 or len(agenda_pages) != 1 or int(votes[0][0]) != fiscal_year:
        raise ValueError("ANNUAL_DIVIDEND_RESOLUTION_AGENDA_UNVERIFIED")
    yes, no, abstain = (int(count.replace(",", "")) for count in votes[0][1:])
    total = int(attendees[0].replace(",", ""))
    if yes + no + abstain != total or yes * 2 <= total:
        raise ValueError("ANNUAL_DIVIDEND_RESOLUTION_VOTES_NOT_RECONCILED")
    return dict(symbol=symbol, fiscal_year=fiscal_year, meeting_date=held.isoformat(),
                published_date=published.isoformat(), physical_page=agenda_pages[0],
                yes_votes=yes, no_votes=no, abstentions=abstain, decision="APPROVED",
                implementation_verified=False, payment_verified=False, action="no_order")
