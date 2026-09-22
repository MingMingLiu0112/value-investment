"""Pin issuer-linked 2025 Midea Group Finance Co. size disclosures.

The finance-company figures establish the relative size of a related financial
entity. They are not a standalone financial-business carve-out, enterprise-value
bridge, FCFF net-debt input, tax allocation, WACC component, or share count.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-20260922"
POINTER = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json"

SOURCES = [
    {
        "id": "kelu_march_2026_finance_co_risk_assessment",
        "issuer": "Shenzhen Clou Electronics Co., Ltd.",
        "url": "http://static.cninfo.com.cn/finalpage/2026-03-21/1225023273.PDF",
        "path": "runtime/midea-finance-co-kelu-2025-annual-risk-20260321.pdf",
        "sha256": "3c7e329e24a51eb72acc5a50be06d2658cc04b44a7faa35fc4b7c4bf9c6fa530",
        "board_date": "2026-03-19",
        "publication_date": "2026-03-21",
        "pages": [1, 4],
    },
    {
        "id": "hekang_march_2026_finance_co_risk_assessment",
        "issuer": "Beijing Hiconics Eco-energy Technology Co., Ltd.",
        "url": "http://static.cninfo.com.cn/finalpage/2026-03-21/1225021603.PDF",
        "path": "runtime/midea-finance-co-hekang-2025-annual-risk-20260321.pdf",
        "sha256": "f88bb343ef494f601fac5f297dc039c53dd451af6d76896a1323f10b9348823b",
        "board_date": "2026-03-21",
        "publication_date": "2026-03-21",
        "pages": [1, 4],
    },
    {
        "id": "kelu_august_2026_finance_service_agreement_announcement",
        "issuer": "Shenzhen Clou Electronics Co., Ltd.",
        "url": "http://static.cninfo.com.cn/finalpage/2026-08-27/1225514586.PDF",
        "path": "runtime/midea-finance-co-kelu-2025-related-transaction-20260827.pdf",
        "sha256": "d1043b86538bc0aeafc2bb1a5285abda5084f1dfe9c3033fbd2ed1aa8bc9f4b2",
        "board_date": "2026-08-26",
        "publication_date": "2026-08-27",
        "pages": [2, 3],
    },
]

MIdea_consolidated_attributable_ordinary_net_profit_cny = "43945411000"
MIdea_consolidated_attributable_ordinary_equity_cny = "223221305000"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_page_text(path: Path, page: int) -> str:
    reader = PdfReader(path)
    text = reader.pages[page - 1].extract_text() or ""
    return re.sub(r"\s+", "", text)


def assert_source_text(source: dict[str, object], page: int, snippets: list[str]) -> None:
    path = ROOT / str(source["path"])
    text = normalized_page_text(path, page)
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        raise ValueError(
            f"{source['id']} page {page} does not contain expected text: {missing}"
        )


def cny_from_wan(raw_wan: str) -> str:
    return str(int(Decimal(raw_wan.replace(",", "")) * Decimal("10000")))


def validate_sources() -> None:
    for source in SOURCES:
        path = ROOT / str(source["path"])
        if digest(path) != source["sha256"]:
            raise ValueError(f"Finance-company source changed: {source['id']}")

    assert_source_text(
        SOURCES[0],
        1,
        ["美的集团股份有限公司持有95%股权"],
    )
    assert_source_text(
        SOURCES[0],
        4,
        [
            "资产总额4,443,999.24万元",
            "负债总额3,659,543.65万元",
            "净资产784,455.59万元",
            "营业收入59,913.46万元",
            "净利润41,054.49万元",
            "（未经审计）",
        ],
    )
    assert_source_text(
        SOURCES[1],
        1,
        ["美的集团股份有限公司持有95%股权", "广东威灵电机制造有限公司持有5%股权"],
    )
    assert_source_text(
        SOURCES[1],
        4,
        [
            "资产总额4,443,999.24万元",
            "负债总额3,659,543.65万元",
            "净资产784,455.59万元",
            "营业收入59,913.46万元",
            "净利润41,054.49万元",
        ],
    )
    assert_source_text(
        SOURCES[2],
        2,
        ["美的集团股份有限公司持有美的财务公司95%股权"],
    )
    assert_source_text(
        SOURCES[2],
        3,
        [
            "资产总额4,446,413.06万元",
            "负债总额3,660,553.73万元",
            "净资产785,859.34万元",
            "营业收入59,913.46万元",
            "净利润41,052.83万元",
            "（已经审计）",
        ],
    )


def build_payload() -> dict:
    validate_sources()

    unaudited = {
        "assets_cny": cny_from_wan("4,443,999.24"),
        "liabilities_cny": cny_from_wan("3,659,543.65"),
        "net_assets_cny": cny_from_wan("784,455.59"),
        "revenue_cny": cny_from_wan("59,913.46"),
        "net_profit_cny": cny_from_wan("41,054.49"),
    }
    audited = {
        "assets_cny": cny_from_wan("4,446,413.06"),
        "liabilities_cny": cny_from_wan("3,660,553.73"),
        "net_assets_cny": cny_from_wan("785,859.34"),
        "revenue_cny": cny_from_wan("59,913.46"),
        "net_profit_cny": cny_from_wan("41,052.83"),
    }

    net_profit_to_midea = (
        Decimal(audited["net_profit_cny"])
        / Decimal(MIdea_consolidated_attributable_ordinary_net_profit_cny)
    )
    net_assets_to_midea = (
        Decimal(audited["net_assets_cny"])
        / Decimal(MIdea_consolidated_attributable_ordinary_equity_cny)
    )

    payload = {
        "symbol": "000333",
        "package_version": "midea-finance-co-2025-size-observation-v1",
        "assessment_date": "2026-09-22",
        "subject": "Midea Group Finance Co., Ltd.",
        "status": "OBSERVATION_NOT_MODEL_INPUT",
        "source_type": "issuer_linked_finance_company_size_observation",
        "as_of": "2025-12-31",
        "finance_company_scope": {
            "registered_capital_cny": "3500000000",
            "direct_owner": "Midea Group Co., Ltd. (95%)",
            "indirect_owner": "Guangdong Weiling Motor Manufacturing Co., Ltd. (5%)",
            "supervisor": "National Financial Regulatory Administration and its local office",
        },
        "observations": [
            {
                "id": "march_risk_assessment_unaudited",
                "audit_status": "unaudited",
                "as_of": "2025-12-31",
                "values": unaudited,
                "source_ids": [
                    "kelu_march_2026_finance_co_risk_assessment",
                    "hekang_march_2026_finance_co_risk_assessment",
                ],
                "note": (
                    "Both linked listed companies report the same five values. This is a "
                    "cross-check of the cited figures, not an independent audit."
                ),
            },
            {
                "id": "august_related_transaction_announcement_audited",
                "audit_status": "audited_as_disclosed_in_related_listed_company_announcement",
                "as_of": "2025-12-31",
                "values": audited,
                "source_ids": ["kelu_august_2026_finance_service_agreement_announcement"],
                "note": (
                    "The announcement states that the 2025 figures are audited. It still "
                    "does not provide a standalone full profit statement, balance sheet, "
                    "tax, debt, cash, or working-capital split."
                ),
            },
        ],
        "derived_scale_candidates": {
            "status": "CANDIDATE_NOT_MODEL_INPUT",
            "audited_net_profit_to_midea_consolidated_attributable_ordinary_net_profit": format(
                net_profit_to_midea, ".8f"
            ),
            "audited_net_assets_to_midea_consolidated_attributable_ordinary_equity": format(
                net_assets_to_midea, ".8f"
            ),
            "basis": {
                "midea_consolidated_attributable_ordinary_net_profit_cny": MIdea_consolidated_attributable_ordinary_net_profit_cny,
                "midea_consolidated_attributable_ordinary_equity_cny": MIdea_consolidated_attributable_ordinary_equity_cny,
            },
            "limitation": (
                "The finance company is consolidated within Midea's ordinary equity. Its "
                "book equity is not a transferable listed-equity minority adjustment."
            ),
        },
        "conclusion": (
            "The finance company is operationally immaterial at consolidated scale, but "
            "these size observations do not establish an industrial EBIT carve-out, "
            "enterprise-value bridge, tax allocation, WACC, net debt, or share input. "
            "FCFF remains fail-closed."
        ),
        "blockers": [
            "finance_company_figures_are_not_full_standalone_statements",
            "finance_business_category_may_include_more_than_the_finance_company",
            "no_audited_industrial_tax_debt_cash_or_working_capital_allocation",
            "finance_company_book_equity_is_not_a_transferable_listed_equity_value",
        ],
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "formal_fair_value": None,
        "valuation_status": "VALUATION_NOT_READY",
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "evidence_refs": [
            {
                "id": source["id"],
                "path": source["path"],
                "url": source["url"],
                "sha256": source["sha256"],
                "pages": source["pages"],
                "issuer": source["issuer"],
                "board_date": source["board_date"],
                "publication_date": source["publication_date"],
            }
            for source in SOURCES
        ],
    }
    return payload


def main() -> None:
    payload = build_payload()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_digest = digest(target)
    manifest = {
        "script_sha256": digest(Path(__file__).resolve()),
        "evidence_sha256": evidence_digest,
        "source_sha256s": {source["id"]: source["sha256"] for source in SOURCES},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    POINTER.write_text(
        json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "sha256": evidence_digest},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": target.relative_to(ROOT).as_posix(),
        "sha256": evidence_digest,
        "status": payload["status"],
        "valuation_status": payload["valuation_status"],
        "registered_valuation_inputs": payload["registered_valuation_inputs"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
