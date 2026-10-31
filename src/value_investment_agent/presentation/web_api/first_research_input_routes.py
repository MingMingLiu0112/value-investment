"""Public immutable-input replay, not a research-start or approval endpoint."""
from datetime import datetime,timezone
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from ...application.product.first_research_input_view_v1 import read_first_research_input


def register_first_research_input_routes(api:FastAPI,*,project,clock=lambda:datetime.now(timezone.utc)):
    @api.get("/api/v1/first-research-inputs/{symbol}")
    def first_research_input(symbol:str):
        try:
            result=read_first_research_input(root=project,symbol=symbol,now=clock())
        except ValueError as error:
            return JSONResponse(dict(action="no_order",status="INVALID_SYMBOL",reason=str(error)),
                status_code=422,headers={"Cache-Control":"no-store"})
        return JSONResponse(result,headers={"Cache-Control":"no-store"})
