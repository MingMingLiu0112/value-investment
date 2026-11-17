"""Immutable receipt/replay and existing shared service for direct owner cash."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from .direct_owner_cash_compilation_v1 import compile_source_bound_owner_cash
from .direct_owner_cash_input_adapter_v1 import run_direct_owner_cash_research, DESCRIPTOR_VERSION
from .parent_direct_cash_research import _bound, _unique
from ...valuation_models.direct_owner_cash_v1 import MODEL_ID, MODEL_VERSION, SCENARIO_CONTRACT
from ..product.company_research import _serialize_outcome
from ..product.common import require_inside

RECEIPT_SCHEMA = "direct-owner-cash-first-input-receipt-v1"
FILES = (
 "application/research/direct_owner_cash_compilation_v1.py",
 "application/research/direct_owner_cash_research_v1.py",
 "application/research/direct_owner_cash_input_adapter_v1.py",
 "application/research/parent_direct_owner_cash_sources.py",
 "application/research/parent_direct_cash_research.py",
 "application/research/parent_cash_research.py",
 "application/decision/direct_owner_cash_price_draft_v1.py",
 "domain/decision/value_price_policy.py",
 "infrastructure/filings/pdf_text.py",
 "infrastructure/filings/pdfium_runtime.py",
 "domain/valuation/direct_parent_owner_cash_v1.py",
 "domain/valuation/parent_direct_operating_cash.py",
 "valuation_models/direct_owner_cash_v1.py",
 "valuation_models/residual_income_path_v4.py",
)
def _bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def _implementations():
    source=Path(__file__).resolve().parents[2]
    return {name:sha256((source/name).read_bytes()).hexdigest() for name in FILES}
def _read(root,binding):
    _, raw=_bound(root,binding)
    return json.loads(raw,object_pairs_hook=_unique)
def _write(root,path,value):
    path=require_inside(root/"runtime",path,"direct owner output")
    path.parent.mkdir(parents=True,exist_ok=True)
    data=_bytes(value)
    with path.open("xb") as stream:stream.write(data)
    return dict(path=path.relative_to(root).as_posix(),sha256=sha256(data).hexdigest())

def _package(spec,compiled):
    from ...valuation_models.direct_owner_cash_v1 import DirectOwnerCashScenario, scenario_to_payload
    from decimal import Decimal
    sources=deepcopy(spec["source_descriptors"])
    pinned={(row["path"],row["sha256"]) for row in spec["owner_sources"]}
    if {(row["local_path"],row["sha256"]) for row in sources} != pinned:
        raise ValueError("DIRECT_RESEARCH_SOURCE_DESCRIPTOR_BINDING_MISMATCH")
    refs=[dict(id=row["id"],sha256=row["sha256"]) for row in sources]
    scenarios={}
    for name,row in compiled["scenarios"].items():
        scenarios[name]=scenario_to_payload(DirectOwnerCashScenario(
            cost_of_equity=Decimal(row["cost_of_equity"]),
            forecast_roes=tuple(Decimal(x) for x in row["forecast_roes"]),
            forecast_retentions=tuple(Decimal(x) for x in row["forecast_retentions"]),
            symbol=spec["symbol"],opening=row["opening"],years=row["years"],terminal=row["terminal"],
            ordinary_shares=Decimal(row["ordinary_shares"]),currency="CNY"))
    case=deepcopy(spec["research_case"])
    case.update(symbol=spec["symbol"],name=spec["issuer_name"],as_of=spec["research_as_of"],
        run_id=spec["run_id"],research_version=spec["research_version"],generated_at=spec["computed_at"],
        evidence_status="verified",valuation_status="conditional_research_only",research_status="PENDING_REVIEW",
        financial_period=spec["valuation_date"],evidence_refs=refs, missing_date_reasons={"quote_date":"Historical conditional research; no current-price comparison"},
        blockers=list(dict.fromkeys([*case.get("blockers",[]),"ECONOMIC_RESEARCH_NOT_APPROVED"])))
    return dict(schema_version="m1-valuation-package-v2",descriptor_version=DESCRIPTOR_VERSION,
        symbol=spec["symbol"],name=spec["issuer_name"],profile_id="quality_compounder",
        requested_model=MODEL_ID,run_id=spec["run_id"],
        point_in_time=dict(report_period=spec["valuation_date"],valuation_date=spec["valuation_date"],
            research_as_of=spec["research_as_of"],available_at=spec["computed_at"],computed_at=spec["computed_at"]),
        dependencies=dict(rule_version=RECEIPT_SCHEMA,model_id=MODEL_ID,model_version=MODEL_VERSION,
            parser_version="parent-direct-owner-cash-sources-v1"),
        sources=sources,research_case=case,
        facts=dict(kind="quality_compounder",symbol=spec["symbol"],as_of=spec["valuation_date"],
            verified=True,confidence="低",evidence_refs=refs,blockers=[],
            operating_inputs=dict(start_book_equity=compiled["opening"]["book"],
                opening_cash=compiled["opening"]["cash"],ordinary_shares=compiled["ordinary_shares"]),
            scenario_inputs=scenarios),
        assumptions=None,assumption_bindings=[],
        source_contract=dict(schema_version="source-bound-direct-owner-cash-v1",
            strict_contemporaneous_pit=False,spec_sha256=sha256(_bytes(spec)).hexdigest(),
            raw_source_bindings=compiled["source_bindings"],implementation_sha256=_implementations()))

def execute_direct_owner_cash_spec(*,root,spec_binding,now):
    spec=_read(root,spec_binding)
    created=datetime.fromisoformat(spec["computed_at"])
    if created.utcoffset() is None or created>now:
        raise ValueError("DIRECT_RESEARCH_FUTURE_OR_NAIVE_INPUT")
    if spec.get("profile_id")!="quality_compounder" or spec.get("model_applicable") is not True:
        raise ValueError("DIRECT_RESEARCH_PROFILE_NOT_APPLICABLE")
    # Model applicability is a research assertion, not classifier or quality approval.
    if not spec.get("model_applicability_evidence"):
        raise ValueError("DIRECT_RESEARCH_PROFILE_EVIDENCE_REQUIRED")
    compiled=compile_source_bound_owner_cash(root=root,spec=spec,now=created)
    package=_package(spec,compiled)
    outcome,descriptor=run_direct_owner_cash_research(package,now=created,root=root)
    if outcome.valuation is None or outcome.valuation.status!="conditional_research_only":
        raise ValueError("DIRECT_RESEARCH_SHARED_MODEL_NOT_CONSUMED")
    value=json.loads(outcome.valuation.to_json())
    for name,row in compiled["scenarios"].items():
        if value["assumptions"]["scenario_calculations"][name]!=row["calculation"]:
            raise ValueError("DIRECT_RESEARCH_ANNUAL_CONSUMPTION_MISMATCH")
    for binding in compiled["source_bindings"]:
        _bound(root,binding)
    result=_serialize_outcome(outcome)
    return dict(symbol=spec["symbol"],action="no_order",formal_eligibility=False,
        main_range_adopted=False,main_valuation_range=None,
        input_descriptor_sha256=descriptor.input_sha256,
        input_fingerprint=sha256(_bytes(descriptor.as_policy())).hexdigest(),
        valuation=value,valuation_status=outcome.valuation.status,research_case=package["research_case"],
        compiled=compiled,package=package,research_result=result,artifact_bundle=result["artifact_bundle"],
        source_bindings=compiled["source_bindings"],blockers=result["blockers"],
        scenario_label_scope="CONDITIONAL_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
        compilation_scope="SOURCE_REPLAYED_DIRECT_PARENT_CASH_NOT_CURRENT_PRICE_OR_APPROVAL")

def build_direct_owner_cash_receipt(*,root,spec_binding,output_dir,now):
    root=Path(root).resolve()
    output=require_inside(root/"runtime",Path(output_dir).resolve(),"direct owner receipt")
    if output.exists():raise FileExistsError("DIRECT_RESEARCH_NEW_OUTPUT_REQUIRED")
    result=execute_direct_owner_cash_spec(root=root,spec_binding=spec_binding,now=now)
    result_binding=_write(root,output/"result.json",result)
    receipt=dict(schema_version=RECEIPT_SCHEMA,symbol=result["symbol"],action="no_order",
        spec_binding=spec_binding,result_binding=result_binding,implementation_sha256=_implementations(),
        source_bindings=result["source_bindings"],formal_eligibility=False,
        input_descriptor_sha256=result["input_descriptor_sha256"])
    binding=_write(root,output/"receipt.json",receipt)
    replay_direct_owner_cash_receipt(root=root,receipt_binding=binding,now=now)
    return dict(receipt_binding=binding,result=result)

def replay_direct_owner_cash_receipt(*,root,receipt_binding,now):
    receipt=_read(root,receipt_binding)
    if (receipt.get("schema_version")!=RECEIPT_SCHEMA or receipt.get("action")!="no_order"
            or receipt.get("implementation_sha256")!=_implementations()):
        raise ValueError("DIRECT_RESEARCH_RECEIPT_OR_IMPLEMENTATION_CHANGED")
    expected=_read(root,receipt["result_binding"])
    result=execute_direct_owner_cash_spec(root=root,spec_binding=receipt["spec_binding"],now=now)
    def economic_payload(value):
        value=deepcopy(value)
        # Repository insertion clocks are actual storage events, not economic inputs.
        for bundle in (value["artifact_bundle"],value["research_result"]["artifact_bundle"]):
            for artifact in bundle["artifacts"]:
                artifact.pop("created_at",None)
        return value
    if _bytes(economic_payload(result))!=_bytes(economic_payload(expected)) or result["symbol"]!=receipt["symbol"]:
        raise ValueError("DIRECT_RESEARCH_COLD_REPLAY_CHANGED")
    if result["source_bindings"] != receipt["source_bindings"]:
        raise ValueError("DIRECT_RESEARCH_SOURCE_CLOSURE_CHANGED")
    if result["input_descriptor_sha256"]!=receipt["input_descriptor_sha256"]:
        raise ValueError("DIRECT_RESEARCH_DESCRIPTOR_CHANGED")
    return expected
