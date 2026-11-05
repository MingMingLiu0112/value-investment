"""Read/recompile one explicitly registered first input using the existing engine."""
from datetime import datetime
import json
import re

from ..research.first_research_input_v1 import replay_first_research_input
from ..research.agent_review.web_research import _binding, _raw, MAX_JSON, _json

REGISTRY="config/current-first-research-inputs-v1.json"
SCHEMA="current-first-research-inputs-v1"


def read_first_research_input(*,root,symbol,now:datetime):
    base=dict(schema_version="first-research-input-view-v1",symbol=symbol,action="no_order",
        formal_eligibility=False,main_range_adopted=False,main_valuation_range=None,
        scope="CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
        current_price=None,condition_price=None,personal_quantity=None,
        user_acceptance="NOT_CONFIRMED",status="NOT_STARTED",
        reason="FIRST_INPUT_NOT_REGISTERED")
    if re.fullmatch(r"[0-9]{6}",symbol) is None:
        raise ValueError("Invalid first-research symbol")
    path=root/REGISTRY
    if not path.exists():
        return base
    try:
        registry=_json(_raw(path,64*1024))
        if (set(registry)!={"schema_version","action","cases"}
                or registry["schema_version"]!=SCHEMA or registry["action"]!="no_order"
                or not isinstance(registry["cases"],dict)):
            raise ValueError("First-input registry contract mismatch")
        entry=registry["cases"].get(symbol)
        if entry is None:return base
        if not isinstance(entry,dict) or set(entry)!={"receipt"}:
            raise ValueError("First-input registry entry invalid")
        ref=entry["receipt"]
        receipt_path=_binding(root,ref)
        import hashlib
        raw=_raw(receipt_path,MAX_JSON)
        if hashlib.sha256(raw).hexdigest()!=ref["sha256"]:
            raise ValueError("First-input receipt changed")
        receipt=_json(raw)
        if receipt.get("symbol")!=symbol or receipt.get("action")!="no_order":
            raise ValueError("First-input receipt issuer mismatch")
        # Public reads do not expose arbitrary local paths or private inputs.
        for binding in receipt.get("source_bindings",[]):
            _binding(root,binding,runtime_only=False)
        for key in ("spec_binding","package_binding","proposal_binding"):
            _binding(root,receipt[key],runtime_only=key!="spec_binding")
        result=replay_first_research_input(root=root,receipt_binding=ref,now=now)
        def bound_json(binding):
            target=_binding(root,binding,runtime_only=False)
            data=_raw(target,MAX_JSON)
            if hashlib.sha256(data).hexdigest()!=binding["sha256"]:
                raise ValueError("First-input consumed source changed after replay")
            return _json(data)
        package=bound_json(receipt["package_binding"])
        spec=bound_json(receipt["spec_binding"])
        assumptions=bound_json(spec["assumption_binding"])
        native=bound_json(spec["native_facts_binding"])
        if (result["research_case"]["symbol"]!=symbol or result["action"]!="no_order"
                or result["formal_eligibility"] is not False or result["main_range_adopted"] is not False):
            raise ValueError("First-input result changes formal research boundaries")
        return dict(base,status="SOURCE_BOUND_FIRST_INPUT_COMPILED",reason=None,
            input_fingerprint=result["input_fingerprint"],receipt_binding=ref,
            financial_basis=result["research_case"]["financial_period"],
            research_as_of=result["research_case"]["as_of"],
            research_case=result["research_case"],valuation=result["valuation"],
            valuation_status=result["valuation_status"],annual_ledgers=result["annual_ledgers"],
            blockers=result["blockers"],source_bindings=result["source_bindings"],
            compilation_scope=result["compilation_scope"],scenario_label_scope=result["scenario_label_scope"],
            sources=package["sources"],operating_assumptions=assumptions,
            native_fact_count=len(native["facts"]),
            source_review="NATIVE_FACT_ROWS_COLD_REPLAYED_NOT_ECONOMIC_APPROVAL",
            investment_conclusion="PRIMARY_RANGE_REJECTED_CONDITIONAL_PRESSURE_RESEARCH_ONLY")
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as error:
        return dict(base,status="UNASSESSABLE",reason=str(error))
