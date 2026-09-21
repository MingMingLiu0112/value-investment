#!/usr/bin/env python3
"""Verify annual parent-equity facts and the latest disclosed interim basis."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader
from value_investment_agent.historical_asof import publication_date_upper_bound


ROOT = Path(__file__).resolve().parents[1]
ANNUAL_INPUTS = ROOT / "runtime/strategy-validation/moutai-annual-inputs-20260909T055311360531Z/annual-inputs.json"
ANNUAL_INPUTS_SHA256 = "116d725d44e39d2d5ba2e5ef197db358e628b9822fb120066388acc4b6f263d2"
REPORT = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf"
REPORT_SHA256 = "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"
SUMMARY_PAGE = 6
SHARES_PAGE = 47
INDEX = REPORT.parent.parent / "600519-1-55d2bc88ebfd28dce332f5b06cb4f1050cc8abeef054f207647bc3d01a21e39f.json"
INDEX_SHA256 = "55d2bc88ebfd28dce332f5b06cb4f1050cc8abeef054f207647bc3d01a21e39f"
INTERIM = REPORT.parent / "600519-1225475868.pdf"
INTERIM_SHA256 = "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6"
CURRENT_INDEX = ROOT / "runtime/historical-filing-index/20260914T105550116419Z/600519-1-02d4bb62799a0054b0d916643a52fae9c84d469e020904f636001c6166f91636.json"
CURRENT_INDEX_SHA256 = "02d4bb62799a0054b0d916643a52fae9c84d469e020904f636001c6166f91636"
CURRENT_REFERENCES = {
    "ttm": ("runtime/company-research/600519-ttm-scope-20260909T072356118039Z/evidence.json", "2d518b72fc2c9b8a60663c1f64121bfa45247de6262668db44ab656f27b6c57e"),
    "equity_rollforward": ("runtime/company-research/600519-equity-rollforward-20260909T095644229753Z/evidence.json", "ebcc17eae6bb2896fdd7d0dae5ae6c516f1fca1a2996be7a70b37e08e868b621"),
    "capital_review": ("runtime/company-research/600519-current-share-price-review-20260909T135607541717Z/evidence.json", "b4d38f775005c34b3367e85dfb279748b70f2596732c68e6822a2482414d4e16"),
    "reviewed_index": ("runtime/historical-filing-index/20260909T134257473871Z/600519-1-a77b9723c9927b004ffad1ea2aa7b0e68383aade80744e7307cc56dbeddef802.json", "a77b9723c9927b004ffad1ea2aa7b0e68383aade80744e7307cc56dbeddef802"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: str) -> str:
    return "".join(value.split())


def report_metadata(report: Path, report_hash: str, ident: str, title: str) -> dict[str, object]:
    if digest(INDEX) != INDEX_SHA256 or digest(report) != report_hash:
        raise ValueError("Pinned annual index or PDF changed")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    if (index.get("url") != "https://www.cninfo.com.cn/new/hisAnnouncement/query"
            or index.get("timestamp_precision") != "announcement_date_not_intraday_verified"):
        raise ValueError("Unexpected announcement source or date precision")
    records = [row for row in index["response"]["announcements"]
               if str(row["announcementId"]) == ident and row["secCode"] == "600519"]
    if len(records) != 1:
        raise ValueError("Annual announcement identity is missing or ambiguous")
    record = records[0]
    stamp = record["announcementTime"]
    if type(stamp) is not int or record["announcementTitle"] != title:
        raise ValueError("Unexpected annual announcement title or date encoding")
    day = datetime.fromtimestamp(stamp / 1000, timezone(timedelta(hours=8))).date().isoformat()
    if record["adjunctUrl"] != f"finalpage/{day}/{ident}.PDF":
        raise ValueError("Annual index date and PDF URL disagree")
    return {
        "source_id": "cninfo:" + ident,
        "source_url": "https://static.cninfo.com.cn/" + record["adjunctUrl"],
        "published_date": day,
        "available_at": publication_date_upper_bound(day).isoformat(),
        "timestamp_precision": "date",
        "availability_basis": "china_publication_date_upper_bound",
        "source_index_path": str(INDEX.relative_to(ROOT)),
        "source_index_hash": INDEX_SHA256,
        "raw_file_hash": report_hash,
    }


def annual_report_metadata() -> dict[str, object]:
    return report_metadata(REPORT, REPORT_SHA256, "1225114741", "贵州茅台2025年年度报告")


def summary_numbers(value: str, *, include_capital: bool = True) -> dict[str, Decimal]:
    """Extract only the current-year values from the audited summary page."""
    text = compact(value)
    patterns = {
        "parent_equity_cny": r"归属于上市公司股东的净资产([0-9,]+\.[0-9]{2})",
        "parent_profit_cny": r"归属于上市公司股东的净利润([0-9,]+\.[0-9]{2})",
    }
    if include_capital:
        patterns["reported_share_capital_cny"] = r"股本([0-9,]+\.[0-9]{2})"
    result: dict[str, Decimal] = {}
    for field, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one current-year {field} on the summary page")
        result[field] = Decimal(matches[0].replace(",", ""))
    return result


def share_numbers(value: str) -> dict[str, Decimal]:
    text = compact(value)
    if "单位：股" not in text or "本次变动前" not in text or "本次变动后" not in text:
        raise ValueError("Missing share-count unit or period headings")
    number = r"([0-9]{1,3}(?:,[0-9]{3})+)"
    movement = r"(-[0-9]{1,3}(?:,[0-9]{3})+)"
    counts = []
    for label in ("三、股份总数", "1、人民币普通股"):
        matches = re.findall(re.escape(label) + number + "100" + movement * 2 + number + "100", text)
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous ordinary-share movement")
        opening, other, delta, closing = (Decimal(item.replace(",", "")) for item in matches[0])
        if other != delta or opening + delta != closing or min(opening, closing) <= 0:
            raise ValueError("Ordinary-share movement does not reconcile")
        counts.append((opening, delta, closing))
    if counts[0] != counts[1]:
        raise ValueError("Total and ordinary share-count scopes differ")
    opening, delta, closing = counts[0]
    return {"opening_issued_shares": opening, "share_change": delta, "ending_issued_shares": closing}


def ex_nonrecurring_profit_numbers(value: str) -> dict[str, Decimal]:
    matches = re.findall(r"归属于上市公司股东的扣除非经常性损益的净利润"
                         r"(-?[0-9,]+\.[0-9]{2})(-?[0-9,]+\.[0-9]{2})", compact(value))
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous ex-nonrecurring parent-profit comparison")
    return dict(zip(("current", "prior"), (Decimal(item.replace(",", "")) for item in matches[0])))


def extract_dual_decoder_page(page_number: int, parser, *, report: Path = REPORT,
                              report_hash: str = REPORT_SHA256) -> dict[str, Decimal]:
    if digest(report) != report_hash:
        raise ValueError("Pinned 2025 annual report changed")
    pypdf_text = PdfReader(str(report)).pages[page_number - 1].extract_text() or ""
    with pdfium.PdfDocument(str(report)) as document:
        page = document[page_number - 1]
        text_page = page.get_textpage()
        try:
            pdfium_text = text_page.get_text_range()
        finally:
            text_page.close()
            page.close()
    pypdf_values, pdfium_values = parser(pypdf_text), parser(pdfium_text)
    if pypdf_values != pdfium_values:
        raise ValueError(f"Annual-report decoders disagree on page {page_number}")
    return pypdf_values


def comprehensive_income_numbers(value: str) -> dict[str, Decimal]:
    text = compact(value)
    money = r"(-?[0-9,]+\.[0-9]{2})"
    matches = re.findall(r"（一）综合收益总额" + money * 3, text)
    if len(matches) != 1 or "归属于母公司所有者权益" not in text or "单位：元币种：人民币" not in text:
        raise ValueError("Missing parent comprehensive-income row or scope")
    oci, profit, total = (Decimal(item.replace(",", "")) for item in matches[0])
    if oci + profit != total:
        raise ValueError("Net profit and OCI do not reconcile to comprehensive income")
    return {"parent_oci_cny": oci, "parent_profit_cny": profit, "parent_comprehensive_income_cny": total}


def validate_capital_inventory(old_index: dict, current_index: dict) -> datetime:
    for index in (old_index, current_index):
        records = index["response"]["announcements"]
        if (index.get("url") != "https://www.cninfo.com.cn/new/hisAnnouncement/query"
                or index["query"]["category"] or index["query"]["searchkey"]
                or index["query"]["stock"] != "600519,gssh0600519"
                or index["response"]["hasMore"] is not False
                or len(records) != index["response"]["totalAnnouncement"]
                or len({row["announcementId"] for row in records}) != len(records)
                or any(row["secCode"] != "600519" for row in records)):
            raise ValueError("Capital-event index is incomplete or has the wrong scope")
    old_records = {row["announcementId"]: row for row in old_index["response"]["announcements"]}
    new_records = {row["announcementId"]: row for row in current_index["response"]["announcements"]}
    if (old_index["query"]["seDate"] != "2026-06-01~2026-09-09"
            or current_index["query"]["seDate"] != "2026-06-01~2026-09-14"
            or new_records != old_records):
        raise ValueError("New or changed announcements require capital-event review")
    checked_at = datetime.fromisoformat(current_index["fetched_at"])
    if (checked_at.tzinfo is None
            or checked_at.astimezone(timezone(timedelta(hours=8))).date().isoformat() != "2026-09-14"):
        raise ValueError("Capital-event review time does not cover the queried date")
    return checked_at


def current_disclosed_basis(annual: dict) -> dict:
    metadata = report_metadata(INTERIM, INTERIM_SHA256, "1225475868", "贵州茅台2026年半年度报告")
    options = {"report": INTERIM, "report_hash": INTERIM_SHA256}
    summary = extract_dual_decoder_page(5, lambda text: summary_numbers(text, include_capital=False), **options)
    shares = extract_dual_decoder_page(22, share_numbers, **options)
    income = extract_dual_decoder_page(37, comprehensive_income_numbers, **options)
    recurring_annual = extract_dual_decoder_page(SUMMARY_PAGE, ex_nonrecurring_profit_numbers)
    recurring_interim = extract_dual_decoder_page(5, ex_nonrecurring_profit_numbers, **options)
    packs = {}
    for name, (relative, expected) in CURRENT_REFERENCES.items():
        path = ROOT / relative
        if digest(path) != expected:
            raise ValueError("Current-basis reference changed: " + name)
        packs[name] = json.loads(path.read_text(encoding="utf-8"))
    if digest(CURRENT_INDEX) != CURRENT_INDEX_SHA256:
        raise ValueError("Current capital-event index changed")
    current_index = json.loads(CURRENT_INDEX.read_text(encoding="utf-8"))
    checked_at = validate_capital_inventory(packs["reviewed_index"], current_index)
    movements = packs["equity_rollforward"]["calculations"]["parent_equity"]
    opening, comprehensive, repurchases, distributions = map(Decimal, movements["signed_inputs"])
    if (packs["equity_rollforward"]["source_sha256"] != INTERIM_SHA256
            or summary["parent_profit_cny"] != income["parent_profit_cny"]
            or comprehensive != income["parent_comprehensive_income_cny"]
            or opening != Decimal(annual["parent_equity_cny"])
            or opening + comprehensive + repurchases + distributions != summary["parent_equity_cny"]
            or shares["opening_issued_shares"] != Decimal(annual["ending_issued_shares"])
            or shares["ending_issued_shares"] != Decimal(packs["capital_review"]["disclosure_supported_ordinary_share_assumption"])
            or packs["capital_review"]["distribution"]["deduct_again_from_june_book_equity"] is not False):
        raise ValueError("Interim facts do not reconcile to the annual/capital basis")
    ttm = packs["ttm"]["ttm"]["parent_profit"]
    ttm_rows = ttm["input_rows"]
    for row in ttm_rows:
        if digest(ROOT / row["path"]) != row["sha256"]:
            raise ValueError("TTM original changed")
    fy, current, prior = (Decimal(row["current"]) for row in ttm_rows)
    if (packs["ttm"]["reported_flow_research_supported"] is not True
            or fy != Decimal(annual["parent_profit_cny"]) or current != income["parent_profit_cny"]
            or fy + current - prior != Decimal(ttm["value"])):
        raise ValueError("Reported TTM profit does not reconcile")
    recurring_ttm = recurring_annual["current"] + recurring_interim["current"] - recurring_interim["prior"]
    return {
        "basis_version": "moutai-2026h1-current-disclosure-basis-v1",
        "period_end": "2026-06-30", **metadata,
        "assessment_available_at": max(datetime.fromisoformat(metadata["available_at"]), checked_at).isoformat(),
        "availability_scope": "Report facts use available_at; the subsequent capital inventory is usable only from assessment_available_at.",
        "parent_equity_cny": str(summary["parent_equity_cny"]),
        "parent_profit_h1_cny": str(income["parent_profit_cny"]),
        "parent_oci_h1_cny": str(income["parent_oci_cny"]),
        "parent_comprehensive_income_h1_cny": str(comprehensive),
        "ttm_parent_profit_cny": ttm["value"],
        "ttm_ex_nonrecurring_parent_profit_cny": str(recurring_ttm),
        "ex_nonrecurring_profit_bridge": {
            "annual_cny": str(recurring_annual["current"]),
            "current_h1_cny": str(recurring_interim["current"]),
            "prior_h1_comparative_cny": str(recurring_interim["prior"]),
            "annual_physical_page": SUMMARY_PAGE, "interim_physical_page": 5,
            "reported_ttm_minus_ex_nonrecurring_ttm_cny": str(Decimal(ttm["value"]) - recurring_ttm),
            "interpretation": "Issuer-defined ex-nonrecurring TTM; not a complete through-cycle earnings normalization.",
        },
        "ttm_ending_equity_profit_ratio": str(Decimal(ttm["value"]) / summary["parent_equity_cny"]),
        "issued_shares": str(shares["ending_issued_shares"]),
        "share_basis": "Latest disclosed ordinary shares, with unchanged complete subsequent announcement inventory; not a registry certificate.",
        "share_evidence": {"physical_page": 22, "unit": "shares", "values": {key: str(value) for key, value in shares.items()}},
        "equity_bridge": {"opening_equity_cny": str(opening), "net_profit_cny": str(current),
                          "oci_cny": str(income["parent_oci_cny"]), "repurchase_equity_change_cny": str(repurchases),
                          "distribution_equity_change_cny": str(distributions), "closing_equity_cny": str(summary["parent_equity_cny"]),
                          "physical_page": 37, "deduct_reported_distributions_again": False},
        "event_query": {"path": str(CURRENT_INDEX.relative_to(ROOT)), "sha256": CURRENT_INDEX_SHA256,
                        "window": current_index["query"]["seDate"], "checked_at": current_index["fetched_at"],
                        "complete": True, "new_or_changed_announcements": 0},
        "inputs": {name: {"path": relative, "sha256": expected} for name, (relative, expected) in CURRENT_REFERENCES.items()},
        "as_of_registry_verified": False,
        "current_net_assets_observed": False,
        "limitations": ["TTM is reported profit, not a forecast or a normalized-earnings approval.",
                        "Current valuation still needs explicit post-report earnings/distribution and discount timing assumptions.",
                        "Consolidated finance-subsidiary cash flows are not freely distributable cash."],
    }


def historical_chain() -> list[dict[str, object]]:
    if digest(ANNUAL_INPUTS) != ANNUAL_INPUTS_SHA256:
        raise ValueError("Pinned annual input archive changed")
    rows = json.loads(ANNUAL_INPUTS.read_text(encoding="utf-8"))
    if len(rows) != 11 or rows[-1]["period_label"] != "2024-12-31":
        raise ValueError("Unexpected historical annual-input coverage")
    chain = []
    for row in rows:
        inputs = row["inputs"]
        chain.append({
            "period_end": row["period_label"],
            "available_at": row["available_at"],
            "source_id": row["source_id"],
            "source_url": row["source_url"],
            "raw_file_hash": row["raw_file_hash"],
            "parent_equity_cny": inputs["parent_equity_cny"],
            "parent_profit_cny": inputs["parent_profit_cny"],
            "ending_issued_shares": inputs["ending_issued_shares"],
            "reported_basic_eps": inputs["reported_basic_eps"],
            "validation_status": row["validation_status"],
        })
    return chain


def build() -> dict[str, object]:
    metadata = annual_report_metadata()
    values = extract_dual_decoder_page(SUMMARY_PAGE, summary_numbers)
    shares = extract_dual_decoder_page(SHARES_PAGE, share_numbers)
    chain = historical_chain()
    prior = chain[-1]
    if (Decimal(prior["parent_equity_cny"]) != Decimal("233105984399.47")
            or Decimal(prior["parent_profit_cny"]) != Decimal("86228146421.62")
            or Decimal(prior["ending_issued_shares"]) != Decimal("1256197800.00")):
        raise ValueError("2024 historical anchor changed")
    current = {
        "period_end": "2025-12-31",
        **metadata,
        **{key: str(value) for key, value in values.items()},
        "ending_issued_shares": str(shares["ending_issued_shares"]),
        "reported_basic_eps": "65.66",
        "validation_status": "verified_two_decoders_same_issuer_original",
        "physical_page": SUMMARY_PAGE,
        "share_evidence": {
            "physical_page": SHARES_PAGE,
            "unit": "shares",
            "table_label": "三、股份总数 / 1、人民币普通股",
            "values": {key: str(value) for key, value in shares.items()},
            "method": "direct_disclosed_counts_and_share_rollforward_two_decoders_same_original",
            "monetary_capital_used_as_shares": False,
        },
    }
    if (values["parent_equity_cny"] != Decimal("244637811032.18")
            or values["parent_profit_cny"] != Decimal("82320067101.68")
            or shares["opening_issued_shares"] != Decimal(prior["ending_issued_shares"])
            or shares["ending_issued_shares"] != Decimal("1252270215")):
        raise ValueError("Unexpected 2025 annual-summary values")
    if values["parent_equity_cny"] <= Decimal(prior["parent_equity_cny"]):
        raise ValueError("2025 parent equity did not reconcile directionally with disclosed comparative")
    chain.append(current)
    for row in chain:
        equity = Decimal(str(row["parent_equity_cny"]))
        profit = Decimal(str(row["parent_profit_cny"]))
        shares = Decimal(str(row["ending_issued_shares"]))
        if min(equity, profit, shares) <= 0:
            raise ValueError("Nonpositive parent-equity input")
        row["ending_book_value_per_issued_share_cny"] = str(equity / shares)
        row["annual_parent_profit_per_issued_share_cny"] = str(profit / shares)
        row["ending_equity_profit_ratio"] = str(profit / equity)
    return {
        "symbol": "600519",
        "contract_version": "moutai-consolidated-parent-equity-inputs-v2",
        "supersedes_contract_version": "moutai-consolidated-parent-equity-inputs-v1",
        "corrections": ["2025 disclosure date derived from official index instead of April 2",
                        "2025 issued shares extracted from share-count table rather than monetary capital"],
        "scope": "consolidated issuer parent-attributable equity, profit, and issued shares; not industrial FCFF",
        "chain": chain,
        "chain_count": len(chain),
        "latest_period": current["period_end"],
        "latest_available_at": current["available_at"],
        "current_disclosed_basis": current_disclosed_basis(current),
        "point_in_time_ready_for_research": True,
        "valuation_approved": False,
        "trade_approved": False,
        "limitations": [
            "The chain is an issuer-report fact package, not a residual-income or dividend valuation by itself.",
            "Parent-attributable equity includes the consolidated finance subsidiary and does not validate an industrial FCFF carveout.",
            "The 2025 report confirms shares at the reporting date, not a current registry or later repurchase/cancellation treatment.",
            "Cost of equity, forward profitability, payout/reinvestment and accounting-policy continuity remain valuation dependencies; execution is a separate simulation dependency.",
        ],
    }


def main() -> int:
    payload = build()
    output = ROOT / "runtime/company-research" / (
        "600519-consolidated-parent-equity-inputs-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "inputs": {
            str(ANNUAL_INPUTS.relative_to(ROOT)): ANNUAL_INPUTS_SHA256,
            str(REPORT.relative_to(ROOT)): REPORT_SHA256,
            str(INDEX.relative_to(ROOT)): INDEX_SHA256,
            str(INTERIM.relative_to(ROOT)): INTERIM_SHA256,
            str(CURRENT_INDEX.relative_to(ROOT)): CURRENT_INDEX_SHA256,
            **{relative: expected for relative, expected in CURRENT_REFERENCES.values()},
        },
        "script_sha256": digest(Path(__file__)),
        "outputs": {"evidence.json": digest(evidence)},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "chain_count": payload["chain_count"], "valuation_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
