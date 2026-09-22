"""Build an unaudited parent-attributable operating-profit pro forma for 601088."""
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
OUT = ROOT / "runtime" / "company-research" / "shenhua-2025-parent-operating-profit-bridge-20260921"


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


def _ratio(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = 30
        return format(value, ".9f")


def build() -> dict:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != SOURCE_HASH:
        raise ValueError("Shenhua 2025 annual report hash mismatch")
    reader = PdfReader(str(SOURCE))

    page_text(reader, 337, ("营业收入", "294,916", "营业利润", "75,532", "利润总额", "79,339"))
    page_text(reader, 338, ("归属于母公司股东的净利润", "52,849", "少数股东损益", "9,934"))
    page_text(reader, 340, ("母公司利润表", "投资收益", "44,607", "营业利润", "64,233", "利润总额", "67,384"))
    page_text(reader, 428, ("当期所得税费用", "16,511", "递延所得税的变动", "(9)"))
    page_text(reader, 429, ("会计利润", "79,339", "所得税费用", "16,556"))
    page_text(reader, 258, ("重要的非全资子公司", "准格尔能源", "归属于", "少数股东的损益"))
    page_text(reader, 460, ("报告分部利润总额", "46,597", "79,339"))

    facts = {
        2025: {
            "consolidated_operating_profit": 75_532,
            "consolidated_pretax_profit": 79_339,
            "consolidated_income_tax": 16_556,
            "consolidated_net_profit": 62_783,
            "parent_net_profit": 52_849,
            "minority_net_profit": 9_934,
            "parent_entity_operating_profit": 64_233,
            "parent_entity_pretax_profit": 67_384,
            "parent_entity_income_tax": 5_024,
            "parent_entity_net_profit": 62_360,
            "parent_entity_investment_income": 44_607,
            "parent_entity_associate_investment_income": 3_224,
        },
        2024: {
            "consolidated_operating_profit": 87_082,
            "consolidated_pretax_profit": 82_928,
            "consolidated_income_tax": 16_929,
            "consolidated_net_profit": 65_999,
            "parent_net_profit": 55_805,
            "minority_net_profit": 10_194,
            "parent_entity_operating_profit": 48_207,
            "parent_entity_pretax_profit": 48_378,
            "parent_entity_income_tax": 5_874,
            "parent_entity_net_profit": 42_504,
            "parent_entity_investment_income": 25_401,
            "parent_entity_associate_investment_income": 3_478,
        },
    }

    candidates = {}
    for year, data in facts.items():
        consolidated_operating = Decimal(data["consolidated_operating_profit"])
        consolidated_pretax = Decimal(data["consolidated_pretax_profit"])
        consolidated_tax = Decimal(data["consolidated_income_tax"])
        consolidated_net = Decimal(data["consolidated_net_profit"])
        parent_net = Decimal(data["parent_net_profit"])
        minority_net = Decimal(data["minority_net_profit"])

        with localcontext() as context:
            context.prec = 40
            effective_tax_rate = consolidated_tax / consolidated_pretax
            parent_net_share = parent_net / consolidated_net
            parent_operating_profit = consolidated_operating * parent_net_share

            minority_gross_up = minority_net / (Decimal(1) - effective_tax_rate)
            minority_method_pretax = consolidated_pretax - minority_gross_up
            minority_method_operating = minority_method_pretax - (
                (consolidated_pretax - consolidated_operating) * parent_net_share
            )
            parent_net_gross_up = parent_net / (Decimal(1) - effective_tax_rate)
            parent_net_method_operating = parent_net_gross_up - (
                (consolidated_pretax - consolidated_operating) * parent_net_share
            )
            method_delta = abs(parent_operating_profit - minority_method_operating)

        upper_bound = consolidated_operating - minority_net
        lower_bound = consolidated_operating - (minority_net / Decimal("0.75"))
        candidates[str(year)] = {
            "consolidated_operating_profit": _money(consolidated_operating),
            "consolidated_pretax_profit": _money(consolidated_pretax),
            "parent_net_profit": _money(parent_net),
            "minority_net_profit": _money(minority_net),
            "effective_tax_rate": _ratio(effective_tax_rate),
            "parent_net_share": _ratio(parent_net_share),
            "parent_attributable_pretax_operating_profit_candidate": _money(parent_operating_profit),
            "equivalent_derivations": {
                "minority_gross_up_method": _money(minority_method_operating),
                "parent_net_gross_up_method": _money(parent_net_method_operating),
                "method_delta_cny": _money(method_delta),
            },
            "statutory_minority_tax_interval": {
                "lower_bound_parent_operating_profit": _money(lower_bound),
                "upper_bound_parent_operating_profit": _money(upper_bound),
                "assumption": (
                    "Minority pre-tax operating profit is at least minority net profit and "
                    "is taxed at no more than the 25% statutory rate; this is an interval, not "
                    "a subsidiary-by-subsidiary allocation."
                ),
            },
            "non_operating_net_consolidated": _money(consolidated_pretax - consolidated_operating),
            "evidence_refs": [
                source_ref("shenhua_consolidated_income_page_337", 337, "Consolidated income statement"),
                source_ref("shenhua_profit_ownership_page_338", 338, "Profit allocation to parent and minority shareholders"),
                source_ref("shenhua_tax_reconciliation_page_429", 429, "Consolidated tax reconciliation"),
            ],
        }

    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "exchange_filed_annual_report_parent_operating_profit_pro_forma",
        "source_url": SOURCE_URL,
        "package_version": "shenhua-parent-operating-profit-bridge-v1",
        "status": "parent_operating_profit_pro_forma_compiled_not_reviewed_or_approved",
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Turn audited consolidated ownership and tax disclosures into a transparent "
            "parent-attributable pre-tax operating-profit candidate. The annual report does "
            "not publish this exact line item, so the bridge remains a non-statutory pro forma "
            "and is never fed to the valuation model without independent review."
        ),
        "key_accounting_boundaries": [
            "The model requires pre-tax parent-attributable operating profit; parent net profit must not be entered directly.",
            "Parent legal-entity pre-tax profit includes subsidiary investment income and non-operating items and is not a group parent claim.",
            "Consolidated pre-tax profit cannot be assigned entirely to the parent because 9,934 CNY millions belongs to minority shareholders.",
            "The audited filing does not disclose minority operating profit or subsidiary-by-subsidiary pre-tax profit, so any allocation is a pro forma.",
        ],
        "audited_facts": facts,
        "derivation": {
            "formula": (
                "consolidated operating profit * (parent net profit / consolidated net profit)"
            ),
            "assumption": (
                "The parent's share of after-tax consolidated profit is a valid allocation key "
                "for pre-tax operating profit. This assumes a uniform effective tax rate and no "
                "material difference between profit and operating-profit ownership proportions."
            ),
            "equivalent_minority_derivation": (
                "consolidated pretax profit - minority net profit / (1 - consolidated effective "
                "tax rate) - parent share of consolidated non-operating items"
            ),
            "candidate_values": candidates,
            "model_input": None,
            "review_status": "not_reviewed_or_approved",
            "review_requirements": [
                "Obtain audited parent-attributable operating profit or a subsidiary-by-subsidiary pre-tax/tax/minority allocation.",
                "Exclude or separately normalize the coal-resource rectification and other special items when constructing mid-cycle profit.",
                "Do not use 2025's current-cycle profit as the base scenario without a reviewed full-cycle normalization.",
            ],
        },
        "normalization_observation": (
            "These candidates are current-year audited-cycle observations (2025 and restated "
            "2024), not normalized mid-cycle bear/base/bull inputs. Low current profit or PE "
            "does not approve any scenario."
        ),
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
    pointer = ROOT / "runtime" / "company-research" / "shenhua-2025-parent-operating-profit-bridge-latest.json"
    pointer.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest().upper(),
        "status": payload["status"],
        "candidate_2025_cny_millions": payload["derivation"]["candidate_values"]["2025"]["parent_attributable_pretax_operating_profit_candidate"],
        "model_input": payload["derivation"]["model_input"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
