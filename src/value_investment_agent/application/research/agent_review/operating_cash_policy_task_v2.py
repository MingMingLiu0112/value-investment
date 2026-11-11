"""Source-bound D2 cash follow-up with an explicit dividend-profit denominator.

It shares the existing task store, provider budget and response schema. The
versioned source manifest pins this adapter; historical v7 tasks stay intact.
"""
from dataclasses import replace
import json
import re

from .operating_cash_policy_task_v1 import OperatingCashPolicyTaskService
from .operating_policy_denominator_review_v1 import review_task_view

PLAN_ID = "cninfo:1224808850:conditional-return-plan"
APPROVAL_ID = "cninfo:1225321219:approved-return-plan"
CONDITION_ID = "cninfo:1224808850:return-plan-conditions"
CORRECT_DENOMINATOR = re.compile(
    r"consolidated\s+(?:net\s+)?profit\s+attributable\s+to\s+(?:parent\s+)?shareholders|"
    r"(?:合并)?归(?:属)?母(?:公司股东)?净利润|归属于母公司股东净利润",
    flags=re.IGNORECASE,
)


class OperatingCashPolicyTaskServiceV2(OperatingCashPolicyTaskService):
    def _request(self, spec, context):
        rows = {row.get("id"): row for row in context.get("evidence", [])}
        if not all(key in rows for key in (PLAN_ID, APPROVAL_ID, CONDITION_ID)):
            raise ValueError("V8_PLAN_APPROVAL_AND_CONDITIONS_REQUIRED")
        base = super()._request(spec, context)
        anchor = dict(fiscal_years=[2025, 2026, 2027], conditional_minimum_ratio="0.75",
            profit_denominator="consolidated_profit_attributable_to_parent_shareholders",
            historical_dps_floor_cny="1.22", approved_plan_evidence_ids=[PLAN_ID, APPROVAL_ID, CONDITION_ID],
            limitation="Subject to operating funding needs and future board/shareholder distribution approval; not parent cash capacity or a forecast payment.")
        return replace(base,
            user=base.user + "\nSOURCE_BOUND_APPROVED_CONDITIONAL_RETURN_PLAN="
                + json.dumps(anchor, ensure_ascii=False, sort_keys=True),
            system=base.system + " For a target_payout_ratio citing this approved plan, the denominator is "
                "consolidated profit attributable to parent shareholders, NEVER standalone-parent net profit. "
                "State that denominator explicitly in every quantified scenario rationale. The policy's 75% "
                "floor is conditional on operating funding needs and later dividend approval; it cannot establish "
                "parent accessible cash, reserves, maintenance, working capital or scheduled commitments. "
                "If those terms lack separately reasoned scenarios, retain UNKNOWN.")

    def _result(self, spec, state, context):
        result = super()._result(spec, state, context)
        if result is None:
            return None
        review = review_task_view({"research_result": result})["economic_validation"]
        if review["status"] == "REJECTED":
            raise ValueError("SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT")
        for row in result["years"].values():
            for path in row["shareholder_cash_paths"].values():
                term = path["terms"]["target_payout_ratio"]
                if (term["classification"] == "FORECAST_ASSUMPTION"
                        and PLAN_ID in term["evidence_ids"]
                        and not CORRECT_DENOMINATOR.search(term["rationale"])):
                    raise ValueError("SOURCE_PAYOUT_PROFIT_DENOMINATOR_NOT_EXPLICIT")
        return result
