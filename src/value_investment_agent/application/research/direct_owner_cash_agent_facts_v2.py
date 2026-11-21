"""Project numbered parent-company statements into a versioned D2 task.

The projection contains no existing forecast scenarios. It is not an E2 input,
valuation, or permission to turn consolidated earnings into parent cash.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from .direct_owner_cash_compilation_v1 import SCHEMA
from .parent_direct_owner_cash_sources_v2 import read_parent_direct_owner_cash_sources_v2
from ...domain.valuation.parent_direct_operating_cash import SCOPE
from ..product.common import require_inside

VERSION = "direct-owner-cash-agent-facts-v2"
_OPERATING_FIELDS = {"revenue", "cost", "customer_cash", "supplier_cash", "cfo"}
_FINANCING_FIELDS = (
    "short_term_borrowings_cny", "current_noncurrent_liabilities_cny",
    "long_term_borrowings_cny", "bonds_payable_cny", "lease_liabilities_cny",
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _finite(value):
    if not isinstance(value, str):
        raise ValueError("PARENT_AGENT_FACT_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("PARENT_AGENT_FACT_DECIMAL_INVALID") from error
    if not number.is_finite():
        raise ValueError("PARENT_AGENT_FACT_FINITE_REQUIRED")
    return str(number)


def _historical_financing_range(statement):
    """Expose reported parent rows without filling blank debt cells with zero.

    The selected rows can include non-debt items in the current portion of
    noncurrent liabilities. Their sum is not a certified debt lower bound or
    a schedule of dated repayments/refinancing.
    """
    balance = statement.get("balance_sheet") or {}
    components = {}
    lower = Decimal(0)
    known_count = 0
    for field in _FINANCING_FIELDS:
        row = balance.get(field)
        value = row.get("current") if isinstance(row, dict) else None
        if value is None:
            components[field] = {"classification": "UNKNOWN", "value_cny": None}
            continue
        source_refs = row.get("source_refs")
        amount = Decimal(_finite(value))
        if amount < 0 or not source_refs:
            raise ValueError("PARENT_AGENT_FINANCING_ROW_INVALID:" + field)
        lower += amount
        known_count += 1
        components[field] = dict(classification="FACT", value_cny=str(amount),
                                 source_refs=source_refs)
    liability = balance.get("liabilities_cny")
    ceiling = None
    if isinstance(liability, dict) and liability.get("current") is not None:
        amount = Decimal(_finite(liability["current"]))
        if amount < lower or not liability.get("source_refs"):
            raise ValueError("PARENT_AGENT_FINANCING_RANGE_INVALID")
        ceiling = dict(classification="FACT", value_cny=str(amount),
                       source_refs=liability["source_refs"])
    flows = statement.get("cash_flow") or {}
    cash_movements = {}
    for field in ("borrowings_received_cny", "debt_repayments_paid_cny"):
        row = flows.get(field)
        value = row.get("current") if isinstance(row, dict) else None
        if value is None:
            cash_movements[field] = dict(classification="UNKNOWN", value_cny=None)
            continue
        amount = Decimal(_finite(value))
        if amount < 0 or not row.get("source_refs"):
            raise ValueError("PARENT_AGENT_FINANCING_CASH_ROW_INVALID:" + field)
        cash_movements[field] = dict(classification="FACT", value_cny=str(amount),
                                     source_refs=row["source_refs"])
    received = cash_movements["borrowings_received_cny"]["value_cny"]
    repaid = cash_movements["debt_repayments_paid_cny"]["value_cny"]
    return dict(period_end=statement["period_end"], scope=SCOPE, currency="CNY",
                components=components,
                selected_liability_rows_sum_cny=str(lower) if known_count else None,
                reported_component_count=known_count,
                on_balance_liabilities_ceiling=ceiling,
                financing_cash_flows=dict(
                    period_start=statement.get("period_start"),
                    period_end=statement["period_end"],
                    components=cash_movements,
                    net_borrowing_cash_cny=(str(Decimal(received) - Decimal(repaid))
                                            if received is not None and repaid is not None
                                            else None),
                    classification="HISTORICAL_CASH_FLOW_NOT_DEBT_BALANCE_CHANGE"),
                complete_financing_scope_verified=False,
                dated_maturity_schedule_verified=False,
                future_refinancing_verified=False,
                classification="PARTIAL_HISTORICAL_LIABILITY_ROWS_NOT_DEBT_FACT")


def read_parent_cash_agent_facts_v2(*, root: Path, spec_binding: dict,
                                    now: datetime) -> dict:
    """Reopen pinned originals; expose only historical parent facts and gaps.

    A pre-existing source-bound spec may supply the source manifest and anchor
    names. Its scenario values are intentionally neither read nor projected.
    """
    root = Path(root).resolve()
    if (not isinstance(spec_binding, dict) or set(spec_binding) != {"path", "sha256"}
            or not isinstance(spec_binding["path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", spec_binding["sha256"])
            or Path(spec_binding["path"]).is_absolute()
            or ".." in Path(spec_binding["path"]).parts):
        raise ValueError("PARENT_AGENT_SPEC_BINDING_INVALID")
    if now.utcoffset() is None:
        raise ValueError("PARENT_AGENT_CLOCK_REQUIRED")
    path = require_inside(root / "runtime", root / spec_binding["path"],
                          "parent cash research spec")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec_binding["sha256"]:
        raise ValueError("PARENT_AGENT_SPEC_HASH_CHANGED")
    spec = json.loads(raw)
    if (spec.get("schema_version") != SCHEMA or spec.get("action") != "no_order"
            or spec.get("scope") != SCOPE or spec.get("currency") != "CNY"
            or spec.get("model_applicable") is not True
            or not spec.get("model_applicability_evidence")
            or not re.fullmatch(r"[0-9]{6}", spec.get("symbol", ""))):
        raise ValueError("PARENT_AGENT_SOURCE_SCOPE_INVALID")
    if (spec.get("source_adapter_version") != "NUMBERED_CNINFO_V2"
            or spec.get("operating_sources") != []):
        raise ValueError("PARENT_AGENT_V2_NUMBERED_SOURCE_REQUIRED")
    at = datetime.fromisoformat(spec["computed_at"])
    if at.utcoffset() is None or at > now:
        raise ValueError("PARENT_AGENT_FUTURE_SOURCE")
    evidence = read_parent_direct_owner_cash_sources_v2(
        root=root, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
        sources=spec["owner_sources"], evaluated_at=at,
        constraint_binding=spec.get("constraint_binding"),
        fund_selection=spec.get("fund_selection"))
    observations = []
    numbered_fields = {
        "revenue": ("income", "revenue"),
        "cost": ("income", "cost"),
        "customer_cash": ("cash_flow", "customer_cash_cny"),
        "supplier_cash": ("cash_flow", "supplier_cash_cny"),
        "cfo": ("cash_flow", "cfo_cny"),
    }
    for statement in evidence["statements"]:
        row = dict(period_end=statement["period_end"],
                   symbol=statement["symbol"], scope=statement["scope"],
                   source_refs={})
        for name, (section, field) in numbered_fields.items():
            try:
                sourced = statement[section][field]
                row[name] = sourced["current"]
                row["source_refs"][name] = sourced["source_refs"]
            except (KeyError, TypeError) as error:
                raise ValueError("PARENT_AGENT_V2_OPERATING_FIELD_MISSING:" + name) from error
        cash_fields = ("customer_cash", "supplier_cash", "cfo")
        if all(statement["cash_flow"][numbered_fields[key][1]].get("comparative")
               is not None for key in cash_fields):
            changes = {
                key: Decimal(row[key]) - Decimal(
                    statement["cash_flow"][numbered_fields[key][1]]["comparative"])
                for key in cash_fields
            }
            row["cash_change_explanation"] = dict(
                classification="DERIVED_HISTORICAL_CASH_CHANGE_NOT_WORKING_CAPITAL",
                cfo_change_cny=str(changes["cfo"]),
                customer_receipt_change_cny=str(changes["customer_cash"]),
                lower_supplier_payments_contribution_cny=str(-changes["supplier_cash"]),
                other_operating_cash_change_cny=str(
                    changes["cfo"] - changes["customer_cash"] + changes["supplier_cash"]),
            )
        profit = statement["income"].get("parent_net_profit_cny")
        if profit is not None and profit.get("current") is not None:
            observed_profit = Decimal(_finite(profit["current"]))
            row["profit_and_operating_cash"] = dict(
                classification="HISTORICAL_CFO_VS_PARENT_PROFIT_NOT_TERMINAL_CONVERSION",
                parent_profit_cny=str(observed_profit),
                operating_cash_cny=row["cfo"],
                operating_cash_minus_parent_profit_cny=str(Decimal(row["cfo"]) - observed_profit),
                profit_source_refs=profit["source_refs"], cash_source_refs=row["source_refs"]["cfo"],
            )
        observations.append(row)
    statements = {row["period_end"]: row for row in evidence["statements"]}
    if len(statements) != len(evidence["statements"]):
        raise ValueError("PARENT_AGENT_DUPLICATE_REPORT_PERIOD")
    facts = {}
    for name, ref in spec["fact_anchors"].items():
        if (not isinstance(ref, dict)
                or set(ref) != {"period_end", "section", "field", "column"}):
            raise ValueError("PARENT_AGENT_ANCHOR_INVALID")
        if ref["section"] == "operating":
            matches = [row for row in observations if row["period_end"] == ref["period_end"]]
            if (len(matches) != 1 or ref["column"] != "current"
                    or ref["field"] not in _OPERATING_FIELDS):
                raise ValueError("PARENT_AGENT_OPERATING_ANCHOR_INVALID")
            value = matches[0][ref["field"]]
            source_refs = matches[0]["source_refs"][ref["field"]]
        else:
            if (ref["section"] not in {"balance_sheet", "income", "cash_flow"}
                    or ref["column"] not in {"current", "comparative"}
                    or ref["period_end"] not in statements):
                raise ValueError("PARENT_AGENT_STATEMENT_ANCHOR_INVALID")
            statement = statements[ref["period_end"]]
            if statement["scope"] != SCOPE or statement["currency"] != "CNY":
                raise ValueError("PARENT_AGENT_STATEMENT_SCOPE_MISMATCH")
            sourced = statement[ref["section"]][ref["field"]]
            value = sourced[ref["column"]]
            source_refs = sourced["source_refs"]
        if not source_refs or name in facts:
            raise ValueError("PARENT_AGENT_FACT_SOURCE_MISSING")
        facts[name] = dict(value_cny=_finite(value), period_end=ref["period_end"],
                           section=ref["section"], field=ref["field"],
                           column=ref["column"], scope=SCOPE, currency="CNY",
                           source_refs=source_refs)
    if not facts:
        raise ValueError("PARENT_AGENT_FACTS_REQUIRED")
    share_facts = [row["ordinary_shares_evidence"] for row in evidence["statements"]
                   if row["period_end"] == spec["valuation_date"]]
    if len(share_facts) != 1 or not isinstance(share_facts[0], dict) or not share_facts[0].get("source_refs"):
        raise ValueError("PARENT_AGENT_DATED_SHARES_REQUIRED")
    shares = share_facts[0]
    if (shares.get("period_end") != spec["valuation_date"]
            or shares.get("unit") != "shares"
            or shares.get("scope") != "TOTAL_ISSUED_ORDINARY_SHARES"
            or shares.get("classification") not in {"FACT", "DERIVED_FACT"}):
        raise ValueError("PARENT_AGENT_SHARE_SCOPE_INVALID")
    financing = [_historical_financing_range(row) for row in evidence["statements"]]
    basis_financing = [row for row in financing
                       if row["period_end"] == spec["valuation_date"]]
    if len(basis_financing) != 1:
        raise ValueError("PARENT_AGENT_FINANCING_BASIS_NOT_UNIQUE")
    projected = dict(schema_version=VERSION, symbol=spec["symbol"],
        issuer_name=spec["issuer_name"], as_of=spec["computed_at"],
        valuation_date=spec["valuation_date"], facts=facts,
        model_applicability_evidence=spec["model_applicability_evidence"],
        opening_fact_anchors={key: row["anchor"] for key, row in spec["opening"].items()
                              if row.get("classification") == "FACT"},
        ordinary_shares=dict(count=_finite(shares["count"]), period_end=shares["period_end"],
                             unit="shares", scope=shares["scope"],
                             classification=shares["classification"],
                             derivation=shares.get("derivation"),
                             source_refs=shares["source_refs"]),
        source_status=evidence["status"],
        historical_financing_range=basis_financing[0],
        historical_financing_observations=financing,
        parent_operating_cash_observations=observations,
        working_capital_cash_component=evidence["working_capital_cash_component"],
        constraints=evidence["constraints"], unresolved=evidence["unresolved"],
        fund_commitment_evidence=evidence["fund_commitment_evidence"],
        action="no_order", formal_eligibility=False,
        scope=SCOPE, currency="CNY", forecast_scenarios_present=False)
    projected["input_fingerprint"] = hashlib.sha256(_canonical(projected)).hexdigest()
    return projected
