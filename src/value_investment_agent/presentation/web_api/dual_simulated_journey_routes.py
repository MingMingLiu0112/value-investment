"""Server-pinned public research and explicit disposable dual-sleeve rehearsal."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...application.portfolio.simulated_trade_journey import (
    SourceResearchVersionChanged, run_source_bound_dual_sleeve_journey,
)
from ...application.portfolio.private_portfolio_service import JournalConflict
from ...application.product.common import require_inside
from .simulated_journey_routes import _Binding, _ExpectedCandidate


class _Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class _HotspotIdentity(_Strict):
    symbol: str = Field(pattern=r'^[036][0-9]{5}$')
    receipt_binding: _Binding
    entry_freeze_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class _SourceIdentity(_Strict):
    core: list[_ExpectedCandidate] = Field(min_length=1, max_length=2)
    hotspot: _HotspotIdentity


class _Account(_Strict):
    namespace: Literal['TEST_ONLY']
    confirmed: Literal[True]
    opening_day: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    initial_cash_cny: str = Field(pattern=r'^[1-9][0-9]{0,9}(?:\.[0-9]{1,2})?$')
    policy: dict[str, Any]
    hypothetical_marks: dict[str, str]

    @field_validator('confirmed', mode='before')
    @classmethod
    def confirmed_boolean(cls, value):
        if value is not True:
            raise ValueError('Explicit TEST_ONLY confirmation required')
        return value


class _DualFill(_Strict):
    transaction_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    side: Literal['BUY', 'SELL']
    sleeve: Literal['CORE_VALUE', 'HOTSPOT_SATELLITE']
    symbol: str = Field(pattern=r'^[036][0-9]{5}$')
    exchange: Literal['SSE', 'SZSE']
    quantity: str = Field(pattern=r'^[1-9][0-9]{0,6}$')
    price_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    fees_cny: str = Field(pattern=r'^[0-9]{1,10}(?:\.[0-9]{1,6})?$')
    trade_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    trading_unit: Literal['100'] | None = None


class _Narrative(_Strict):
    thesis: str = Field(min_length=1, max_length=2000)
    hold_logic: str = Field(min_length=1, max_length=2000)
    invalidation_conditions: list[str] = Field(min_length=1, max_length=20)


class _ManualFill(_Strict):
    fill: _DualFill
    intent: Literal['BUY', 'ADD', 'REDUCE', 'EXIT']
    rationale: str = Field(min_length=1, max_length=2000)
    entry_transaction_id: str | None = Field(default=None, min_length=1, max_length=80)
    entry_narrative: _Narrative | None = None
    entry_rationales: dict[str, str] | None = Field(default=None, max_length=12)
    requested_quantity: str | None = Field(default=None, pattern=r'^[1-9][0-9]{0,6}$')


class _Request(_Strict):
    confirmed_hypothetical: Literal[True]
    expected_sources: _SourceIdentity
    test_only_account: _Account
    manual_fills: list[_ManualFill] = Field(min_length=1, max_length=12)

    @field_validator('confirmed_hypothetical', mode='before')
    @classmethod
    def confirmed_boolean(cls, value):
        if value is not True:
            raise ValueError('Explicit hypothetical-accounting confirmation required')
        return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate public source pointer field')
        result[key] = value
    return result


def _run(project, now, **kwargs):
    pointer = require_inside(project, project / 'config/hotspot-replay-review-v1.json', 'public swing pointer')
    raw = pointer.read_bytes()
    pins = json.loads(raw, object_pairs_hook=_unique_object)
    if pins.get('action') != 'no_order':
        raise ValueError('Public research pointer must remain no_order')
    binding = _Binding.model_validate(pins['simulated_hotspot_lifecycle_receipt_binding']).model_dump()
    result = run_source_bound_dual_sleeve_journey(core_root=project, hotspot_root=project,
        workspace_root=project, now=now, core_symbols=('600519',),
        hotspot_receipt_binding=binding, **kwargs)
    if sha256(pointer.read_bytes()).digest() != sha256(raw).digest():
        raise SourceResearchVersionChanged('Registered swing source changed during rehearsal')
    return result


def register_dual_simulated_journey_routes(api: FastAPI, *, project,
        clock=lambda: datetime.now(timezone.utc)):
    headers = {'Cache-Control': 'no-store'}

    def rejected(status='SOURCE_OR_REHEARSAL_UNAVAILABLE'):
        return JSONResponse(dict(action='no_order', status=status,
            detail='公开来源或假设记账条件未通过；未改变真实账户，也未形成策略建议。'),
            status_code=409, headers=headers)

    @api.get('/api/v1/simulated-trade-journey/dual-sleeve')
    def read_dual_journey():
        try:
            return JSONResponse(_run(project, clock()), headers=headers)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError, JournalConflict):
            return rejected()

    @api.post('/api/v1/simulated-trade-journey/dual-sleeve')
    def rehearse_dual_journey(payload: _Request):
        try:
            result = _run(project, clock(), expected_sources=payload.expected_sources.model_dump(),
                test_only_account=payload.test_only_account.model_dump(),
                manual_fills=[row.model_dump(exclude_none=True) for row in payload.manual_fills])
            return JSONResponse(result, headers=headers)
        except SourceResearchVersionChanged:
            return rejected('RESEARCH_VERSION_CHANGED')
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError, JournalConflict):
            return rejected('SIMULATED_REHEARSAL_REJECTED')
