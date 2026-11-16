"""Validate independent parent-cash scenario drafts before existing E2 compilation.

The model supplies every year's value and explanation. Source facts, opening
equity/cash, shares, issuer identity and model applicability stay host-owned.
This module makes no provider call and confers no main valuation or action.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from .direct_owner_cash_agent_facts_v1 import read_parent_cash_agent_facts
from .direct_owner_cash_compilation_v1 import compile_source_bound_owner_cash
from ...domain.valuation.direct_parent_owner_cash_v1 import FLOW_KEYS
from ..product.common import require_inside

VERSION = "direct-owner-cash-agent-draft-v1"
SCENARIOS = ("bear", "base", "bull")
DRIVERS = ("revenue", "cost", "other_operating_cash")
POLICY = frozenset(FLOW_KEYS - {"operating_cash"})
SERIES = frozenset(DRIVERS) | POLICY
TERMINAL_POLICY = frozenset(FLOW_KEYS)
HORIZON = 10


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _number(value):
    if not isinstance(value, str):
        raise ValueError("PARENT_DRAFT_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("PARENT_DRAFT_DECIMAL_INVALID") from error
    if not number.is_finite():
        raise ValueError("PARENT_DRAFT_FINITE_REQUIRED")
    return str(number)


def _explanation(value, anchors):
    if (not isinstance(value, dict)
            or set(value) != {"evidence_anchors", "mechanism", "counter_evidence",
                              "reopen_condition", "values"}
            or not isinstance(value["evidence_anchors"], list)
            or not 1 <= len(value["evidence_anchors"]) <= 8
            or len(set(value["evidence_anchors"])) != len(value["evidence_anchors"])
            or not set(value["evidence_anchors"]) <= anchors):
        raise ValueError("PARENT_DRAFT_TERM_SOURCE_INVALID")
    for key in ("mechanism", "counter_evidence", "reopen_condition"):
        if not isinstance(value[key], str) or len(value[key].strip()) < 12:
            raise ValueError("PARENT_DRAFT_TERM_EXPLANATION_REQUIRED:" + key)


def _term(value, anchors, *, count, note):
    _explanation(value, anchors)
    if not isinstance(value["values"], list) or len(value["values"]) != count:
        raise ValueError("PARENT_DRAFT_EXPLICIT_VALUES_REQUIRED")
    values = [_number(raw) for raw in value["values"]]
    return [dict(classification="FORECAST_ASSUMPTION", value=raw,
                 evidence_anchors=list(value["evidence_anchors"]),
                 rationale=value["mechanism"] + " " + note,
                 counter_evidence=value["counter_evidence"],
                 reopen_condition=value["reopen_condition"]) for raw in values]


def _load_spec(root, binding):
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or not isinstance(binding["path"], str)
            or not isinstance(binding["sha256"], str)
            or len(binding["sha256"]) != 64
            or Path(binding["path"]).is_absolute()
            or ".." in Path(binding["path"]).parts):
        raise ValueError("PARENT_DRAFT_SPEC_BINDING_INVALID")
    path = require_inside(root / "runtime", root / binding["path"], "parent draft source spec")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("PARENT_DRAFT_SPEC_HASH_CHANGED")
    return json.loads(raw)


def assemble_parent_cash_drafts(*, root: Path, spec_binding: dict, drafts: dict,
                                generated_at: datetime) -> dict:
    """Return an unapproved source-bound E2 candidate with all three paths.

    A caller must separately retain the raw model responses, provider usage and
    request fingerprints through the existing D1 task store before publication.
    """
    root = Path(root).resolve()
    if generated_at.utcoffset() is None or set(drafts) != set(SCENARIOS):
        raise ValueError("PARENT_DRAFT_CLOCK_OR_SCENARIOS_INVALID")
    context = read_parent_cash_agent_facts(root=root, spec_binding=spec_binding,
                                           now=generated_at)
    if context["valuation_date"] != context["facts"]["revenue"]["period_end"]:
        raise ValueError("PARENT_DRAFT_OPERATING_HISTORY_PERIOD_INVALID")
    spec = deepcopy(_load_spec(root, spec_binding))
    spec["scenarios"] = {}
    anchors = set(context["facts"])
    first_year = int(context["valuation_date"][:4]) + 1
    expected_years = list(range(first_year, first_year + HORIZON))
    history_start = context["valuation_date"][:4] + "-01-01"
    for scenario in SCENARIOS:
        draft = drafts[scenario]
        if (not isinstance(draft, dict)
                or set(draft) != {"schema_version", "scenario", "source_fingerprint",
                                  "years", "annual_notes", "series", "terminal",
                                  "cost_of_equity", "rationale", "counter_evidence",
                                  "reopen_condition"}
                or draft["schema_version"] != VERSION or draft["scenario"] != scenario
                or draft["source_fingerprint"] != context["input_fingerprint"]
                or draft["years"] != expected_years
                or set(draft["series"]) != SERIES):
            raise ValueError("PARENT_DRAFT_SOURCE_OR_HORIZON_INVALID:" + scenario)
        notes = draft["annual_notes"]
        if (not isinstance(notes, list) or len(notes) != HORIZON
                or any(not isinstance(note, str) or len(note.strip()) < 12
                       for note in notes)):
            raise ValueError("PARENT_DRAFT_ANNUAL_MECHANISM_REQUIRED")
        for key in ("rationale", "counter_evidence", "reopen_condition"):
            if not isinstance(draft[key], str) or len(draft[key].strip()) < 12:
                raise ValueError("PARENT_DRAFT_SCENARIO_EXPLANATION_REQUIRED")
        vectors = {name: _term(value, anchors, count=HORIZON, note="")
                   for name, value in draft["series"].items()}
        annual = []
        for index, year in enumerate(expected_years):
            driver = dict(historical_start=history_start,
                          historical_end=context["valuation_date"],
                          rationale=draft["rationale"] + " " + notes[index],
                          counter_evidence=draft["counter_evidence"],
                          reopen_condition=draft["reopen_condition"])
            for name in DRIVERS:
                row = deepcopy(vectors[name][index])
                row["rationale"] += " " + notes[index]
                driver[name] = row
            policy = {}
            for name in POLICY:
                row = deepcopy(vectors[name][index])
                row["rationale"] += " " + notes[index]
                policy[name] = row
            annual.append(dict(year=year, operating_forecast=driver, policy=policy))
        terminal = draft["terminal"]
        if (not isinstance(terminal, dict)
                or set(terminal) != {"policy", "remaining_scheduled_events",
                                     "max_transition_years", "financing",
                                     "rationale", "counter_evidence", "reopen_condition"}
                or set(terminal["policy"]) != TERMINAL_POLICY
                or not isinstance(terminal["remaining_scheduled_events"], list)
                or type(terminal["max_transition_years"]) is not int):
            raise ValueError("PARENT_DRAFT_TERMINAL_CONTRACT_INVALID")
        for key in ("rationale", "counter_evidence", "reopen_condition"):
            if not isinstance(terminal[key], str) or len(terminal[key].strip()) < 12:
                raise ValueError("PARENT_DRAFT_TERMINAL_EXPLANATION_REQUIRED")
        tail = {key: terminal[key] for key in ("remaining_scheduled_events",
            "max_transition_years", "rationale", "counter_evidence", "reopen_condition")}
        tail["policy"] = {name: _term(value, anchors, count=1, note="")[0]
                          for name, value in terminal["policy"].items()}
        if terminal["financing"] is not None:
            tail["financing"] = terminal["financing"]
        spec["scenarios"][scenario] = dict(
            rationale=draft["rationale"], counter_evidence=draft["counter_evidence"],
            reopen_condition=draft["reopen_condition"],
            cost_of_equity=_term(draft["cost_of_equity"], anchors, count=1, note="")[0],
            years=annual, terminal=tail)
    # Existing compiler reopens the originals and enforces all cash, debt,
    # distribution and terminal equations. Its rejection is never bypassed.
    compiled = compile_source_bound_owner_cash(root=root, spec=spec, now=generated_at)
    return dict(schema_version=VERSION, symbol=context["symbol"],
        source_fingerprint=context["input_fingerprint"],
        scenario_draft_sha256={name: hashlib.sha256(_canonical(drafts[name])).hexdigest()
                               for name in SCENARIOS},
        candidate_spec=spec, compiled=compiled, action="no_order",
        formal_eligibility=False, main_range_adopted=False)
