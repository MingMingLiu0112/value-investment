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
        if result.get("status") == "SOURCE_BOUND_FIRST_INPUT_COMPILED":
            from ...application.product.first_input_quote_alignment_v1 import read_first_input_quote_alignment
            result["e2_quote_alignment"] = read_first_input_quote_alignment(
                root=project, symbol=symbol, first_input=result, now=clock())
            result["successor_update"] = read_first_research_update(
                root=project, symbol=symbol, now=clock(), predecessor_binding=result["receipt_binding"])
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
