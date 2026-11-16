"""V18 term-specific historical candidate ledger for a conditional cash request."""
from dataclasses import replace
import json
import re

from . import operating_horizon_split_v13 as split
from . import operating_horizon_draft_v3 as full
from . import operating_cash_policy_draft_v14 as v14
from .operating_driver_draft_v2 import _payload

VERSION = "operating-horizon-request-v18-cash-historical-candidates"
PATTERNS = {
    "target_payout_ratio": r"dividend|distribution|split|分红|派息|权益分派|利润分配",
    "accessible_profit_ratio": r"parent|母公司|profit|净利润|cash.flow|经营.*现金|CFO",
    "reserve_ratio": r"parent|母公司|profit|净利润|cash|现金|reserve|留存|capex|购建",
    "net_maintenance_cash_cny": r"capex|购建|资本|固定资产|cash.flow|现金流",
    "operating_wc_cash_cny": r"working.capital|营运|经营.*现金|应收|存货|应付|CFO",
    "commitment_cash_cny": r"commitment|承诺|合同|在建|投资|购建|capex",
}
PREFERRED_IDS = {
    "target_payout_ratio": ("historical-split-implementation",),
    "accessible_profit_ratio": ("parent-cash-v2:investment_income_cash_cny", "parent-cash-v2:cfo_cny"),
    "reserve_ratio": ("parent-cash-v2:cash_end_cny", "parent-cash-v2:gross_capex_cny"),
    "net_maintenance_cash_cny": ("parent-cash-v2:gross_capex_cny", "parent_capex"),
    "operating_wc_cash_cny": ("parent-cash-v2:cfo_cny",),
    "commitment_cash_cny": ("horizon-p135", "horizon-p101"),
}


def candidates(context, source_binding):
    projected = split._project(context, source_binding)
    rows = [row for row in projected["evidence"] if row.get("period", "") < "2027-01-01"
            and not v14._MARKER.search(row["id"])]
    result = {}
    for term in full.TERMS:
        pattern = re.compile(PATTERNS[term], re.I)
        result[term] = [dict(id=row["id"], period=row["period"], scope=row["scope"],
            field=row.get("field"), value=row.get("value"), unit=row["unit"],
            source_id=row["source_id"], pdf_sha256=row["pdf_sha256"],
            text=row["text"]) for row in rows if pattern.search(" ".join(
                str(row.get(k, "")) for k in ("field", "text", "scope")))]
    return result


def build_cash_request(request, context, source_binding):
    ledger = candidates(context, source_binding)
    instructions = (VERSION + ": The attached TERM_HISTORICAL_CANDIDATES are verified historical "
        "source rows, never 2027 cash facts or default numeric assumptions. For each of the six "
        "terms in bear/base/bull, examine the relevant row IDs and period/scope/value separately. "
        "A numeric FORECAST_ASSUMPTION needs a cited candidate ID and a Mechanism: rationale "
        "that names its historical period, explains the conditional 2027 change, parent versus "
        "consolidated scope, economic reason and overturn condition. UNKNOWN/null is allowed "
        "when a defensible bridge is absent. FY2025 parent investment-income cash, parent CFO, and gross capex, plus 2026H1 parent CFO and gross capex, are historical parent-only anchors if present in the sealed rows. Assess whether they bound a conditional path; never auto-transfer them to 2027. Historical parent CFO is not accessible profit; "
        "gross capex is not proven maintenance cash; a commitment has no proven payment year. "
        "Historical split notices prove past implementation only, never a 2027 payout target. "
        "Do not infer that a prior_conditional_hypothesis exists. No forced buy or order.")
    # The V13 request already carries the full sealed evidence. Repeat only a
    # compact index here: the real 74-row source exceeds the request cap if
    # each matching row is copied again under several cash terms.
    selected = {}
    for term, rows in ledger.items():
        matches = [row["id"] for row in rows
            if any(marker in row["id"] for marker in PREFERRED_IDS[term])]
        selected[term] = list(dict.fromkeys(matches or [row["id"] for row in rows]))[:2]
    attached = json.dumps(selected,
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(request.user) + len(attached) > 76000:
        raise ValueError("V18_CANDIDATE_REQUEST_OVER_BUDGET")
    return replace(request, system=request.system + " " + instructions,
        user=request.user + "\nTERM_CANDIDATE_IDS=" + attached)


def validate_response(response, context, source_binding):
    ledger = candidates(context, source_binding)
    payload = _payload(response.text if hasattr(response, "text") else response)
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for term in full.TERMS:
            item = path[term]
            if item["classification"] == "FORECAST_ASSUMPTION":
                ids = {row["id"] for row in ledger[term]}
                if item["value"] is None or not ids.intersection(item["evidence_ids"]):
                    raise ValueError("V18_NUMERIC_TERM_LACKS_HISTORICAL_CANDIDATE")
    return True


