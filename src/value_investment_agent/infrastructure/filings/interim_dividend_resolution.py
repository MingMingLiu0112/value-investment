"""Read an exact interim dividend vote from a shareholder resolution original."""
from datetime import date
import re
import unicodedata


_DAY = r"(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日"
_VOTES = r"(\d[\d,]*)\s+\d+\.\d+\s+(\d[\d,]*)\s+\d+\.\d+\s+(\d[\d,]*)\s+\d+\.\d+"


def parse_interim_dividend_resolution(pages, *, symbol, published):
    """Identify the approved agenda item, without inferring amount or payment."""
    if not pages or len(pages) > 16 or any(not page.strip() for page in pages):
        raise ValueError("INTERIM_DIVIDEND_RESOLUTION_INCOMPLETE")
    pages = [unicodedata.normalize("NFKC", page) for page in pages]
    compact = lambda text: re.sub(r"\s+", "", text)
    cover = compact(pages[0])
    title = re.search(r"(20[0-9]{2})年[第0-9一二三四五六七八九十]+次临时股东(?:大会|会)决议公告", cover)
    code = re.findall(r"证券代码:([0-9]{6})", cover)
    meeting = re.findall(r"股东(?:大会|会)召开的时间:" + _DAY, cover)
    footer = re.search(r"董事会" + _DAY + r"(?:[0-9]{1,3})?$", compact(pages[-1]))
    attendees = re.findall(r"(?m)出席会议的股东所持有表决权的股份总数\s*\(股\)\s*([0-9,]+)[ \t]*$", pages[0].replace("\r", "\n"))
    if not title or code != [symbol] or len(meeting) != 1 or not footer or len(attendees) != 1:
        raise ValueError("INTERIM_DIVIDEND_RESOLUTION_IDENTITY_UNVERIFIED")
    held = date(*map(int, meeting[0]))
    if held.year != int(title[1]) or not held <= date(*map(int, footer.groups())) <= published:
        raise ValueError("INTERIM_DIVIDEND_RESOLUTION_CHRONOLOGY_UNVERIFIED")

    items = []
    for physical_page, page in enumerate(pages, 1):
        for block in re.split(r"\d+\s*[、.]\s*议案名称\s*:", page):
            agenda = re.match(r"\s*《([^》]{1,120})》\s*审议结果\s*:\s*([^\s]+)", block)
            if not agenda:
                continue
            proposal = re.fullmatch(r"(?:公司)?(?:关于)?(20[0-9]{2})年中期利润分配预案(?:的议案)?", compact(agenda[1]))
            if proposal:
                items.append((physical_page, agenda, proposal, block))
    if len(items) != 1:
        raise ValueError("INTERIM_DIVIDEND_RESOLUTION_AGENDA_UNVERIFIED")
    page, agenda, proposal, block = items[0]
    rows = re.findall(r"(?m)^\s*A\s*股\s+" + _VOTES + r"\s*$", block)
    if int(proposal[1]) != held.year or agenda[2] != "通过" or len(rows) != 1:
        raise ValueError("INTERIM_DIVIDEND_RESOLUTION_PASS_UNVERIFIED")
    yes, no, abstain = (int(value.replace(",", "")) for value in rows[0])
    total = int(attendees[0].replace(",", ""))
    if yes + no + abstain != total or yes * 2 <= total:
        raise ValueError("INTERIM_DIVIDEND_RESOLUTION_VOTES_NOT_RECONCILED")
    return dict(symbol=symbol, fiscal_year=held.year, meeting_date=held.isoformat(),
                published_date=published.isoformat(), physical_page=page,
                yes_votes=yes, no_votes=no, abstentions=abstain, decision="APPROVED",
                implementation_verified=False, payment_verified=False, action="no_order")
