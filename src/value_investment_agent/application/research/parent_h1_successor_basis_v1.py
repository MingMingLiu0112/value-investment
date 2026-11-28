"""E1 bridge from a sealed annual task to an independently replayed H1 basis."""

from datetime import date, datetime
from pathlib import Path

from .parent_cash_task_receipt_v3 import replay_parent_cash_task_receipt
from .parent_h1_opening_cash_v1 import read_parent_h1_opening_cash


def prepare_parent_h1_successor(*, root: Path, predecessor_binding: dict,
                                period_end: str, now: datetime) -> dict:
    predecessor = replay_parent_cash_task_receipt(
        root=root, receipt_binding=predecessor_binding, now=now)
    prior_end = date.fromisoformat(predecessor["descriptor"]["point_in_time"]["valuation_date"])
    h1_end = date.fromisoformat(period_end)
    if ((prior_end.month, prior_end.day) != (12, 31)
            or h1_end != date(prior_end.year + 1, 6, 30)):
        raise ValueError("PARENT_H1_SUCCESSOR_REQUIRES_NEXT_FISCAL_HALF_YEAR")
    basis = read_parent_h1_opening_cash(
        root=root, spec_binding=predecessor["provenance"]["spec_binding"],
        period_end=period_end, now=now)
    if (basis["reconciliation"]["statement"]["symbol"] != predecessor["symbol"]
            or predecessor["formal_eligibility"] is not False
            or predecessor["main_range_adopted"] is not False):
        raise ValueError("PARENT_H1_SUCCESSOR_ISSUER_OR_BOUNDARY_MISMATCH")
    return dict(
        status="PARENT_H1_SUCCESSOR_BASIS_VERIFIED", symbol=predecessor["symbol"],
        predecessor_binding=dict(predecessor_binding),
        predecessor_input_descriptor_sha256=predecessor["input_descriptor_sha256"],
        predecessor_valuation_date=prior_end.isoformat(), period_end=period_end,
        opening_cash=basis, valuation_recomputed=False, condition_price=None,
        formal_eligibility=False, action="no_order",
    )
