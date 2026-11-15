"""Read a statutory reserve rule from an issuer's articles of association."""

from hashlib import sha256
from pathlib import Path
import re
import unicodedata

from .pdf_text import extract_pages


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def read_statutory_reserve_clause(path: Path, *, issuer: str, expected_sha256: str) -> dict:
    """Verify a unique operative clause. No future appropriation is inferred."""
    if re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None:
        raise ValueError("RESERVE_CHARTER_HASH_REQUIRED")
    if sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("RESERVE_CHARTER_HASH_CHANGED")
    pages = extract_pages(path)
    cover = _compact(pages[0]) if pages else ""
    if not issuer or not re.match(r"^(?:—\d+—)?" + re.escape(_compact(issuer)) + "章程", cover):
        raise ValueError("RESERVE_CHARTER_ISSUER_MISMATCH")
    rule = re.compile(
        r"公司分配当年税后利润时,应当提取利润的(?:10%|百分之十)"
        r"列入公司法定公积金。公司法定公积金累计额为公司注册资本的"
        r"(?:50%|百分之五十)以上的,可以不再提取"
    )
    matches = [(page, match.group()) for page, text in enumerate(pages, 1)
               for match in rule.finditer(_compact(text))]
    if len(matches) != 1:
        raise ValueError("RESERVE_CHARTER_UNIQUE_OPERATIVE_CLAUSE_REQUIRED")
    if sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("RESERVE_CHARTER_HASH_CHANGED")
    page, clause = matches[0]
    return {
        "issuer": issuer, "physical_page": page, "source_sha256": expected_sha256,
        "clause_sha256": sha256(clause.encode("utf-8")).hexdigest(),
        "ordinary_appropriation_ratio": "0.10", "optional_stop_capital_ratio": "0.50",
        "scope": "ISSUER_ARTICLES_RULE_TEXT", "future_appropriation": None,
        "action": "no_order",
    }
