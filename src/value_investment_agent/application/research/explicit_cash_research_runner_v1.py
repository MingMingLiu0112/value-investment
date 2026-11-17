"""Explicit quarterly revalidation inputs through the existing v4 service.

Caller cold-verifies company/source semantics and compiles the three cash paths.
This read-only assembly does not collect sources, rebuild cash formulas, reuse
an old proposal, or grant research/main-range/price approval.
"""
from copy import deepcopy
from dataclasses import fields, replace
from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

from ...m1_valuation_package_builder import build_descriptor
from ...research_input import (ResearchInputDescriptor, ResearchSourceContract,
    finalize_input_descriptor, build_research_run_spec)
from ...research_application import ResearchApplicationService
from ..product.source_bound_inputs import (source_catalog_sha256, validate_source_bound_descriptor,
    verify_package_local_sources)
from ...valuation_models.residual_income_path_v4 import MODEL_VERSION
from .v4_input_adapter import scenario_payload, _v2_payload, V4ResearchInputDescriptor
from .v4_valuation_router import build_v4_valuation_router
from ...domain.valuation.operating_profit_cash_path_v1 import VERSION as CASH_VERSION, PROFIT_BASIS

VERSION = "quarterly-operating-revalidation-v1"
SCENARIOS = {"bear", "base", "bull"}


def _number(value):
    if not isinstance(value,(str,Decimal)):
        raise ValueError("EXPLICIT_CASH_FINITE_DECIMAL_REQUIRED")
    result=Decimal(value)
    if not result.is_finite():
        raise ValueError("EXPLICIT_CASH_FINITE_DECIMAL_REQUIRED")
    return result


def _text_metadata(value, expected):
    if (not isinstance(value,dict) or set(value)!=set(expected)
            or any(not isinstance(value[key],str) or not value[key].strip() for key in expected)):
        raise ValueError("EXPLICIT_CASH_METADATA_INVALID")


