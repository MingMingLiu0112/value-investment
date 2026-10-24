"""Read-only economic diagnostics for the exact registered pending candidate."""
from datetime import datetime, timezone
from copy import deepcopy

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ...application.product.common import normalize_symbol
from ...application.product.pending_candidate_supplement import load_current_pending_candidate_supplement
from ...application.product.source_native_economic_review_v1 import build_source_native_economic_review


def register_source_native_economic_routes(api: FastAPI, *, project, replacement_bindings=None):
    def mapping():
        if replacement_bindings is None:
            return {}
        try:
            value = replacement_bindings() if callable(replacement_bindings) else replacement_bindings
        except Exception as error:
            raise ValueError('Economic comparison mapping unavailable') from error
        if not isinstance(value, dict):
            raise ValueError('Economic comparison mapping must be an object')
        value = deepcopy(value)
        for symbol, entry in value.items():
            if (normalize_symbol(symbol) != symbol or not isinstance(entry, dict)
                    or set(entry) != {'baseline_candidate_binding', 'replacement_candidate_binding'}):
                raise ValueError('Economic comparison mapping contract differs')
            for ref in entry.values():
                if (not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}
                        or not all(isinstance(v, str) and v for v in ref.values())):
                    raise ValueError('Economic comparison requires exact path/hash bindings')
        return value

    @api.get('/api/v1/value-economic-review/{symbol}')
    def read(symbol: str):
        try:
            symbol = normalize_symbol(symbol)
            registered = load_current_pending_candidate_supplement(root=project, symbol=symbol)
            if registered is None:
                raise ValueError('No current pending candidate')
            binding = registered['candidate_binding']
            before = mapping()
            comparison = before.get(symbol)
            if comparison is not None and comparison['baseline_candidate_binding'] != binding:
                raise ValueError('Economic comparison baseline differs from pending candidate')
            result = build_source_native_economic_review(root=project, candidate_binding=binding,
                replacement_candidate_binding=(comparison['replacement_candidate_binding'] if comparison else None),
                now=datetime.now(timezone.utc))
            latest = load_current_pending_candidate_supplement(root=project, symbol=symbol)
            if latest is None or latest['candidate_binding'] != binding or mapping() != before:
                raise ValueError('Pending candidate changed during economic review')
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            return JSONResponse(dict(status='ECONOMIC_REVIEW_UNAVAILABLE', action='no_order',
                formal_eligibility=False, price_admitted=False,
                detail='当前候选或经济复核来源未能核验，不能据此形成主估值或价格结论。'),
                status_code=409, headers={'Cache-Control': 'no-store'})
