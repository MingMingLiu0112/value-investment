"""Independently review the three Shenhua B3 bridge packages against full interim originals."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
ANNUAL = ROOT / "runtime" / "shenhua-2025-official.pdf"
HKEX_INTERIM = ROOT / "runtime" / "company-research" / "shenhua-2026-interim-review-20260921" / "2026082802610.pdf"
CN_INTERIM = ROOT / "runtime" / "company-research" / "shenhua-2026-interim-review-20260921" / "shenhua-2026-interim-report-cn-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "shenhua-2026-bridge-independent-review-20260921"

ANNUAL_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
ANNUAL_HASH = "460EA07EE14D3AEB2B7518A25F87B47833EA5473715D911C378C15F7425698FC"
HKEX_INTERIM_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0828/2026082802610.pdf"
HKEX_INTERIM_HASH = "A270E12BB523350F4066BA78C99B78057A1D82A39A9E0EF2C9A6E4AF46F0AE2E"
CN_INTERIM_URL = "http://www.shenhuachina.com/zgshww/ggythjh/202608/802b531b2ee54ac3823e6375b30291ea/files/09bacea0e8c640ea80a50cb023d84169.pdf"
CN_INTERIM_HASH = "7017CFD2F11DD6B4A284D35365950B33FD1EF36EE53C884BEA7A9D90C2602B9D"

SHARE_BRIDGE = ROOT / "runtime" / "company-research" / "shenhua-2026-share-bridge-20260921" / "evidence.json"
PROFIT_BRIDGE = ROOT / "runtime" / "company-research" / "shenhua-2025-parent-operating-profit-bridge-20260921" / "evidence.json"
NET_CASH_BRIDGE = ROOT / "runtime" / "company-research" / "shenhua-2025-attributable-net-cash-bridge-20260921" / "evidence.json"

REVIEW_DATE = date(2026, 9, 21)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _page_text(reader: PdfReader, page_number: int, expected: tuple[str, ...], label: str) -> str:
    text = (reader.pages[page_number - 1].extract_text() or "").replace("\x00", " ")
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"{label} page {page_number} does not contain expected evidence {missing!r}")
    return text


def _source_ref(ref_id: str, path: Path, url: str, sha256: str, page: int, quote: str) -> dict:
    return {
        "id": ref_id,
        "path": path.relative_to(ROOT).as_posix(),
        "url": url,
        "sha256": sha256,
        "page": page,
        "quoted_facts": [quote],
    }


def _bridge_ref(ref_id: str, path: Path) -> dict:
    return {
        "id": ref_id,
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
    }


def build() -> dict:
    if _sha256(ANNUAL) != ANNUAL_HASH:
        raise ValueError("Shenhua 2025 annual report hash mismatch")
    if _sha256(HKEX_INTERIM) != HKEX_INTERIM_HASH:
        raise ValueError("HKEX 2026 interim report hash mismatch")
    if _sha256(CN_INTERIM) != CN_INTERIM_HASH:
        raise ValueError("Company Chinese 2026 interim report hash mismatch")

    hkex = PdfReader(str(HKEX_INTERIM))
    _page_text(hkex, 2, ("21,689,434,304", "RMB21,256 million"), "HKEX 2026 interim")
    _page_text(hkex, 26, ("65,722", "82,705"), "HKEX 2026 interim")
    _page_text(hkex, 27, ("18,197", "19,941"), "HKEX 2026 interim")
    _page_text(
        hkex,
        99,
        ("19,868,519,955", "1,820,914,349", "21,689,434,304"),
        "HKEX 2026 interim",
    )
    _page_text(
        hkex,
        100,
        (
            "1,363,248,446",
            "457,665,903",
            "16 March 2026",
            "7 April 2026",
            "did not purchase",
            "not hold any treasury shares",
        ),
        "HKEX 2026 interim",
    )
    _page_text(hkex, 107, ("1,363,248,446", "16 March 2029"), "HKEX 2026 interim")
    _page_text(hkex, 108, ("7 October 2026",), "HKEX 2026 interim")
    _page_text(
        hkex,
        114,
        (
            "Restricted bank deposits",
            "18,197",
            "65,722",
            "Cash and cash equivalents",
            "51,673",
        ),
        "HKEX 2026 interim",
    )
    _page_text(
        hkex,
        115,
        ("74,923", "Share capital", "21,689", "Non-controlling interests", "99,608"),
        "HKEX 2026 interim",
    )
    _page_text(hkex, 123, ("current net liabilities", "RMB31,619 million"), "HKEX 2026 interim")
    _page_text(hkex, 137, ("82,705", "157,628"), "HKEX 2026 interim")
    _page_text(
        hkex,
        141,
        (
            "18,311,952,304",
            "3,377,482,000",
            "1,322,301,165",
            "40,947,281",
            "457,665,903",
        ),
        "HKEX 2026 interim",
    )
    _page_text(
        hkex,
        153,
        ("1,363", "million A shares", "RMB85,791 million", "RMB7,728 million", "1,322 million", "RMB90,942 million"),
        "HKEX 2026 interim",
    )

    cn = PdfReader(str(CN_INTERIM))
    _page_text(cn, 3, ("21,689,434,304",), "company Chinese 2026 interim")
    _page_text(cn, 100, ("21,689,434,304", "1,820,914,349"), "company Chinese 2026 interim")
    _page_text(cn, 101, ("1,363,248,446", "457,665,903"), "company Chinese 2026 interim")
    _page_text(cn, 115, ("51,673", "65,722", "18,197", "82,705", "31,619"), "company Chinese 2026 interim")
    _page_text(cn, 116, ("99,608",), "company Chinese 2026 interim")
    _page_text(
        cn,
        142,
        (
            "18,311,952,304",
            "3,377,482,000",
            "1,322,301,165",
            "40,947,281",
            "457,665,903",
        ),
        "company Chinese 2026 interim",
    )

    share_payload = json.loads(SHARE_BRIDGE.read_text(encoding="utf-8"))
    profit_payload = json.loads(PROFIT_BRIDGE.read_text(encoding="utf-8"))
    net_cash_payload = json.loads(NET_CASH_BRIDGE.read_text(encoding="utf-8"))

    share_candidate = share_payload["ordinary_share_denominator_candidate"]
    if share_candidate["review_status"] != "not_reviewed_or_approved":
        raise ValueError("Share bridge was not in the expected pre-review state")
    if share_candidate["candidate_value"] != 21_689_434_304:
        raise ValueError("Unexpected share-denominator candidate")
    if profit_payload["derivation"]["review_status"] != "not_reviewed_or_approved":
        raise ValueError("Profit bridge was not in the expected pre-review state")
    if net_cash_payload["candidate_derivations"]["review_status"] != "not_reviewed_or_approved":
        raise ValueError("Net-cash bridge was not in the expected pre-review state")

    a_share_total = 16_491_037_955 + 1_363_248_446 + 457_665_903
    total_after_issuance = a_share_total + 3_377_482_000
    if a_share_total != 18_311_952_304 or total_after_issuance != 21_689_434_304:
        raise ValueError("HKEX note-26 share arithmetic does not reconcile")

    ordinary_share_refs = [
        _source_ref("hkex_interim_share_capital_page_99", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 99,
                    "19,868,519,955 before changes; 1,820,914,349 issued; ending total 21,689,434,304"),
        _source_ref("hkex_interim_issuance_page_100", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 100,
                    "1,363,248,446 acquisition shares and 457,665,903 placement shares; no treasury shares"),
        _source_ref("hkex_interim_note_26_page_141", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 141,
                    "18,311,952,304 A shares plus 3,377,482,000 H shares"),
        _source_ref("company_cn_interim_share_pages_100_101", CN_INTERIM, CN_INTERIM_URL, CN_INTERIM_HASH, 100,
                    "Independent company Chinese-report numeric match for ending and issued shares"),
    ]

    profit_refs = [
        _source_ref("hkex_interim_income_ownership_page_113", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 113,
                    "H1 parent profit 31,054 and minority profit 7,010; no parent-attributable pre-tax operating profit"),
        _source_ref("hkex_interim_segment_profit_page_126", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 126,
                    "Segment pre-tax profit is disclosed by segment, not after minority and tax allocation"),
    ]

    net_cash_refs = [
        _source_ref("hkex_interim_balance_sheet_page_114", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 114,
                    "Consolidated cash 51,673, restricted deposits 18,197 and time deposits 65,722"),
        _source_ref("hkex_interim_debt_note_page_137", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 137,
                    "Consolidated current and non-current borrowings total 157,628"),
        _source_ref("hkex_interim_working_capital_page_123", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 123,
                    "Current net liabilities 31,619 is a working-capital measure, not attributable financial net cash"),
        _source_ref("hkex_interim_equity_page_115", HKEX_INTERIM, HKEX_INTERIM_URL, HKEX_INTERIM_HASH, 115,
                    "Parent equity 459,227 and minority interests 99,608; no subsidiary cash/debt allocation"),
    ]

    ordinary_shares_review = {
        "decision": "approved_as_point_in_time_ordinary_shares",
        "candidate_package": _bridge_ref("shenhua_2026_share_bridge", SHARE_BRIDGE),
        "candidate_value": 21_689_434_304,
        "as_of": "2026-06-30",
        "review_status": "approved_point_in_time_denominator",
        "approved_model_input_contract": {
            "field": "ordinary_shares",
            "value": 21_689_434_304,
        },
        "registered_in_cyclical_facts_operating_inputs": False,
        "registration_conditions": [
            "Register only for a valuation as_of at or after 2026-06-30.",
            "Register together with an aligned as_of and after all other CyclicalFacts inputs have provenance.",
            "Recheck for a company action between the report disclosure date and a future valuation date.",
        ],
        "basis": [
            "The HKEX full interim report directly shows 21,689,434,304 ordinary shares.",
            "The issuance bridge reconciles: 19,868,519,955 + 1,363,248,446 + 457,665,903.",
            "The report states no purchase, sale, redemption or treasury shares during H1 2026.",
            "Note 26 reconciles 18,311,952,304 A shares plus 3,377,482,000 H shares.",
            "The company's Chinese interim report independently matches the same numeric share tokens.",
        ],
        "evidence_refs": ordinary_share_refs,
    }

    profit_review = {
        "decision": "rejected_for_verified_model_input",
        "candidate_package": _bridge_ref("shenhua_parent_operating_profit_bridge", PROFIT_BRIDGE),
        "review_status": "rejected_for_verified_model_input",
        "retained_use": "dated_unaudited_pro_forma_research_interval_only",
        "model_input": None,
        "reason": (
            "The full interim report still does not disclose parent-attributable pre-tax operating "
            "profit or subsidiary-by-subsidiary pre-tax, tax and minority allocations. The existing "
            "bridge allocates pre-tax operating profit using the after-tax parent net-profit share, "
            "which requires an unsupported uniform effective-tax and ownership assumption. The H1 "
            "segment and ownership disclosures reduce ambiguity but do not convert the pro forma "
            "into an audited model input."
        ),
        "evidence_refs": profit_refs,
    }

    net_cash_review = {
        "decision": "rejected_for_model_input",
        "candidate_package": _bridge_ref("shenhua_attributable_net_cash_bridge", NET_CASH_BRIDGE),
        "review_status": "rejected_for_model_input",
        "retained_use": "2025_parent_legal_entity_balance_sheet_interval_only",
        "model_input": None,
        "reason": (
            "The 2026 HKEX full interim report provides consolidated cash, restricted deposits, "
            "time deposits and borrowings, but no parent-company or subsidiary-level cash/debt split "
            "and no minority cash allocation. A parent legal-entity cash balance is not equivalent "
            "to group net cash attributable to parent ordinary equity. The RMB31,619 million current "
            "net-liability disclosure is working capital, not financial net cash."
        ),
        "evidence_refs": net_cash_refs,
    }

    payload = {
        "symbol": "601088",
        "package_version": "shenhua-bridge-independent-review-v1",
        "review_date": REVIEW_DATE.isoformat(),
        "review_scope": (
            "Independent review of the ordinary-share, parent operating-profit and attributable "
            "net-cash bridge packages against the full HKEX and company Chinese 2026 interim reports."
        ),
        "engineering_status": "bridge_independent_review_complete",
        "current_data_status": "full_2026_interim_reports_reviewed",
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Approve or reject each bridge candidate with source URLs, hashes, page references and "
            "an explicit decision. The review is a data-integrity decision, not a valuation, "
            "simulation, position or trading decision."
        ),
        "source_documents": [
            {
                "id": "hkex_2026_interim_full_report",
                "path": HKEX_INTERIM.relative_to(ROOT).as_posix(),
                "url": HKEX_INTERIM_URL,
                "sha256": HKEX_INTERIM_HASH,
                "size_bytes": HKEX_INTERIM.stat().st_size,
                "pdf_pages": len(hkex.pages),
                "review_note": "Full HKEX interim results announcement and report; readable English text layer.",
            },
            {
                "id": "company_cn_2026_interim_full_report",
                "path": CN_INTERIM.relative_to(ROOT).as_posix(),
                "url": CN_INTERIM_URL,
                "sha256": CN_INTERIM_HASH,
                "size_bytes": CN_INTERIM.stat().st_size,
                "pdf_pages": len(cn.pages),
                "review_note": (
                    "Company Chinese report uses a custom embedded font whose text layer is not "
                    "readable by the local decoder; numeric tokens were independently matched on "
                    "the cited pages and agree with the HKEX version."
                ),
            },
        ],
        "decisions": {
            "ordinary_shares": ordinary_shares_review,
            "parent_attributable_pretax_operating_profit": profit_review,
            "net_cash_attributable_to_parent": net_cash_review,
        },
        "interim_consolidated_facts_2026_06_30": {
            "cash_and_cash_equivalents_cny_millions": 51_673,
            "restricted_bank_deposits_cny_millions": 18_197,
            "time_deposits_over_three_months_cny_millions": 65_722,
            "current_borrowings_cny_millions": 82_705,
            "non_current_borrowings_cny_millions": 74_923,
            "total_borrowings_cny_millions": 157_628,
            "total_equity_cny_millions": 558_835,
            "parent_equity_cny_millions": 459_227,
            "minority_interests_cny_millions": 99_608,
            "current_net_liabilities_cny_millions": 31_619,
            "informational_consolidated_liquid_financial_assets_minus_borrowings_cny_millions": -22_036,
            "observation": (
                "The informational consolidated figure adds cash equivalents, restricted bank deposits "
                "and over-three-month time deposits, then subtracts total borrowings. It is a balance-sheet "
                "observation only and is not attributable parent net cash."
            ),
        },
        "registered_cyclical_facts_operating_inputs": [],
        "model_gate_summary": {
            "ordinary_shares": "review-approved, not yet registered",
            "parent_attributable_pretax_operating_profit": "rejected",
            "net_cash_attributable_to_parent": "rejected",
            "valuation_effect": "The shared cyclical model remains VALUATION_NOT_READY with null bear/base/bull values.",
        },
        "next_action": (
            "Obtain a statutory or subsidiary-level allocation of pre-tax profit, tax, minority interests, "
            "cash and debt. Do not synthesize those allocations from consolidated ratios. The approved "
            "ordinary-share denominator may be registered once the valuation date and all remaining "
            "normalized inputs have aligned provenance."
        ),
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }
    return payload


def main() -> int:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "script_sha256": _sha256(Path(__file__)),
        "evidence_sha256": _sha256(target),
        "source_sha256": {
            "annual_report": ANNUAL_HASH,
            "hkex_2026_interim_full_report": HKEX_INTERIM_HASH,
            "company_cn_2026_interim_full_report": CN_INTERIM_HASH,
        },
        "reviewed_bridge_sha256": {
            "share_bridge": _sha256(SHARE_BRIDGE),
            "parent_operating_profit_bridge": _sha256(PROFIT_BRIDGE),
            "attributable_net_cash_bridge": _sha256(NET_CASH_BRIDGE),
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pointer = ROOT / "runtime" / "company-research" / "shenhua-2026-bridge-independent-review-latest.json"
    pointer.write_text(
        json.dumps(
            {
                "path": OUT.relative_to(ROOT).as_posix(),
                "sha256": _sha256(target),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output": str(target),
                "sha256": _sha256(target),
                "status": payload["engineering_status"],
                "ordinary_shares": payload["decisions"]["ordinary_shares"]["decision"],
                "parent_operating_profit": payload["decisions"]["parent_attributable_pretax_operating_profit"]["decision"],
                "attributable_net_cash": payload["decisions"]["net_cash_attributable_to_parent"]["decision"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
