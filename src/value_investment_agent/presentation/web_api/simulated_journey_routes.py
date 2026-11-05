"""Public-source reads and explicitly requested disposable accounting, never orders."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...application.portfolio.simulated_trade_journey import (
    run_simulated_trade_journey, run_source_bound_simulated_trade_journey, SourceResearchVersionChanged,
)

_SAMPLE_SYMBOLS = ('600519', '600887')


class _Fill(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    transaction_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    side: Literal['BUY', 'SELL']
    sleeve: Literal['CORE_VALUE']
    symbol: Literal['600519', '600887']
    exchange: Literal['SSE']
    quantity: str = Field(pattern=r'^[1-9][0-9]{0,6}$')
    price_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    fees_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    trade_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    trading_unit: Literal['100'] | None = None


class _ManualReference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    fill: _Fill
    research_reference: Literal['HISTORICAL_RECONSTRUCTION'] | None = None


class _Binding(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class _ExpectedCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    symbol: Literal['600519', '600887']
    candidate_binding: _Binding
    research_version: str = Field(min_length=1, max_length=256)


class _ManualRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confirmed_hypothetical: Literal[True]
    initial_cash_cny: str = Field(default='100000', pattern=r'^[0-9]{1,12}(?:\.[0-9]{1,2})?$')
    manual_fills: list[_ManualReference] = Field(min_length=1, max_length=4)
    expected_candidates: list[_ExpectedCandidate] = Field(min_length=1, max_length=2)

    @field_validator('confirmed_hypothetical', mode='before')
    @classmethod
    def actual_boolean_confirmation(cls, value):
        if value is not True:
            raise ValueError('Explicit hypothetical-accounting confirmation required')
        return value


def register_simulated_journey_routes(api: FastAPI, *, project,
                                     clock=lambda: datetime.now(timezone.utc)):
    headers = {'Cache-Control': 'no-store'}

    @api.get('/api/v1/simulated-trade-journey')
    def read_simulated_journey(mode: Literal['accounting_demo', 'source_bound'] = 'accounting_demo'):
        try:
            result = (run_source_bound_simulated_trade_journey(project, clock(), symbols=_SAMPLE_SYMBOLS) if mode == 'source_bound'
                      else run_simulated_trade_journey(project, clock()))
            return JSONResponse(result, headers=headers)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            return JSONResponse(dict(action='no_order', status='SOURCE_OR_REHEARSAL_UNAVAILABLE',
                detail='公开研究或演练来源不可核验；未改变私人账户，未生成策略建议。'),
                status_code=409, headers=headers)

    @api.post('/api/v1/simulated-trade-journey')
    def rehearse_manual_records(payload: _ManualRequest):
        try:
            result = run_source_bound_simulated_trade_journey(project, clock(),
                symbols=_SAMPLE_SYMBOLS,
                manual_fills=[row.model_dump(exclude_none=True) for row in payload.manual_fills],
                initial_cash_cny=payload.initial_cash_cny,
                expected_candidates=[row.model_dump() for row in payload.expected_candidates])
            return JSONResponse(result, headers=headers)
        except SourceResearchVersionChanged:
            return JSONResponse(dict(action='no_order', status='RESEARCH_VERSION_CHANGED',
                detail='研究版本已变化；请重新读取来源后再确认模拟记录，未运行记账。'),
                status_code=409, headers=headers)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            return JSONResponse(dict(action='no_order', status='SIMULATED_REHEARSAL_REJECTED',
                detail='来源或模拟成交条件未通过；临时演练不构成实际成交、原始买入依据或策略批准。'),
                status_code=409, headers=headers)
