"""Narrow filing identity and attachment parsing; never certify corporate no-change."""
from datetime import datetime
import re

from .cash_implementation import _compact
from .cash_implementation_v2 import _exact_security_header
from .capital_disclosure import parse_hk_form_a_share_buyback
from ...quote_sessions import CHINA


def _page_texts(pages):
    result = []
    for index, page in enumerate(pages, 1):
        lines = [line for line in page.splitlines() if line.strip()]
        if lines and lines[0].strip() == str(index):
            lines = lines[1:]
        result.append(_compact("\n".join(lines)))
    return result


def _legal_name(pages, symbol):
    lines = [_compact(line) for line in pages[0].splitlines() if line.strip() and not line.strip().isdigit()]
    names = [line for line in lines[:5] if re.fullmatch(r"[^，,。:;《》]{3,100}股份有限公司", line)]
    if len(names) != 1 or not _exact_security_header(_compact(pages[0]), symbol):
        raise ValueError("Unique implementation issuer legal name and A code required")
    return names[0]


def _direct_identity(pages, *, name, symbol, published_date):
    texts = _page_texts(pages)
    first, body = texts[0], "".join(texts)
    if not _exact_security_header(first, symbol) or name not in first:
        return None
    try:
        if _legal_name(pages, symbol) != name:
            return None
    except ValueError:
        return None
    signed = re.search(r"董事会(20\d{2})年(\d{1,2})月(\d{1,2})日$", body)
    body_date = datetime(*map(int, signed.groups()), tzinfo=CHINA).date().isoformat() if signed else None
    if body_date is not None and body_date > published_date:
        raise ValueError("Body signature follows official publication date")
    return dict(status="BOUND_ISSUER_A_CODE_AND_BODY_NAME", body_legal_name=name, body_a_code=symbol,
        body_signature_date=body_date, signature_authenticity_independently_proven=False,
        date_scope="BODY_SIGNATURE_DATE_NOT_PUBLIC_AVAILABILITY", document_role="ISSUER_FILING_CONTEXT")


def _attachment_titles(texts):
    matches = re.findall(r"四、附件(.*?)(?:特此公告|董事会)", "".join(texts))
    if len(matches) != 1:
        return []
    section = matches[0]
    if not re.fullmatch(r"(?:\([一二三四五六七八九十]+\)《[^》]{1,300}》)+", section):
        return []
    titles = re.findall(r"《([^》]{1,300})》", section)
    return titles if len(titles) == len(set(titles)) else []


def _references(texts, title, number):
    title_pages = [index for index, text in enumerate(texts, 1) if f"《{title}》" in text]
    number_pages = [index for index, text in enumerate(texts, 1)
        if re.search(r"(?<![0-9])" + re.escape(number) + r"(?![0-9])", text)]
    cues = []
    for index, text in enumerate(texts, 1):
        for match in re.finditer(r"更正|修订|取消|撤销|作废", text):
            if len(cues) < 32:
                cues.append(dict(page=index, cue=match[0], context=text[max(0, match.start() - 35):match.end() + 45]))
    return dict(reference_status="EXPLICIT_IMPLEMENTATION_REFERENCE" if title_pages or number_pages
        else "NO_EXPLICIT_IMPLEMENTATION_REFERENCE_IDENTIFIED", title_reference_pages=title_pages,
        number_reference_pages=number_pages, change_cues=cues, cue_excerpt_limit=32,
        effect_status="NOT_DETERMINED", no_change=None, revision_absence_proven=False,
        scope="REFERENCE_AND_CUES_NOT_PROOF_OF_CASH_REVISION_OR_ITS_ABSENCE")


def _classify(item, *, name, symbol, attachments):
    texts = item["texts"]
    if not any(texts):
        return dict(status="UNRESOLVED", reason="IMAGE_ONLY_OR_UNREADABLE_BODY", document_role="UNRESOLVED")
    direct = _direct_identity(item["pages"], name=name, symbol=symbol, published_date=item["published_date"])
    if direct is not None:
        return direct
    if "FF305" in texts[0]:
        parsed = parse_hk_form_a_share_buyback(item["pages"], symbol=symbol)
        if parsed["submitted_date"] > item["published_date"]:
            raise ValueError("HK form submission follows official publication")
        return dict(status="BOUND_EXPLICIT_A_CODE_IN_HK_FORM", document_role="HK_FORM_A_SHARE_CONTEXT",
            body_a_code=symbol, body_share_class="A", execution_venue=parsed["execution_venue"],
            signature_authenticity_independently_proven=False)
    title = _compact(item["title"])
    sponsors = attachments.get(title, [])
    opinion = re.fullmatch(r"([^，,。:;《》]{3,100}股份有限公司)关于" + re.escape(name)
        + r"股东向特定机构投资者询价转让股份相关资格的核查意见", title)
    mandate = None
    if opinion and texts[0].startswith(title):
        author = opinion[1]
        paragraph = texts[0][len(title):].split("。", 1)[0] + "。"
        alias = r"(?:\(以下简称[^()]{1,60}\))?"
        holder = r"[^(),。;《》]{3,100}(?:股份有限公司|有限公司|合伙企业)(?:\(有限合伙\))?"
        mandate = re.fullmatch(re.escape(author) + alias + "受" + re.escape(name) + alias + r"股东"
            + holder + alias + r"委托,组织实施本次[^。;]{1,100}股东向特定机构投资者询价转让" + alias + "。", paragraph)
        if re.search(r"(?:未受|并未受|未获|未获得)[^。;]{0,80}委托|委托[^。;]{0,50}(?:说法|声明|陈述)不实",
                "".join(texts)):
            mandate = None
    if opinion and sponsors and item.get("official_title_count", 1) != 1:
        return dict(status="UNRESOLVED", reason="ATTACHMENT_TITLE_MATCHES_MULTIPLE_OFFICIAL_ORIGINALS",
            document_role="UNRESOLVED")
    if sponsors and texts[0].startswith(title) and opinion and mandate:
        author = opinion[1]
        if author == name:
            raise ValueError("Distinct third-party author identity unresolved")
        return dict(status="BOUND_ISSUER_ATTACHMENT_AND_EXPLICIT_BODY_SUBJECT",
            document_role="THIRD_PARTY_OPINION_NOT_ISSUER_AUTHORED", body_subject_legal_name=name,
            body_author=author, attachment_anchor_bindings=sponsors,
            body_signature_date=None, signature_authenticity_independently_proven=False,
            date_scope="OFFICIAL_INDEX_DATE_ONLY_NOT_BODY_SIGNATURE_OR_INTRADAY_AVAILABILITY")
    return dict(status="UNRESOLVED", reason="BODY_SUBJECT_OR_CROSS_SHARE_CLASS_MAPPING_NOT_PROVEN",
        document_role="UNRESOLVED")
