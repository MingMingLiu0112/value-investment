"""Source-bound parent financing bridge; a residual is not a debt fact.

This compares identified balance-sheet rows with reported gross borrowing
cash flows. It deliberately cannot infer a maturity schedule, outstanding
principal, or a refinancing facility from the difference.
"""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from .parent_direct_cash_research import _bound, _unique
from .parent_direct_owner_cash_sources import _read_statement


BALANCE_FIELDS = (
    "short_term_borrowings_cny", "current_noncurrent_liabilities_cny",
    "long_term_borrowings_cny", "lease_liabilities_cny",
)
FLOW_FIELDS = ("borrowings_received_cny", "debt_repaid_cny")
SCOPE = "ISSUER_PARENT_STANDALONE"


def _fact(statement, section, field):
    fact = statement[section][field]
    refs = fact["source_refs"]
    if (fact["classification"] != "FACT" or fact["scope"] != SCOPE
            or fact["currency"] != "CNY"
            or refs["current_period"] != statement["period_end"]
            or refs["field"] != field
            or not refs.get("path") or not refs.get("sha256")):
        raise ValueError("PARENT_FINANCING_FACT_SCOPE_OR_SOURCE_CHANGED:" + field)
    value = Decimal(fact["current"])
    if not value.is_finite() or value < 0:
        raise ValueError("PARENT_FINANCING_INVALID_FACT:" + field)
    return value, refs


def reconcile_parent_financing(fy, followup):
    """Return the explicit residual, not an invented financing classification."""
    if (fy["symbol"] != followup["symbol"] or fy["issuer_name"] != followup["issuer_name"]
            or fy["scope"] != SCOPE or followup["scope"] != SCOPE
            or fy["period_end"][-6:] != "-12-31"
            or followup["period_end"][-6:] != "-06-30"
            or date.fromisoformat(followup["period_end"]).year
                != date.fromisoformat(fy["period_end"]).year + 1
            or followup["opening_balance_as_of"] != fy["period_end"]):
        raise ValueError("PARENT_FINANCING_PERIOD_OR_ISSUER_MISMATCH")
    statements = (fy, followup)
    missing = {row["period_end"]: [field for field in BALANCE_FIELDS if field not in row["balance_sheet"]]
               for row in statements}
    comparable = [field for field in BALANCE_FIELDS
                  if all(field in row["balance_sheet"] for row in statements)]
    refs = []
    totals = []
    for row in statements:
        values = []
        for field in BALANCE_FIELDS:
            if field in missing[row["period_end"]]:
                continue
            value, source = _fact(row, "balance_sheet", field)
            if field in comparable:
                values.append(value)
            refs.append(source)
        totals.append(sum(values, Decimal(0)) if comparable else None)
    received, received_ref = _fact(followup, "cash_flow", FLOW_FIELDS[0])
    repaid, repaid_ref = _fact(followup, "cash_flow", FLOW_FIELDS[1])
    refs.extend((received_ref, repaid_ref))
    net_borrowing = received - repaid
    complete_lines = len(comparable) == len(BALANCE_FIELDS)
    balance_change = totals[1] - totals[0] if comparable else None
    difference = balance_change - net_borrowing if complete_lines else None
    if not complete_lines:
        status = "PARTIAL_MISSING_COMPARABLE_BALANCE_LINES"
    elif difference:
        status = "PARTIAL_SCOPE_NOT_BALANCED"
    else:
        status = "IDENTIFIED_LINES_MATCH_REPORTED_NET_CASH_NOT_COMPLETE_SCOPE"
    return dict(schema_version="parent-financing-bridge-v1", symbol=fy["symbol"],
        period_start=fy["period_end"], period_end=followup["period_end"],
        scope=SCOPE, currency="CNY", action="no_order",
        opening_identified_balance_cny=str(totals[0]) if comparable else None,
        closing_identified_balance_cny=str(totals[1]) if comparable else None,
        identified_balance_change_cny=str(balance_change) if comparable else None,
        comparable_balance_fields=comparable, missing_balance_fields_by_period=missing,
        reported_net_borrowing_cash_cny=str(net_borrowing),
        unallocated_reconciliation_difference_cny=str(difference) if complete_lines else None,
        reconciliation_status=status,
        complete_debt_scope_verified=False, maturity_schedule_verified=False,
        actual_refinancing_capacity_verified=False, source_refs=refs)


