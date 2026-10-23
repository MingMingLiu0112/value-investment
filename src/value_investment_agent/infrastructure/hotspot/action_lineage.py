"""Bounded official-body identities and explicit amendment references."""
from datetime import date, datetime
import re

from .cash_implementation import _compact, _pdf
from ..evidence.historical_price_correspondence import require_inside, sha256_file
from ...domain.hotspot.action_lineage import relate_action_documents
from ...quote_sessions import CHINA


NUMBER = r"(?:临)?20\d{2}-\d+"
REFERENCE = re.compile(r"于(20\d{2})年(\d{1,2})月(\d{1,2})日在[^。]{0,180}?披露了《([^》]{1,120})》"
                       r"\(公告编号:?(" + NUMBER + r")\)")


def parse_action_identity(pages, *, symbol):
    if not pages or len(pages) > 16 or sum(map(len, pages)) > 120_000:
        raise ValueError("Readable bounded action document required")
    header_lines = [line for line in pages[0].splitlines() if line.strip() and not line.strip().isdigit()]
    header = _compact("".join(header_lines[:3]))
    text = _compact("".join(pages))
    number = re.search(r"公告编号:?(" + NUMBER + r")", header)
    publication = re.search(r"董事会(20\d{2})年(\d{1,2})月(\d{1,2})日$", text)
    title = re.search(r"20\d{2}年(?:年度|半年度|中期)?权益分派实施(?:的)?(?:更正|修订|取消|撤销)?公告", header)
    if f"证券代码:{symbol}" not in header or not number or not publication or not title:
        raise ValueError("Issuer, action title, own number or footer date unresolved")
    if any(word in header for word in ("澄清", "传闻", "预案", "示例", "不取消", "未取消", "不撤销", "未撤销", "拟取消", "拟撤销")):
        kind = "UNRESOLVED_CHANGE"
    elif any(word in header for word in ("更正公告", "修订公告")):
        kind = "CORRECTION"
    elif re.search(r"(?:关于)?(?:取消|撤销)(?:20\d{2}年(?:年度|中期|半年度)?)?"
                   r"权益分派(?:实施公告|方案)(?:的公告)?$", header):
        kind = "CANCELLATION"
    elif any(word in header for word in ("取消", "撤销", "更正", "修订")):
        kind = "UNRESOLVED_CHANGE"
    else:
        kind = "IMPLEMENTATION"
    preamble = text.split("更正前", 1)[0]
    refs = [dict(number=m[5], title=m[4], published_date=date(*map(int, m.groups()[:3])).isoformat(),
                 matched_text=m[0]) for m in REFERENCE.finditer(preamble)]
    section = re.search(r"更正前:([^:]{1,40}):", text)
    cancellation = re.search(r"(?:^|[。;])(?:本公司|公司)决定(?:取消|撤销)(?:上述|本次)"
        r"(?:权益分派(?:实施公告|方案)?|利润分配方案)[。;]", text)
    noncash = re.search(r"每10股转增([1-9][0-9]*(?:\.[0-9]+)?)股", text)
    return dict(symbol=symbol, announcement_number=number[1], title=title[0], kind=kind,
        published_date=date(*map(int, publication.groups())).isoformat(), references=refs,
        operative_correction="现更正如下:" in text and "更正前:" in text and "更正后:" in text,
        operative_cancellation=cancellation is not None,
        cancellation_statement=cancellation[0] if cancellation else None,
        changed_section=section[1] if section else None,
        unchanged_remainder_declared="其他内容不变" in text,
        noncash_terms_present=True if noncash else None,
        noncash_clause=noncash[0] if noncash else None,
        body_pages=list(range(1, len(pages) + 1)))


def inspect_action_lineage(*, root, symbol, announcements, acquired_at, now):
    """Read originals, not supplied relation flags; all unresolved records remain."""
    result = dict(schema_version="hotspot-source-action-lineage-v1", links=[], unresolved=[],
        evidence_bindings=[], complete_chain_proven=False, comparison_allowed=False,
        historical_availability_proven=False,
        scope="BOUND_HISTORICAL_FILING_RELATION_NOT_CURRENT_PRICE_BASIS_OR_POSITION", action="no_order")
    if len(announcements) > 16:
        result["unresolved"] = [dict(reason="DOCUMENT_COUNT_EXCEEDS_BOUNDED_REVIEW", count=len(announcements))]
        return result
    documents = []
    for announcement in announcements:
        try:
            if len(announcement["evidence_bindings"]) != 1:
                raise ValueError("One bound PDF per action identity required")
            item = announcement["evidence_bindings"][0]
            binding = dict(path=item["path"], sha256=item["sha256"], url=announcement["source_url"],
                           available_at=acquired_at)
            pages, _ = _pdf(root, binding, now)
            identity = parse_action_identity(pages, symbol=symbol)
            if datetime.fromisoformat(announcement["published_at"]).astimezone(CHINA).date().isoformat() != identity["published_date"]:
                raise ValueError("Body publication date differs from official index")
            if f'/finalpage/{identity["published_date"]}/' not in binding["url"]:
                raise ValueError("Body publication date differs from original URL")
            documents.append(dict(identity=identity, binding=binding))
            result["evidence_bindings"].append(binding)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            result["unresolved"].append(dict(announcement_id=announcement["announcement_id"], reason=str(error)))
    originals = [doc for doc in documents if doc["identity"]["kind"] == "IMPLEMENTATION"]
    for amendment in [doc for doc in documents if doc["identity"]["kind"] != "IMPLEMENTATION"]:
        matches = []
        for original in originals:
            relation = relate_action_documents(original["identity"], amendment["identity"])
            if relation["relation_status"] == "EXPLICIT_TARGET_MATCH":
                matches.append(dict(**relation, original_binding=original["binding"], amendment_binding=amendment["binding"],
                    reference_evidence=amendment["identity"]["references"],
                    original_pages=original["identity"]["body_pages"], amendment_pages=amendment["identity"]["body_pages"]))
        if len(matches) == 1:
            result["links"].append(matches[0])
        else:
            result["unresolved"].append(dict(announcement_number=amendment["identity"]["announcement_number"],
                reason="EXPLICIT_ORIGINAL_MISSING_OR_AMBIGUOUS", match_count=len(matches)))
    if any(sha256_file(require_inside(root, root / ref["path"], "lineage original")) != ref["sha256"]
           for ref in result["evidence_bindings"]):
        raise ValueError("Lineage original changed during read")
    return result
