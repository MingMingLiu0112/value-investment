from datetime import datetime, timezone
from decimal import Decimal

from value_investment_agent.quality import evaluate
from value_investment_agent.valuation import build_reference_records


def point(field_name: str, value: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "symbol": "600519",
        "field_name": field_name,
        "value": Decimal(value),
        "period_label": "2026-06-30",
        "created_at": now,
        "fetched_at": now,
        "validation_status": "pending",
        "source_id": "source-1",
    }


def test_pe_pb_reference_uses_true_ttm_eps_and_bvps() -> None:
    records = build_reference_records([point("eps_ttm", "40"), point("bvps", "200")], ["600519"])
    values = {record.field_name: record.value for record in records}

    assert values["model_pe_fair_value"] == Decimal("720.00")
    assert values["model_pb_fair_value"] == Decimal("800.00")
    assert values["model_fair_value"] == Decimal("760.00")


def test_model_reference_never_creates_a_trade_signal() -> None:
    now = datetime.now(timezone.utc)
    result = evaluate(
        "600519",
        [
            {**point("current_price", "500"), "created_at": now, "fetched_at": now},
            {**point("model_fair_value", "760"), "created_at": now},
        ],
        30,
        Decimal("0.03"),
    )

    assert result.status == "模型估值待复核"
    assert result.signal == "等待复核"
    assert result.target_weight == Decimal("0")
