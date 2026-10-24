"""Persistent hypothetical account over the existing journal and public readers."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json

from .private_portfolio_service import JournalValidationError
from .simulated_portfolio_service_v1 import create_simulated_portfolio_service
from .simulated_trade_journey import (
    SourceResearchVersionChanged, _source_bound_cases, _dual_hotspot_source,
)
from ..product.common import require_inside
from ...domain.execution.exchange_calendar import next_exchange_session


ACCOUNT_ID = 'paper-dual-v1'


def _sources(project, now, *, core_symbols):
    pointer = require_inside(project, project / 'config/hotspot-replay-review-v1.json', 'public swing pointer')
    raw = pointer.read_bytes()
    config = json.loads(raw)
    if config.get('action') != 'no_order':
        raise ValueError('Public research must remain no_order')
    binding = config['simulated_hotspot_lifecycle_receipt_binding']
    core, _ = _source_bound_cases(project, core_symbols, now)
    swing = _dual_hotspot_source(project, binding, now)
    rows = [(f"core:{item['symbol']}", item['symbol'], 'CORE_VALUE',
        item['research']['candidate_binding'], item['research']['available_at']) for item in core]
    receipt = require_inside(project, project / binding['path'], 'retained swing reference')
    sealed_at = json.loads(receipt.read_bytes())['generated_at']
    rows.append((f"swing:{swing['symbol']}", swing['symbol'], 'HOTSPOT_SATELLITE', binding, sealed_at))
    if sha256(pointer.read_bytes()).digest() != sha256(raw).digest():
        raise SourceResearchVersionChanged('Public research pointer changed')
    references = {key: dict(deepcopy(ref), symbol=symbol, available_at=available_at)
        for key, symbol, _, ref, available_at in rows}
    items = [dict(id=key, symbol=symbol, sleeve=sleeve, candidate_binding=deepcopy(ref),
        scope='REFERENCE_ONLY_NOT_APPROVAL') for key, symbol, sleeve, ref, _ in rows]
    return references, items


def read_simulated_portfolio_workbench(project, now, *, core_symbols, mutation=None):
    # Reading the account does not depend on today's source discovery succeeding.
    account = create_simulated_portfolio_service(repository_root=project, account_id=ACCOUNT_ID).read()
    try:
        _, items = _sources(project, now, core_symbols=core_symbols)
        sources = dict(status='AVAILABLE', items=items)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        sources = dict(status='UNAVAILABLE', items=[])
    result = dict(schema_version='persistent-simulated-workbench-v1', action='no_order',
        namespace='SIMULATED', formal_eligibility=False, actual_account_used=False,
        position_guidance=None, server_now=now.isoformat(), account=account, sources=sources)
    if mutation is not None:
        result['mutation'] = mutation
    return result


def mutate_simulated_portfolio(project, now, operation, request, *, core_symbols):
    payload = deepcopy(request)
    references = {}
    if operation in {'prepare-fill', 'confirm-entry'}:
        try:
            references, items = _sources(project, now, core_symbols=core_symbols)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            if operation == 'confirm-entry' or payload['fill']['side'] == 'BUY':
                raise JournalValidationError('Current public reference is unavailable') from error
            items = []
    service = create_simulated_portfolio_service(repository_root=project, account_id=ACCOUNT_ID,
        research_sources=references)
    if operation == 'initialize':
        payload.update(holdings=[], sleeve_allocations={}, policy={})
        method = service.initialize
    elif operation == 'prepare-fill':
        fill = payload['fill']
        symbol = fill['symbol']
        if not symbol.startswith(('00', '30', '60')):
            raise JournalValidationError('Security trading rules are not supported by this simulation')
        venue = 'SSE' if symbol.startswith('6') else 'SZSE'
        if fill['exchange'] != venue:
            raise JournalValidationError('Security and exchange disagree')
        if fill['side'] == 'BUY':
            if not any(item['symbol'] == symbol and item['sleeve'] == fill['sleeve'] for item in items):
                raise JournalValidationError('Select a displayed reference for a new simulated buy')
            fill.update(trading_unit='100',
                next_sell_session=next_exchange_session(venue, date.fromisoformat(fill['trade_date'])).isoformat())
        method = service.prepare_fill
    elif operation == 'confirm-fill':
        method = service.confirm_fill
    elif operation == 'cancel-fill':
        payload['reason'] = payload.pop('confirmation_note')
        payload['cancelled_at'] = payload.pop('confirmed_at')
        method = service.cancel_fill
    elif operation == 'confirm-entry':
        expected = payload.pop('expected_source_binding')
        reference = references.get(payload['source_id'])
        if reference is None or expected != {key: reference[key] for key in ('path', 'sha256')}:
            raise SourceResearchVersionChanged('Displayed research reference changed')
        method = service.confirm_entry_hypothesis
    else:
        raise JournalValidationError('Unsupported simulated operation')
    result, digest = method(payload)
    return dict(operation=operation, record_sha256=digest, result=result)
