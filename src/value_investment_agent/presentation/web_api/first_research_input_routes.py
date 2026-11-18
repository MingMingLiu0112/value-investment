"""Public immutable-input replay, not a research-start or approval endpoint."""
from datetime import datetime,timezone
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from ...application.product.first_research_input_view_v1 import read_first_research_input
from ...application.product.first_research_update_view_v1 import read_first_research_update
from ...application.product.quote_bridge import execute_quote_bridge_for_symbol


def register_first_research_input_routes(api:FastAPI,*,project,clock=lambda:datetime.now(timezone.utc)):
    @api.get("/api/v1/first-research-inputs/{symbol}")
    def first_research_input(symbol:str):
        try:
            result=read_first_research_input(root=project,symbol=symbol,now=clock())
        except ValueError as error:
            return JSONResponse(dict(action="no_order",status="INVALID_SYMBOL",reason=str(error)),
                status_code=422,headers={"Cache-Control":"no-store"})
        if result.get("receipt_schema_version") == "parent-remaining-year-successor-receipt-v1":
            from ...application.research.parent_remaining_year_alignment import read_parent_remaining_year_alignment
            try:
                result["direct_cash_alignment"] = read_parent_remaining_year_alignment(
                    root=project, receipt_binding=result["receipt_binding"], now=clock())
            except (ValueError, OSError, KeyError, TypeError, AttributeError, ArithmeticError) as error:
                result["direct_cash_alignment"] = dict(
                    schema_version="parent-remaining-year-alignment-v1", status="BLOCKED",
                    reason_codes=["SUCCESSOR_ALIGNMENT_SOURCE_REPLAY_FAILED: " + str(error)],
                    research_artifact_kind="PARENT_REMAINING_YEAR_SUCCESSOR_RECEIPT",
                    receipt_binding=result["receipt_binding"],
                    candidate_binding=result["receipt_binding"],
                    input_descriptor_sha256=result.get("input_descriptor_sha256"),
                    checks=[], evidence_bindings=[], currentpricecomparison=False,
                    formal_eligibility=False, action="no_order")
            result["e2_quote_alignment"] = dict(
                schema_version="first-input-quote-alignment-v1", status="UNASSESSABLE",
                reason="E2_QUOTE_ALIGNMENT_NOT_APPLICABLE_TO_REMAINING_YEAR_SUCCESSOR",
                quote_usable_for_e2_research=False, current_valuation_comparable=False,
                condition_price=None, formal_eligibility=False, action="no_order")
            result["successor_update"] = dict(
                status="NOT_APPLICABLE", reason="DISPLAYED_RECEIPT_IS_REMAINING_YEAR_SUCCESSOR",
                action="no_order", formal_eligibility=False, price_admitted=False)
            result["quote_observation"] = dict(
                status="NOT_REQUESTED_FOR_SUCCESSOR_F2_PROJECTION",
                reason="QUOTE_REQUIRES_EXACT_BOUND_F2_EVIDENCE",
                display_price=None, price_admitted=False, comparison_eligible=False)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        if result.get("status") == "SOURCE_BOUND_FIRST_INPUT_COMPILED":
            if result.get("direct_owner_cash") is not None:
                from ...application.research.direct_owner_cash_alignment_v1 import read_direct_owner_cash_alignment
                try:
                    result["direct_cash_alignment"] = read_direct_owner_cash_alignment(
                        root=project, receipt_binding=result["receipt_binding"], now=clock())
                except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
                    result["direct_cash_alignment"] = dict(
                        schema_version="direct-owner-cash-alignment-v1",
                        research_artifact_kind="DIRECT_OWNER_CASH_RECEIPT",
                        status="BLOCKED", action="no_order", formal_eligibility=False,
                        currentpricecomparison=False,
                        receipt_binding=result["receipt_binding"],
                        candidate_binding=result["receipt_binding"],
                        input_descriptor_sha256=result.get("input_descriptor_sha256"),
                        valuation_date=result.get("financial_basis"),
                        reason_codes=["DIRECT_ALIGNMENT_SOURCE_REPLAY_FAILED: " + str(error)],
                        checks=[], evidence_bindings=[])
            from ...application.product.first_input_quote_alignment_v1 import read_first_input_quote_alignment
            result["e2_quote_alignment"] = read_first_input_quote_alignment(
                root=project, symbol=symbol, first_input=result, now=clock())
            result["successor_update"] = read_first_research_update(
                root=project, symbol=symbol, now=clock(), displayed_binding=result["receipt_binding"])
            if (result["successor_update"].get("status") == "UNASSESSABLE"
                    and result["successor_update"].get("reason") ==
                    "E1 predecessor differs from the currently displayed first input"):
                historical = read_first_research_update(
                    root=project, symbol=symbol, now=clock())
                if historical.get("status") == "SOURCE_BOUND_CONDITIONAL_SUCCESSOR":
                    # Both old versions cold replay, but this chain is not a
                    # successor of the first input currently shown above.
                    result["historical_successor_update"] = historical
            # A verified close is a separate observation. It must not populate
            # current_price or turn this historical conditional study into F2.
            try:
                bridge = execute_quote_bridge_for_symbol(project, symbol, today=clock())
                quote = bridge.get("quote") or {}
                result["quote_observation"] = {
                    "status": bridge["status"],
                    "reason": bridge.get("reason"),
                    "research_day": bridge.get("research_day"),
                    "quote_verification_status": bridge.get("quote_verification_status"),
                    "quote_date": quote.get("quote_date"),
                    "display_price": quote.get("display_price"),
                    "bundle_sha256": quote.get("bundle_sha256"),
                    "price_admitted": bridge.get("price_admitted") is True,
                    "comparison_eligible": (bridge.get("compatibility") or {}).get(
                        "comparison_eligible", {}).get("eligible") is True,
                }
            except (ValueError, OSError, KeyError, TypeError):
                result["quote_observation"] = {
                    "status": "UNASSESSABLE", "reason": "QUOTE_OBSERVATION_REPLAY_FAILED",
                    "research_day": None, "quote_verification_status": None,
                    "quote_date": None,
                    "display_price": None, "bundle_sha256": None,
                    "price_admitted": False, "comparison_eligible": False,
                }
        return JSONResponse(result,headers={"Cache-Control":"no-store"})
