"""Explicit, source-bound direct owner cash E1 successor; no adoption or price."""

from copy import deepcopy
from datetime import datetime, date
from decimal import Decimal, localcontext
from functools import wraps
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .direct_owner_cash_research_v1 import (
    _bytes, _read, _write, _package, replay_direct_owner_cash_receipt,
)
from .direct_owner_cash_compilation_v1 import financing_maturity_floor
from .direct_owner_cash_input_adapter_v1 import run_direct_owner_cash_research
from .parent_direct_cash_research import read_parent_direct_cash_research, _bound
from .agent_review.quarterly_parent_cash_source import replay_quarterly_parent_cash
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.quarterly_parent_operating_facts import build_quarterly_parent_operating_observations
from ...domain.valuation.parent_remaining_year_cash import build_parent_remaining_year_cash
from ...domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path, FLOW_KEYS
from ...domain.research.issuer_identity import source_identity_matches_registered_issuer
from ...valuation_models.direct_owner_cash_v1 import scenario_to_payload, DirectOwnerCashScenario
from ..product.company_research import _serialize_outcome
from ..product.common import require_inside

SCHEMA = "parent-remaining-year-successor-spec-v1"
RECEIPT_SCHEMA = "parent-remaining-year-successor-receipt-v1"
IMPLEMENTATIONS = (
    "application/research/parent_remaining_year_successor.py",
    "application/research/parent_remaining_year_review.py",
    "domain/valuation/parent_remaining_year_cash.py",
    "infrastructure/filings/quarterly_parent_operating_facts.py",
    "infrastructure/filings/quarterly_parent_cash_facts.py",
)


def _implementations():
    source = Path(__file__).resolve().parents[2]
    return {name: sha256((source / name).read_bytes()).hexdigest() for name in IMPLEMENTATIONS}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    if not isinstance(value, str):
        raise ValueError("SUCCESSOR_DECIMAL_STRING_REQUIRED")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("SUCCESSOR_FINITE_NUMBER_REQUIRED")
    return result


def _precise(function):
    @wraps(function)
    def run(*args, **kwargs):
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            return function(*args, **kwargs)
    return run


