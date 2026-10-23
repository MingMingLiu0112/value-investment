"""Narrow cash-only implementation-body parser with native registry replay."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

from ..evidence.historical_distribution_correspondence import verify_distribution_correspondence
from ..evidence.historical_price_correspondence import require_inside, sha256_file
from ..filings.official_pdf import validate_pdf_original
from ..filings.pdf_text import extract_pages
from ...corporate_actions import extract_distribution_dates
from ...quote_sessions import CHINA


PARSER_VERSION = "sse-explicit-cash-implementation-body-v1"


def _compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def revision_warning(pages):
    text = _compact("".join(pages))
    return any(word in text for word in ("更正", "修订", "取消", "作废", "撤销"))


def parse_cash_implementation_pages(pages: list[str], *, symbol: str) -> dict:
    """Unsupported forms are rejected, not guessed from a dividend keyword."""
    if not pages or len(pages) > 16 or any(not page.strip() for page in pages):
        raise ValueError("Complete readable implementation pages required")
    text = _compact("".join(pages))
    if len(text) > 120_000 or f"证券代码:{symbol}" not in _compact(pages[0]):
        raise ValueError("Implementation issuer/text bounds mismatch")
    if revision_warning(pages):
        raise ValueError("Revision/cancellation text requires explicit lineage review")
    if "权益分派实施公告" not in _compact(pages[0]) or "差异化分红送转:否" not in text:
        raise ValueError("Explicit nondifferential implementation required")
    if any(word in text for word in ("送红股", "转增股本", "配股", "拆股", "合股", "股份转换")):
        raise ValueError("Possible noncash terms require a separate reviewed model")
    # Full-match the complete scheme between its section boundaries. Additional
    # share/rights terms or an unknown layout cannot silently become cash-only.
    schemes = [(index, match) for index, page in enumerate(pages, 1)
               if (match := re.search(r"\(三\)分配方案:(.*?)三、相关日期", _compact(page)))]
    if len(schemes) != 1:
        raise ValueError("One complete scheme on a traceable page required")
    scheme_page, scheme = schemes[0]
    number = r"((?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?)"
    terms = re.fullmatch(r"本次利润分配以方案实施前的公司总股本" + number
        + r"股为基数,每股派发现金红利" + number + r"元\(含税\),共计派发现金红利"
        + number + r"元\(含税\)。", scheme[1] if scheme else "")
    if terms is None:
        raise ValueError("Unsupported or noncash distribution scheme")
    shares, cash, total = (Decimal(value.replace(",", "")) for value in terms.groups())
    if min(shares, cash, total) <= 0 or shares != shares.to_integral_value():
        raise ValueError("Invalid cash scheme quantities")
    if (shares * cash).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != total:
        raise ValueError("Declared total does not reconcile with gross cash per share")
    header = re.findall(r"A股每股现金红利([0-9.]+)元\(含税\)", text)
    if len(header) != 1 or Decimal(header[0]) != cash:
        raise ValueError("Header cash and implementation scheme disagree")
    dates = {}
    candidates = extract_distribution_dates(pages)
    for key in ("record_date", "ex_date", "cash_payment_date"):
        values = {row["value"] for row in candidates if row["field"] == key}
        if len(values) != 1:
            raise ValueError("Implementation date missing or conflicting: " + key)
        dates[key] = values.pop()
    if not dates["record_date"] < dates["ex_date"] <= dates["cash_payment_date"]:
        raise ValueError("Invalid implementation chronology")
    publication = re.search(r"董事会(20\d{2})年(\d{1,2})月(\d{1,2})日$", text)
    identity = re.search(r"公告编号:((?:临)?20\d{2}-\d+)", _compact(pages[0]))
    if not publication or not identity:
        raise ValueError("Publication date or announcement number absent")
    published = date(*map(int, publication.groups()))
    if published.isoformat() > dates["record_date"]:
        raise ValueError("Publication follows record date")
    return dict(parser_version=PARSER_VERSION, symbol=symbol, announcement_number=identity[1],
        published_date=published.isoformat(), **dates, cash_per_share=str(cash),
        total_shares=str(shares), total_gross_cash=str(total), currency="CNY",
        event_kind="EXPLICIT_NONDIFFERENTIAL_CASH_ONLY_IMPLEMENTATION",
        body_terms_reconciled=True, date_candidates=candidates,
        body_page_count=len(pages), term_pages=dict(cash_header=[1], scheme=[scheme_page],
            chronology=sorted({row["page"] for row in candidates}), publication=[len(pages)]),
        amendment_chain_verified=False, action="no_order")


def _pdf(root, ref, now):
    stamp = datetime.fromisoformat(ref["available_at"])
    url = urlparse(ref["url"])
    publication_path = re.fullmatch(r"/finalpage/(20\d{2}-\d{2}-\d{2})/[0-9]+\.PDF", url.path, re.I)
    if (stamp.utcoffset() is None or stamp > now or url.scheme != "https"
            or url.hostname != "static.cninfo.com.cn" or url.username or url.password
            or url.query or url.fragment or not publication_path
            or date.fromisoformat(publication_path[1]) > stamp.astimezone(CHINA).date()):
        raise ValueError("Official PDF acquisition/URL unavailable")
    path = require_inside(root, root / ref["path"], "cash implementation original")
    if Path(ref["path"]).is_absolute() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Invalid PDF path/size")
    if sha256_file(path) != ref["sha256"]:
        raise ValueError("Implementation PDF hash mismatch")
    validate_pdf_original(path)
    pages = extract_pages(path, limit=17)
    if sha256_file(path) != ref["sha256"] or not pages or len(pages) > 16:
        raise ValueError("Implementation PDF changed or exceeds parser scope")
    return pages, stamp


def load_cash_implementation(*, root: Path, symbol: str, record_date: date,
        registry_binding: dict, now: datetime, related_disclosure_bindings: tuple = ()) -> dict:
    """Reconcile one native registry event with its implementation body.

    Empty related bindings never prove absence of corrections. Any supplied
    correction/cancellation blocks mapping pending lineage review.
    """
    if now.utcoffset() is None or type(record_date) is not date:
        raise ValueError("Explicit record date and aware cutoff required")
    root = root.resolve()
    available = datetime.fromisoformat(registry_binding["available_at"])
    path = require_inside(root, root / registry_binding["path"], "cash registry")
    if (available.utcoffset() is None or available > now or Path(registry_binding["path"]).is_absolute()
            or path.stat().st_size > 4 * 1024 * 1024 or sha256_file(path) != registry_binding["sha256"]):
        raise ValueError("Cash registry binding unavailable")
    rows = [row for row in json.loads(path.read_bytes())["events"]
            if row["symbol"] == symbol and row["record_date"] == record_date.isoformat()]
    if len(rows) != 1 or len(rows[0]["evidence"]) != 1:
        raise ValueError("One event with one implementation original required")
    event = rows[0]
    original = dict(event["evidence"][0], available_at=available.isoformat())
    proof = verify_distribution_correspondence(root=root, symbol=symbol,
        sessions=[dict(date=record_date.isoformat()), dict(date=record_date.isoformat())],
        cash_events=[dict(event_id=symbol + ":" + record_date.isoformat(), record_date=event["record_date"],
            ex_date=event["ex_date"], payment_date=event["cash_payment_date"], cash_per_share=event["cash_per_share"],
            bonus_shares_per_share=event.get("bonus_shares_per_share", "0"),
            bonus_listing_date=event.get("bonus_listing_date"))],
        references=[dict(kind="reviewed_event_registry", path=registry_binding["path"],
                         sha256=registry_binding["sha256"]), dict(kind="distribution", **event["evidence"][0])])
    if proof["status"] != "MATCH" or Decimal(event.get("bonus_shares_per_share") or "0") != 0:
        raise ValueError("Cash-only registry correspondence not established")
    pages, acquired = _pdf(root, original, now)
    parsed = parse_cash_implementation_pages(pages, symbol=symbol)
    if any(parsed[key] != event[key] for key in ("record_date", "ex_date", "cash_payment_date")):
        raise ValueError("Registry dates differ from implementation body")
    if Decimal(parsed["cash_per_share"]) != Decimal(event["cash_per_share"]):
        raise ValueError("Registry cash differs from implementation body")
    if (date.fromisoformat(parsed["published_date"]) > acquired.astimezone(CHINA).date()
            or date.fromisoformat(parsed["ex_date"]) > now.astimezone(CHINA).date()
            or f'/finalpage/{parsed["published_date"]}/' not in original["url"]):
        raise ValueError("Publication/effectivity/acquisition dates unavailable")
    if len(related_disclosure_bindings) > 16:
        raise ValueError("Related document count exceeds scope")
    warnings = []
    for ref in related_disclosure_bindings:
        related, _ = _pdf(root, ref, now)
        if f"证券代码:{symbol}" not in _compact(related[0]):
            raise ValueError("Related disclosure issuer mismatch")
        if revision_warning(related):
            warnings.append(dict(binding=dict(ref), status="REVISION_OR_CANCELLATION_REQUIRES_LINKAGE"))
    references = [dict(registry_binding), original, *map(dict, related_disclosure_bindings)]
    if any(sha256_file(require_inside(root, root / ref["path"], "cash event source"))
           != ref["sha256"] for ref in references):
        raise ValueError("Cash event source changed during read")
    return dict(terms=parsed, registry_correspondence=proof,
        evidence_bindings=references, cash_payment_status="DECLARED_SCHEDULE_NOT_PROOF_OF_RECEIPT",
        body_evidence_binding=dict(path=original["path"], sha256=original["sha256"],
            url=original["url"], read_pages=list(range(1, parsed["body_page_count"] + 1))),
        revision_status="PENDING_LINKAGE" if warnings else "ABSENCE_NOT_PROVEN",
        revision_warnings=warnings, complete_window_coverage=False,
        historical_availability_proven=False, action="no_order")
