"""Input contract for native parent tasks backed by ruled FY and H1 statements."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from . import direct_owner_cash_agent_facts_v2 as agent
from .company_profile_sources_v1 import _bound
from .fresh_issuer_distribution_v1 import replay_fresh_issuer_distribution
from .direct_owner_cash_policy_capital_v1 import opening_debt_basis
from .company_profile_sources_v2 import load_registered_source_profile
from ...valuation_models.direct_owner_cash_v2 import MODEL_ID, MODEL_VERSION
from .direct_owner_cash_agent_draft_v2 import _load_spec
from .parent_note_grid_agent_facts_v1 import SCHEMA as MANIFEST_SCHEMA, _observation
from .parent_note_grid_sources_v1 import VERSION, read_note_grid_parent_cash
from ..product.common import require_inside

OPERATING = {"revenue": ("income", "revenue"), "cost": ("income", "cost"),
             "customer_cash": ("cash_flow", "customer_cash_cny"),
             "supplier_cash": ("cash_flow", "supplier_cash_cny"), "cfo": ("cash_flow", "cfo_cny")}


def _research_applicability(root, spec, statements, cutoff):
    """Authorize this model to investigate the issuer at the registered cutoff."""
    pin = spec.get("model_applicability_evidence")
    if (not isinstance(pin, dict) or set(pin) != {"profile_input_sha256", "model_version", "purpose", "economic_adoption"}
            or pin["model_version"] != MODEL_VERSION or pin["purpose"] != "CONDITIONAL_PARENT_RESEARCH"
            or pin["economic_adoption"] is not False):
        raise ValueError("NOTE_GRID_SOURCE_BOUND_APPLICABILITY_REQUIRED")
    profile = load_registered_source_profile(root=root, symbol=spec["symbol"], now=cutoff)
    route = profile.get("route") or {}
    contract = profile.get("applicability_contract") or {}
    if (profile.get("input_fingerprint") != pin["profile_input_sha256"]
            or profile.get("status") != "SOURCE_BOUND_ROUTE_ONLY" or profile.get("company_name") != spec["issuer_name"]
            or profile.get("symbol") != spec["symbol"] or profile.get("template_candidate") != "quality_compounder"
            or profile.get("action") != "no_order" or profile.get("formal_eligibility") is not False
            or route.get("status") != "SUPPORTED" or route.get("selected_model") != MODEL_ID
            or contract.get("primary_model") != MODEL_ID or contract.get("profile_id") != "quality_compounder"):
        raise ValueError("NOTE_GRID_RESEARCH_MODEL_OR_PROFILE_MISMATCH")
    profile_reports = [(r["period"], r["sha256"]) for r in profile["evidence_refs"]]
    if profile_reports != [(s["period_end"], s["source_binding"]["sha256"]) for s in statements]:
        raise ValueError("NOTE_GRID_PROFILE_REPORTS_MISMATCH")
    for s in statements:
        if (s["scope"] != agent.SCOPE or s["currency"] != "CNY" or not all(s["checks"].values())
                or any(s[section][field]["current"] is None for section, field in
                       [*OPERATING.values(), ("income", "parent_net_profit_cny"), ("cash_flow", "gross_capex_cny"),
                        ("cash_flow", "investment_income_cash_cny"), ("balance_sheet", "book_equity_cny")])):
            raise ValueError("NOTE_GRID_PARENT_RESEARCH_INPUTS_UNVERIFIED")
    return dict(**pin, symbol=spec["symbol"], profile_id=profile["template_candidate"], model_id=MODEL_ID,
                scope=agent.SCOPE, report_fingerprints=profile_reports,
                applicability="SOURCE_BOUND_CONDITIONAL_RESEARCH", unresolved_funding_is_cash=False)


def read_evidence(*, root, spec, now):
    if (spec.get("schema_version") != agent.SCHEMA or spec.get("source_adapter_version") != VERSION
            or spec.get("scope") != agent.SCOPE or spec.get("currency") != "CNY"
            or spec.get("action") != "no_order" or spec.get("operating_sources") != []
            or spec.get("model_applicable") is not True or not spec.get("model_applicability_evidence")):
        raise ValueError("NOTE_GRID_TASK_SOURCE_CONTRACT_INVALID")
    # These branches require a distinct quarterly, financing, or commitment replay.
    unsupported = {"quarterly_financing_source", "first_year_operating_cash_method", "annual_capex_evidence",
                   "first_year_cash_receipts_evidence", "paid_note_interest_sources", "conditional_financing_stress"}
    if unsupported.intersection(spec) or spec.get("constraint_binding") is not None or spec.get("fund_selection") is not None:
        raise ValueError("NOTE_GRID_TASK_UNSUPPORTED_SOURCE_EXTENSION")
    at = datetime.fromisoformat(spec["computed_at"])
    binding = spec["source_manifest_binding"]
    root = Path(root).resolve()
    require_inside(root / "runtime", root / binding["path"], "note-grid source manifest")
    manifest = json.loads(_bound(root, binding, limit=16384))
    if (set(manifest) != {"schema_version", "source_adapter_version", "symbol", "issuer_name",
                          "owner_sources", "action", "computed_at"}
            or manifest["schema_version"] != MANIFEST_SCHEMA
            or any(manifest[key] != spec[key] for key in ("symbol", "issuer_name", "source_adapter_version",
                                                          "owner_sources", "action"))
            or len(manifest["owner_sources"]) != 2):
        raise ValueError("NOTE_GRID_TASK_MANIFEST_MISMATCH")
    cutoff = datetime.fromisoformat(manifest["computed_at"])
    if (any(t.utcoffset() is None for t in (at, now, cutoff)) or not cutoff <= at <= now):
        raise ValueError("NOTE_GRID_TASK_SOURCE_CLOCK_INVALID")
    fy, h1 = manifest["owner_sources"]
    basis = spec["valuation_date"]
    if (not basis.endswith("-12-31") or fy["period_end"] != basis
            or h1["period_end"] != str(int(basis[:4])+1)+"-06-30"):
        raise ValueError("NOTE_GRID_TASK_FY_H1_REQUIRED")
    result = read_note_grid_parent_cash(root=root, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
                                        sources=spec["owner_sources"], evaluated_at=cutoff)
    _bound(root, binding)
    qualification = _research_applicability(root, spec, result["statements"], at)
    paid = spec.get("implemented_distribution_receipt_binding")
    if not paid:
        raise ValueError("NOTE_GRID_IMPLEMENTED_DISTRIBUTION_RECEIPT_REQUIRED")
    event = replay_fresh_issuer_distribution(root=root, receipt_binding=paid, symbol=spec["symbol"], now=at)
    if (event["issuer_name"] != spec["issuer_name"] or event["distribution"]["fiscal_year"] != int(basis[:4])
            or event["confirmation_original_sha256"] != result["statements"][1]["source_binding"]["sha256"]):
        raise ValueError("NOTE_GRID_DISTRIBUTION_ISSUER_PERIOD_OR_CONFIRMATION_MISMATCH")
    return dict(**result, implemented_distribution=dict(receipt_binding=paid, **event),
                source_manifest_binding=binding, research_applicability=qualification,
                constraints=None, fund_commitment_evidence=None,
                working_capital_cash_component=None)


def task_context(*, root, spec_binding, now):
    spec = _load_spec(Path(root), spec_binding)
    evidence = read_evidence(root=root, spec=spec, now=now)
    fy, h1 = evidence["statements"]
    statements = {row["period_end"]: row for row in (fy, h1)}
    facts = {}
    for name, ref in spec["fact_anchors"].items():
        if set(ref) != {"period_end", "section", "field", "column"} or ref["column"] not in {"current", "comparative"}:
            raise ValueError("NOTE_GRID_TASK_INVALID_ANCHOR:" + name)
        section, field = ref["section"], ref["field"]
        if section == "operating" and ref["column"] == "current" and field in OPERATING:
            section, field = OPERATING[field]
        if section not in {"income", "balance_sheet", "cash_flow"} or ref["period_end"] not in statements:
            raise ValueError("NOTE_GRID_TASK_INVALID_ANCHOR:" + name)
        row = statements[ref["period_end"]][section].get(field)
        if row is None or row[ref["column"]] is None:
            raise ValueError("NOTE_GRID_TASK_UNKNOWN_ANCHOR:" + name)
        facts[name] = dict(**ref, value_cny=agent._finite(row[ref["column"]]), currency="CNY",
                           scope=agent.SCOPE, source_refs=row["source_refs"])
    if set(spec["opening"]) != {"book", "cash", "debt", "capacity"}:
        raise ValueError("NOTE_GRID_TASK_OPENING_FIELDS_REQUIRED")
    for key in ("capacity", "debt"):
        term = spec["opening"][key]
        # The two statements do not certify total financing or legal payout capacity.
        if (term.get("classification") != "FORECAST_ASSUMPTION"
                or not all(isinstance(term.get(k), str) and term[k].strip()
                           for k in ("rationale", "counter_evidence", "reopen_condition"))
                or not term.get("evidence_anchors") or any(k not in facts for k in term["evidence_anchors"])):
            raise ValueError("NOTE_GRID_TASK_EXPLICIT_OPENING_ASSUMPTION_REQUIRED:" + key)
        forms = [set(["value"]), {"anchor", "factor"}, {"linear_terms"}]
        explanatory = {"classification", "evidence_anchors", "rationale", "counter_evidence", "reopen_condition"}
        if set(term) - explanatory not in forms or not isinstance(term["evidence_anchors"], list):
            raise ValueError("NOTE_GRID_TASK_OPENING_AMOUNT_INVALID:" + key)
        if "linear_terms" in term:
            if (not isinstance(term["linear_terms"], list) or not term["linear_terms"]
                    or any(set(t) != {"anchor", "factor"} or t["anchor"] not in term["evidence_anchors"]
                           for t in term["linear_terms"])):
                raise ValueError("NOTE_GRID_TASK_OPENING_AMOUNT_INVALID:" + key)
        if "anchor" in term and term["anchor"] not in term["evidence_anchors"]:
            raise ValueError("NOTE_GRID_TASK_OPENING_AMOUNT_INVALID:" + key)
        opening_debt_basis({"debt": term}, facts)
    for key, field in (("book", "book_equity_cny"), ("cash", "closing_cash_and_equivalents_cny")):
        opening = spec["opening"][key]
        anchor = facts.get(opening.get("anchor"), {})
        if (opening != {"classification": "FACT", "anchor": opening.get("anchor")} or anchor.get("field") != field
                or anchor["period_end"] != spec["valuation_date"] or anchor["column"] != "current"):
            raise ValueError("NOTE_GRID_TASK_OPENING_SCOPE_INVALID:" + key)
    revenue = facts.get("revenue", {})
    if revenue.get("period_end") != spec["valuation_date"] or revenue.get("field") != "revenue" or revenue["column"] != "current":
        raise ValueError("NOTE_GRID_TASK_FY_REVENUE_REQUIRED")
    financing = [agent._historical_financing_range(row) for row in (fy, h1)]
    observations = [_observation(row, column) for row in (fy, h1) for column in ("current", "comparative")]
    shares = fy["ordinary_shares_evidence"]
    if not shares or spec["ordinary_shares"] != {k: shares[k] for k in ("classification", "period_end")}:
        raise ValueError("NOTE_GRID_TASK_DATED_SHARES_MISMATCH")
    context = dict(schema_version="parent-note-grid-task-context-v1", symbol=spec["symbol"], issuer_name=spec["issuer_name"],
        valuation_date=spec["valuation_date"], as_of=spec["computed_at"], source_adapter_version=VERSION,
        source_manifest_binding=spec["source_manifest_binding"], spec_binding=spec_binding, facts=facts,
        scope=agent.SCOPE, currency="CNY", ordinary_shares=shares, parent_operating_cash_observations=observations,
        implemented_distribution=evidence["implemented_distribution"],
        historical_financing_range=financing[0], historical_financing_observations=financing,
        model_applicability_evidence=evidence["research_applicability"], economic_adoption=False, constraints=None,
        opening_fact_anchors={k: term["anchor"] for k, term in spec["opening"].items() if term["classification"] == "FACT"},
        source_status=evidence["status"], action="no_order", formal_eligibility=False, forecast_scenarios_present=False)
    if "policy_money_wire" in spec:
        if spec["policy_money_wire"] != "CNY_YUAN_CENT_V1":
            raise ValueError("NOTE_GRID_TASK_UNSUPPORTED_MONEY_WIRE")
        context["policy_money_wire"] = spec["policy_money_wire"]
    _load_spec(Path(root), spec_binding)
    context["input_fingerprint"] = sha256(agent._canonical(context)).hexdigest()
    return context
