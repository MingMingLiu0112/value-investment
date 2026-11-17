"""Immutable, unapproved E1 link between two direct-owner-cash receipts."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .direct_owner_cash_research_v1 import (
    RECEIPT_SCHEMA, _bytes, _read, _write, replay_direct_owner_cash_receipt,
)
from .parent_direct_cash_research import _bound
from ..product.common import require_inside

SCHEMA = "direct-owner-cash-update-v1"
RATIONALE_SCHEMA = "direct-owner-cash-change-rationale-v1"
STATUS = "SUCCESSOR_CONDITIONAL_RESEARCH_PENDING_REVIEW"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _aware(value: str, now: datetime) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("DIRECT_UPDATE_FUTURE_OR_NAIVE_TIME")
    return stamp


def _economics(result: dict) -> dict:
    compiled = result["compiled"]
    return dict(opening=compiled["opening"], ordinary_shares=compiled["ordinary_shares"],
                scenarios={name: dict(cost_of_equity=row["cost_of_equity"],
                                      years=row["years"],
                                      terminal_policy=row["terminal"]["policy"],
                                      remaining_scheduled_events=row["terminal"]["remaining_scheduled_events"],
                                      annual_rows=row["calculation"]["annual_rows"],
                                      operating_forecasts=[{
                                          key: forecast["assumptions"][key]
                                          for key in ("revenue", "cost", "other_operating_cash")}
                                          for forecast in compiled["operating_forecasts"][name]],
                                      terminal_value=row["calculation"].get("terminal_equity_value_cny"))
                           for name, row in compiled["scenarios"].items()})


def _numeric_equivalence(value):
    """Compare printed numeric strings without changing their stored precision."""
    if isinstance(value, dict):
        return {key: _numeric_equivalence(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_numeric_equivalence(item) for item in value]
    if isinstance(value, str):
        try:
            number = Decimal(value)
        except InvalidOperation:
            return value
        return number if number.is_finite() else value
    return value


def _same_economics(left, right) -> bool:
    return _numeric_equivalence(left) == _numeric_equivalence(right)


def _forecast_leaves(value, path=()):
    if isinstance(value, dict):
        if value.get("classification") == "FORECAST_ASSUMPTION":
            yield path, value
        for key, item in value.items():
            yield from _forecast_leaves(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _forecast_leaves(item, (*path, str(index)))


def _assumption_changes(old_spec: dict, new_spec: dict) -> list[dict]:
    old_leaves = dict(_forecast_leaves(old_spec))
    new_leaves = dict(_forecast_leaves(new_spec))
    changes = []
    for path, current in new_leaves.items():
        previous = old_leaves.get(path)
        def economic_declaration(value):
            return {key: item for key, item in value.items()
                    if key not in {"rationale", "counter_evidence", "reopen_condition", "name"}}
        if previous is not None and _same_economics(
                economic_declaration(previous), economic_declaration(current)):
            continue
        anchors = current.get("evidence_anchors")
        declarations = new_spec.get("fact_anchors")
        if (not isinstance(anchors, list) or not anchors or
                not isinstance(declarations, dict) or
                any(not isinstance(anchor, str) or anchor not in declarations
                    for anchor in anchors)):
            raise ValueError("DIRECT_UPDATE_CHANGED_ASSUMPTION_ANCHOR_MISSING")
        changes.append(dict(spec_path=".".join(path),
                            predecessor=deepcopy(previous), successor=deepcopy(current),
                            evidence_anchors={anchor: deepcopy(declarations[anchor])
                                              for anchor in anchors},
                            anchor_validation="REPLAYED_BY_DIRECT_OWNER_CASH_COMPILER"))
    return changes


def _expected(*, root: Path, predecessor_binding: dict, successor_binding: dict,
              change_binding: dict, now: datetime) -> dict:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("DIRECT_UPDATE_AWARE_REVIEW_TIME_REQUIRED")
    old_receipt = _read(root, predecessor_binding)
    new_receipt = _read(root, successor_binding)
    if (old_receipt.get("schema_version") != RECEIPT_SCHEMA or
            new_receipt.get("schema_version") != RECEIPT_SCHEMA or
            predecessor_binding == successor_binding):
        raise ValueError("DIRECT_UPDATE_TWO_DISTINCT_DIRECT_RECEIPTS_REQUIRED")
    old_spec = _read(root, old_receipt["spec_binding"])
    new_spec = _read(root, new_receipt["spec_binding"])
    old = replay_direct_owner_cash_receipt(root=root, receipt_binding=predecessor_binding, now=now)
    new = replay_direct_owner_cash_receipt(root=root, receipt_binding=successor_binding, now=now)
    identity = ("symbol", "issuer_name", "scope", "currency", "valuation_date")
    if (any(old_spec.get(key) != new_spec.get(key) for key in identity) or
            old["symbol"] != new["symbol"] or old["symbol"] != old_spec["symbol"] or
            old_spec.get("currency") != "CNY"):
        raise ValueError("DIRECT_UPDATE_ISSUER_SCOPE_CURRENCY_OR_BASIS_CHANGED")
    old_time = _aware(old_spec["computed_at"], now)
    new_time = _aware(new_spec["computed_at"], now)
    old_day = date.fromisoformat(old_spec["research_as_of"])
    new_day = date.fromisoformat(new_spec["research_as_of"])
    if (new_time < old_time or new_day < old_day or
            old_day > old_time.astimezone(SHANGHAI).date() or
            new_day > new_time.astimezone(SHANGHAI).date() or
            new_day > now.astimezone(SHANGHAI).date()):
        raise ValueError("DIRECT_UPDATE_RESEARCH_TIME_MOVES_BACKWARD_OR_FUTURE")
    before, after = _economics(old), _economics(new)
    changed = [key for key in ("opening", "ordinary_shares")
               if not _same_economics(before[key], after[key])]
    for name in ("bear", "base", "bull"):
        for key in ("cost_of_equity", "years", "terminal_policy",
                    "remaining_scheduled_events", "operating_forecasts",
                    "annual_rows", "terminal_value"):
            if not _same_economics(before["scenarios"][name][key],
                                   after["scenarios"][name][key]):
                changed.append(f"scenarios.{name}.{key}")
    if not changed:
        raise ValueError("DIRECT_UPDATE_ECONOMIC_INPUT_UNCHANGED")
    changed_assumptions = _assumption_changes(old_spec, new_spec)
    evidence = _read(root, change_binding)
    if (evidence.get("schema_version") != RATIONALE_SCHEMA or
            evidence.get("action") != "no_order" or
            evidence.get("symbol") != new["symbol"] or
            evidence.get("predecessor_binding") != predecessor_binding or
            evidence.get("successor_binding") != successor_binding or
            not isinstance(evidence.get("change_rationale"), str) or
            not evidence["change_rationale"].strip() or
            not isinstance(evidence.get("countercase"), str) or
            not evidence["countercase"].strip() or
            not isinstance(evidence.get("source_bindings"), list) or
            not evidence["source_bindings"] or
            any(ref not in new["source_bindings"] for ref in evidence["source_bindings"])):
        raise ValueError("DIRECT_UPDATE_BOUND_RATIONALE_OR_COUNTERCASE_INVALID")
    # The cited bytes must still exist. A prose-only or invented citation cannot
    # serve as an economic change, even when it is contained in the rationale.
    for ref in evidence["source_bindings"]:
        _bound(root, ref)
    yearly = {name: dict(predecessor=before["scenarios"][name]["annual_rows"],
                         successor=after["scenarios"][name]["annual_rows"])
              for name in ("bear", "base", "bull")
              if not _same_economics(before["scenarios"][name]["annual_rows"],
                                     after["scenarios"][name]["annual_rows"])}
    return dict(schema_version=SCHEMA, status=STATUS, action="no_order",
                symbol=new["symbol"], scope=new_spec["scope"], currency="CNY",
                financial_basis=new_spec["valuation_date"],
                research_as_of=new_spec["research_as_of"],
                predecessor_binding=dict(predecessor_binding),
                successor_binding=dict(successor_binding),
                change_binding=dict(change_binding),
                changed_input_fields=changed,
                changed_assumptions=changed_assumptions,
                change_rationale=evidence["change_rationale"],
                countercase=evidence["countercase"],
                predecessor_input_fingerprint=old["input_fingerprint"],
                successor_input_fingerprint=new["input_fingerprint"],
                predecessor_valuation=old["valuation"],
                successor_valuation=new["valuation"],
                valuation_changed=old["valuation"] != new["valuation"],
                yearly_changes=yearly,
                source_bindings=new["source_bindings"],
                formal_eligibility=False, main_range_adopted=False,
                price_admitted=False, condition_price=None,
                personal_quantity=None, approvals_created=0)


def build_direct_owner_cash_update(*, root: Path, predecessor_binding: dict,
                                   successor_binding: dict, change_binding: dict,
                                   output_dir: Path, now: datetime) -> dict:
    root = Path(root).resolve()
    output = require_inside(root / "runtime", Path(output_dir).resolve(), "direct owner update")
    if output.exists():
        raise FileExistsError("DIRECT_UPDATE_NEW_OUTPUT_REQUIRED")
    update = _expected(root=root, predecessor_binding=predecessor_binding,
                       successor_binding=successor_binding,
                       change_binding=change_binding, now=now)
    binding = _write(root, output / "update.json", update)
    replay_direct_owner_cash_update(root, binding, now)
    return dict(update_binding=binding, update=update)


def replay_direct_owner_cash_update(root: Path, update_binding: dict,
                                    now: datetime) -> dict:
    root = Path(root).resolve()
    stored = _read(root, update_binding)
    expected = _expected(root=root,
                         predecessor_binding=stored["predecessor_binding"],
                         successor_binding=stored["successor_binding"],
                         change_binding=stored["change_binding"], now=now)
    if _bytes(stored) != _bytes(expected):
        raise ValueError("DIRECT_UPDATE_FIELDS_OR_YEARLY_PATH_CHANGED")
    return expected
