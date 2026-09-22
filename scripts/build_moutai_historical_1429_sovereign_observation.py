"""Build the narrow 2014 China sovereign-bond coupon observation package for Moutai R1."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/moutai-historical-1429-sovereign-observation-20260922"
POINTER = ROOT / "runtime/company-research/moutai-historical-1429-sovereign-observation-latest.json"

DECISION_WINDOW_EVIDENCE = ROOT / (
    "runtime/strategy-validation/moutai-capital-entry-20260920T092929069969Z/result.json"
)
DECISION_WINDOW_HASH = (
    "201535069fc2397c007c0f6cddb13927c054fd683f675df9e640b43feb4b4e8a"
)

CHINABOND_CANDIDATE = ROOT / (
    "runtime/strategy-validation/moutai-historical-chinabond-government-2014-20260920T133600Z/inspection.json"
)
CHINABOND_CANDIDATE_HASH = (
    "d9df14324d92e904a93b6bf2dd196760eead13f77a7e24243ff45e5343ad004e"
)

REVIEW_DATE = date(2026, 9, 22)

RAW_SOURCES = {
    "mof_2014_no_91_primary": {
        "filename": "mof-2014-no-91-primary.html",
        "url": "http://m.mof.gov.cn/tzgg/201412/t20141217_1168834.htm",
        "sha256": "53cb45825a646d023a70e8c3934247b5970fe380d0a4738b54e56e6ff52d08ce",
        "encoding": "gb2312",
        "content_type": "text/html",
        "get_status": 200,
        "source_role": "Ministry of Finance primary issue notice",
    },
    "szse_2014_12_22_listing_notice": {
        "filename": "szse-2014-12-22-listing-notice.html",
        "url": "http://investor.szse.cn/disclosure/notice/t20141222_511603.html",
        "sha256": "64c14b6c7d12a02be0c043c092596f92804d695b8cc235eead03ddd48c5e498d",
        "encoding": "utf-8",
        "content_type": "text/html",
        "get_status": 200,
        "source_role": "Shenzhen Stock Exchange listing notice",
    },
    "mof_2015_no_5_later_corroboration": {
        "filename": "mof-2015-no-5-corroboration.html",
        "url": "http://www.mof.gov.cn/gp/xxgkml/gks/201501/t20150128_2511171.htm",
        "sha256": "271e2907357010a0a73e91cc1d0b12a7095efef279e94ec790752e11b7560353",
        "encoding": "utf-8",
        "content_type": "text/html",
        "get_status": 200,
        "source_role": "Ministry of Finance later reissue notice",
    },
    "sse_2014_factbook_bond_record": {
        "filename": "sse-2014-factbook-14-guo-zai-29.pdf",
        "url": (
            "http://www.sse.com.cn/aboutus/publication/factbook/documents/c/10170567/"
            "files/cafa59ab90014dd98a4b3de148a75a5d.pdf"
        ),
        "sha256": "e33e456624c8065bb46951a2f6eabd8aa294e192d0a285e3f50bf44fde08fa1d",
        "encoding": None,
        "content_type": "application/pdf",
        "get_status": 200,
        "source_role": "Shanghai Stock Exchange 2015 market-data statistical record",
    },
}

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_html(path: Path, encoding: str) -> str:
    text = TAG_RE.sub(" ", path.read_text(encoding=encoding))
    return SPACE_RE.sub(" ", html.unescape(text)).strip()


def normalized_pdf_page(path: Path, page_index: int) -> str:
    reader = PdfReader(str(path))
    if page_index < 0 or page_index >= len(reader.pages):
        raise ValueError(f"PDF page out of range: {page_index}")
    return SPACE_RE.sub(" ", reader.pages[page_index].extract_text() or "").strip()


def source_record(source_id: str) -> dict:
    spec = RAW_SOURCES[source_id]
    path = OUT / spec["filename"]
    actual = sha256(path)
    if actual != spec["sha256"].lower():
        raise ValueError(f"Source hash mismatch for {source_id}")
    stat = path.stat()
    return {
        "id": source_id,
        "url": spec["url"],
        "path": str(path.relative_to(ROOT)),
        "sha256": actual,
        "archived_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "byte_size": stat.st_size,
        "content_type": spec["content_type"],
        "encoding": spec["encoding"],
        "http_get_status": spec["get_status"],
        "http_head_status": None,
        "source_role": spec["source_role"],
    }


def source_ref(source: dict, *, description: str) -> dict:
    return {
        "id": source["id"],
        "path": source["path"],
        "sha256": source["sha256"],
        "url": source["url"],
        "description": description,
    }


def validate_source_content() -> None:
    primary = normalized_html(OUT / RAW_SOURCES["mof_2014_no_91_primary"]["filename"], "gb2312")
    required_primary = [
        "中华人民共和国财政部公告2014年第91号",
        "2014年记账式附息（二十九期）国债",
        "282.4亿元",
        "票面年利率为3.77%",
        "2014年12月18日开始计息",
        "12月24日起上市交易",
        "2024年12月18日偿还本金并支付最后一次利息",
        "2014年12月17日",
    ]
    missing = [term for term in required_primary if term not in primary]
    if missing:
        raise ValueError(f"MOF 2014 No. 91 page missing required terms: {missing}")

    listing = normalized_html(
        OUT / RAW_SOURCES["szse_2014_12_22_listing_notice"]["filename"], "utf-8"
    )
    required_listing = [
        "关于2014年记账式附息（二十九期）国债上市交易的通知",
        "2014-12-22",
        "101429",
        "国债 1429",
        "3.77",
        "2024",
        "12 月 18 日",
    ]
    missing = [term for term in required_listing if term not in listing]
    if missing:
        raise ValueError(f"SZSE listing page missing required terms: {missing}")

    reissue = normalized_html(
        OUT / RAW_SOURCES["mof_2015_no_5_later_corroboration"]["filename"], "utf-8"
    )
    required_reissue = [
        "中华人民共和国财政部公告2015年第5号",
        "第一次续发行2014年记账式附息（二十九期）国债",
        "2015年1月28日",
        "票面年利率为3.77%",
        "282.4亿元",
    ]
    missing = [term for term in required_reissue if term not in reissue]
    if missing:
        raise ValueError(f"MOF 2015 No. 5 page missing required terms: {missing}")

    cover = normalized_pdf_page(
        OUT / RAW_SOURCES["sse_2014_factbook_bond_record"]["filename"], 0
    )
    if "2015年市场资料" not in cover:
        raise ValueError("SSE factbook cover is not the expected 2015 market-data document")
    bond_page = normalized_pdf_page(
        OUT / RAW_SOURCES["sse_2014_factbook_bond_record"]["filename"], 140
    )
    required_pdf = [
        "019429",
        "14国债29",
        "282.4000",
        "2014-12-18",
        "2014-12-24",
        "2024-12-18",
        "10.00",
        "3.7700",
    ]
    missing = [term for term in required_pdf if term not in bond_page]
    if missing:
        raise ValueError(f"SSE factbook bond page missing required terms: {missing}")


def decision_window_receipt() -> dict:
    actual = sha256(DECISION_WINDOW_EVIDENCE)
    if actual != DECISION_WINDOW_HASH.lower():
        raise ValueError(f"Historical execution receipt hash mismatch: {actual}")
    payload = json.loads(DECISION_WINDOW_EVIDENCE.read_text(encoding="utf-8"))
    fills = [
        row
        for row in payload.get("results", [])
        if row.get("fill", {}).get("date") == "2015-01-06"
        and row.get("fill", {}).get("price") == 200.0
    ]
    if not fills:
        raise ValueError("Historical execution receipt has no 2015-01-06 CNY 200.00 fill")
    return {
        "id": "moutai_historical_executed_entry_receipt",
        "path": str(DECISION_WINDOW_EVIDENCE.relative_to(ROOT)),
        "sha256": actual,
        "url": None,
        "description": (
            "Existing archived replay receipt containing the first 2015-01-06 opening-price fill"
        ),
    }


def chinabond_candidate_ref() -> dict:
    actual = sha256(CHINABOND_CANDIDATE)
    if actual != CHINABOND_CANDIDATE_HASH.lower():
        raise ValueError(f"ChinaBond candidate inspection hash mismatch: {actual}")
    return {
        "id": "moutai_historical_chinabond_government_2014_candidate",
        "path": str(CHINABOND_CANDIDATE.relative_to(ROOT)),
        "sha256": actual,
        "url": None,
        "description": (
            "Prior annual curve candidate rejected for point-in-time historical availability; "
            "not changed by this coupon observation"
        ),
    }


def publication_records() -> list[dict]:
    return [
        {
            "id": "mof_2014_no_91_primary",
            "title": "中华人民共和国财政部公告2014年第91号",
            "publication_date": "2014-12-17",
            "source_id": "mof_2014_no_91_primary",
            "source_role": "issuer_primary_notice",
            "published_before_decision_date": True,
            "availability_role": "primary_decision_window_evidence",
            "key_terms": {
                "issue_name": "2014年记账式附息（二十九期）国债",
                "tenor_years": 10,
                "coupon_percent": "3.77",
                "issue_amount_cny_billion": "282.4",
                "interest_start_date": "2014-12-18",
                "listing_date": "2014-12-24",
                "maturity_date": "2024-12-18",
            },
        },
        {
            "id": "szse_2014_12_22_listing_notice",
            "title": "关于2014年记账式附息（二十九期）国债上市交易的通知",
            "publication_date": "2014-12-22",
            "source_id": "szse_2014_12_22_listing_notice",
            "source_role": "exchange_listing_notice",
            "published_before_decision_date": True,
            "availability_role": "independent_decision_window_corroboration",
            "key_terms": {
                "szse_code": "101429",
                "szse_short_name": "国债1429",
                "coupon_percent": "3.77",
                "tenor_years": 10,
                "listing_date": "2014-12-24",
                "maturity_date": "2024-12-18",
            },
        },
        {
            "id": "mof_2015_no_5_later_corroboration",
            "title": "中华人民共和国财政部公告2015年第5号",
            "publication_date": "2015-01-28",
            "source_id": "mof_2015_no_5_later_corroboration",
            "source_role": "issuer_later_reissue_notice",
            "published_before_decision_date": False,
            "availability_role": "later_independent_corroboration_only",
            "key_terms": {
                "original_issue_name": "2014年记账式附息（二十九期）国债",
                "original_interest_start_date": "2014-12-18",
                "original_coupon_percent": "3.77",
                "original_issue_amount_cny_billion": "282.4",
            },
        },
        {
            "id": "sse_2014_factbook_bond_record",
            "title": "2015年市场资料",
            "publication_date": "2015-annual-publication",
            "source_id": "sse_2014_factbook_bond_record",
            "source_role": "exchange_statistical_record",
            "published_before_decision_date": False,
            "availability_role": "later_independent_corroboration_only",
            "key_terms": {
                "sse_code": "019429",
                "sse_short_name": "14国债29",
                "issue_amount_cny_billion": "282.4",
                "interest_start_date": "2014-12-18",
                "listing_date": "2014-12-24",
                "maturity_date": "2024-12-18",
                "tenor_years": 10,
                "coupon_percent": "3.77",
            },
        },
    ]


def build() -> dict:
    validate_source_content()
    sources = {source_id: source_record(source_id) for source_id in RAW_SOURCES}
    decision_ref = decision_window_receipt()
    publications = publication_records()
    return {
        "symbol": "600519",
        "review_date": REVIEW_DATE.isoformat(),
        "engineering_status": "historical_1429_sovereign_coupon_observation_package_complete",
        "status": "dated_official_coupon_observation_archived_without_capital_cost_input",
        "r1_status": "not_passed",
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "financial_scope_approved": False,
        "simulation_eligible": False,
        "replay_eligible": False,
        "strategy_backtest_complete": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Archive a dated official sovereign-bond coupon observation that was publicly "
            "documented before the first archived Moutai 2015-01-06 execution fill. The coupon is "
            "a contract term, not a resolved risk-free rate or cost of equity."
        ),
        "decision_window": {
            "first_archived_fill_date": "2015-01-06",
            "first_archived_fill_price_cny": 200.0,
            "evidence_ref": decision_ref,
        },
        "instrument": {
            "issue_name": "2014年记账式附息（二十九期）国债",
            "short_names": ["国债1429", "14国债29"],
            "exchange_codes": {"szse": "101429", "sse": "019429"},
            "tenor_years": 10,
            "coupon_percent": "3.77",
            "issue_amount_cny_billion": "282.4",
            "interest_start_date": "2014-12-18",
            "listing_date": "2014-12-24",
            "maturity_date": "2024-12-18",
            "interest_payment_dates": ["June 18", "December 18"],
        },
        "publications": publications,
        "summary": {
            "primary_issuer_notices_before_decision_date": 1,
            "exchange_listing_notices_before_decision_date": 1,
            "later_independent_corroborations": 2,
            "registered_capital_cost_inputs": 0,
        },
        "proven": [
            "A Ministry of Finance primary issue notice dated 2014-12-17 was published before 2015-01-06.",
            "The notice specifies a 10-year fixed-coupon sovereign bond with a 3.77% annual coupon, 282.4 billion CNY actual issue amount, 2014-12-18 interest start, 2014-12-24 listing, and 2024-12-18 maturity.",
            "A SZSE listing notice dated 2014-12-22 independently confirms code 101429, name 国债1429, coupon 3.77%, 10-year tenor, 2014-12-24 listing and 2024-12-18 maturity before the decision date.",
            "The later MOF 2015 No. 5 reissue notice and SSE 2015 market-data record independently repeat the original instrument terms.",
            "The existing archived execution replay contains a 2015-01-06 fill at CNY 200.00.",
        ],
        "not_proven": [
            "The 3.77% issue coupon was the contemporaneous risk-free rate on 2015-01-06.",
            "The issue coupon represented a transaction-based yield-to-maturity available to a January 2015 investor.",
            "A historical beta, equity risk premium, cost of equity, or WACC is resolved.",
            "The full Moutai R1 point-in-time decision chain is validated.",
            "The current conditional model can be treated as a formal fair value or trading signal.",
        ],
        "definition_breaks": [
            "A fixed issue coupon is a contract term, not a zero-coupon or yield-curve risk-free rate.",
            "A 2014-12-17 issue notice is available evidence, but does not by itself establish the yield observable in the secondary market on 2015-01-06.",
            "A 2015-01-28 reissue and a 2015 annual statistical record corroborate terms, not decision-window availability.",
            "Point-in-time instrument documentation is not the same as a complete historical capital-cost model.",
        ],
        "point_in_time_policy": [
            "Only the MOF 2014-12-17 issue notice and SZSE 2014-12-22 listing notice are used as pre-2015-01-06 documentation.",
            "The 2015 reissue and SSE 2015 market-data record are retained only as independent later corroboration.",
            "Hash-bound 2026 downloads confirm currently addressable official pages; they do not prove the pages were never revised after publication.",
            "The decision date is anchored only to the existing archived execution replay, not to a newly invented trade.",
        ],
        "forbidden_calculations": [
            "Register the 3.77% coupon as a historical risk-free rate.",
            "Convert the coupon directly into a historical cost of equity.",
            "Use the coupon as a missing beta or equity-risk-premium proxy.",
            "Replace the unresolved historical WACC with this observation.",
            "Claim that R1 passed because the coupon predates the first archived fill.",
        ],
        "blockers": [
            "historical_secondary_market_risk_free_rate_not_resolved",
            "historical_beta_not_resolved",
            "historical_equity_risk_premium_not_resolved",
            "historical_cost_of_equity_not_resolved",
            "full_r1_point_in_time_decision_chain_not_validated",
        ],
        "registered_capital_cost_inputs": [],
        "evidence_refs": [
            source_ref(sources["mof_2014_no_91_primary"], description="Primary issue terms published 2014-12-17"),
            source_ref(sources["szse_2014_12_22_listing_notice"], description="SZSE listing notice published 2014-12-22"),
            source_ref(sources["mof_2015_no_5_later_corroboration"], description="MOF reissue notice published 2015-01-28"),
            source_ref(sources["sse_2014_factbook_bond_record"], description="SSE 2015 market-data bond record"),
            decision_ref,
            chinabond_candidate_ref(),
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    source_hashes = {
        source_id: source_record(source_id)["sha256"]
        for source_id in RAW_SOURCES
    }
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
        "prior_evidence_sha256s": {
            "moutai_historical_executed_entry_receipt": DECISION_WINDOW_HASH,
            "moutai_historical_chinabond_government_2014_candidate": CHINABOND_CANDIDATE_HASH,
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": digest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": digest,
        "status": payload["status"],
        "r1_status": payload["r1_status"],
        "registered_capital_cost_inputs": payload["registered_capital_cost_inputs"],
        "summary": payload["summary"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
