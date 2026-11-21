"""Rebuild a historical H1 parent-cash opening balance from pinned filings."""

from datetime import datetime
from pathlib import Path

from .direct_owner_cash_research_v1 import _read
from .parent_direct_owner_cash_sources_v2 import read_parent_direct_owner_cash_sources_v2
from ...domain.valuation.parent_cash_policy import reconcile_parent_cash_statement
from ...domain.valuation.parent_direct_operating_cash import SCOPE

_FIELDS = {
    "opening_cash_cny": "opening_cash_and_equivalents_cny",
    "closing_cash_cny": "closing_cash_and_equivalents_cny",
    "cfo_cny": "cfo_cny",
    "cfi_cny": "cfi_cny",
    "cff_cny": "cff_cny",
    "fx_cny": "fx_cny",
    "reported_net_change_cny": "reported_net_change_cny",
}


def read_parent_h1_opening_cash(*, root: Path, spec_binding: dict,
                                period_end: str, now: datetime) -> dict:
    """Return the next period's historical anchor, leaving future flows unknown."""
    root = Path(root).resolve()
    spec = _read(root, spec_binding)
    if (spec.get("action") != "no_order" or spec.get("scope") != SCOPE
            or spec.get("currency") != "CNY"
            or spec.get("source_adapter_version") != "NUMBERED_CNINFO_V2"):
        raise ValueError("H1_OPENING_SOURCE_SPEC_UNSUPPORTED")
    facts = read_parent_direct_owner_cash_sources_v2(
        root=root, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
        sources=spec["owner_sources"], evaluated_at=now)
    matching = [row for row in facts["statements"] if row["period_end"] == period_end]
    if len(matching) != 1:
        raise ValueError("H1_OPENING_EXACT_PERIOD_REQUIRED")
    h1 = matching[0]
    if (h1["period_basis"] != "H1" or h1["scope"] != SCOPE
            or h1["currency"] != "CNY" or not h1["checks"]["cash_statement_reconciled"]):
        raise ValueError("H1_OPENING_RECONCILED_PARENT_STATEMENT_REQUIRED")
    fields = {key: h1["cash_flow"][field] for key, field in _FIELDS.items()}
    reconciliation = reconcile_parent_cash_statement(statement=dict(
        symbol=h1["symbol"], period_start=h1["period_start"], period_end=period_end,
        scope="issuer_parent_standalone", unit="CNY", currency="CNY",
        **{key: fact["current"] for key, fact in fields.items()},
    ))
    return dict(
        status="HISTORICAL_H1_OPENING_CASH_VERIFIED", period_end=period_end,
        source_spec=dict(spec_binding), reconciliation=reconciliation,
        field_sources={key: fact["source_refs"] for key, fact in fields.items()},
        forward_opening_cash_cny=reconciliation["statement"]["closing_cash_cny"],
        historical_flows_already_consumed=True, comparison_date_cash_cny=None,
        distribution_capacity_cny=None, condition_price=None, action="no_order",
    )
