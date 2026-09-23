from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib

import pytest

from value_investment_agent.m1_application_workbook import (
    ACTION_NO_ORDER,
    APPLICATION_SCHEMA,
    BLOCKERS_SHEET,
    DIVIDEND_SHEET,
    OVERVIEW_SHEET,
    REVERSE_SHEET,
    SAMPLE_SHEET,
    VALUATION_SHEET,
    build_application_workbook,
    write_application_workbook,
)
from value_investment_agent.research_read_model import (
    DOSSIER_SCHEMA_VERSION,
    ResearchDossierCollection,
    not_started_dossier,
)


GENERATED_AT = datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc)


def _collection():
    return ResearchDossierCollection(
        schema_version=DOSSIER_SCHEMA_VERSION,
        generated_at=GENERATED_AT,
        action=ACTION_NO_ORDER,
        dossiers=tuple(
            not_started_dossier(
                symbol=symbol,
                name=name,
                as_of=date(2026, 9, 22),
                run_id=f"{symbol}-dossier",
                generated_at=GENERATED_AT,
                research_version="fixture-v1",
                profile_id=profile,
                primary_model=model,
                known_blockers=["fixture research blocker"],
            )
            for symbol, name, profile, model in (
                ("600887", "Fixture Dairy", "quality_compounder", "residual_income_or_equity_value"),
                ("600741", "Fixture Supplier", "mature_manufacturing", "fcff"),
                ("000651", "Fixture Appliance", "mature_manufacturing", "fcff"),
            )
        ),
        input_failures=(),
    )


def _result(symbol, *, quote):
    return {
        "package_id": f"{symbol}-package",
        "symbol": symbol,
        "descriptor_error": None,
        "input_sha256": "a" * 64,
        "run_status": "COMPLETED_WITH_BLOCKERS",
        "blockers": ["formal G3 human valuation approval not present"],
        "action": None,
        "distribution": {
            "symbol": symbol,
            "history": {"status": "PARTIAL"},
            "capacity": {
                "status": "PARTIAL",
                "capital_allocation_context": {
                    "policy_2025_2027": "fixture policy",
                },
            },
            "sustainability": {"status": "LOW", "confidence": "LOW"},
            "blockers": ["fixture dividend blocker"],
        },
        "reverse_valuations": [
            {
                "symbol": symbol,
                "model_type": "fixture-model",
                "driver": "terminal_roe",
                "target_price": quote,
                "lower_bound": "0.09",
                "upper_bound": "0.17",
                "status": "above_registered_envelope",
                "solution": None,
                "blockers": [],
                "action": ACTION_NO_ORDER,
            }
        ],
        "valuation": {
            "symbol": symbol,
            "model_type": "fixture-model",
            "status": "conditional_research_only",
            "confidence": "LOW",
            "bear_value": "8.00",
            "base_value": "12.00",
            "bull_value": "16.00",
            "assumptions": {"scope": "fixture arithmetic"},
            "blockers": [],
        },
        "price_bridge": {
            "symbol": symbol,
            "current_price": quote,
            "margin_to_bear": "-0.20",
            "margin_to_base": "-0.50",
            "bridge_status": "READY" if quote else "PENDING_EXTERNAL_DATA",
            "blockers": [],
        },
        "gate": {
            "results": {
                "G0_证据门": True,
                "G1_财务门": True,
                "G2_商业论点门": True,
                "G3_估值门": False,
            },
            "blockers": ["G3_估值门"],
        },
        "model_validity": {"status": "VALID"},
        "current_data_status": {
            "status": "READY" if quote else "PENDING_EXTERNAL_DATA",
            "waiting_for": [] if quote else ["已验证收盘行情"],
            "blockers": [] if quote else ["等待已验证收盘行情"],
        },
        "research_conclusion": "估值未就绪",
    }


def _application():
    return {
        "schema_version": APPLICATION_SCHEMA,
        "generated_at": GENERATED_AT.isoformat(),
        "action": ACTION_NO_ORDER,
        "package_count": 3,
        "run_status_counts": {"COMPLETED_WITH_BLOCKERS": 3},
        "results": [
            _result("600887", quote="26.77"),
            _result("600741", quote="14.92"),
            _result("000651", quote=None),
        ],
    }