def read_registered_parent_financing_bridge(*, root, fy_statement, now):
    """Use the existing horizon registry and pinned official acquisition receipt."""
    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("PARENT_FINANCING_AWARE_CLOCK_REQUIRED")
    registry_path = root / "config/current-operating-horizon-sources-v1.json"
    if not registry_path.exists():
        return None
    registry = json.loads(registry_path.read_bytes(), object_pairs_hook=_unique)
    if registry.get("schema_version") != "operating-horizon-sources-v1" or registry.get("action") != "no_order":
        raise ValueError("PARENT_FINANCING_HORIZON_REGISTRY_INVALID")
    case = registry.get("cases", {}).get(fy_statement["symbol"])
    if case is None:
        return None
    if case.get("issuer_name") != fy_statement["issuer_name"]:
        raise ValueError("PARENT_FINANCING_REGISTRY_ISSUER_MISMATCH")
    period = f"{int(fy_statement['period_end'][:4])+1}-06-30"
    matches = [row for row in case["parent_cash_observation_receipts"] if row.get("period") == period]
    if len(matches) != 1:
        return None
    _, raw = _bound(root, matches[0]["receipt_binding"])
    receipt = json.loads(raw, object_pairs_hook=_unique)
    source = receipt.get("source")
    if (receipt.get("schema_version") != "official-report-acquisition-v1"
            or receipt.get("status") != "ORIGINAL_ACQUIRED_NOT_FACT_ADMITTED"
            or not isinstance(source, dict)
            or source.get("symbol") != fy_statement["symbol"]
            or source.get("period") != period):
        raise ValueError("PARENT_FINANCING_FOLLOWUP_RECEIPT_INVALID")
    followup = _read_statement(root, fy_statement["symbol"], fy_statement["issuer_name"],
        dict(path=source["path"], sha256=source["sha256"], period_end=period,
             available_at=source["available_at"]), now)
    bridge = reconcile_parent_financing(fy_statement, followup)
    bridge["followup_receipt_binding"] = matches[0]["receipt_binding"]
    return bridge


def read_numbered_financing_evidence(*, root, symbol, financial_basis, now):
    """Read same-basis historical evidence for the first-input review page."""
    from .agent_review.operating_horizon_sources_v1 import _selection
    from .parent_direct_owner_cash_sources_v2 import read_parent_direct_owner_cash_sources_v2

    root = Path(root).resolve()
    registry_path = root / "config/current-operating-horizon-sources-v1.json"
    if not registry_path.is_file() or not isinstance(financial_basis, str) or not financial_basis.endswith("-06-30"):
        return None
    raw = registry_path.read_bytes()
    registry = json.loads(raw, object_pairs_hook=_unique)
    if registry.get("schema_version") != "operating-horizon-sources-v1" or registry.get("action") != "no_order":
        raise ValueError("PARENT_FINANCING_HORIZON_REGISTRY_INVALID")
    case = registry["cases"].get(symbol)
    if case is None:
        return None
    case = _selection(case)
    layout = dict(cash=case.get("parent_cash_layout"), balance=case.get("parent_balance_layout"),
                  income=case.get("parent_income_layout"))
    if layout != {"cash": "NUMBERED_CNINFO_V2", "balance": "NUMBERED_CNINFO_V2", "income": "NUMBERED_CNINFO_V1"}:
        return None
    opening = f"{date.fromisoformat(financial_basis).year - 1}-12-31"
    receipts = [dict(period_end=row["period"], receipt_binding=row["receipt_binding"], layout=layout)
                for row in case["parent_cash_observation_receipts"] if row["period"] in {opening, financial_basis}]
    if len(receipts) != 2:
        return None
    evidence = read_parent_direct_owner_cash_sources_v2(root=root, symbol=symbol,
        issuer_name=case["issuer_name"], sources=receipts, evaluated_at=now)
    if registry_path.read_bytes() != raw:
        raise ValueError("PARENT_FINANCING_REGISTRY_CHANGED_DURING_READ")
    bridge = reconcile_parent_financing(*evidence["statements"])
    return dict(bridge, scope="ISSUER_PARENT_STANDALONE", model_inputs_changed=False, formal_eligibility=False)
