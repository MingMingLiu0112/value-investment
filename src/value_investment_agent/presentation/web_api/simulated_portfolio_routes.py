"""Local HTTP operations for one server-selected persistent simulated account."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...application.portfolio.private_portfolio_service import JournalConflict, JournalValidationError
from ...application.portfolio.simulated_trade_journey import SourceResearchVersionChanged
from ...application.portfolio.simulated_portfolio_workbench import (
    read_simulated_portfolio_workbench, mutate_simulated_portfolio,
)
from .local_auth import authorize, LocalAuthorizationError, LocalOperatorSession


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class _Mutation(_Strict):
    confirmed_hypothetical: Literal[True]
    idempotency_key: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)

    @field_validator('confirmed_hypothetical', mode='before')
    @classmethod
    def explicit_boolean(cls, value):
        if value is not True:
            raise ValueError('Explicit simulated confirmation required')
        return value


class _Initialize(_Mutation):
    as_of: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    cash_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,2})?$')
    confirmed_at: str = Field(min_length=20, max_length=40)
    confirmation_note: str = Field(min_length=1, max_length=2000)


class _Fill(_Strict):
    transaction_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    side: Literal['BUY', 'SELL']
    sleeve: Literal['CORE_VALUE', 'HOTSPOT_SATELLITE']
    symbol: str = Field(pattern=r'^[036][0-9]{5}$')
    exchange: Literal['SSE', 'SZSE']
    quantity: str = Field(pattern=r'^[1-9][0-9]{0,6}$')
    price_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    fees_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    trade_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class _Prepare(_Mutation):
    fill: _Fill


class _Confirm(_Mutation):
    prepared_record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed_at: str = Field(min_length=20, max_length=40)
    confirmation_note: str = Field(min_length=1, max_length=2000)


class _Binding(_Strict):
    path: str = Field(min_length=1, max_length=400)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class _Narrative(_Strict):
    thesis: str = Field(min_length=1, max_length=2000)
    hold_logic: str = Field(min_length=1, max_length=2000)
    invalidation_conditions: list[str] = Field(min_length=1, max_length=20)


class _Entry(_Mutation):
    fill_record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_id: str = Field(min_length=1, max_length=40)
    expected_source_binding: _Binding
    narrative: _Narrative
    confirmation_note: str = Field(min_length=1, max_length=2000)


class _Changes(_Strict):
    quantity: str | None = Field(default=None, pattern=r'^[1-9][0-9]{0,6}$')
    price_cny: str | None = Field(default=None, pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    fees_cny: str | None = Field(default=None, pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')


class _Correction(_Mutation):
    target_fill_record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_original_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    changes: _Changes
    confirmed_at: str = Field(min_length=20, max_length=40)
    reason: str = Field(min_length=1, max_length=2000)


def register_simulated_portfolio_routes(api: FastAPI, *, project, port=8001,
        clock=lambda: datetime.now(timezone.utc), core_symbols=('600519',)):
    headers = {'Cache-Control': 'no-store'}
    session = LocalOperatorSession()

    def refuse(request):
        try:
            authorize(request, session=session, port=port, require_token=False)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action='no_order', status=error.code, detail=error.detail),
                status_code=403, headers=headers)
        return None

    def emit(request, operation=None, payload=None):
        denial = refuse(request)
        if denial is not None:
            return denial
        mutation = None
        try:
            now = clock()
            if operation:
                mutation = mutate_simulated_portfolio(project, now, operation, payload.model_dump(exclude_none=True),
                    core_symbols=core_symbols)
            result = read_simulated_portfolio_workbench(project, clock(),
                core_symbols=core_symbols, mutation=mutation)
            return JSONResponse(result, headers=headers)
        except SourceResearchVersionChanged:
            status, detail = 'RESEARCH_VERSION_CHANGED', '参考研究已变化，请重新读取后确认。'
        except JournalConflict as error:
            status, detail = error.code, str(error)
        except JournalValidationError as error:
            status, detail = 'SIMULATED_OPERATION_REJECTED', str(error)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            status, detail = 'SIMULATION_UNAVAILABLE', '模拟账户暂不可读，请保留原幂等键并重新读取确认操作结果。'
        return JSONResponse(dict(action='no_order', status=status, detail=detail,
            mutation_may_have_committed=mutation is not None), status_code=409, headers=headers)

    @api.get('/api/v1/simulated-portfolio')
    def read(request: Request):
        return emit(request)

    @api.post('/api/v1/simulated-portfolio/initialize')
    def initialize(request: Request, payload: _Initialize):
        return emit(request, 'initialize', payload)

    @api.post('/api/v1/simulated-portfolio/prepare-fill')
    def prepare(request: Request, payload: _Prepare):
        return emit(request, 'prepare-fill', payload)

    @api.post('/api/v1/simulated-portfolio/confirm-fill')
    def confirm(request: Request, payload: _Confirm):
        return emit(request, 'confirm-fill', payload)

    @api.post('/api/v1/simulated-portfolio/cancel-fill')
    def cancel(request: Request, payload: _Confirm):
        return emit(request, 'cancel-fill', payload)

    @api.post('/api/v1/simulated-portfolio/confirm-entry')
    def entry(request: Request, payload: _Entry):
        return emit(request, 'confirm-entry', payload)

    @api.post('/api/v1/simulated-portfolio/correct-fill')
    def correct(request: Request, payload: _Correction):
        return emit(request, 'correct-fill', payload)
