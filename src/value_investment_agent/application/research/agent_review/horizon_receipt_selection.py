"""Prepare a D2 source selection from two archived official report receipts."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from . import operating_horizon_sources_v1 as horizon

REQUIRED_PERIODS = ("2025-12-31", "2026-06-30")


def prepare_receipt_selection(*, root: Path, symbol: str, issuer_name: str,
                              receipts_by_period: dict, as_of: datetime) -> dict:
    """Replay the supported layout before handing a candidate to the source registry.

    The proposal does not install a registry entry or qualify the cash policy.
    A filing using another layout needs a supported, separately verified parser.
    """
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("HORIZON_SELECTION_REQUIRES_AWARE_CUTOFF")
    if set(receipts_by_period) != set(REQUIRED_PERIODS):
        raise ValueError("HORIZON_RECEIPT_BASE_PERIODS_REQUIRED")
    selection = horizon._selection({
        "issuer_name": issuer_name,
        "parent_cash_observation_receipts": [
            {"period": period, "receipt_binding": deepcopy(receipts_by_period[period])}
            for period in REQUIRED_PERIODS
        ],
        "parent_cash_layout": "LEGACY_BLANK_SAFE_V3",
        "excerpts": [],
    })
    base = horizon._receipt_operating_base(root, symbol, selection, as_of)
    evidence, _, gaps = horizon._supplement(root, symbol, selection, as_of)
    if not evidence:
        raise ValueError("HORIZON_SELECTION_HAS_NO_VERIFIED_EVIDENCE")
    return dict(selection=selection, base_source_binding=base["source_binding"],
                evidence_ids=[row["id"] for row in evidence], statement_basis_gaps=gaps,
                status="SOURCE_REPLAYED_SELECTION_PROPOSAL", formal_eligibility=False,
                action="no_order")


def prepare_receipt_selection_batch(*, root: Path, queue_rows: list, receipts: dict,
                                    budget: int, as_of: datetime) -> dict:
    """Replay retained receipt pairs in queue order within a bounded local budget."""
    if type(budget) is not int or not 1 <= budget <= 30:
        raise ValueError("HORIZON_SELECTION_BATCH_BUDGET_INVALID")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("HORIZON_SELECTION_REQUIRES_AWARE_CUTOFF")
    rows = []
    seen = set()
    for item in queue_rows:
        symbol = item["symbol"]
        if symbol in seen:
            raise ValueError("HORIZON_SELECTION_BATCH_DUPLICATE_SYMBOL")
        seen.add(symbol)
        if len(rows) < budget:
            pins = receipts.get(symbol)
            if pins is None:
                rows.append(dict(symbol=symbol, status="OFFICIAL_RECEIPT_PAIR_REQUIRED"))
                continue
            try:
                proposal = prepare_receipt_selection(root=root, symbol=symbol,
                    issuer_name=pins["issuer_name"], receipts_by_period=pins["receipts_by_period"],
                    as_of=as_of)
                rows.append(dict(symbol=symbol, **proposal))
            except (ValueError, OSError, KeyError, TypeError) as error:
                rows.append(dict(symbol=symbol, status="SOURCE_REPLAY_REJECTED",
                                 reason=str(error)))
    return dict(as_of=as_of.isoformat(), budget=budget, queue_count=len(seen), items=rows,
                action="no_order", formal_eligibility=False)
