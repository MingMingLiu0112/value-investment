"""Deterministic presentation contract; never evaluates investment eligibility."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping


@dataclass(frozen=True)
class OpportunitySurface:
    symbol: str
    company_name: str
    strategy: Literal['CORE_VALUE', 'HOTSPOT_SATELLITE']
    as_of: str
    quote_date: str
    scope: str
    basis: str
    candidate_action: str
    risk: str
    next_trigger: str
    action: Literal['no_order'] = 'no_order'


def validate_extensions(payload: Mapping[str, Any], input_sha256: str) -> None:
    """Source bytes are verified by the publication pipeline and renderer."""
    if payload.get('schema_version') != 'dual-product-surface-v1':
        raise ValueError('unsupported presentation extension schema')
    if payload.get('action') != 'no_order' or payload.get('input_sha256') != input_sha256:
        raise ValueError('extension boundary or publication binding mismatch')
    bindings = payload.get('source_bindings')
    if not isinstance(bindings, list) or not bindings:
        raise ValueError('extensions require source bindings')
    for binding in bindings:
        if (not isinstance(binding, dict) or not isinstance(binding.get('path'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', binding.get('sha256', ''))):
            raise ValueError('invalid extension source binding')
    for key in ('hotspot_report', 'dual_sleeve_report'):
        report = payload.get(key)
        if report is not None and (not isinstance(report, dict) or report.get('action') != 'no_order'):
            raise ValueError(f'{key} must preserve no_order')


def hotspot_surfaces(report: Mapping[str, Any] | None) -> tuple[OpportunitySurface, ...]:
    if report is None:
        return ()
    if report.get('action') != 'no_order':
        raise ValueError('hotspot action must be no_order')
    result = []
    seen = set()
    for item in report.get('opportunities', []):
        symbol = item['symbol']
        if symbol in seen:
            raise ValueError('duplicate hotspot symbol')
        seen.add(symbol)
        # A presentation adapter cannot derive or upgrade a trading candidate.
        state = item.get('state', 'UNKNOWN')
        if state not in {'UNKNOWN', 'HOT_WATCH', 'SETUP_FORMING', 'ENTRY_REVIEW_CANDIDATE',
                         'POSITION_RISK_ALERT', 'EXIT_REVIEW_CANDIDATE', 'INVALIDATED', 'NO_SIGNAL'}:
            raise ValueError('unsupported hotspot research state')
        if state == 'ENTRY_REVIEW_CANDIDATE':
            gates = item.get('gates', {})
            required = ('core_value', 'risk', 'pit', 'oos', 'cost', 'shadow')
            if any(gates.get(key) is not True for key in required):
                raise ValueError('entry review requires explicit upstream gates')
        result.append(OpportunitySurface(
            symbol=symbol, company_name=item.get('company_name', symbol),
            strategy='HOTSPOT_SATELLITE', as_of=item.get('as_of', report.get('as_of', 'UNKNOWN')),
            quote_date=item.get('quote_date', 'UNKNOWN'), scope=item.get('scope', '研究观察'),
            basis=item.get('basis', 'UNKNOWN'), candidate_action=state,
            risk=item.get('risk', 'UNKNOWN'), next_trigger=item.get('next_trigger', 'UNKNOWN'),
        ))
    return tuple(result)


def selected_candidate(supplements: list[Mapping[str, Any]], symbol: str) -> Mapping[str, Any] | None:
    """Use upstream selected/current marker, never infer current from filename/date."""
    candidates = [item for item in supplements if item.get('symbol') == symbol
                  and item.get('model_context_scope') == 'ACTUALLY_CONSUMED'
                  and item.get('candidate_valuation', {}).get('status') == 'conditional_research_only']
    if any(item.get('action') != 'no_order' for item in candidates):
        raise ValueError('candidate action must be no_order')
    if len(candidates) > 1:
        current = [item for item in candidates if item.get('is_current') is True]
        if len(current) != 1:
            raise ValueError('ambiguous current research candidate')
        return current[0]
    return candidates[0] if candidates else None
