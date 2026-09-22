"""Audit Shenhua 2025 legal-entity and subsidiary ownership boundaries."""
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
OUT = ROOT / "runtime" / "company-research" / "shenhua-2025-subsidiary-allocation-evidence-20260921"


def source_ref(ref_id: str, page: int, description: str, quoted_facts: list[str]) -> dict:
    return {
        "id": ref_id,
        "path": SOURCE.relative_to(ROOT).as_posix(),
        "url": SOURCE_URL,
        "sha256": SOURCE_HASH,
        "page": page,
        "unit": "CNY millions",
        "description": description,
        "quoted_facts": quoted_facts,
    }


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = (reader.pages[page - 1].extract_text() or "").replace("\x00", " ").replace("\u200a", " ")
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def _number(value: int) -> Decimal:
    return Decimal(value)


def _sum(values: list[int | None]) -> int:
    return sum(value or 0 for value in values)


def build() -> dict:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != SOURCE_HASH:
        raise ValueError("Shenhua 2025 annual report hash mismatch")
    reader = PdfReader(str(SOURCE))

    page_text(reader, 152, ("归属于母公司股东权益合计", "409,107", "少数股东权益", "72,344"))
    page_text(reader, 338, ("归属于母公司股东的净利润", "52,849", "少数股东损益", "9,934"))
    page_text(reader, 340, ("母公司利润表", "投资收益", "44,607", "营业利润", "64,233", "利润总额", "67,384"))
    page_text(reader, 428, ("煤炭资源领域专项整治", "(4,118)", "当期所得税费用", "16,511"))
    page_text(reader, 429, ("会计利润", "79,339", "所得税费用", "16,556"))
    page_text(
        reader,
        439,
        (
            "重要的非全资子公司",
            "准格尔能源",
            "宝日希勒能源",
            "定州发电",
            "朔黄铁路",
            "远海航运",
            "黄骅港务",
            "北电胜利能源",
            "归属于",
            "少数股东的损益",
            "向少数股东",
            "宣告分派的股利",
            "少数股东",
            "权益余额",
        ),
    )
    page_text(reader, 440, ("联营企业的主要财务信息", "财务公司", "北京国电", "浩吉铁路", "神东天隆"))

    parent_entity = {
        2025: {
            "revenue_cny_millions": 74_055,
            "operating_profit_cny_millions": 64_233,
            "pretax_profit_cny_millions": 67_384,
            "income_tax_cny_millions": 5_024,
            "net_profit_cny_millions": 62_360,
            "investment_income_cny_millions": 44_607,
            "associate_investment_income_cny_millions": 3_224,
        },
        2024: {
            "revenue_cny_millions": 79_188,
            "operating_profit_cny_millions": 48_207,
            "pretax_profit_cny_millions": 48_378,
            "income_tax_cny_millions": 5_874,
            "net_profit_cny_millions": 42_504,
            "investment_income_cny_millions": 25_401,
            "associate_investment_income_cny_millions": 3_478,
        },
    }

    subsidiaries = [
        {
            "name": "准格尔能源",
            "minority_holding_pct": 42,
            "minority_profit_cny_millions": 2_766,
            "dividends_to_minority_cny_millions": 14_191,
            "minority_equity_cny_millions": 8_468,
            "revenue_cny_millions": 13_016,
            "net_profit_cny_millions": 6_519,
            "operating_cash_flow_cny_millions": 34_794,
            "total_assets_cny_millions": 29_489,
            "total_liabilities_cny_millions": 8_887,
        },
        {
            "name": "宝日希勒能源",
            "minority_holding_pct": 43,
            "minority_profit_cny_millions": 1_215,
            "dividends_to_minority_cny_millions": 1_193,
            "minority_equity_cny_millions": 5_017,
            "revenue_cny_millions": 8_183,
            "net_profit_cny_millions": 2_797,
            "operating_cash_flow_cny_millions": 3_379,
            "total_assets_cny_millions": 16_517,
            "total_liabilities_cny_millions": 4_994,
        },
        {
            "name": "定州发电",
            "minority_holding_pct": 59,
            "minority_profit_cny_millions": 436,
            "dividends_to_minority_cny_millions": 508,
            "minority_equity_cny_millions": 1_897,
            "revenue_cny_millions": 4_423,
            "net_profit_cny_millions": 733,
            "operating_cash_flow_cny_millions": 751,
            "total_assets_cny_millions": 4_204,
            "total_liabilities_cny_millions": 1_017,
        },
        {
            "name": "朔黄铁路",
            "minority_holding_pct": 47,
            "minority_profit_cny_millions": 3_086,
            "dividends_to_minority_cny_millions": None,
            "minority_equity_cny_millions": 18_553,
            "revenue_cny_millions": 23_061,
            "net_profit_cny_millions": 6_512,
            "operating_cash_flow_cny_millions": 4_511,
            "total_assets_cny_millions": 48_238,
            "total_liabilities_cny_millions": 10_571,
        },
        {
            "name": "远海航运",
            "minority_holding_pct": 49,
            "minority_profit_cny_millions": 100,
            "dividends_to_minority_cny_millions": 62,
            "minority_equity_cny_millions": 3_358,
            "revenue_cny_millions": 3_989,
            "net_profit_cny_millions": 205,
            "operating_cash_flow_cny_millions": -15,
            "total_assets_cny_millions": 7_566,
            "total_liabilities_cny_millions": 713,
        },
        {
            "name": "黄骅港务",
            "minority_holding_pct": 30,
            "minority_profit_cny_millions": 512,
            "dividends_to_minority_cny_millions": 387,
            "minority_equity_cny_millions": 3_940,
            "revenue_cny_millions": 5_388,
            "net_profit_cny_millions": 1_691,
            "operating_cash_flow_cny_millions": 2_236,
            "total_assets_cny_millions": 13_734,
            "total_liabilities_cny_millions": 1_379,
        },
        {
            "name": "北电胜利能源",
            "minority_holding_pct": 37,
            "minority_profit_cny_millions": 717,
            "dividends_to_minority_cny_millions": 446,
            "minority_equity_cny_millions": 4_490,
            "revenue_cny_millions": 6_677,
            "net_profit_cny_millions": 1_951,
            "operating_cash_flow_cny_millions": 3_561,
            "total_assets_cny_millions": 16_816,
            "total_liabilities_cny_millions": 4_893,
        },
    ]

    named_minority_profit = _sum([item["minority_profit_cny_millions"] for item in subsidiaries])
    named_dividends = _sum([item["dividends_to_minority_cny_millions"] for item in subsidiaries])
    named_minority_equity = _sum([item["minority_equity_cny_millions"] for item in subsidiaries])
    consolidated_minority_profit = 9_934
    consolidated_minority_equity = 72_344

    with localcontext() as context:
        context.prec = 30
        parent_profit_share = format(_number(52_849) / _number(52_849 + 9_934), ".9f")
        investment_income_share = format(_number(44_607) / _number(64_233), ".9f")

    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "exchange_filed_annual_report_legal_and_subsidiary_ownership_boundary_audit",
        "source_url": SOURCE_URL,
        "package_version": "shenhua-subsidiary-allocation-evidence-v1",
        "status": "subsidiary_allocation_boundary_audited_no_verified_allocation",
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Pin the audited parent legal-entity and named non-wholly-owned subsidiary facts that "
            "define Shenhua's ownership boundary. The annual report still does not disclose a "
            "subsidiary-by-subsidiary allocation of pre-tax profit and tax, so the package does not "
            "manufacture the missing allocation and leaves all model inputs null."
        ),
        "key_findings": [
            "The parent legal-entity operating profit includes RMB44,607 million of investment income; it is not the group-level parent-attributable pre-tax operating profit required by the cyclical model.",
            "The seven named material non-wholly-owned subsidiaries explain RMB8,832 million of consolidated minority profit, leaving RMB1,102 million attributable to other ownership arrangements and consolidation adjustments.",
            "The same named subsidiaries explain RMB45,723 million of minority equity, leaving RMB26,621 million of consolidated minority equity outside the named list.",
            "The annual report gives each named subsidiary revenue, net profit, cash flow, assets and liabilities, but no pre-tax profit, tax or reconciliation of its after-tax profit to the minority claim.",
        ],
        "parent_entity_income_statement": parent_entity,
        "parent_entity_boundary": {
            "conclusion": "parent_legal_entity_profit_is_not_group_parent_operating_profit",
            "observations": {
                "parent_entity_2025_investment_income_cny_millions": 44_607,
                "parent_entity_2025_associate_investment_income_cny_millions": 3_224,
                "parent_entity_2025_operating_profit_cny_millions": 64_233,
                "parent_profit_share_of_consolidated_profit": parent_profit_share,
                "investment_income_share_of_parent_entity_operating_profit": investment_income_share,
                "accounting_note": (
                    "Associate earnings use the equity method and are not consolidated non-controlling "
                    "interests; the parent legal-entity investment-income line also contains subsidiary "
                    "distributions, making it unsuitable as normalized parent operating profit."
                ),
            },
        },
        "named_non_wholly_owned_subsidiaries": {
            "disclosure_page": 439,
            "subsidiaries": subsidiaries,
            "totals": {
                "named_minority_profit_cny_millions": named_minority_profit,
                "named_dividends_to_minority_cny_millions": named_dividends,
                "named_minority_equity_cny_millions": named_minority_equity,
            },
            "notes": [
                "朔黄铁路 declares no dividend in the retained 2025 table, so its dividend is recorded as null, not zero.",
                "The named list is material, not exhaustive; unidentified subsidiaries and consolidation adjustments can explain the residual minority amounts.",
            ],
        },
        "consolidated_ownership_facts": {
            2025: {
                "parent_net_profit_cny_millions": 52_849,
                "minority_net_profit_cny_millions": consolidated_minority_profit,
                "parent_equity_cny_millions": 409_107,
                "minority_equity_cny_millions": consolidated_minority_equity,
                "total_equity_cny_millions": 481_451,
            },
            2024: {
                "parent_net_profit_cny_millions": 55_805,
                "minority_net_profit_cny_millions": 10_194,
                "parent_equity_cny_millions": 419_559,
                "minority_equity_cny_millions": 77_086,
                "total_equity_cny_millions": 496_645,
            },
        },
        "reconciliation_gaps": {
            "minority_profit": {
                "named_subsidiaries_cny_millions": named_minority_profit,
                "consolidated_cny_millions": consolidated_minority_profit,
                "residual_cny_millions": consolidated_minority_profit - named_minority_profit,
                "interpretation": "Named-subsidiary minority profit does not fully reconcile the consolidated minority profit.",
            },
            "minority_equity": {
                "named_subsidiaries_cny_millions": named_minority_equity,
                "consolidated_cny_millions": consolidated_minority_equity,
                "residual_cny_millions": consolidated_minority_equity - named_minority_equity,
                "interpretation": "Named-subsidiary minority equity does not fully reconcile the consolidated minority-equity balance.",
            },
        },
        "tax_and_non_recurring_observations": {
            "coal_rectification_non_recurring_item_2025_cny_millions": -4_118,
            "consolidated_accounting_profit_2025_cny_millions": 79_339,
            "current_income_tax_2025_cny_millions": 16_511,
            "total_income_tax_2025_cny_millions": 16_556,
            "note": (
                "The tax reconciliation is consolidated only. It does not allocate current tax, deferred tax "
                "or preferential rates among the parent and each non-wholly-owned subsidiary."
            ),
        },
        "model_derivations": {
            "normalized_parent_operating_profit": {
                "status": "cannot_derive_from_sub_legal_entity_or_named_subsidiary_disclosure",
                "candidate_values": {},
                "model_input": None,
                "review_requirement": (
                    "Obtain audited parent-attributable pre-tax operating profit or a subsidiary-by-subsidiary "
                    "allocation of pre-tax profit, tax and minority interests. No parent legal-entity line item or "
                    "named-subsidiary minority line may be substituted."
                ),
            },
            "attributable_net_cash": {
                "status": "outside_this_evidence_package",
                "candidate_values": {},
                "model_input": None,
                "note": "Ownership-boundary facts do not allocate cash, restricted deposits or debt to the parent common-equity claim.",
            },
        },
        "evidence_refs": [
            source_ref("shenhua_consolidated_equity_page_152", 152, "Consolidated parent and minority equity", ["归属于母公司股东权益合计 409,107", "少数股东权益 72,344"]),
            source_ref("shenhua_consolidated_profit_page_338", 338, "Consolidated profit by ownership", ["归属于母公司股东的净利润 52,849", "少数股东损益 9,934"]),
            source_ref("shenhua_parent_entity_income_page_340", 340, "Parent legal-entity income statement", ["营业收入 74,055", "投资收益 44,607", "营业利润 64,233", "利润总额 67,384"]),
            source_ref("shenhua_non_recurring_and_tax_page_428", 428, "Non-recurring item and current tax", ["煤炭资源领域专项整治 (4,118)", "当期所得税费用 16,511"]),
            source_ref("shenhua_tax_reconciliation_page_429", 429, "Consolidated tax reconciliation", ["会计利润 79,339", "所得税费用 16,556"]),
            source_ref("shenhua_subsidiary_boundary_page_439", 439, "Material non-wholly-owned subsidiary ownership and financial information", ["准格尔能源", "少数股东权益余额", "经营活动现金净流入"]),
            source_ref("shenhua_associate_boundary_page_440", 440, "Material associate financial information", ["联营企业的主要财务信息", "财务公司", "北京国电"]),
        ],
        "linked_evidence": [],
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
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime" / "company-research" / "shenhua-2025-subsidiary-allocation-evidence-latest.json"
    pointer.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
        "status": payload["status"],
        "named_minority_profit": payload["reconciliation_gaps"]["minority_profit"]["named_subsidiaries_cny_millions"],
        "named_minority_equity": payload["reconciliation_gaps"]["minority_equity"]["named_subsidiaries_cny_millions"],
        "model_input": payload["model_derivations"]["normalized_parent_operating_profit"]["model_input"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
