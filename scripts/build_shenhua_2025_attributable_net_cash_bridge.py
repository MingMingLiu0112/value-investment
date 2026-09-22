"""Compile 601088's attributable net-cash bridge without approving a model input."""
from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "shenhua-2025-official.pdf"
SOURCE_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SOURCE_HASH = "460EA07EE14D3AEB2B7518A25F87B47833EA5473715D911C378C15F7425698FC"
SHARE_BRIDGE = ROOT / "runtime" / "company-research" / "shenhua-2026-share-bridge-20260921" / "evidence.json"
OUT = ROOT / "runtime" / "company-research" / "shenhua-2025-attributable-net-cash-bridge-20260921"


def source_ref(ref_id: str, page: int, description: str) -> dict:
    return {
        "id": ref_id,
        "path": SOURCE.relative_to(ROOT).as_posix(),
        "url": SOURCE_URL,
        "sha256": SOURCE_HASH,
        "page": page,
        "unit": "CNY millions",
        "description": description,
    }


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = (reader.pages[page - 1].extract_text() or "").replace("\x00", " ")
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def _money(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = 30
        return format(value, ".3f")


def build() -> dict:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != SOURCE_HASH:
        raise ValueError("Shenhua 2025 annual report hash mismatch")
    reader = PdfReader(str(SOURCE))

    page_text(reader, 329, ("货币资金", "96,772", "其中：存放财务公司款项", "41,247"))
    page_text(reader, 331, ("短期借款", "409", "一年内到期的非流动负债", "9,364"))
    page_text(reader, 332, ("长期借款", "28,268", "租赁负债", "971"))
    page_text(reader, 334, ("母公司资产负债表", "货币资金", "83,347", "39,540"))
    page_text(reader, 335, ("一年内到期的非流动负债", "1,458", "长期借款", "150", "租赁负债", "38"))
    page_text(reader, 392, ("17,637", "55,847", "合计", "96,772"))
    page_text(reader, 462, ("限制用途的资金", "11,886", "43,807", "54,168", "39,561"))
    page_text(reader, 152, ("归属于母公司股东权益合计", "409,107", "少数股东权益", "72,344"))
    page_text(reader, 28, ("受限资产余额", "17,841", "限制用途的资金共计", "17,637"))
    page_text(reader, 258, ("财务公司", "40", "重要的联营企业"))

    if not SHARE_BRIDGE.exists():
        raise ValueError("Shenhua 2026 share bridge has not been generated")
    share_bridge = json.loads(SHARE_BRIDGE.read_text(encoding="utf-8"))
    issuance = {item["id"]: item for item in share_bridge["post_balance_issuances"]}
    acquisition_cash = Decimal(issuance["acquisition_asset_share_issuance"]["cash_consideration_cny"])
    placement_net = Decimal(issuance["placement_supplementary_fund_share_issuance"]["net_proceeds_cny"])

    consolidated_cash = Decimal(96_772)
    consolidated_debt = Decimal(409 + 9_364 + 28_268 + 971)
    consolidated_surface_net_cash = consolidated_cash - consolidated_debt

    parent_cash = Decimal(83_347)
    parent_finance_company_deposits = Decimal(39_540)
    parent_bank_deposits = Decimal(43_807)
    parent_debt = Decimal(1_458 + 150 + 38)
    parent_surface_net_cash = parent_cash - parent_debt
    parent_restricted_cash = Decimal(11_886)
    parent_unrestricted_bank_cash_net_debt = parent_bank_deposits - parent_restricted_cash - parent_debt
    parent_cash_less_restricted_net_debt = parent_cash - parent_restricted_cash - parent_debt

    cash_event_net = placement_net - acquisition_cash

    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "exchange_filed_annual_report_attributable_net_cash_bridge",
        "source_url": SOURCE_URL,
        "package_version": "shenhua-attributable-net-cash-bridge-v1",
        "status": "attributable_net_cash_bridge_compiled_not_reviewed_or_approved",
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Compile cash, debt, restricted-cash and minority disclosures into transparent "
            "attributable net-cash candidates. The annual report does not allocate every "
            "consolidated cash and debt item to the parent common-equity claim, so no value "
            "is promoted to CyclicalFacts or the shared valuation model."
        ),
        "key_accounting_boundaries": [
            "Consolidated cash includes cash held by non-wholly-owned subsidiaries and finance-company deposits.",
            "Minority equity must not be included in a parent-common-equity net-cash anchor.",
            "The finance company is a 40% associate, not a wholly-owned bank; its deposits are not automatically fungible group cash.",
            "Restricted cash, three-month-plus deposits and post-balance acquisition cash must be treated separately.",
        ],
        "audited_balance_sheet_facts": {
            "consolidated_cash_cny_millions": 96_772,
            "consolidated_finance_company_deposits_cny_millions": 41_247,
            "consolidated_interest_bearing_debt_proxy_cny_millions": int(consolidated_debt),
            "consolidated_restricted_cash_cny_millions": 17_637,
            "consolidated_deposits_over_three_months_cny_millions": 55_847,
            "minority_equity_cny_millions": 72_344,
            "parent_cash_cny_millions": 83_347,
            "parent_finance_company_deposits_cny_millions": 39_540,
            "parent_bank_deposits_cny_millions": 43_807,
            "parent_debt_proxy_cny_millions": int(parent_debt),
            "parent_restricted_cash_cny_millions": 11_886,
            "parent_deposits_over_three_months_cny_millions": 54_168,
            "parent_finance_company_deposits_over_three_months_cny_millions": 39_561,
        },
        "candidate_derivations": {
            "consolidated_surface_net_cash": _money(consolidated_surface_net_cash),
            "parent_surface_net_cash": _money(parent_surface_net_cash),
            "parent_unrestricted_bank_cash_net_of_parent_debt": _money(parent_unrestricted_bank_cash_net_debt),
            "parent_cash_less_restricted_cash_net_of_parent_debt": _money(parent_cash_less_restricted_net_debt),
            "conservative_attributable_interval": {
                "lower_bound": _money(parent_unrestricted_bank_cash_net_debt),
                "upper_bound": _money(parent_surface_net_cash),
                "assumption": (
                    "Lower bound excludes finance-company deposits and parent restricted cash "
                    "while subtracting parent debt; upper bound includes all parent cash. "
                    "The interval is a review aid, not a reviewed valuation anchor."
                ),
            },
            "model_input": None,
            "review_status": "not_reviewed_or_approved",
            "review_requirements": [
                "Choose the net cash that is excess to normalized operating working capital, not the balance-sheet cash balance.",
                "Reconcile parent and consolidated restricted cash, deposits over three months and finance-company liquidity risk.",
                "Exclude minority-owned cash and debt and document the allocation basis.",
                "Update for the 2026 acquisition and placement before using a post-2025 valuation date.",
            ],
            "evidence_refs": [
                source_ref("shenhua_consolidated_cash_page_329", 329, "Consolidated cash and finance-company deposits"),
                source_ref("shenhua_consolidated_debt_pages_331_332", 331, "Consolidated short-term and current debt"),
                source_ref("shenhua_parent_balance_page_334", 334, "Parent cash and finance-company deposits"),
                source_ref("shenhua_parent_debt_page_335", 335, "Parent debt"),
                source_ref("shenhua_cash_note_page_392", 392, "Consolidated cash note and restricted/deposit detail"),
                source_ref("shenhua_parent_cash_note_page_462", 462, "Parent cash note and restricted/deposit detail"),
                source_ref("shenhua_equity_page_152", 152, "Parent and minority equity"),
            ],
        },
        "post_balance_cash_events": {
            "status": "observed_but_current_net_cash_not_derivable",
            "acquisition_cash_consideration_cny": format(acquisition_cash, ".2f"),
            "placement_net_proceeds_cny": format(placement_net, ".2f"),
            "net_transaction_cash_effect_cny": format(cash_event_net, ".2f"),
            "observation": (
                "The retained interim summary confirms the new share denominator but does not "
                "disclose cash, debt, restricted cash or minority cash at 2026-06-30, so a "
                "post-acquisition attributable net-cash value cannot be reconstructed from the "
                "current retained evidence set."
            ),
            "linked_evidence": {
                "id": "shenhua_2026_share_bridge",
                "path": SHARE_BRIDGE.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(SHARE_BRIDGE.read_bytes()).hexdigest().upper(),
            },
        },
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
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
        "evidence_sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
        "source_sha256": SOURCE_HASH,
        "linked_share_bridge_sha256": payload["post_balance_cash_events"]["linked_evidence"]["sha256"],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime" / "company-research" / "shenhua-2025-attributable-net-cash-bridge-latest.json"
    pointer.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
        "status": payload["status"],
        "interval_cny_millions": payload["candidate_derivations"]["conservative_attributable_interval"],
        "model_input": payload["candidate_derivations"]["model_input"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
