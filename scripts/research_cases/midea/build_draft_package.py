"""Build the versioned 000333 draft research package from retained originals.

This is a case-input adapter. Valuation remains in the shared residual-income
model and the package deliberately carries no human approval or order intent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.event_scan import (  # noqa: E402
    AnnouncementReview,
    COVERAGE_INCOMPLETE,
    EVENT_SCAN_SCHEMA,
    PRE_MODEL_PENDING_HUMAN_REVIEW,
    REVIEW_PENDING_HUMAN_REVIEW,
    SCAN_PENDING_HUMAN_REVIEW,
    EventScanResult,
)
from value_investment_agent.application.product.source_bound_inputs import (  # noqa: E402
    source_catalog_sha256,
)
from value_investment_agent.m1_valuation_package_builder import (  # noqa: E402
    build_descriptor,
)
from value_investment_agent.research_input import build_research_run_spec  # noqa: E402


SYMBOL = "000333"
NAME = "美的集团"
RESEARCH_DATE = "2026-10-17"
VALUATION_DATE = "2026-10-16"
RUN_ID = "midea-draft-20261017-v2"
OUTPUT_DIR = ROOT / "runtime" / "company-research" / RUN_ID
EVENT_SCAN_RETRIEVED_AT = "2026-10-17T17:49:45.662894+08:00"
EVENT_ORIGINAL_RETRIEVED_AT = "2026-10-17T17:49:52+08:00"

ANNUAL = {
    "id": "midea_fy2025_annual",
    "path": "runtime/midea-2025-official.pdf",
    "url": "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF",
    "sha256": "16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6",
    "published_at": "2026-03-31T00:00:00+08:00",
    "available_at": "2026-03-31T23:59:59+08:00",
}
H1 = {
    "id": "midea_2026h1",
    "path": (
        "runtime/prospective-public-event-20260927/"
        "gapfill-000333-20260927T091704729284Z/1225531404.pdf"
    ),
    "url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF",
    "sha256": "576dd80e353e53296a800b03e9889a9cbb2e8b91fa2ab3c1dace7c10159179b8",
    "published_at": "2026-08-29T00:00:00+08:00",
    "available_at": "2026-08-29T23:59:59+08:00",
}
HKEX_DENOMINATOR = {
    "id": "midea_202606_hkex_monthly_return",
    "path": (
        "runtime/company-research/midea-denominator-recheck-20261013/"
        "hkex-window-20260701-20260807/originals/"
        "12235688-2026070700419_c.pdf"
    ),
    "url": (
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0707/"
        "2026070700419_c.pdf"
    ),
    "sha256": "fab9be2f0349dcda9880b178e45e4dd65474b98635bf454adeeb19ed7bc3ecfd",
    "published_at": "2026-07-07T16:30:00+08:00",
    "available_at": "2026-07-07T16:30:00+08:00",
}
QUOTE = {
    "id": "midea_quote_20261016",
    "path": "runtime/quote-sessions/20261016T090031652233Z/bundle.json",
    "sha256": "08a8cb10dbb7785870645f8b2e1ab7d4a5f3f6cf8bf4295da5b5baa8ccbd927e",
}
EVENT_DOCUMENTS = (
    {
        "id": "cninfo_1225608903",
        "path": (
            "runtime/prospective-public-event-2026-10-17/"
            "gapfill-000333-20261017T094945395069Z/1225608903.PDF"
        ),
        "url": "https://static.cninfo.com.cn/finalpage/2026-10-17/1225608903.PDF",
        "title": "关于以集中竞价交易方式回购A股股份进展情况的公告",
        "rule_kind": "buyback_progress",
        "published_at": "2026-10-17T00:00:00+08:00",
        "available_at": "2026-10-17T00:00:00+08:00",
        "sha256": "cca6dc38ff6b5353422fe36f173108931ec53c734372d2b30cfeacb6260077fd",
    },
    {
        "id": "cninfo_1225603532",
        "path": (
            "runtime/prospective-public-event-2026-10-17/"
            "gapfill-000333-20261017T094945395069Z/1225603532.PDF"
        ),
        "url": "https://static.cninfo.com.cn/finalpage/2026-10-14/1225603532.PDF",
        "title": "2026年第一次临时股东会决议公告",
        "rule_kind": "egm_resolution",
        "published_at": "2026-10-14T00:00:00+08:00",
        "available_at": "2026-10-15T00:00:00+08:00",
        "sha256": "6732a5255485d7cdd81d0b73af961fac639c3f344420b84c1a69ac135be7a0bd",
    },
    {
        "id": "cninfo_1225603533",
        "path": (
            "runtime/prospective-public-event-2026-10-17/"
            "gapfill-000333-20261017T094945395069Z/1225603533.PDF"
        ),
        "url": "https://static.cninfo.com.cn/finalpage/2026-10-14/1225603533.PDF",
        "title": "北京市嘉源律师事务所关于美的集团2026年第一次临时股东会的法律意见书",
        "rule_kind": "legal_opinion",
        "published_at": "2026-10-14T00:00:00+08:00",
        "available_at": "2026-10-15T00:00:00+08:00",
        "sha256": "e0aebb190712c15e82b29297c1e27d843564ea51cfe36f587eb0955bbe63985c",
    },
    {
        "id": "cninfo_1225603534",
        "path": (
            "runtime/prospective-public-event-2026-10-17/"
            "gapfill-000333-20261017T094945395069Z/1225603534.PDF"
        ),
        "url": "https://static.cninfo.com.cn/finalpage/2026-10-14/1225603534.PDF",
        "title": "关于回购注销部分限制性股票减资暨通知债权人的公告",
        "rule_kind": "capital_reduction_notice",
        "published_at": "2026-10-14T00:00:00+08:00",
        "available_at": "2026-10-15T00:00:00+08:00",
        "sha256": "b38a3d71faa803d485d3400410a1dab61699653fc8635e6b2d435df86f04d733",
    },
)

SCENARIOS = {
    "bear": {
        "cost_of_equity": "0.09",
        "forecast_roes": ["0.15", "0.14", "0.13", "0.12", "0.11"],
        "terminal_roe": "0.095",
        "terminal_growth": "0.015",
        "retention": "0.40",
    },
    "base": {
        "cost_of_equity": "0.09",
        "forecast_roes": ["0.18", "0.17", "0.16", "0.155", "0.15"],
        "terminal_roe": "0.11",
        "terminal_growth": "0.02",
        "retention": "0.35",
    },
    "bull": {
        "cost_of_equity": "0.09",
        "forecast_roes": ["0.205", "0.20", "0.195", "0.19", "0.185"],
        "terminal_roe": "0.13",
        "terminal_growth": "0.025",
        "retention": "0.30",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_write(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return _sha256(path)


def _source(
    *,
    source_id: str,
    kind: str,
    relative_path: str,
    location: str,
    published_at: str,
    available_at: str,
    availability_basis: str,
    identity: dict[str, Any] | None = None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    path = ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    result: dict[str, Any] = {
        "id": source_id,
        "kind": kind,
        "location": location,
        "local_path": relative_path,
        "sha256": _sha256(path),
        "published_at": published_at,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        "source_available_at": available_at,
        "availability_basis": availability_basis,
        "parser_version": "midea-draft-case-input-v2",
    }
    if identity is not None:
        result["issuer_identity"] = identity
    return result


def _verify_fixed_digest(item: dict[str, str]) -> None:
    actual = _sha256(ROOT / item["path"])
    if actual != item["sha256"]:
        raise ValueError(f"retained source hash changed: {item['path']}: {actual}")


def _cninfo_identity() -> dict[str, Any]:
    return {
        "venue": "CNINFO",
        "security_code": SYMBOL,
        "issuer_name": NAME,
        "organization_id": "9900005965",
    }


def _build_event_scan(path: Path) -> str:
    event_sources = [
        _source(
            source_id=item["id"],
            kind="official_issuer_filing",
            relative_path=item["path"],
            location=item["url"],
            published_at=item["published_at"],
            available_at=item["available_at"],
            availability_basis=(
                "CNINFO date-only publication; timestamp is a date boundary, "
                "not a strict intraday PIT observation"
            ),
            identity=_cninfo_identity(),
            retrieved_at=EVENT_ORIGINAL_RETRIEVED_AT,
        )
        for item in EVENT_DOCUMENTS
    ]
    by_id = {item["id"]: item for item in event_sources}
    announcements = tuple(
        AnnouncementReview(
            announcement_id=item["id"].removeprefix("cninfo_"),
            published_at=datetime.fromisoformat(item["published_at"]),
            title=item["title"],
            source_url=item["url"],
            rule_kind=item["rule_kind"],
            review_status=REVIEW_PENDING_HUMAN_REVIEW,
            materiality_candidate=True,
            pre_model=(
                datetime.fromisoformat(item["published_at"]).date()
                < datetime.fromisoformat(VALUATION_DATE).date()
            ),
            evidence_refs=(
                {
                    "id": item["id"],
                    "sha256": by_id[item["id"]]["sha256"],
                    "path": item["path"],
                    "source_url": item["url"],
                },
            ),
            notes=(
                "Retained from the bounded CNINFO snapshot. Coverage is not a "
                "full-day completeness proof; strict contemporaneous PIT is not "
                "proven and human materiality review is pending."
            ),
        )
        for item in EVENT_DOCUMENTS
    )
    scan = EventScanResult(
        schema_version=EVENT_SCAN_SCHEMA,
        symbol=SYMBOL,
        provider="cninfo",
        scan_from=datetime.fromisoformat("2026-10-13").date(),
        scan_to=datetime.fromisoformat(RESEARCH_DATE).date(),
        validity_from=datetime.fromisoformat(VALUATION_DATE).date(),
        validity_to=datetime.fromisoformat(RESEARCH_DATE).date(),
        status=SCAN_PENDING_HUMAN_REVIEW,
        coverage_status=COVERAGE_INCOMPLETE,
        pre_model_review_status=PRE_MODEL_PENDING_HUMAN_REVIEW,
        announcements=announcements,
        blockers=(
            "EVENT_COVERAGE_INCOMPLETE: the CNINFO snapshot was captured before the research day closed.",
            "Four 2026-10-14 and 2026-10-17 announcements remain PENDING_HUMAN_REVIEW.",
            "STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN: CNINFO provided date-level times and retained files were acquired after the research cutoff.",
        ),
        evidence_refs=tuple(
            {
                "id": item["id"],
                "sha256": next(
                    source["sha256"]
                    for source in event_sources
                    if source["id"] == item["id"]
                ),
                "path": item["path"],
                "source_url": item["url"],
            }
            for item in EVENT_DOCUMENTS
        ),
        retrieved_at=datetime.fromisoformat(EVENT_SCAN_RETRIEVED_AT),
        parser_version="midea-draft-event-scan-v2",
    )
    return _json_write(path, scan.as_policy())


def _assumption_memo(generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": "midea-draft-assumption-memo-v2",
        "action": "no_order",
        "symbol": SYMBOL,
        "name": NAME,
        "status": "DRAFT_NOT_APPROVED",
        "generated_at": generated_at,
        "research_as_of": RESEARCH_DATE,
        "valuation_date": VALUATION_DATE,
        "profile_id": "mature_manufacturing",
        "model": "residual-income-equity-shared-dated-v2",
        "human_approved": False,
        "scenarios": SCENARIOS,
        "limitations": [
            "Cost of equity is a candidate 9% policy hurdle, not an issuer-specific estimate.",
            "ROE paths and retention are candidate research judgments and have not been approved.",
            "The draft is conditional research only and cannot generate a BUY/SELL action.",
            "Distribution inputs are NOT_ADMITTED.",
        ],
    }


def _assumptions_and_bindings(
    sources: list[dict[str, Any]], memo_ref: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    annual_ref = {"id": ANNUAL["id"], "sha256": next(s["sha256"] for s in sources if s["id"] == ANNUAL["id"])}
    h1_ref = {"id": H1["id"], "sha256": next(s["sha256"] for s in sources if s["id"] == H1["id"])}
    denominator_ref = {
        "id": HKEX_DENOMINATOR["id"],
        "sha256": next(s["sha256"] for s in sources if s["id"] == HKEX_DENOMINATOR["id"]),
    }
    fields: list[dict[str, Any]] = [
        {
            "path": "cost_of_equity",
            "name": "cost_of_equity",
            "unit": "decimal",
            "ordering": "ascending",
            "basis": "Candidate 9% equity hurdle applied to all scenarios.",
            "rationale": "No issuer-specific beta estimate is admitted; a common hurdle keeps the draft internally consistent.",
            "refs": [memo_ref, h1_ref],
        },
        *[
            {
                "path": f"forecast_roes.{index}",
                "name": f"forecast_roe_{year}",
                "unit": "ratio",
                "ordering": "ascending",
                "basis": "Candidate five-year ROE path anchored on audited FY2025 and unaudited H1 2026.",
                "rationale": "The path allows margin and competitive pressure while preserving a quality-compounder base case.",
                "refs": [memo_ref, annual_ref, h1_ref],
            }
            for index, year in enumerate(range(2026, 2031))
        ],
        {
            "path": "terminal_roe",
            "name": "terminal_roe",
            "unit": "ratio",
            "ordering": "ascending",
            "basis": "Candidate terminal excess-return persistence assumption.",
            "rationale": "Terminal ROE remains above or near the equity hurdle by scenario without assuming permanent high excess returns.",
            "refs": [memo_ref, annual_ref, h1_ref],
        },
        {
            "path": "terminal_growth",
            "name": "terminal_growth",
            "unit": "ratio",
            "ordering": "ascending",
            "basis": "Candidate long-run nominal growth band.",
            "rationale": "Growth is capped below the 9% equity hurdle in every scenario.",
            "refs": [memo_ref, annual_ref],
        },
        {
            "path": "retention",
            "name": "retention",
            "unit": "ratio",
            "ordering": "descending",
            "basis": "Candidate reinvestment and shareholder-return allocation.",
            "rationale": "The bear case retains more capital to defend operations; the bull case distributes more of higher earnings.",
            "refs": [memo_ref, annual_ref, denominator_ref],
        },
    ]
    assumptions = []
    for field in fields:
        assumptions.append(
            {
                "name": field["name"],
                "unit": field["unit"],
                "bear": SCENARIOS["bear"][field["path"] if "." not in field["path"] else field["path"].split(".")[0]][int(field["path"].split(".")[1])]
                if field["path"].startswith("forecast_roes.")
                else SCENARIOS["bear"][field["path"]],
                "base": SCENARIOS["base"][field["path"] if "." not in field["path"] else field["path"].split(".")[0]][int(field["path"].split(".")[1])]
                if field["path"].startswith("forecast_roes.")
                else SCENARIOS["base"][field["path"]],
                "bull": SCENARIOS["bull"][field["path"] if "." not in field["path"] else field["path"].split(".")[0]][int(field["path"].split(".")[1])]
                if field["path"].startswith("forecast_roes.")
                else SCENARIOS["bull"][field["path"]],
                "basis": field["basis"],
                "rationale": field["rationale"],
                "confidence": "low",
                "sensitivity": "high" if field["path"] in {"cost_of_equity", "terminal_roe"} else "medium",
                "evidence_refs": field["refs"],
                "blockers": ["CANDIDATE_DRAFT_ASSUMPTION_NOT_HUMAN_VALIDATED"],
                "ordering": field["ordering"],
            }
        )
    bindings = []
    for scenario in ("bear", "base", "bull"):
        for field in fields:
            if field["path"].startswith("forecast_roes."):
                index = int(field["path"].split(".")[1])
                expected = SCENARIOS[scenario]["forecast_roes"][index]
            else:
                expected = SCENARIOS[scenario][field["path"]]
            bindings.append(
                {
                    "assumption_name": field["name"],
                    "scenario": scenario,
                    "field_path": field["path"],
                    "expected_value": expected,
                    "evidence_refs": field["refs"],
                }
            )
    if len(bindings) != 27:
        raise ValueError(f"expected 27 scenario bindings, got {len(bindings)}")
    return (
        {
            "assumptions": assumptions,
            "evidence_refs": [memo_ref, annual_ref, h1_ref, denominator_ref],
            "blockers": ["CANDIDATE_DRAFT_ASSUMPTIONS_NOT_HUMAN_VALIDATED"],
        },
        bindings,
    )


def build_package() -> dict[str, Any]:
    for item in (ANNUAL, H1, HKEX_DENOMINATOR):
        _verify_fixed_digest(item)
    for item in EVENT_DOCUMENTS:
        actual = _sha256(ROOT / item["path"])
        if actual != item["sha256"]:
            raise ValueError(f"retained event hash changed: {item['path']}: {actual}")
    if _sha256(ROOT / QUOTE["path"]) != QUOTE["sha256"]:
        raise ValueError("retained quote bundle hash changed")

    output = OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    event_scan_path = output / "event-scan-20261017.json"
    event_scan_sha = _build_event_scan(event_scan_path)
    generated_at = datetime.now(timezone.utc).isoformat()
    memo_path = output / "assumption-memo-v2.json"
    memo_sha = _json_write(memo_path, _assumption_memo(generated_at))
    memo_relative = memo_path.relative_to(ROOT).as_posix()
    memo_ref = {"id": "midea_assumption_memo_20261017_v2", "sha256": memo_sha}

    sources = [
        _source(
            source_id=ANNUAL["id"],
            kind="official_issuer_filing",
            relative_path=ANNUAL["path"],
            location=ANNUAL["url"],
            published_at=ANNUAL["published_at"],
            available_at=ANNUAL["available_at"],
            availability_basis="CNINFO date-only publication; end-of-day upper bound",
            identity=_cninfo_identity(),
        ),
        _source(
            source_id=H1["id"],
            kind="official_issuer_filing",
            relative_path=H1["path"],
            location=H1["url"],
            published_at=H1["published_at"],
            available_at=H1["available_at"],
            availability_basis="CNINFO date-only publication; end-of-day upper bound",
            identity=_cninfo_identity(),
        ),
        _source(
            source_id=HKEX_DENOMINATOR["id"],
            kind="official_exchange_filing",
            relative_path=HKEX_DENOMINATOR["path"],
            location=HKEX_DENOMINATOR["url"],
            published_at=HKEX_DENOMINATOR["published_at"],
            available_at=HKEX_DENOMINATOR["available_at"],
            availability_basis="HKEX exact disclosure timestamp from retained window index",
            identity={
                "venue": "HKEX",
                "security_code": "00300",
                "issuer_name": "美的集團",
            },
        ),
        *[
            _source(
                source_id=item["id"],
                kind="official_issuer_filing",
                relative_path=item["path"],
                location=item["url"],
                published_at=item["published_at"],
                available_at=item["available_at"],
                availability_basis=(
                    "CNINFO date-only publication; timestamp is a date boundary, "
                    "not a strict intraday PIT observation"
                ),
                identity=_cninfo_identity(),
                retrieved_at=EVENT_ORIGINAL_RETRIEVED_AT,
            )
            for item in EVENT_DOCUMENTS
        ],
        {
            "id": QUOTE["id"],
            "kind": "quote_session",
            "location": QUOTE["path"],
            "local_path": QUOTE["path"],
            "sha256": QUOTE["sha256"],
            "published_at": "2026-10-16T17:00:31+08:00",
            "retrieved_at": "2026-10-16T17:00:31+08:00",
            "source_available_at": "2026-10-16T17:00:31+08:00",
            "availability_basis": "retained dual-source quote session fetch time",
            "parser_version": "quote-session-collection-v1",
        },
        {
            "id": "midea_event_scan_20261017",
            "kind": "research_artifact",
            "location": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            "local_path": event_scan_path.relative_to(ROOT).as_posix(),
            "sha256": event_scan_sha,
            "published_at": EVENT_SCAN_RETRIEVED_AT,
            "retrieved_at": EVENT_SCAN_RETRIEVED_AT,
            "source_available_at": EVENT_SCAN_RETRIEVED_AT,
            "availability_basis": (
                "bounded CNINFO snapshot captured before the research day closed; "
                "not a full-day completeness proof and strict contemporaneous PIT "
                "is not proven"
            ),
            "parser_version": "midea-draft-event-scan-v2",
        },
        {
            "id": memo_ref["id"],
            "kind": "research_artifact",
            "location": memo_relative,
            "local_path": memo_relative,
            "sha256": memo_ref["sha256"],
            "published_at": generated_at,
            "retrieved_at": generated_at,
            "source_available_at": generated_at,
            "availability_basis": "candidate scenario memo generated with this draft; not human approved",
            "parser_version": "midea-draft-assumption-memo-v2",
        },
    ]
    recorded_at = datetime.now(timezone.utc).isoformat()
    assumptions, bindings = _assumptions_and_bindings(sources, memo_ref)
    annual_ref = {"id": ANNUAL["id"], "sha256": next(s["sha256"] for s in sources if s["id"] == ANNUAL["id"])}
    h1_ref = {"id": H1["id"], "sha256": next(s["sha256"] for s in sources if s["id"] == H1["id"])}
    denominator_ref = {
        "id": HKEX_DENOMINATOR["id"],
        "sha256": next(s["sha256"] for s in sources if s["id"] == HKEX_DENOMINATOR["id"]),
    }
    quote_ref = {
        "kind": "quote_session",
        "symbol": SYMBOL,
        "ref_id": QUOTE["id"],
        "bundle_path": QUOTE["path"],
        "bundle_sha256": QUOTE["sha256"],
    }
    event_ref = {
        "id": "midea_event_scan_20261017",
        "symbol": SYMBOL,
        "path": event_scan_path.relative_to(ROOT).as_posix(),
        "sha256": event_scan_sha,
    }
    event_doc_refs = [item["id"] for item in EVENT_DOCUMENTS]
    fact_anchors = [
        {
            "field": "fy2025_parent_profit_cny",
            "source_id": ANNUAL["id"],
            "physical_page": 10,
            "source_value": "43945411000",
            "unit": "CNY",
            "scope": "consolidated_parent_profit",
            "period_end": "2025-12-31",
        },
        {
            "field": "fy2025_parent_equity_cny",
            "source_id": ANNUAL["id"],
            "physical_page": 10,
            "source_value": "223221305000",
            "unit": "CNY",
            "scope": "consolidated_parent_equity",
            "period_end": "2025-12-31",
        },
        {
            "field": "fy2025_weighted_roe",
            "source_id": ANNUAL["id"],
            "physical_page": 10,
            "source_value": "0.1970",
            "unit": "ratio",
            "scope": "weighted_average_parent_roe",
            "period_end": "2025-12-31",
        },
        {
            "field": "h1_2026_revenue_cny",
            "source_id": H1["id"],
            "physical_page": 7,
            "source_value": "260042490000",
            "unit": "CNY",
            "scope": "consolidated_revenue",
            "period_end": "2026-06-30",
        },
        {
            "field": "h1_2026_parent_profit_cny",
            "source_id": H1["id"],
            "physical_page": 7,
            "source_value": "26446037000",
            "unit": "CNY",
            "scope": "consolidated_parent_profit",
            "period_end": "2026-06-30",
        },
        {
            "field": "h1_2026_adjusted_parent_profit_cny",
            "source_id": H1["id"],
            "physical_page": 7,
            "source_value": "19595179000",
            "unit": "CNY",
            "scope": "consolidated_parent_profit_ex_nonrecurring",
            "period_end": "2026-06-30",
        },
        {
            "field": "h1_2026_adjusted_parent_profit_yoy",
            "source_id": H1["id"],
            "physical_page": 7,
            "source_value": "-0.2531",
            "unit": "ratio",
            "scope": "consolidated_parent_profit_ex_nonrecurring_yoy",
            "period_end": "2026-06-30",
        },
        {
            "field": "h1_2026_parent_equity_cny",
            "source_id": H1["id"],
            "physical_page": 7,
            "source_value": "212861055000",
            "unit": "CNY",
            "scope": "consolidated_parent_equity",
            "period_end": "2026-06-30",
        },
        {
            "field": "h1_2026_roe",
            "source_id": H1["id"],
            "physical_page": 7,
            "source_value": "0.1133",
            "unit": "ratio",
            "scope": "weighted_average_parent_roe",
            "period_end": "2026-06-30",
        },
    ]
    source_contract = {
        "schema_version": "source-bound-research-inputs-v2",
        # The cutoff is the actual package-finalization instant. It is never
        # moved ahead of retained evidence or backdated to manufacture PIT.
        "cutoff_at": recorded_at,
        "distribution_input_status": "NOT_ADMITTED",
        "strict_contemporaneous_pit": "NOT_PROVEN",
        "event_coverage_status": COVERAGE_INCOMPLETE,
        "source_catalog_sha256": source_catalog_sha256(sources),
        "fact_semantics_scope": "source_anchored_parent_profit_equity_and_share_denominator_not_full_financial_quality",
        "fact_anchors": fact_anchors,
        "scenario_memo": memo_ref,
    }
    package = {
        "schema_version": "m1-valuation-package-v2",
        "package_version": "20261017.2",
        "descriptor_version": "000333-draft-source-bound-v2",
        "symbol": SYMBOL,
        "name": NAME,
        "profile_id": "mature_manufacturing",
        "requested_model": "residual_income_or_equity_value",
        "run_id": RUN_ID,
        "point_in_time": {
            "report_period": "2026-06-30",
            "research_as_of": RESEARCH_DATE,
            "valuation_date": VALUATION_DATE,
            "available_at": recorded_at,
            "computed_at": recorded_at,
        },
        "dependencies": {
            "rule_version": "m1-valuation-rules-v1",
            "model_id": "residual_income_or_equity_value",
            "model_version": "residual-income-equity-shared-dated-v2",
            "parser_version": "midea-draft-case-input-v2",
            "scan_watermark": "midea-draft-evidence-scan-20261017-v2",
        },
        "source_contract": source_contract,
        "sources": sources,
        "research_case": {
            "symbol": SYMBOL,
            "name": NAME,
            "as_of": RESEARCH_DATE,
            "run_id": RUN_ID,
            "generated_at": generated_at,
            "research_version": RUN_ID,
            "industry": "家用电器-白色家电",
            "investment_path": "成熟制造复利 / 全球化与现金回报",
            "thesis": (
                "美的具备规模化制造、渠道效率、全球化品牌与现金流优势；"
                "2026H1扣非归母净利润同比下降25.31%，公司披露主要涉及汇兑损失与风险管理衍生工具收益的损益分类不对称，"
                "不能直接认定经营盈利同比下降同幅；本次草案只检验在较低ROE假设路径下"
                "是否存在条件性价值，不用历史高ROE外推。"
            ),
            "return_driver": "家电主业效率、全球化收入结构、ToB业务质量、现金转换与股东回报。",
            "mispricing_hypothesis": (
                "当前只检验价格与条件性内在价值区间的关系，不证明市场低估，"
                "也不把当前价格当作买入信号。"
            ),
            "financial_summary": {
                "period_end": "2026-06-30",
                "fy2025_parent_profit_cny": "43945411000",
                "fy2025_parent_equity_cny": "223221305000",
                "fy2025_weighted_roe": "0.1970",
                "h1_2026_revenue_cny": "260042490000",
                "h1_2026_parent_profit_cny": "26446037000",
                "h1_2026_adjusted_parent_profit_cny": "19595179000",
                "h1_2026_adjusted_parent_profit_yoy": "-0.2531",
                "h1_2026_parent_equity_cny": "212861055000",
                "h1_2026_roe": "0.1133",
                "ordinary_shares_20260630": "7464347335",
            },
            "positives": [
                {
                    "kind": "fact",
                    "text": "FY2025归母净利润439.45亿元、归母权益2,232.21亿元，加权ROE 19.70%。",
                    "evidence_refs": [ANNUAL["id"]],
                },
                {
                    "kind": "fact",
                    "text": "FY2025每10股派38.00元，披露基数7,522,863,645股。",
                    "evidence_refs": [ANNUAL["id"]],
                },
                {
                    "kind": "interpretation",
                    "text": "规模、渠道和全球化仍可能支持高于门槛的资本回报，但必须由未来盈利和现金转换验证。",
                    "evidence_refs": [ANNUAL["id"], H1["id"]],
                },
            ],
            "counter_evidence": [
                {
                    "kind": "fact",
                    "text": "2026H1扣非归母净利润195.95亿元，同比下降25.31%；公司披露主要涉及汇兑损失计入经常性损益、风险管理衍生工具收益计入非经常性损益的分类不对称，正常化盈利仍待核验。",
                    "evidence_refs": [H1["id"]],
                },
                {
                    "kind": "fact",
                    "text": "2026H1归母权益2,128.61亿元，加权平均ROE为11.33%，上年同期为11.29%，同比增加0.04个百分点；半年指标不能直接与全年ROE比较判断趋势。",
                    "evidence_refs": [H1["id"]],
                },
                {
                    "kind": "gap",
                    "text": "2026年10月14日三项公告及10月17日回购进展公告仍待逐条材料性复核，模型有效性只能保持UNKNOWN。",
                    "evidence_refs": event_doc_refs,
                },
            ],
            "thesis_breakers": [
                {
                    "kind": "hypothesis",
                    "text": "若未来两年ROE持续低于9%的候选权益门槛，剩余收益假设失效。",
                    "evidence_refs": [H1["id"]],
                },
                {
                    "kind": "hypothesis",
                    "text": "若利润下降伴随经营现金转换和资产负债表质量同步恶化，当前底部ROE路径仍需下调。",
                    "evidence_refs": [H1["id"]],
                },
                {
                    "kind": "hypothesis",
                    "text": "若股本注销、回购或分红导致普通股分母与可分配现金桥接发生变化，必须重算每股价值。",
                    "evidence_refs": [HKEX_DENOMINATOR["id"], *event_doc_refs],
                },
            ],
            "next_events": [
                {
                    "kind": "fact",
                    "text": "人工复核临时股东会决议、法律意见、注册资本减少及最新回购进展公告。",
                    "evidence_refs": event_doc_refs,
                },
                {
                    "kind": "gap",
                    "text": "下一期定期报告发布后复核利润、现金转换和ROE路径。",
                    "evidence_refs": [H1["id"]],
                },
            ],
            "evidence_status": "verified",
            "valuation_status": "conditional_research_only",
            "research_status": "DRAFT_NOT_APPROVED",
            "blockers": [
                "DRAFT_NOT_APPROVED",
                "EVENT_MATERIALITY_PENDING_HUMAN_REVIEW",
                "EVENT_COVERAGE_INCOMPLETE",
                "STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN",
            ],
            "evidence_refs": [
                annual_ref,
                h1_ref,
                denominator_ref,
                *[
                    {
                        "id": item["id"],
                        "sha256": next(s["sha256"] for s in sources if s["id"] == item["id"]),
                    }
                    for item in EVENT_DOCUMENTS
                ],
            ],
            "quote_date": VALUATION_DATE,
            "financial_period": "2026-06-30",
            "missing_date_reasons": {},
        },
        "facts": {
            "kind": "quality_compounder",
            "symbol": SYMBOL,
            "as_of": VALUATION_DATE,
            "verified": True,
            "confidence": "低",
            "evidence_refs": [annual_ref, h1_ref, denominator_ref],
            "blockers": [],
            "operating_inputs": {
                "start_book_equity": "212861055000",
                "ordinary_shares": "7464347335",
            },
            "valuation_timing": {
                "basis_at": "2026-06-30T23:59:59+08:00",
                "valuation_at": "2026-10-16T17:00:31+08:00",
                "evidence_refs": [annual_ref, h1_ref, denominator_ref],
            },
            "scenario_inputs": SCENARIOS,
        },
        "assumptions": assumptions,
        "assumption_bindings": bindings,
        "quote": quote_ref,
        "model_validity_input": {
            "model_id": "residual-income-equity-shared-dated-v2",
            "valid_from": VALUATION_DATE,
            "events": [],
            "event_scan_ref": event_ref,
            "event_scan_evidence_refs": [event_ref],
            "blockers": [
                "EVENT_MATERIALITY_PENDING_HUMAN_REVIEW",
                "EVENT_COVERAGE_INCOMPLETE",
                "STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN",
            ],
        },
        "blockers": [
            "DRAFT_NOT_APPROVED",
            "G3_HUMAN_APPROVAL_ABSENT",
            "EVENT_MATERIALITY_PENDING_HUMAN_REVIEW",
            "EVENT_COVERAGE_INCOMPLETE",
            "STRICT_CONTEMPORANEOUS_PIT_NOT_PROVEN",
            "POSITION_GUIDANCE_BLOCKED_PRIVATE_INPUT",
        ],
    }
    package_path = output / "package.json"
    package_sha = _json_write(package_path, package)
    descriptor = build_descriptor(package, root=ROOT)
    spec = build_research_run_spec(descriptor)
    receipt = {
        "schema_version": "midea-draft-package-build-receipt-v2",
        "action": "no_order",
        "status": "DRAFT_PACKAGE_VALIDATED",
        "symbol": SYMBOL,
        "run_id": RUN_ID,
        "generated_at": generated_at,
        "package": {"path": package_path.relative_to(ROOT).as_posix(), "sha256": package_sha},
        "event_scan": {"path": event_scan_path.relative_to(ROOT).as_posix(), "sha256": event_scan_sha},
        "assumption_memo": {"path": memo_path.relative_to(ROOT).as_posix(), "sha256": memo_sha},
        "quote": {"path": QUOTE["path"], "sha256": QUOTE["sha256"]},
        "descriptor_input_sha256": descriptor.input_sha256,
        "research_run_input_sha256": spec.input_descriptor_sha256,
        "scenario_binding_count": len(bindings),
        "requested_model": descriptor.requested_model,
        "formal_admission": False,
        "position_guidance": None,
        "strict_contemporaneous_pit": "NOT_PROVEN",
    }
    receipt_path = output / "package-build-receipt.json"
    receipt_sha = _json_write(receipt_path, receipt)
    return {
        "package_path": str(package_path),
        "package_sha256": package_sha,
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha,
        "descriptor_input_sha256": descriptor.input_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(build_package(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
