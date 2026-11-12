"""Historical standalone-parent cash conversion anchors for D2 research.

The CFO/profit difference includes non-cash adjustments, receivables, payables,
tax and other effects. It is neither an isolated working-capital figure nor a
forecast of accessible shareholder cash.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


VERSION = "parent-cash-conversion-anchor-v1"
_FAMILIES = (
    ("parent_net_profit", "cfo_cny", "gross_capex_cny"),
    ("parent_net_profit", "parent_cfo", "parent_capex"),
)
_SCOPES = {
    "parent_net_profit": "parent",
    "cfo_cny": "ISSUER_PARENT_STANDALONE",
    "gross_capex_cny": "ISSUER_PARENT_STANDALONE",
    "parent_cfo": "parent",
    "parent_capex": "parent",
}


def historical_parent_cash_conversion(context: dict) -> dict | None:
    """Return only complete, same-original, same-period parent observations."""
    by_period: dict[str, dict[str, list[dict]]] = {}
    for row in context.get("evidence", []):
        field = row.get("field")
        if field not in _SCOPES or row.get("unit") != "CNY":
            continue
        if row.get("scope") != _SCOPES[field]:
            continue
        period = row.get("period")
        if not isinstance(period, str) or not period:
            continue
        by_period.setdefault(period, {}).setdefault(field, []).append(row)
    periods = []
    for period, fields in sorted(by_period.items()):
        candidates = []
        for family in _FAMILIES:
            if any(len(fields.get(field, [])) != 1 for field in family):
                continue
            rows = [fields[field][0] for field in family]
            original_hash = rows[0].get("pdf_sha256")
            if (not isinstance(original_hash, str) or len(original_hash) != 64
                    or len({row.get("pdf_sha256") for row in rows}) != 1
                    or len({row.get("available_at") for row in rows}) != 1
                    or len({row.get("period_basis") for row in rows}) != 1
                    or any(not isinstance(row.get("source_id"), str)
                           or not isinstance(row.get("id"), str) or not row["id"]
                           for row in rows)):
                continue
            # Two parsers may use a CNINFO receipt ID and a raw-PDF ID for
            # the same original. Do not require equal labels, but never join
            # cash-flow and capex rows from different parser sources.
            if rows[1]["source_id"] != rows[2]["source_id"]:
                continue
            if (rows[0]["source_id"] != rows[1]["source_id"]
                    and rows[1]["source_id"] != "official:" + original_hash):
                continue
            try:
                amounts = tuple(Decimal(str(row["value"])) for row in rows)
            except (KeyError, InvalidOperation, TypeError):
                continue
            if any(not value.is_finite() for value in amounts) or amounts[2] < 0:
                continue
            candidates.append((rows, amounts))
        if not candidates or any(values != candidates[0][1] for _, values in candidates[1:]):
            continue
        rows, (profit, cfo, capex) = candidates[0]
        periods.append(dict(period=period, period_basis=rows[0]["period_basis"],
            source_id=rows[0]["source_id"], pdf_sha256=rows[0]["pdf_sha256"],
            available_at=rows[0]["available_at"], parent_profit_cny=str(profit),
            parent_cfo_cny=str(cfo), parent_gross_capex_cny=str(capex),
            cfo_less_profit_cny=str(cfo - profit),
            cfo_less_gross_capex_cny=str(cfo - capex),
            evidence_ids=[row["id"] for row in rows]))
    if not periods:
        return None
    return dict(schema_version=VERSION, action="no_order", periods=periods,
        limitation=("Historical standalone-parent arithmetic only. CFO minus profit is not "
                    "working-capital cash by itself; gross capex is not maintenance capex. "
                    "H1 is not an annual run rate. No future cash access, dividend capacity, "
                    "commitment schedule or valuation is inferred."))
