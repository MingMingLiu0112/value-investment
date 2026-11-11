"""Annual research with official supplemental context and explicit cost mechanisms."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from . import operating_horizon_draft_v1 as prior
from . import operating_draft_v1 as common
from .operating_driver_draft_v2 import _payload, _exact
from ....infrastructure.agent_runtime.provider import LLMResponse

VERSION="operating-horizon-draft-v2"
MECHANISMS=("INPUT_PRICE", "INDEPENDENT_EFFICIENCY", "UNRESOLVED_SENSITIVITY")


def build_request(context, years, max_completion_tokens=4096):
    request=prior.build_request(context,years,max_completion_tokens)
    schema=deepcopy(request.output_schema)
    for row in schema["properties"]["years"]["properties"].values():
        for path in row["properties"]["operating_paths"]["properties"].values():
            path["required"].append("unit_cost_mechanism")
            path["properties"]["unit_cost_mechanism"]={"type":"string","enum":list(MECHANISMS)}
    return replace(request,output_schema=schema,system=request.system+" " + VERSION +
        ": Use the bound interim report and acquisition/consolidation period excerpts when supplied. "
        "Do not request documents already in this context as future events. Separate consolidation "
        "coverage from same-scope volume and price/mix; never annualize H1 mechanically. "
        "Every other_pretax_cny must cite consolidated pre_tax_profit as the residual anchor, "
        "and must never cite parent cash/investment receipts as consolidated earnings evidence. "
        "Residual includes finance costs and other earnings; it is neither cash nor wholly nonrecurring. "
        "unit_cost_mechanism must be INPUT_PRICE, INDEPENDENT_EFFICIENCY, or UNRESOLVED_SENSITIVITY. "
        "Fixed-cost absorption is already in fixed_cogs_share, so never count scale dilution again "
        "in unit_cost_change. fixed_cogs_share is the uncertain historical cost split, not future utilisation. "
        "Use UNRESOLVED_SENSITIVITY when numbers have no empirical derivation; do not claim they are proven. "
        "UNKNOWN capital MUST have lower=null, upper=null, unit=not_quantified. Distinguish missing "
        "context from company non-disclosure. All numerical ranges remain unadopted sensitivity hypotheses.")


def validate_response(response,context,years,generated_at):
    text=response.text if isinstance(response,LLMResponse) else response
    payload=_payload(text)
    _exact(payload,("years",))
    _exact(payload["years"],[str(y) for y in years])
    evidence={row["id"]:row for row in context["evidence"]}
    basis,plans=prior.annual_plan(context,years)
    mechanisms={}
    for year,row in payload["years"].items():
        _exact(row["operating_paths"],("bear","base","bull"))
        mechanisms[year]={}
        for name,path in row["operating_paths"].items():
            mechanism=path.pop("unit_cost_mechanism",None)
            if mechanism not in MECHANISMS:
                raise ValueError("INDEPENDENT_UNIT_COST_MECHANISM_REQUIRED")
            refs=path["drivers"]["other_pretax_cny"]["evidence_ids"]
            cited=[evidence.get(ref,{}) for ref in refs]
            if any(r.get("scope")=="parent" or str(r.get("field","")).startswith("parent_") for r in cited):
                raise ValueError("PARENT_CASH_NOT_CONSOLIDATED_EARNINGS_EVIDENCE")
            anchor=basis["baselines"][plans[year]["baseline_period"]]["fields"]["pre_tax_profit"]["evidence_id"]
            if anchor not in refs:
                raise ValueError("CONSOLIDATED_PRETAX_RESIDUAL_ANCHOR_REQUIRED")
            mechanisms[year][name]=mechanism
    sanitized=common._canonical(payload)
    forwarded=replace(response,text=sanitized) if isinstance(response,LLMResponse) else sanitized
    result=prior.validate_response(forwarded,context,years,generated_at)
    result.update(schema_version=VERSION,prompt_version=VERSION,
        response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        quantification_status="CONDITIONAL_SENSITIVITY_NOT_EMPIRICALLY_PROVEN_BOUNDS")
    for year,row in result["years"].items():
        row["unit_cost_mechanisms"]=mechanisms[year]
    return result