@_precise
def _recalculate(*, root, spec_binding, now):
    root = Path(root).resolve()
    spec = _read(root, spec_binding)
    if set(spec) != {"schema_version", "action", "predecessor_binding", "quarterly_source",
                     "period_end", "computed_at", "research_as_of", "run_id",
                     "research_version", "change_rationale", "counter_evidence",
                     "reopen_condition", "scenarios"} or spec["schema_version"] != SCHEMA or spec["action"] != "no_order":
        raise ValueError("SUCCESSOR_SPEC_CONTRACT_INVALID")
    created = datetime.fromisoformat(spec["computed_at"])
    if (now.utcoffset() is None or created.utcoffset() is None or created > now
            or date.fromisoformat(spec["research_as_of"]) > created.astimezone(ZoneInfo("Asia/Shanghai")).date()
            or any(not _text(spec[key]) for key in ("run_id", "research_version",
                "change_rationale", "counter_evidence", "reopen_condition"))):
        raise ValueError("SUCCESSOR_TIME_OR_REASON_INVALID")
    predecessor = replay_direct_owner_cash_receipt(
        root=root, receipt_binding=spec["predecessor_binding"], now=created)
    old_receipt = _read(root, spec["predecessor_binding"])
    old_spec = _read(root, old_receipt["spec_binding"])
    source = spec["quarterly_source"]
    acquired = datetime.fromisoformat(source["acquired_at"])
    research_day = date.fromisoformat(spec["research_as_of"])
    published_day = date.fromisoformat(source["url"].split("/")[-2])
    if (acquired.utcoffset() is None
            or acquired.astimezone(ZoneInfo("Asia/Shanghai")).date() > research_day
            or published_day > acquired.astimezone(ZoneInfo("Asia/Shanghai")).date()
            or published_day > research_day):
        raise ValueError("SUCCESSOR_SOURCE_AFTER_RESEARCH_AS_OF")
    cash_facts = replay_quarterly_parent_cash(root=root, source=source, symbol=old_spec["symbol"],
        issuer_name=old_spec["issuer_name"], period_end=spec["period_end"], now=created)
    source_path = require_inside(root / "runtime", root / source["path"], "successor quarterly original")
    pages = extract_pages(source_path)
    observed = build_quarterly_parent_operating_observations(pages, symbol=old_spec["symbol"],
        issuer_name=old_spec["issuer_name"], period_end=spec["period_end"])
    if sha256(source_path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("SUCCESSOR_QUARTER_SOURCE_CHANGED")
    for row in observed:
        row["source_refs"] = [dict(ref, **source) for ref in row["source_refs"]]
    current, comparative = observed
    history = [row for binding in old_spec["operating_sources"]
        for row in read_parent_direct_cash_research(root=root, receipt_binding=binding,
            evaluated_at=created)["observed"]
        if row["period_end"] == old_spec["valuation_date"]]
    if (len(history) != 1 or spec["period_end"] != f"{int(old_spec['valuation_date'][:4])+1}-09-30"
            or set(spec["scenarios"]) != {"bear", "base", "bull"}):
        raise ValueError("SUCCESSOR_EXACT_FIRST_YEAR_CHAIN_REQUIRED")
    compiled = deepcopy(predecessor["compiled"])
    annuals = {}
    for name, input_row in spec["scenarios"].items():
        if set(input_row) != {"q4_forecast", "years", "terminal", "cost_of_equity",
                              "rationale", "counter_evidence", "reopen_condition",
                              "field_provenance"}:
            raise ValueError("SUCCESSOR_SCENARIO_CONTRACT_INVALID")
        if any(not _text(input_row[key]) for key in ("rationale", "counter_evidence", "reopen_condition")):
            raise ValueError("SUCCESSOR_SCENARIO_REASON_REQUIRED")
        q4 = input_row["q4_forecast"]
        if set(q4) != {"revenue", "cost", "other_operating_cash", "parent_profit",
                       "gross_capex", "investment_cash_received", "rationale",
                       "counter_evidence", "reopen_condition"}:
            raise ValueError("SUCCESSOR_EXACT_Q4_ASSUMPTION_REQUIRED")
        q4 = dict(q4, symbol=old_spec["symbol"], scope=old_spec["scope"], currency="CNY",
                  classification="FORECAST_ASSUMPTION", period_start=f"{spec['period_end'][:4]}-10-01",
                  period_end=f"{spec['period_end'][:4]}-12-31",
                  source_refs=[spec["predecessor_binding"], spec_binding, source])
        annual = build_parent_remaining_year_cash(historical_full_year=history[0],
            historical_nine_months=comparative, current_nine_months=current,
            q4_forecast=q4, as_of=created.date())
        rows = deepcopy(input_row["years"])
        old_years = compiled["scenarios"][name]["years"]
        changed_fields = set()
        if (len(rows) != len(old_years) or not rows
                or [r.get("year") for r in rows] != [r["year"] for r in old_years]):
            raise ValueError("SUCCESSOR_ALL_ANNUAL_PERIODS_REQUIRED")
        for row in rows:
            if set(row) != {"year", "policy"} or set(row["policy"]) != FLOW_KEYS:
                raise ValueError("SUCCESSOR_COMPLETE_ANNUAL_POLICY_REQUIRED")
            for amount in row["policy"].values():
                _number(amount)
            old_policy = old_years[[item["year"] for item in old_years].index(row["year"])]["policy"]
            for field in FLOW_KEYS:
                if _number(row["policy"][field]) != _number(old_policy[field]):
                    changed_fields.add(f"years.{row['year']}.policy.{field}")
            if (_number(row["policy"]["debt_repayment"])
                    < financing_maturity_floor(compiled["evidence"].get("constraints"), row["year"])):
                raise ValueError("DIRECT_INPUT_FINANCING_MATURITY_UNCOVERED")
        old_forecasts = compiled["operating_forecasts"][name]
        if (len(old_forecasts) != len(old_years)
                or any(_number(row["policy"]["operating_cash"])
                       != _number(old_forecasts[index]["operating_cash"])
                       for index, row in enumerate(rows) if index > 0)):
            raise ValueError("SUCCESSOR_LATER_OPERATING_FORECAST_MUST_INHERIT_VERIFIED_PREDECESSOR")
        if _number(rows[0]["policy"]["operating_cash"]) != _number(annual["full_year"]["cfo"]["total"]):
            raise ValueError("SUCCESSOR_FIRST_YEAR_CFO_NOT_RECALCULATED")
        if (_number(rows[0]["policy"]["parent_profit"])
                != _number(observed[0]["net_profit"]) + _number(q4["parent_profit"])):
            raise ValueError("SUCCESSOR_FIRST_YEAR_PROFIT_NOT_RECONCILED")
        if min(_number(q4["gross_capex"]), _number(q4["investment_cash_received"])) < 0:
            raise ValueError("SUCCESSOR_NEGATIVE_Q4_CAPITAL_FLOW")
        if (_number(rows[0]["policy"]["maintenance_capex"]) +
                _number(rows[0]["policy"]["growth_capex"]) !=
                _number(cash_facts["fields"]["cash_capex"]["current"]) +
                _number(q4["gross_capex"])):
            raise ValueError("SUCCESSOR_CAPEX_NOT_RECONCILED")
        if (_number(rows[0]["policy"]["investment_cash_received"])
                != _number(cash_facts["fields"]["investment_income_cash_cny"]["current"]) +
                _number(q4["investment_cash_received"])):
            raise ValueError("SUCCESSOR_INVESTMENT_RECEIPTS_NOT_RECONCILED")
        terminal = deepcopy(input_row["terminal"])
        if (set(terminal) != set(compiled["scenarios"][name]["terminal"])
                or set(terminal["policy"]) != FLOW_KEYS):
            raise ValueError("SUCCESSOR_COMPLETE_TERMINAL_REQUIRED")
        old_terminal = compiled["scenarios"][name]["terminal"]
        for field in FLOW_KEYS:
            if _number(terminal["policy"][field]) != _number(old_terminal["policy"][field]):
                changed_fields.add("terminal.policy." + field)
        if _number(input_row["cost_of_equity"]) != _number(compiled["scenarios"][name]["cost_of_equity"]):
            changed_fields.add("cost_of_equity")
        if ({key: value for key, value in terminal.items() if key != "policy"}
                != {key: value for key, value in old_terminal.items() if key != "policy"}):
            changed_fields.add("terminal.structure")
        provenance = input_row["field_provenance"]
        if not isinstance(provenance, dict) or set(provenance) != changed_fields:
            raise ValueError("SUCCESSOR_CHANGED_FIELD_PROVENANCE_REQUIRED")
        known_anchors = set(old_spec["fact_anchors"]) | {"Q3_PARENT_9M"}
        for path, declaration in provenance.items():
            if (not isinstance(declaration, dict)
                    or set(declaration) != {"classification", "evidence_anchors", "rationale",
                                            "counter_evidence", "reopen_condition"}
                    or declaration["classification"] != "FORECAST_ASSUMPTION"
                    or not isinstance(declaration["evidence_anchors"], list)
                    or not declaration["evidence_anchors"]
                    or any(anchor not in known_anchors for anchor in declaration["evidence_anchors"])
                    or any(not _text(declaration[key]) for key in
                           ("rationale", "counter_evidence", "reopen_condition"))):
                raise ValueError("SUCCESSOR_CHANGED_FIELD_EVIDENCE_INVALID:" + path)
            if (path.startswith(f"years.{rows[0]['year']}.policy.")
                    and path.rsplit(".", 1)[-1] in {"operating_cash", "parent_profit",
                        "maintenance_capex", "growth_capex", "investment_cash_received"}
                    and "Q3_PARENT_9M" not in declaration["evidence_anchors"]):
                raise ValueError("SUCCESSOR_Q3_ANCHOR_REQUIRED:" + path)
        calculation = compile_direct_owner_cash_path(opening=compiled["opening"],
            years=rows, terminal=terminal, ordinary_shares=compiled["ordinary_shares"],
            cost_of_equity=str(_number(input_row["cost_of_equity"])),
            scope=old_spec["scope"], currency="CNY")
        prior = compiled["scenarios"][name]
        prior.update(years=rows, terminal=terminal,
            cost_of_equity=input_row["cost_of_equity"], calculation=calculation,
            forecast_roes=[r["roe_assumption"] for r in calculation["annual_rows"]],
            forecast_retentions=[r["retention_assumption"] for r in calculation["annual_rows"]])
        compiled["operating_forecasts"][name] = [dict(
            year=rows[0]["year"], operating_cash=rows[0]["policy"]["operating_cash"],
            classification="FACT_9M_PLUS_Q4_FORECAST_ASSUMPTION",
            source_refs=[source, spec_binding], annual_components=annual,
            q4_assumptions=deepcopy(input_row["q4_forecast"]),
            field_provenance=input_row["field_provenance"].get(
                f"years.{rows[0]['year']}.policy.operating_cash",
                {"classification": "INHERITED_VERIFIED_PREDECESSOR",
                 "predecessor_binding": spec["predecessor_binding"]})),
            *deepcopy(old_forecasts[1:])]
        annuals[name] = annual
    compiled["assumptions"] = {name: dict(
        q4_forecast=deepcopy(input_row["q4_forecast"]),
        field_provenance=deepcopy(input_row["field_provenance"]),
        later_operating_forecasts_inherited_from=spec["predecessor_binding"])
        for name, input_row in spec["scenarios"].items()}
    compiled["source_bindings"] = [*compiled["source_bindings"],
        {"path": source["path"], "sha256": source["sha256"]}, spec_binding]
    package = _package(old_spec, compiled)
    annual_identity = old_spec["source_descriptors"][0]["issuer_identity"]
    annual_location = old_spec["source_descriptors"][0]["location"]
    if (annual_identity.get("security_code") != old_spec["symbol"]
            or not source_identity_matches_registered_issuer(
                symbol=old_spec["symbol"], location=annual_location,
                issuer_identity=annual_identity)):
        raise ValueError("SUCCESSOR_PREDECESSOR_ISSUER_IDENTITY_MISMATCH")
    quarter_descriptor = dict(
        id="cninfo:" + source["url"].rsplit("/", 1)[1].removesuffix(".PDF"),
        kind="quarterly_report", location=source["url"],
        local_path=source["path"], sha256=source["sha256"],
        retrieved_at=source["acquired_at"],
        parser_version="quarterly-parent-operating-facts-v1",
        issuer_identity=dict(venue="CNINFO", security_code=old_spec["symbol"],
            organization_id=annual_identity["organization_id"],
            issuer_name=annual_identity["issuer_name"]))
    quarter_ref = {"id": quarter_descriptor["id"], "sha256": source["sha256"]}
    package["sources"].append(quarter_descriptor)
    for refs in (package["facts"]["evidence_refs"], package["research_case"]["evidence_refs"]):
        if quarter_ref not in refs:
            refs.append(quarter_ref)
    package["run_id"] = spec["run_id"]
    package["point_in_time"].update(research_as_of=spec["research_as_of"],
        computed_at=spec["computed_at"], available_at=spec["computed_at"])
    package["research_case"].update(run_id=spec["run_id"],
        research_version=spec["research_version"], as_of=spec["research_as_of"],
        generated_at=spec["computed_at"])
    package["dependencies"]["rule_version"] = RECEIPT_SCHEMA
    package["source_contract"].update(schema_version=RECEIPT_SCHEMA,
        spec_sha256=spec_binding["sha256"], raw_source_bindings=compiled["source_bindings"],
        quarterly_source_context=dict(report_period=spec["period_end"],
            published_date_from_official_url=published_day.isoformat(),
            acquired_at=source["acquired_at"], publication_time_verified=False))
    for name, row in compiled["scenarios"].items():
        package["facts"]["scenario_inputs"][name] = scenario_to_payload(
            DirectOwnerCashScenario(cost_of_equity=Decimal(row["cost_of_equity"]),
                forecast_roes=tuple(Decimal(v) for v in row["forecast_roes"]),
                forecast_retentions=tuple(Decimal(v) for v in row["forecast_retentions"]),
                symbol=old_spec["symbol"], opening=row["opening"], years=row["years"],
                terminal=row["terminal"], ordinary_shares=Decimal(row["ordinary_shares"]),
                currency="CNY"))
    outcome, descriptor = run_direct_owner_cash_research(package, now=created, root=root)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("SUCCESSOR_SHARED_MODEL_NOT_CONSUMED:" + str(outcome.blockers))
    valuation = json.loads(outcome.valuation.to_json())
    for name, row in compiled["scenarios"].items():
        if valuation["assumptions"]["scenario_calculations"][name] != row["calculation"]:
            raise ValueError("SUCCESSOR_SHARED_MODEL_CALCULATION_CHANGED")
    for binding in compiled["source_bindings"]:
        _bound(root, binding)
    if sha256(source_path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("SUCCESSOR_QUARTER_SOURCE_CHANGED")
    return dict(schema_version=RECEIPT_SCHEMA, symbol=old_spec["symbol"],
        action="no_order", formal_eligibility=False,
        successor_adopted=False, main_range_adopted=False,
        predecessor_binding=spec["predecessor_binding"], spec_binding=spec_binding,
        quarterly_source=source, annual_recalculations=annuals,
        input_descriptor_sha256=descriptor.input_sha256, valuation=valuation,
        compiled=compiled, research_case=package["research_case"],
        package=package, research_result=_serialize_outcome(outcome),
        source_bindings=compiled["source_bindings"])


def replay_parent_remaining_year_successor(*, root, receipt_binding, now):
    receipt = _read(Path(root).resolve(), receipt_binding)
    if (receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("action") != "no_order"
            or receipt.get("implementation_sha256") != _implementations()):
        raise ValueError("SUCCESSOR_RECEIPT_VERSION_INVALID")
    expected = _recalculate(root=root, spec_binding=receipt["spec_binding"], now=now)
    stored = _read(Path(root).resolve(), receipt["result_binding"])
    def stable(value):
        value = deepcopy(value)
        for artifact in value["research_result"]["artifact_bundle"]["artifacts"]:
            artifact.pop("created_at", None)
        return value
    if (_bytes(stable(stored)) != _bytes(stable(expected))
            or receipt["input_descriptor_sha256"] != expected["input_descriptor_sha256"]
            or receipt["predecessor_binding"] != expected["predecessor_binding"]
            or receipt["symbol"] != expected["symbol"]
            or receipt["source_bindings"] != expected["source_bindings"]):
        raise ValueError("SUCCESSOR_COLD_REPLAY_CHANGED")
    return stored


def build_parent_remaining_year_successor(*, root, spec_binding, output_dir, now):
    root = Path(root).resolve()
    output = require_inside(root / "runtime", Path(output_dir).resolve(), "remaining year successor")
    if output.exists():
        raise FileExistsError("SUCCESSOR_NEW_OUTPUT_REQUIRED")
    result = _recalculate(root=root, spec_binding=spec_binding, now=now)
    result_binding = _write(root, output / "result.json", result)
    receipt = dict(schema_version=RECEIPT_SCHEMA, symbol=result["symbol"], action="no_order",
        predecessor_binding=result["predecessor_binding"], spec_binding=spec_binding,
        result_binding=result_binding, input_descriptor_sha256=result["input_descriptor_sha256"],
        source_bindings=result["source_bindings"],
        implementation_sha256=_implementations())
    receipt_binding = _write(root, output / "receipt.json", receipt)
    replay_parent_remaining_year_successor(root=root, receipt_binding=receipt_binding, now=now)
    return dict(receipt_binding=receipt_binding, result=result)
