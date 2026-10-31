"""Public read-only D2 assumptions; never execute a task or approve research."""
from datetime import datetime, timezone
import re

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from ...application.research.operating_assumption_draft_v1 import load_operating_assumption_draft


def register_operating_assumption_routes(api: FastAPI, *, project,
                                        clock=lambda: datetime.now(timezone.utc)):
    @api.get("/api/v1/research-assumption-drafts/{symbol}")
    def operating_assumption_draft(symbol: str):
        headers = {"Cache-Control": "no-store"}
        if re.fullmatch(r"[0-9]{6}", symbol) is None:
            return JSONResponse({"action":"no_order","status":"INVALID_SYMBOL"},status_code=422,headers=headers)
        try:
            result = load_operating_assumption_draft(root=project,symbol=symbol,now=clock())
        except (ValueError,OSError,KeyError,TypeError) as error:
            result = dict(schema_version="operating-assumption-draft-v1",symbol=symbol,
                action="no_order",status="UNASSESSABLE",formal_eligibility=False,
                valuation_computed=False,branches=[],source_bindings=[],
                blockers=["SOURCE_OR_ASSUMPTION_CONTRACT_REJECTED"],reason=str(error))
        return JSONResponse(result,headers=headers)
