"""Build the dated 2014 appraisal-policy observation package for Moutai R1.

The package pins a SZSE-disclosed 2014 asset-appraisal report and uses only its
dated professional methodology observations as a bounded stress raster. It does
not register a risk-free rate, ERP, beta, cost of equity, WACC, fair value, or
any replay/trade/live admission.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/company-research/moutai-historical-capital-cost-policy-20260922"
POINTER = ROOT / "runtime/company-research/moutai-historical-capital-cost-policy-latest.json"

REVIEW_DATE = date(2026, 9, 22)

SOURCE_ID = "szse_2014_10_24_kunyuanshangfeng_erdian_appraisal"
SOURCE_SPEC = {
    "filename": "szse-2014-10-24-kunyuanshangfeng-erdian-policy-observation.pdf",
    "url": (
        "https://disc.static.szse.cn/download/disc/disk01/finalpage/2014-10-24/"
        "d936de48-27a0-452c-8ed3-66fb7fc90e54.PDF"
    ),
    "sha256": "7ad0105ee3a85f9b765cec874adc771878a657cac2067806909411e2309ce987",
    "content_type": "application/pdf",
    "get_status": 200,
    "source_role": (
        "Shenzhen Stock Exchange disclosure of a Kunyuan asset-appraisal report "
        "and supporting appraisal explanation"
    ),
}

PRIOR_EVIDENCE = [
    {
        "id": "moutai_historical_executed_entry_receipt",
        "path": (
            "runtime/strategy-validation/"
            "moutai-capital-entry-20260920T092929069969Z/result.json"
        ),
        "sha256": "201535069fc2397c007c0f6cddb13927c054fd683f675df9e640b43feb4b4e8a",
        "description": "Existing archived replay receipt containing the 2015-01-06 fill",
    },
    {
        "id": "moutai_historical_2015_01_yield_observations",
        "path": (
            "runtime/company-research/"
            "moutai-historical-2015-01-yield-observations-20260922/evidence.json"
        ),
        "sha256": "0cbbc220f5050e328e085f548e444a0c9c01ee993b73590fc8a7a3b375b58de1",
        "description": "Dated public yield observations bracketing the 2015-01-06 decision",
    },
    {
        "id": "moutai_historical_1429_sovereign_observation_package",
        "path": (
            "runtime/company-research/"
            "moutai-historical-1429-sovereign-observation-20260922/evidence.json"
        ),
        "sha256": "fc06756d257084c397746a87ea34c2e8d9995858fb4d6396508d52a9ab80f454",
        "description": "Pre-decision sovereign coupon observation retained without capital-cost input",
    },
    {
        "id": "moutai_historical_chinabond_government_2014_candidate",
        "path": (
            "runtime/strategy-validation/"
            "moutai-historical-chinabond-government-2014-20260920T133600Z/inspection.json"
        ),
        "sha256": "d9df14324d92e904a93b6bf2dd196760eead13f77a7e24243ff45e5343ad004e",
        "description": "Annual curve candidate not accepted as a point-in-time historical input",
    },
    {
        "id": "moutai_later_period_market_beta_research",
        "path": (
            "runtime/valuation-research/"
            "moutai-market-beta-20260909T164802225529Z/evidence.json"
        ),
        "sha256": "6f177ccdca3ec55c1c14b251a9dcc64817b9ca9cc6ffec4ac7bfdb3259bc60a0",
        "description": "Later-period company market-beta research; not a 2015 point-in-time beta",
    },
    {
        "id": "moutai_historical_beta_input_audit",
        "path": (
            "runtime/strategy-validation/"
            "moutai-historical-beta-input-audit-20260920T084526Z/evidence.json"
        ),
        "sha256": "5ab168cc99915d4e6e52570d989a588052a4c71e8955a73751066c5b60f180c1",
        "description": "Prior beta-input audit showing historical replay eligibility remains unproven",
    },
]

RF_PROPOSAL = {
    "low": "3.4966",
    "base": "3.6251",
    "high": "3.75",
}
ERP_PROPOSAL = "7.47"
BETA_RASTER = {
    "low": "0.80",
    "base": "1.00",
    "high": "1.20",
}
COST_OF_EQUITY_RASTER = {
    "low": "9.4726",
    "base": "11.0951",
    "high": "12.714",
}

SPACE_RE = re.compile(r"\s+")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return SPACE_RE.sub(" ", " ".join(pages)).strip()


def require_hash(path: Path, expected: str, source_id: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"Source hash mismatch for {source_id}: {actual}")


def source_record() -> dict:
    path = OUT / SOURCE_SPEC["filename"]
    require_hash(path, SOURCE_SPEC["sha256"], SOURCE_ID)
    stat = path.stat()
    return {
        "id": SOURCE_ID,
        "url": SOURCE_SPEC["url"],
        "path": str(path.relative_to(ROOT)),
        "sha256": SOURCE_SPEC["sha256"],
        "archived_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "byte_size": stat.st_size,
        "content_type": SOURCE_SPEC["content_type"],
        "encoding": None,
        "http_get_status": SOURCE_SPEC["get_status"],
        "source_role": SOURCE_SPEC["source_role"],
    }


def source_ref(source: dict, *, description: str) -> dict:
    return {
        "id": source["id"],
        "path": source["path"],
        "sha256": source["sha256"],
        "url": source["url"],
        "description": description,
    }


def prior_refs() -> list[dict]:
    refs = []
    for item in PRIOR_EVIDENCE:
        path = ROOT / item["path"]
        require_hash(path, item["sha256"], item["id"])
        refs.append(
            {
                "id": item["id"],
                "path": str(path.relative_to(ROOT)),
                "sha256": item["sha256"],
                "url": None,
                "description": item["description"],
            }
        )
    return refs


def validate_cost_of_equity_raster() -> None:
    for scenario in ("low", "base", "high"):
        calculated = (
            Decimal(RF_PROPOSAL[scenario])
            + Decimal(ERP_PROPOSAL) * Decimal(BETA_RASTER[scenario])
        )
        rendered = format(calculated.normalize(), "f")
        if rendered != COST_OF_EQUITY_RASTER[scenario]:
            raise ValueError(
                f"Cost-of-equity raster mismatch for {scenario}: "
                f"expected {COST_OF_EQUITY_RASTER[scenario]}, got {rendered}"
            )


def validate_source_content() -> None:
    path = OUT / SOURCE_SPEC["filename"]
    reader = PdfReader(str(path))
    creation_date = reader.metadata.get("/CreationDate") if reader.metadata else None
    if creation_date != "D:20141023173556Z":
        raise ValueError(f"Unexpected PDF creation metadata: {creation_date}")

    text = normalized_pdf(path)
    required_phrases = [
        "坤元评报〔2014〕364号",
        "甘肃上峰水泥股份有限公司",
        "台州市亚东水泥制造有限公司",
        "二〇一四年十月十四日",
        "到期收益率4.39%作为无风险报酬率",
        "亚东水泥公司 Beta 系数= 1.0766",
        "市场风险溢价为 7.47%",
        "企业特定风险调整系数为 2%",
        "14.43%",
    ]
    missing = [term for term in required_phrases if term not in text]
    if missing:
        raise ValueError(f"Appraisal PDF missing required terms: {missing}")

    required_patterns = {
        "appraisal_base_date": r"评估基准日为\s*2014\s*年\s*7\s*月\s*31\s*日",
        "long_bond_selection": (
            r"到期日距评估基准日\s*10\s*年以上的交易品种的平\s*均\s*"
            r"到期收益率\s*4\.39%作为无风险报酬率"
        ),
        "erp_period": r"2001\s*年到\s*2013\s*年",
        "erp_method": r"几何平均收益率估算的\s*ERP\s*的算术平均值",
        "cement_company_beta": r"亚东水泥公司\s*Beta\s*系数\s*=\s*1\.0766",
    }
    missing_patterns = [
        name for name, pattern in required_patterns.items() if not re.search(pattern, text)
    ]
    if missing_patterns:
        raise ValueError(f"Appraisal PDF missing required patterns: {missing_patterns}")


def appraisal_observation() -> dict:
    return {
        "report_number": "坤元评报〔2014〕364号",
        "report_date": "2014-10-14",
        "appraisal_base_date": "2014-07-31",
        "disclosure_url_path_date": "2014-10-24",
        "pdf_creation_metadata": "D:20141023173556Z",
        "appraisal_firm": "坤元资产评估有限公司",
        "engager": "甘肃上峰水泥股份有限公司",
        "subject_company": "台州市亚东水泥制造有限公司",
        "subject_industry": "cement",
        "observed_values": {
            "risk_free_rate_percent": "4.39",
            "equity_risk_premium_percent": "7.47",
            "subject_company_beta": "1.0766",
            "subject_company_specific_risk_percent": "2",
            "subject_company_cost_of_equity_percent": "14.43",
        },
        "risk_free_method": (
            "Average maturity yield on 2014-07-31 from government bonds with more "
            "than ten years to maturity"
        ),
        "erp_method": (
            "HS300 component geometric-return annual estimates from 2001 to 2013; "
            "arithmetic average of the geometric-return ERP estimates"
        ),
        "beta_method": "Wind terminal cement-peer beta unlevered and relevered to subject",
        "transfer_boundary": {
            "beta": "not_transferable_to_moutai",
            "specific_risk": "not_transferable_to_moutai",
            "cost_of_equity": "not_transferable_to_moutai",
            "reason": (
                "The three subject-company parameters embed a cement-company capital "
                "structure and peer set. Only the dated ERP methodology/value and the "
                "broad long-dated government-bond selection rule are policy observations."
            ),
        },
        "disclosure_date_evidence": (
            "The SZSE URL contains a 2014-10-24 disclosure path date and the PDF "
            "creation metadata is 2014-10-23. These observations do not independently "
            "prove the disclosure timestamp used by the 2015 decision process."
        ),
    }


def build() -> dict:
    validate_cost_of_equity_raster()
    validate_source_content()
    source = source_record()
    refs = prior_refs()
    return {
        "symbol": "600519",
        "review_date": REVIEW_DATE.isoformat(),
        "engineering_status": "historical_capital_cost_policy_observation_package_complete",
        "status": (
            "dated_professional_appraisal_erp_and_method_observation_archived_as_"
            "unadmitted_stress_raster"
        ),
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
            "Record a dated professional appraisal disclosure from 2014-10-14/24 and "
            "study a bounded capital-cost raster. No raster value is admitted as a "
            "point-in-time Moutai input."
        ),
        "appraisal_observation": appraisal_observation(),
        "capital_cost_policy_candidate": {
            "status": "studied_stress_raster_unadmitted",
            "risk_free_rate_percent": {
                "proposal": RF_PROPOSAL,
                "provenance": (
                    "Prior public yield observations around 2015-01-05/06; not an exact "
                    "same-day risk-free term-structure input"
                ),
                "admitted": False,
            },
            "equity_risk_premium_percent": {
                "proposal": ERP_PROPOSAL,
                "provenance": (
                    "2014-10-14 Kunyuan appraisal observation using HS300 2001-2013 "
                    "geometric-return methodology"
                ),
                "admitted": False,
            },
            "beta": {
                "proposal": BETA_RASTER,
                "provenance": (
                    "Studied low/base/high boundary raster only; no 2015 point-in-time "
                    "Moutai beta is available"
                ),
                "admitted": False,
            },
            "cost_of_equity_percent": {
                "proposal": COST_OF_EQUITY_RASTER,
                "formula": "rf + beta * erp",
                "admitted": False,
            },
        },
        "not_transferable_from_cement_subject": {
            "subject_company_beta": "1.0766",
            "subject_company_specific_risk_percent": "2",
            "subject_company_cost_of_equity_percent": "14.43",
            "transfer_status": "not_transferable_to_moutai",
        },
        "unresolved": [
            "exact_same_day_risk_free_term_structure",
            "point_in_time_2015_moutai_beta",
            "uniquely_correct_historical_equity_risk_premium",
            "moutai_company_specific_risk_and_capital_structure",
            "full_r1_point_in_time_decision_chain",
        ],
        "not_proven": [
            "The 7.47% ERP observation is the unique correct ERP for a January 2015 Moutai decision.",
            "The 4.39% appraisal risk-free rate or any 2015 yield observation is the correct equity-valuation term structure.",
            "A raster beta of 0.80, 1.00, or 1.20 is a point-in-time Moutai beta.",
            "Any raster cost of equity is a validated historical Moutai cost of capital.",
            "R1 can pass because a dated professional ERP observation has now been archived.",
        ],
        "definition_breaks": [
            "A professional appraisal ERP observation is dated policy evidence, not a market fact that must be reused for Moutai.",
            "A cement-company beta, specific risk, and cost of equity belong to the cement subject, not to Moutai.",
            "A stress raster explores sensitivity; it does not establish the most likely or policy-approved parameter.",
            "An official disclosure URL path date and PDF creation metadata are not full timestamp provenance for the 2015 decision.",
        ],
        "point_in_time_policy": [
            "The appraisal report date is 2014-10-14 and its appraisal base date is 2014-07-31.",
            "The SZSE URL carries a 2014-10-24 path; no later revision status is claimed.",
            "The existing 2015-01-06 execution receipt remains the only decision-date anchor.",
            "No parameter from the 2026 appraisal download is backfilled as if it had been selected in January 2015.",
        ],
        "forbidden_calculations": [
            "Register 4.39% as a Moutai historical risk-free rate.",
            "Register 7.47% as the admitted historical ERP without an independent uniqueness decision.",
            "Register 0.80, 1.00, or 1.20 as the historical Moutai beta.",
            "Register 9.4726%, 11.0951%, or 12.714% as a validated cost of equity.",
            "Transfer the cement subject beta, specific risk, or cost of equity to Moutai.",
            "Use the stress raster to mark R1, simulation, replay, trade, or live admission as passed.",
        ],
        "blockers": [
            "historical_risk_free_rate_contract_not_registered",
            "historical_beta_not_resolved",
            "historical_equity_risk_premium_not_uniquely_resolved",
            "historical_cost_of_equity_not_registered",
            "full_r1_point_in_time_decision_chain_not_validated",
        ],
        "registered_capital_cost_inputs": [],
        "evidence_refs": [
            source_ref(
                source,
                description=(
                    "SZSE-disclosed 2014 Kunyuan appraisal report and explanation; "
                    "cement-subject parameters are explicitly bounded"
                ),
            ),
            *refs,
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": digest,
        "source_sha256s": {SOURCE_ID: SOURCE_SPEC["sha256"]},
        "prior_evidence_sha256s": {
            item["id"]: item["sha256"] for item in PRIOR_EVIDENCE
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    POINTER.write_text(
        json.dumps(
            {"path": OUT.relative_to(ROOT).as_posix(), "sha256": digest},
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
                "sha256": digest,
                "status": payload["status"],
                "r1_status": payload["r1_status"],
                "registered_capital_cost_inputs": payload["registered_capital_cost_inputs"],
                "capital_cost_policy_candidate": payload["capital_cost_policy_candidate"],
                "unresolved": payload["unresolved"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
