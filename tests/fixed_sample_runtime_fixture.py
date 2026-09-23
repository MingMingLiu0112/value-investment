"""Self-contained frozen runtime fixture shared by C3 importer and replay tests.

The files are written into a temporary repository root. They intentionally use
the tracked fixed-sample manifest so the offline CI path can exercise the same
admission policies without relying on the ignored ``runtime/`` directory.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

from value_investment_agent.distribution import (
    CAPACITY_PARTIAL,
    DIVIDEND_ORDINARY,
    DIVIDEND_PAID,
    HISTORY_PARTIAL,
    SUSTAINABILITY_UNKNOWN,
    YIELD_CURRENT,
    YIELD_NORMALIZED,
    YIELD_NORMALIZED_SCENARIO,
    YIELD_NOT_READY,
    YIELD_TRAILING_PAID,
    DistributionCapacity,
    DividendHistory,
    DividendRecord,
    DividendResearchResult,
    DividendSustainabilityAssessment,
    DividendYieldSnapshot,
)
from value_investment_agent.research_e2e_replay import (
    MOUTAI_CURRENT_MODEL_POINTER,
)
from value_investment_agent.research_runtime_import import (
    RESEARCH_POINTER,
    REVIEW_POINTER,
    VALUATION_POINTERS,
)


REF = {"id": "e-1", "sha256": "a" * 64}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 9, 21)


def _write_pinned(root: Path, pointer_name: str, payload: dict) -> None:
    pointer = root / pointer_name
    pointer.parent.mkdir(parents=True, exist_ok=True)
    output = pointer.parent / f"{pointer.stem}-evidence" / "evidence.json"
    output.parent.mkdir(parents=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    pointer.write_text(
        json.dumps(
            {
                "path": output.parent.relative_to(root).as_posix(),
                "sha256": digest,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _case(symbol: str, name: str, as_of: str = "2026-09-21") -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "as_of": as_of,
        "run_id": "fixture-run",
        "generated_at": "2026-09-21T12:00:00+00:00",
        "research_version": "v1",
        "industry": "test",
        "investment_path": "test",
        "thesis": "thesis",
        "return_driver": "driver",
        "mispricing_hypothesis": "mispricing",
        "financial_summary": {},
        "positives": [
            {"kind": "fact", "text": "positive", "evidence_refs": ["e-1"]}
        ],
        "counter_evidence": [
            {"kind": "fact", "text": "counter", "evidence_refs": ["e-1"]}
        ],
        "thesis_breakers": [
            {"kind": "hypothesis", "text": "breaker", "evidence_refs": ["e-1"]}
        ],
        "next_events": [{"kind": "gap", "text": "next"}],
        "evidence_status": "verified",
        "valuation_status": "not_ready",
        "research_status": "financial_scope_approved",
        "blockers": ["g3"],
        "evidence_refs": [REF],
        "quote_date": None,
        "financial_period": None,
        "missing_date_reasons": {
            "quote_date": "not available",
            "financial_period": "not available",
        },
    }


def _gate() -> dict:
    return {
        "results": {
            "G0_证据门": True,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": False,
        },
        "blockers": ["G3_估值门"],
        "conclusion": "估值未就绪",
    }


def _result(
    symbol: str,
    model_type: str,
    valuation_date: str,
    *,
    moutai: bool = False,
) -> dict:
    values = (
        {
            "bear_value": "100",
            "base_value": "120",
            "bull_value": "140",
        }
        if moutai
        else {
            "bear_value": None,
            "base_value": None,
            "bull_value": None,
        }
    )
    return {
        "symbol": symbol,
        "model_type": model_type,
        "valuation_date": valuation_date,
        **values,
        "confidence": "低",
        "assumptions": {},
        "sensitivities": [],
        "evidence_refs": [REF],
        "blockers": [],
        "status": "conditional_research_only" if moutai else "not_ready",
        "model_version": f"{symbol}-v1",
    }


def _valuation_payload(
    symbol: str,
    model_type: str,
    valuation_date: str,
    *,
    moutai: bool = False,
) -> dict:
    result = _result(
        symbol,
        model_type,
        valuation_date,
        moutai=moutai,
    )
    bridge = {
        "symbol": symbol,
        "valuation_date": valuation_date,
        "quote_date": valuation_date if moutai else None,
        "current_price": "100" if moutai else None,
        "margin_to_bear": None,
        "margin_to_base": None,
        "model_validity_status": "VALID" if moutai else "UNKNOWN",
        "quote_status": "verified_close" if moutai else "PENDING_EXTERNAL_DATA",
        "bridge_status": "PENDING_EXTERNAL_DATA",
        "evidence_refs": [REF],
        "quote_evidence_refs": [],
        "blockers": [],
        "schema_version": "c0-v1",
        "model_id": f"{symbol}-v1" if moutai else None,
        "model_version": f"{symbol}-v1",
        "model_as_of": valuation_date,
        "quote_symbol": symbol if moutai else None,
        "valuation_bear_value": "100" if moutai else None,
        "valuation_base_value": "120" if moutai else None,
    }
    payload = {
        "result": result,
        "price_bridge": bridge,
    }
    if moutai:
        payload["model_validity"] = {
            "model_id": REF["sha256"],
            "symbol": symbol,
            "model_as_of": valuation_date,
            "valid_from": valuation_date,
            "last_material_event_check": valuation_date,
            "financial_statement_changed": False,
            "capital_structure_changed": False,
            "material_event_found": False,
            "status": "VALID",
            "blockers": [],
            "evidence_refs": [REF],
        }
    return payload


def _yield_snapshot(symbol: str, yield_type: str) -> DividendYieldSnapshot:
    return DividendYieldSnapshot(
        symbol=symbol,
        basis_type=(
            YIELD_TRAILING_PAID
            if yield_type == YIELD_CURRENT
            else YIELD_NORMALIZED_SCENARIO
        ),
        dividend_basis_period="not available",
        dividend_per_share=None,
        dividend_known_at=None,
        quote_date=None,
        current_price=None,
        currency="CNY",
        share_basis="ordinary shares",
        dividend_yield=None,
        yield_type=yield_type,
        evidence_refs=[REF],
        status=YIELD_NOT_READY,
        blockers=["not_ready"],
    )


def _cash_return(
    symbol: str,
    profile_id: str,
    *,
    yield_types: tuple[str, ...] = (),
    as_of: date = AS_OF,
) -> dict:
    record_year = as_of.year - 1
    record = DividendRecord(
        symbol=symbol,
        fiscal_period=f"FY{record_year}",
        dividend_type=DIVIDEND_ORDINARY,
        status=DIVIDEND_PAID,
        dividend_per_share=Decimal("1"),
        currency="CNY",
        announcement_date=date(record_year, 3, 1),
        approval_date=date(record_year, 4, 1),
        ex_date=date(record_year, 5, 1),
        payment_date=date(record_year, 6, 1),
        known_at=date(record_year, 6, 1),
        share_basis="ordinary shares",
        evidence_refs=[REF],
    )
    history = DividendHistory(
        symbol=symbol,
        records=(record,),
        as_of=as_of,
        evidence_refs=[REF],
        status=HISTORY_PARTIAL,
        blockers=["history_partial"],
    )
    capacity = DistributionCapacity(
        symbol=symbol,
        profile_id=profile_id,
        as_of=as_of,
        evidence_refs=[REF],
        status=CAPACITY_PARTIAL,
        blockers=["capacity_partial"],
    )
    sustainability = DividendSustainabilityAssessment(
        symbol=symbol,
        profile_id=profile_id,
        as_of=as_of,
        status=SUSTAINABILITY_UNKNOWN,
        coverage_context="not assessed",
        capital_requirements="not assessed",
        balance_sheet_pressure="not assessed",
        cycle_risk="not assessed",
        growth_source="not assessed",
        breakers=(),
        confidence="UNKNOWN",
        reasons=(),
        blockers=["sustainability_unknown"],
        evidence_refs=[REF],
    )
    return DividendResearchResult(
        symbol=symbol,
        profile_id=profile_id,
        history=history,
        capacity=capacity,
        sustainability=sustainability,
        yield_snapshots=tuple(
            _yield_snapshot(symbol, yield_type) for yield_type in yield_types
        ),
        as_of=as_of,
    ).as_policy()


def _moutai_model_payload() -> dict:
    scenarios = []
    for name, cost_of_equity, roe, terminal_roe in (
        ("bear", "0.12", "0.10", "0.08"),
        ("base", "0.10", "0.10", "0.10"),
        ("bull", "0.08", "0.12", "0.12"),
    ):
        scenarios.append(
            {
                "scenario": name,
                "basis_origin_calculation": {
                    "cost_of_equity_cny_nominal": cost_of_equity,
                    "forecast_years": [
                        {
                            "year": 1,
                            "roe_assumption": roe,
                            "retention_assumption": "0.25",
                        }
                    ],
                    "terminal_roe": terminal_roe,
                },
            }
        )
    return {
        "symbol": "600519",
        "facts": {
            "parent_equity_cny": "1000",
            "issued_shares": "100",
        },
        "model_policy": {
            "forecast_years": 1,
            "terminal_growth": "0.02",
        },
        "results": scenarios,
    }


def write_fixed_sample_runtime_fixture(root: Path) -> None:
    """Write all frozen pointers and copy the tracked fixed-sample manifest."""
    profiles = {
        "600519": (
            "quality_compounder",
            "residual_income_or_equity_value",
            "2026-09-21",
            True,
        ),
        "000333": (
            "mature_manufacturing",
            "FCFF",
            "2025-12-31",
            False,
        ),
        "601088": (
            "cyclical_cash_return",
            "cyclical_normalized",
            "2025-12-31",
            False,
        ),
    }
    research_records = [
        {
            "case": _case(symbol, name, as_of=valuation_date),
            "gate": _gate(),
        }
        for symbol, name in (
            ("600519", "Moutai"),
            ("000333", "Midea"),
            ("601088", "Shenhua"),
        )
        for _, _, valuation_date, _ in (profiles[symbol],)
    ]
    _write_pinned(
        root,
        RESEARCH_POINTER,
        {
            "version": "excel-mvp-research-cases-v1",
            "generated_at": "2026-09-21T12:00:00+00:00",
            "records": research_records,
            "formal_trade_instructions": False,
        },
    )
    for symbol, (profile_id, model_type, valuation_date, moutai) in profiles.items():
        _write_pinned(
            root,
            VALUATION_POINTERS[symbol],
            _valuation_payload(
                symbol,
                model_type,
                valuation_date,
                moutai=moutai,
            ),
        )
    _write_pinned(
        root,
        MOUTAI_CURRENT_MODEL_POINTER,
        _moutai_model_payload(),
    )

    yield_types = {
        "600519": (YIELD_CURRENT,),
        "000333": (),
        "601088": (YIELD_CURRENT, YIELD_NORMALIZED),
    }
    companies = []
    for symbol, (profile_id, _, _, _) in profiles.items():
        decision = (
            "CONTINUE_CONDITIONAL_MODEL"
            if symbol == "600519"
            else "RESOLVE_MODEL_INPUTS"
            if symbol == "000333"
            else "PAUSE_PRODUCTION_VALUATION"
        )
        companies.append(
            {
                "symbol": symbol,
                "profile_id": profile_id,
                "engineering_contract_reusable": True,
                "research_sample_status": "ADMITTED_FOR_RESEARCH",
                "admission_evidence": ["case", "route"],
                "production_valuation_status": "NOT_AVAILABLE",
                "bounded_value_judgment": (
                    "CONDITIONAL" if symbol == "600519" else "NOT_AVAILABLE"
                ),
                "cash_return_status": "PARTIAL",
                "cash_return_explanation": "partial distribution research",
                "decision": decision,
                "decision_reason": "keep research only",
                "required_evidence": ["model inputs"],
                "blockers": ["valuation_not_ready"],
                "evidence_refs": [REF],
                "human_confirmation_required": True,
                "action": "no_order",
                "cash_return_research": _cash_return(
                    symbol,
                    profile_id,
                    yield_types=yield_types[symbol],
                    as_of=date.fromisoformat(profiles[symbol][2]),
                ),
            }
        )
    _write_pinned(
        root,
        REVIEW_POINTER,
        {
            "version": "fixed-sample-admission-review-v1",
            "generated_at": "2026-09-21T12:00:00+00:00",
            "input_refs": [],
            "protocol_version": "fixed-sample-admission-v1",
            "rule_version": "fixed-sample-admission-v1",
            "as_of": "2026-09-21",
            "engineering_orchestration_status": "REUSABLE",
            "production_valuation_available": False,
            "research_sample_members": ["600519", "000333", "601088"],
            "companies": companies,
            "blockers": ["valuation_not_ready"],
            "evidence_refs": [REF],
            "human_confirmation_required": True,
            "action": "no_order",
            "interpretation": "research only",
        },
    )
    manifest_root = root / "config"
    manifest_root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        PROJECT_ROOT / "config" / "fixed-sample-manifest.json",
        manifest_root / "fixed-sample-manifest.json",
    )