def _all_text(workbook) -> str:
    return "\n".join(
        str(cell.value)
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_application_workbook_keeps_no_order_and_displays_all_domains():
    workbook = build_application_workbook(_application(), _collection())

    assert workbook.sheetnames[:6] == [
        OVERVIEW_SHEET,
        VALUATION_SHEET,
        DIVIDEND_SHEET,
        REVERSE_SHEET,
        BLOCKERS_SHEET,
        SAMPLE_SHEET,
    ]
    text = _all_text(workbook)
    assert "action=no_order" in text
    assert "fixture policy" in text
    assert "above_registered_envelope" not in text
    assert "高于登记包络" in text
    assert "formal G3 human valuation approval not present" in text
    assert "买入" not in text
    assert "卖出" not in text
    assert "目标仓位" not in text


def test_dividend_sheet_keeps_ac5_layers_visible():
    application = _application()
    yili = next(item for item in application["results"] if item["symbol"] == "600887")
    huayu = next(item for item in application["results"] if item["symbol"] == "600741")
    yili["distribution"].update(
        {
            "history": {
                "status": "PARTIAL",
                "records": [
                    {
                        "fiscal_period": "FY2024-final",
                        "dividend_type": "ordinary",
                        "status": "paid",
                        "dividend_per_share": "1.22",
                        "announcement_date": "2025-04-30",
                        "approval_date": "2025-05-20",
                        "ex_date": "2025-06-06",
                        "payment_date": "2025-06-06",
                        "known_at": "2026-09-22",
                        "blockers": [],
                    },
                    {
                        "fiscal_period": "FY2025-final",
                        "dividend_type": "ordinary",
                        "status": "proposed",
                        "dividend_per_share": "0.90",
                        "announcement_date": "2026-04-30",
                        "blockers": ["pending shareholder approval"],
                    },
                ],
            },
            "capacity": {
                "status": "PARTIAL",
                "capital_allocation_context": {
                    "fact_policy_forecast_separation": "paid facts; policy; no forecast",
                    "special_dividend_observation": "none identified",
                },
            },
            "sustainability": {
                "status": "LOW",
                "confidence": "LOW",
                "coverage_context": "retained statutory lifecycle evidence",
            },
            "yield_snapshots": [
                {
                    "basis_type": "trailing_paid",
                    "yield_type": "current",
                    "dividend_basis_period": "2025-09-22/2026-09-22",
                    "dividend_per_share": "0.48",
                    "current_price": "26.77",
                    "dividend_yield": "0.01793051923795293239",
                    "status": "READY",
                    "blockers": [],
                },
                {
                    "basis_type": "declared",
                    "yield_type": "current",
                    "dividend_per_share": "0.90",
                    "current_price": "26.77",
                    "dividend_yield": "0.03361972357116174823",
                    "status": "READY",
                    "blockers": [],
                },
                {
                    "basis_type": "normalized_scenario",
                    "yield_type": "normalized",
                    "status": "NOT_READY",
                    "blockers": ["normalized dividend basis is not assessed"],
                },
            ],
        }
    )
    huayu["distribution"]["yield_snapshots"] = [
        {
            "basis_type": "trailing_paid",
            "yield_type": "current",
            "status": "NOT_READY",
            "blockers": ["no paid ex-date in trailing window"],
        },
        {
            "basis_type": "declared",
            "yield_type": "current",
            "dividend_per_share": "1.00",
            "current_price": "14.92",
            "dividend_yield": "0.06702412868632707775",
            "status": "READY",
            "blockers": [],
        },
        {
            "basis_type": "normalized_scenario",
            "yield_type": "normalized",
            "status": "NOT_READY",
            "blockers": ["normalized dividend basis is not assessed"],
        },
    ]

    workbook = build_application_workbook(application, _collection())
    sheet = workbook[DIVIDEND_SHEET]
    text = "\n".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert sheet["E5"].value == "低"
    assert "法定股利生命周期台账" in text
    assert "当前价股息收益率快照" in text
    assert "普通股利" in text
    assert "已支付" in text
    assert "已提议" in text
    assert "滚动已支付" in text
    assert "已宣告" in text
    assert "正常化情景" in text
    assert "特别股利" in text
    assert "事实/政策/预测" in text
    assert "1.79%" in text
    assert "3.36%" in text
    assert "6.70%" in text
    assert "normalized dividend basis is not assessed" in text


def test_application_workbook_writer_is_hash_pinned_and_no_overwrite(tmp_path):
    collection = _collection()
    application = _application()
    result = write_application_workbook(
        root=tmp_path,
        application_payload=application,
        collection=collection,
        output=tmp_path / "candidate.xlsx",
    )

    target = tmp_path / result["workbook_path"]
    assert target.exists()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == result["workbook_sha256"]
    assert result["action"] == ACTION_NO_ORDER

    with pytest.raises(ValueError, match="already exists"):
        write_application_workbook(
            root=tmp_path,
            application_payload=application,
            collection=collection,
            output=tmp_path / "candidate.xlsx",
        )