def run_explicit_cash_research(*, root: Path, template_package: dict,
        compiled_scenarios: dict, source_catalog: list, evidence_refs: list,
        assumption_metadata: dict, version_metadata: dict, now: datetime) -> dict:
    """Assemble a new descriptor and execute ResearchApplicationService once.

    compiled_scenarios: untouched bear/base/bull compile_operating_profit_cash_path
    results, including typed_scenario, rows, opening_state and terminal contract.
    version_metadata: run_id/generated_at/rationale/countercase (explicit strings).
    assumption_metadata: basis/rationale/confidence/sensitivity (explicit strings).
    Returns descriptor/package/outcome/annual_ledgers; typed objects are retained
    deliberately for the caller's existing serializer. No output is persisted.
    """
    root=Path(root).resolve()
    _text_metadata(version_metadata,("run_id","generated_at","rationale","countercase"))
    _text_metadata(assumption_metadata,("basis","rationale","confidence","sensitivity"))
    made=datetime.fromisoformat(version_metadata["generated_at"])
    if made.utcoffset() is None or now.utcoffset() is None or made>now:
        raise ValueError("EXPLICIT_CASH_TIME_INVALID")
    if (template_package.get("schema_version")!="m1-valuation-package-v2"
            or template_package.get("facts",{}).get("kind")!="quality_compounder"
            or not template_package.get("source_contract")
            or not isinstance(compiled_scenarios,dict) or set(compiled_scenarios)!=SCENARIOS):
        raise ValueError("EXPLICIT_CASH_SOURCE_BOUND_TEMPLATE_AND_THREE_SCENARIOS_REQUIRED")
    if version_metadata["run_id"]==template_package["run_id"]:
        raise ValueError("EXPLICIT_CASH_NEW_RUN_ID_REQUIRED")
    data=deepcopy(template_package)
    catalog=deepcopy(source_catalog)
    refs=deepcopy(evidence_refs)
    if not isinstance(catalog,list) or not catalog or not isinstance(refs,list) or not refs:
        raise ValueError("EXPLICIT_CASH_SOURCE_REFS_REQUIRED")
    by_id={row["id"]:row for row in catalog}
    if len(by_id)!=len(catalog) or len({ref["id"] for ref in refs})!=len(refs):
        raise ValueError("EXPLICIT_CASH_DUPLICATE_SOURCE_OR_REFERENCE")
    bound=verify_package_local_sources(root,dict(schema_version="m1-valuation-package-v2",sources=catalog))
    for ref in refs:
        row=by_id.get(ref.get("id"))
        if row is None or ref.get("path")!=row["local_path"] or ref.get("sha256")!=row["sha256"]:
            raise ValueError("EXPLICIT_CASH_EVIDENCE_CATALOG_MISMATCH")
    typed,ledgers={},{}
    book=_number(data["facts"]["operating_inputs"]["start_book_equity"])
    shares=_number(data["facts"]["operating_inputs"]["ordinary_shares"])
    for name, result in compiled_scenarios.items():
        if (result.get("version")!=CASH_VERSION or result.get("profit_basis")!=PROFIT_BASIS
                or result.get("action")!="no_order" or result.get("formal_eligibility") is not False
                or result.get("funding_status")!="FUNDED" or len(result.get("rows",[]))!=10):
            raise ValueError("EXPLICIT_CASH_COMPILED_TEN_YEAR_PATH_REQUIRED")
        scenario=result["typed_scenario"]
        scenario_payload(scenario)  # Existing typed/terminal contract validation.
        if (result["terminal_economic_contract"]!=scenario.terminal_economic_contract
                or _number(result["opening_state"]["book_equity_cny"])!=book
                or _number(result["opening_state"]["ordinary_shares"])!=shares
                or result["opening_state"]["as_of"]!=data["point_in_time"]["valuation_date"]):
            raise ValueError("EXPLICIT_CASH_OPENING_OR_TERMINAL_MISMATCH")
        for index,row in enumerate(result["rows"]):
            if (type(row["year"]) is not int or row["year"]!=index+1
                    or _number(row["forecast_roe"])!=scenario.forecast_roes[index]
                    or _number(row["retention"])!=scenario.forecast_retentions[index]):
                raise ValueError("EXPLICIT_CASH_LEDGER_SCENARIO_MISMATCH")
        typed[name]=scenario
        ledgers[name]=deepcopy({k:v for k,v in result.items() if k!="typed_scenario"})
    serialized={name:scenario_payload(item) for name,item in typed.items()}
    data.update(descriptor_version=VERSION,run_id=version_metadata["run_id"],sources=catalog)
    # No carried-forward trade/market/research approval can approve new inputs.
    for key in ("quote","model_validity_input","valuation_approval","distribution_result",
            "entry_thesis","investment_consistency_review","human_research_approval",
            "event_materiality_review","valuation","model_validity","price_bridge",
            "decision_recommendation","position_guidance"):
        data.pop(key,None)
    as_of=made.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    data["point_in_time"].update(research_as_of=as_of,available_at=made.isoformat(),computed_at=made.isoformat())
    case=data["research_case"]
    case.update(as_of=as_of,generated_at=made.isoformat(),run_id=data["run_id"],
        research_version=VERSION,evidence_refs=refs,quote_date=None,
        thesis=version_metadata["rationale"],counter_evidence=[dict(kind="interpretation",
            text=version_metadata["countercase"],evidence_refs=[ref["id"] for ref in refs])],
        blockers=list(dict.fromkeys([*case.get("blockers",[]),"ECONOMIC_RESEARCH_NOT_APPROVED",
            "EXPLICIT_CASH_INPUTS_NOT_ADOPTED_MAIN_RANGE"])))
    data["dependencies"].update(rule_version=VERSION,model_version=MODEL_VERSION)
    data["facts"].update(scenario_inputs=serialized,evidence_refs=refs)
    paths=["cost_of_equity","terminal_roe","terminal_growth"]+[
        f"{prefix}.{i}" for prefix in ("forecast_roes","forecast_retentions") for i in range(10)]
    rows,bindings=[],[]
    for path in paths:
        bits=path.split(".")
        values={name:(value[bits[0]][int(bits[1])] if len(bits)==2 else value[path])
            for name,value in serialized.items()}
        rows.append(dict(name=path,unit="ratio",**values,**assumption_metadata,
            ordering="non_monotonic",evidence_refs=refs))
        bindings.extend(dict(assumption_name=path,scenario=name,field_path=path,
            expected_value=value,evidence_refs=refs) for name,value in values.items())
    data["assumptions"]=dict(assumptions=rows,evidence_refs=refs,blockers=[])
    data["assumption_bindings"]=bindings
    data["source_contract"].update(cutoff_at=made.isoformat(),source_catalog_sha256=source_catalog_sha256(catalog))
    compatibility=deepcopy(data)
    compatibility["facts"]["scenario_inputs"]={name:_v2_payload(item) for name,item in serialized.items()}
    parse=deepcopy(compatibility)
    parse["schema_version"]="m1-valuation-package-v1"
    parse.pop("source_contract",None)
    legacy=build_descriptor(parse,root=root)
    values={field.name:getattr(legacy,field.name) for field in fields(ResearchInputDescriptor)}
    values.update(distribution_result=None,source_contract=ResearchSourceContract.from_payload(data["source_contract"]),input_sha256=None)
    validated=finalize_input_descriptor(ResearchInputDescriptor(**values))
    validate_source_bound_descriptor(compatibility,validated)
    values={field.name:getattr(validated,field.name) for field in fields(ResearchInputDescriptor)}
    values.update(facts=replace(validated.facts,scenario_inputs=typed),input_sha256=None)
    descriptor=finalize_input_descriptor(V4ResearchInputDescriptor(**values))
    outcome=ResearchApplicationService(router=build_v4_valuation_router(),now_utc=lambda:now).run_company_research(
        build_research_run_spec(descriptor))
    if any(hashlib.sha256(path.read_bytes()).hexdigest()!=digest for path,digest in bound):
        raise ValueError("EXPLICIT_CASH_SOURCE_BYTES_CHANGED")
    return dict(schema_version=VERSION,descriptor=descriptor,package=data,outcome=outcome,
        annual_ledgers=ledgers,input_descriptor_sha256=descriptor.input_sha256,
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        action="no_order",formal_eligibility=False,main_range_adopted=False,
        condition_price=None,personal_quantity=None)
