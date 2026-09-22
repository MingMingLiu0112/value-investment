"""Build a narrow 2015-01 yield-observation package for Moutai R1.

This package pins dated public observations around the first archived
2015-01-06 fill. It does not register any capital-cost input and does not
change valuation, simulation, backtest, trade, or live admission.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/moutai-historical-2015-01-yield-observations-20260922"
POINTER = ROOT / "runtime/company-research/moutai-historical-2015-01-yield-observations-latest.json"

DECISION_WINDOW_EVIDENCE = ROOT / (
    "runtime/strategy-validation/moutai-capital-entry-20260920T092929069969Z/result.json"
)
DECISION_WINDOW_HASH = (
    "201535069fc2397c007c0f6cddb13927c054fd683f675df9e640b43feb4b4e8a"
)

PRIOR_COUPON_PACKAGE = ROOT / (
    "runtime/company-research/moutai-historical-1429-sovereign-observation-20260922/"
    "evidence.json"
)
PRIOR_COUPON_PACKAGE_HASH = (
    "fc06756d257084c397746a87ea34c2e8d9995858fb4d6396508d52a9ab80f454"
)

CHINABOND_CANDIDATE = ROOT / (
    "runtime/strategy-validation/moutai-historical-chinabond-government-2014-20260920T133600Z/"
    "inspection.json"
)
CHINABOND_CANDIDATE_HASH = (
    "d9df14324d92e904a93b6bf2dd196760eead13f77a7e24243ff45e5343ad004e"
)

REVIEW_DATE = date(2026, 9, 22)
DECISION_DATE = date(2015, 1, 6)
OBSERVATION_DATE = date(2015, 1, 5)

RAW_SOURCES = {
    "chinabond_2015_01_05_history_query": {
        "filename": "chinabond-history-2015-01-05-10y.html",
        "url": (
            "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"
            "?startDate=2015-01-05&endDate=2015-01-05&gjqx=10"
            "&qxId=hzsylqx&locale=cn_ZH"
        ),
        "sha256": "caf7da1d2fc5f8bcd15ac80f5eb06e1550341f6d14d5d0778ddf95d4f043e576",
        "encoding": "utf-8",
        "content_type": "text/html",
        "get_status": 200,
        "source_role": "ChinaBond official historical government-yield query",
    },
    "csj_2015_01_06_A14": {
        "filename": "csj-2015-01-06-A14.html",
        "url": (
            "https://epaper.cs.com.cn/zgzqb/html/2015-01/06/"
            "nw.D110000zgzqb_20150106_3-A14.htm?div=0"
        ),
        "sha256": "2472fe29e62a23081685244e32ed50486083a3ccbc4d69641923a1f03c460ccd",
        "encoding": "utf-8",
        "content_type": "text/html",
        "get_status": 200,
        "source_role": "China Securities Journal dated newspaper page",
    },
    "pbc_2015_monthly_statistics_pdf": {
        "filename": "pbc-chinabond-2015-monthly-statistics.pdf",
        "url": (
            "http://camlmac.pbc.gov.cn/eportal/fileDir/defaultCurSite/resource/"
            "cms/2016/03/2016030411050376993.pdf"
        ),
        "sha256": "893e9080cf434e1dcfcd39fb269d9d818becc86e604943495107aefadc8412c8",
        "encoding": None,
        "content_type": "application/pdf",
        "get_status": 200,
        "source_role": "PBoC later monthly statistics",
    },
    "boc_2014_12_17_daily_reference": {
        "filename": "boc-2014-12-17-daily-reference.html",
        "url": "https://www.bankofchina.com/fimarkets/boud/201412/t20141217_4326832.html",
        "sha256": "4b262617c64797e35c57761b714f8607c20a2a7763e6d5e54a64d6a146428216",
        "encoding": "utf-8",
        "content_type": "text/html",
        "get_status": 200,
        "source_role": "Bank of China dated pre-decision bond-market reference",
    },
}

SPACE_RE = re.compile(r"\s+")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_html(path: Path, encoding: str) -> str:
    soup = BeautifulSoup(path.read_text(encoding=encoding, errors="replace"), "html.parser")
    return SPACE_RE.sub(" ", soup.get_text(" ", strip=True)).strip()


def normalized_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return SPACE_RE.sub(" ", " ".join(pages)).strip()


def require_hash(path: Path, expected: str, source_id: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"Source hash mismatch for {source_id}: {actual}")


def source_record(source_id: str) -> dict:
    spec = RAW_SOURCES[source_id]
    path = OUT / spec["filename"]
    require_hash(path, spec["sha256"], source_id)
    stat = path.stat()
    return {
        "id": source_id,
        "url": spec["url"],
        "path": str(path.relative_to(ROOT)),
        "sha256": spec["sha256"],
        "archived_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "byte_size": stat.st_size,
        "content_type": spec["content_type"],
        "encoding": spec["encoding"],
        "http_get_status": spec["get_status"],
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


def extract_chinabond_ten_year_value(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for row in soup.select("#gjqxData tr"):
        cells = [" ".join(cell.get_text(" ", strip=True).split()) for cell in row.find_all("td")]
        if len(cells) < 9 or cells[0] != "中债国债收益率曲线":
            continue
        if cells[1] != "2015-01-05":
            continue
        if cells[8] != "3.6251":
            raise ValueError(f"Unexpected ChinaBond 2015-01-05 10-year value: {cells[8]!r}")
        return "3.6251"
    raise ValueError("ChinaBond 2015-01-05 government-curve row was not found")


def validate_source_content() -> dict:
    chinabond = normalized_html(
        OUT / RAW_SOURCES["chinabond_2015_01_05_history_query"]["filename"], "utf-8"
    )
    required_chinabond = [
        "中债国债收益率曲线",
        "2015-01-05",
        "3.6251",
        "中央国债登记结算有限责任公司编制",
    ]
    if any(needle not in chinabond for needle in required_chinabond):
        raise ValueError("ChinaBond history page did not contain all required labels")

    csj = normalized_html(OUT / RAW_SOURCES["csj_2015_01_06_A14"]["filename"], "utf-8")
    required_csj = [
        "2015年01月06日",
        "迎接一季度债市美好时光",
        "1月5日银行间市场国债收益率稳中有降",
        "10年期国债收益率分别持稳在3.38%、3.52%、3.60%、3.63%附近",
    ]
    if any(needle not in csj for needle in required_csj):
        raise ValueError("China Securities Journal page did not contain all required statements")

    pbc_text = normalized_pdf(OUT / RAW_SOURCES["pbc_2015_monthly_statistics_pdf"]["filename"])
    pbc_reader = PdfReader(str(OUT / RAW_SOURCES["pbc_2015_monthly_statistics_pdf"]["filename"]))
    creation = pbc_reader.metadata.get("/CreationDate") if pbc_reader.metadata else None
    if "2015.01" not in pbc_text or "3.4966" not in pbc_text:
        raise ValueError("PBoC monthly PDF did not contain the January 2015 10-year value")
    if not creation or "20160304" not in creation.replace(":", ""):
        raise ValueError("PBoC monthly PDF did not carry the expected 2016-03-04 creation date")

    boc = normalized_html(OUT / RAW_SOURCES["boc_2014_12_17_daily_reference"]["filename"], "utf-8")
    required_boc = [
        "债市参考2014年12月17日",
        "2014-12-17",
        "10年140021成交在3.75%",
    ]
    if any(needle not in boc for needle in required_boc):
        raise ValueError("Bank of China page did not contain all required yield statements")

    return {
        "chinabond_ten_year_yield_percent": extract_chinabond_ten_year_value(
            OUT / RAW_SOURCES["chinabond_2015_01_05_history_query"]["filename"]
        ),
        "pbc_pdf_creation_date": creation,
    }


def build() -> dict:
    sources = {source_id: source_record(source_id) for source_id in RAW_SOURCES}
    extracted = validate_source_content()
    observations = [
        {
            "id": "boc_2014_12_16_10y_transaction",
            "observation_date": "2014-12-16",
            "publication_date": "2014-12-17",
            "yield_percent": "3.75",
            "curve_or_trade": "interbank_10y_government_bond_transaction",
            "availability_role": "pre_decision_public_market_observation",
            "source_id": "boc_2014_12_17_daily_reference",
        },
        {
            "id": "chinabond_2015_01_05_10y_curve",
            "observation_date": "2015-01-05",
            "publication_date": "current_historical_query_no_original_receipt",
            "yield_percent": extracted["chinabond_ten_year_yield_percent"],
            "curve_or_trade": "chinabond_government_yield_curve_10y",
            "availability_role": "official_current_historical_value_corroborated_by_dated_press",
            "source_id": "chinabond_2015_01_05_history_query",
        },
        {
            "id": "csj_2015_01_06_reported_10y_around",
            "observation_date": "2015-01-05",
            "publication_date": "2015-01-06",
            "yield_percent": "3.63",
            "curve_or_trade": "reported_chinabond_government_yield_curve_10y",
            "availability_role": "dated_contemporaneous_press_corroboration",
            "source_id": "csj_2015_01_06_A14",
        },
        {
            "id": "pbc_2015_01_last_trading_day_10y",
            "observation_date": "2015-01-30",
            "publication_date": "2016-03-04",
            "yield_percent": "3.4966",
            "curve_or_trade": "chinabond_government_yield_curve_monthly_last_trading_day",
            "availability_role": "later_monthly_corroboration_only",
            "source_id": "pbc_2015_monthly_statistics_pdf",
        },
    ]
    decision_ref = {
        "id": "moutai_historical_executed_entry_receipt",
        "path": str(DECISION_WINDOW_EVIDENCE.relative_to(ROOT)),
        "sha256": DECISION_WINDOW_HASH,
        "url": None,
        "description": "Existing archived replay receipt containing the first 2015-01-06 fill",
    }
    prior_coupon_ref = {
        "id": "moutai_historical_1429_sovereign_observation_package",
        "path": str(PRIOR_COUPON_PACKAGE.relative_to(ROOT)),
        "sha256": PRIOR_COUPON_PACKAGE_HASH,
        "url": None,
        "description": "Prior fail-closed sovereign coupon observation package",
    }
    prior_curve_candidate_ref = {
        "id": "moutai_historical_chinabond_government_2014_candidate",
        "path": str(CHINABOND_CANDIDATE.relative_to(ROOT)),
        "sha256": CHINABOND_CANDIDATE_HASH,
        "url": None,
        "description": "Prior 2014 annual curve candidate with unresolved publication contract",
    }
    return {
        "symbol": "600519",
        "review_date": REVIEW_DATE.isoformat(),
        "engineering_status": "historical_2015_01_yield_observation_package_complete",
        "status": "dated_public_yield_observations_archived_without_capital_cost_input",
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
            "Archive dated public government-yield observations around the first archived "
            "Moutai 2015-01-06 execution fill. This narrows the historical evidence gap but "
            "does not resolve beta, equity risk premium, cost of equity, or WACC."
        ),
        "decision_window": {
            "first_archived_fill_date": DECISION_DATE.isoformat(),
            "first_archived_fill_price_cny": 200.0,
            "evidence_ref": decision_ref,
        },
        "observation_window": {
            "pre_decision_observations": ["2014-12-16"],
            "closest_observation_before_fill": "2015-01-05",
            "fill_date": DECISION_DATE.isoformat(),
            "contemporaneous_press_publication": "2015-01-06",
        },
        "observations": observations,
        "summary": {
            "pre_decision_market_observations": 1,
            "closest_pre_fill_curve_observation": "3.6251",
            "dated_press_corroboration": "3.63",
            "later_monthly_corroborations": 1,
            "registered_capital_cost_inputs": 0,
        },
        "proven": [
            "A Bank of China page dated 2014-12-17 reported a 10-year government bond transaction at 3.75%.",
            "ChinaBond's current official historical query returns 3.6251% for the 2015-01-05 10-year government-yield curve.",
            "The China Securities Journal page dated 2015-01-06 reports the 2015-01-05 ChinaBond 10-year yield near 3.63%.",
            "A PBoC-hosted ChinaBond monthly statistics PDF records 3.4966% for the last trading day of January 2015.",
            "The existing archived execution replay contains a 2015-01-06 fill at CNY 200.00.",
        ],
        "not_proven": [
            "The exact time of the 2015-01-06 newspaper publication precedes the archived fill time.",
            "The current ChinaBond historical query is an unchanged original daily publication vintage.",
            "A 10-year government yield is the appropriate maturity/term structure proxy for the equity valuation horizon.",
            "A historical beta, equity risk premium, cost of equity, or WACC is resolved.",
            "The full Moutai R1 point-in-time decision chain is validated.",
        ],
        "definition_breaks": [
            "A 10-year government yield observation is not an equity cost of capital.",
            "A yield-to-maturity curve value is not necessarily the same as a zero-coupon rate.",
            "A dated newspaper report is contemporaneous evidence, not a primary ChinaBond original publication receipt.",
            "A monthly last-trading-day observation cannot represent the 2015-01-06 decision-day rate.",
        ],
        "point_in_time_policy": [
            "Only sources publicly dated before 2015-01-06 are treated as pre-decision market evidence.",
            "The China Securities Journal page dated 2015-01-06 is a contemporaneous press publication, not proof of a pre-trade timestamp.",
            "The ChinaBond historical query is a 2026 retrieval of official historical data and is hash-bound to the retrieved response.",
            "The PBoC 2016-03-04 PDF is later independent corroboration only.",
            "The decision date remains anchored to the existing archived execution replay.",
        ],
        "forbidden_calculations": [
            "Register 3.6251%, 3.63%, 3.75%, or 3.4966% as a risk-free-rate input.",
            "Convert a government-yield observation directly into a historical cost of equity.",
            "Use a yield observation as a missing beta or equity-risk-premium proxy.",
            "Replace the unresolved historical WACC with any observation in this package.",
            "Claim that R1 passed because the observations bracket the first archived fill.",
        ],
        "blockers": [
            "historical_risk_free_rate_contract_not_registered",
            "historical_beta_not_resolved",
            "historical_equity_risk_premium_not_resolved",
            "historical_cost_of_equity_not_resolved",
            "full_r1_point_in_time_decision_chain_not_validated",
        ],
        "registered_capital_cost_inputs": [],
        "evidence_refs": [
            source_ref(
                sources["boc_2014_12_17_daily_reference"],
                description="Dated pre-decision report of a 10-year government-bond transaction at 3.75%",
            ),
            source_ref(
                sources["chinabond_2015_01_05_history_query"],
                description="ChinaBond official historical query returning 3.6251% for 2015-01-05",
            ),
            source_ref(
                sources["csj_2015_01_06_A14"],
                description="Newspaper page dated 2015-01-06 reporting the 2015-01-05 10-year yield near 3.63%",
            ),
            source_ref(
                sources["pbc_2015_monthly_statistics_pdf"],
                description="PBoC later monthly statistics recording 3.4966% for January 2015",
            ),
            decision_ref,
            prior_coupon_ref,
            prior_curve_candidate_ref,
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    source_hashes = {source_id: source_record(source_id)["sha256"] for source_id in RAW_SOURCES}
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
        "prior_evidence_sha256s": {
            "moutai_historical_executed_entry_receipt": DECISION_WINDOW_HASH,
            "moutai_historical_1429_sovereign_observation_package": PRIOR_COUPON_PACKAGE_HASH,
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
        "closest_pre_fill_curve_observation": payload["summary"][
            "closest_pre_fill_curve_observation"
        ],
        "registered_capital_cost_inputs": payload["registered_capital_cost_inputs"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
