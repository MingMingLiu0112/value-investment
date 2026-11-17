"""Recompute retained executions and locate a verified gross-cash entitlement exposure."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .strategy_execution_replay import build_strategy_execution_replay, fingerprint
from ...infrastructure.hotspot.sse_cash_entitlement import load_sse_cash_entitlement
from ...infrastructure.evidence.historical_price_correspondence import require_inside, sha256_file
from ...infrastructure.hotspot import sse_cash_entitlement, cash_implementation, cash_implementation_v2, related_disclosure_identity
from ...quote_sessions import CHINA
from ...domain.hotspot.quantitative_validation import number


def _execution_review(intention, fold):
    fills = [fill for fill in fold['fills'] if fill['order_id'] == intention['id']]
    rejected = [row for row in fold.get('rejected_orders', []) if row['order_id'] == intention['id']]
    result = dict(outcome='UNFILLED', linkage_status='NATIVE_RESULT_MISSING', filled_quantity=None,
        simulated_fill=None, rejection_reasons=[],
        hypothetical_execution_at=intention.get('actual_execution_at'),
        execution_bar_close_label=intention.get('execute_at'),
        native_intention_fingerprint=fingerprint(intention),
        verification_scope='NATIVE_SIMULATION_LINKAGE_NOT_REAL_TRADABILITY',
        actual_broker_execution=False, execution_verified=False, action='no_order')
    if len(fills) > 1 or len(rejected) > 1 or (fills and rejected):
        return dict(result, outcome='NOT_ASSESSABLE', linkage_status='CONFLICTING_NATIVE_RESULTS')
    try:
        clocks = [datetime.fromisoformat(intention[key]) for key in
            ('decision_at', 'actual_execution_at', 'execute_at')]
        if any(clock.utcoffset() is None for clock in clocks) or not clocks[0] < clocks[1] < clocks[2]:
            raise ValueError('Invalid hypothetical execution chronology')
    except (ValueError, TypeError, KeyError):
        return dict(result, outcome='NOT_ASSESSABLE', linkage_status='INVALID_EXECUTION_CHRONOLOGY')
    if fills:
        fill = fills[0]
        if (any(fill.get(key) != intention.get(key) for key in ('symbol', 'side', 'quantity'))
                or any(key not in intention for key in ('symbol', 'side', 'quantity', 'actual_execution_at', 'execute_at'))
                or fill.get('time') != intention['execute_at']
                or fill.get('hypothetical_execution_at') != intention['actual_execution_at']
                or any(key not in fill for key in ('price', 'fees_cny', 'slippage_cny', 'fee_components'))):
            return dict(result, outcome='NOT_ASSESSABLE', linkage_status='FILL_INTENTION_MISMATCH')
        try:
            parts = fill['fee_components']
            if (type(fill['quantity']) is not int or fill['quantity'] <= 0 or fill['quantity'] % 100
                    or fill['side'] not in ('BUY', 'SELL')
                    or not isinstance(parts, dict)
                    or set(parts) != {'commission_cny', 'transfer_fee_cny', 'sell_stamp_tax_cny'}
                    or number(fill['price']) <= 0
                    or sum((number(value) for value in parts.values()), Decimal(0)) != number(fill['fees_cny'])):
                raise ValueError('Invalid native quantity, price or fee decomposition')
            number(fill['slippage_cny'])
        except (ValueError, TypeError, KeyError):
            return dict(result, outcome='NOT_ASSESSABLE', linkage_status='INVALID_NATIVE_FILL_VALUES')
        return dict(result, outcome='FILLED', linkage_status='MATCHED_NATIVE_SIMULATION',
            filled_quantity=fill['quantity'], simulated_fill=dict(fill), execution_verified=True)
    if rejected:
        reasons = [row.get('reason') for row in rejected]
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            return dict(result, outcome='NOT_ASSESSABLE', linkage_status='INVALID_NATIVE_REJECTION')
        return dict(result, outcome='REJECTED', linkage_status='MATCHED_NATIVE_SIMULATION',
            filled_quantity=0, rejection_reasons=reasons, execution_verified=True)
    return result


def inspect_cash_execution_exposure(*, root: Path, symbol: str, cash_binding: dict,
        now: datetime, manifest_binding=None):
    cash = load_sse_cash_entitlement(root=root, binding=cash_binding, symbol=symbol, now=now)
    replay = build_strategy_execution_replay(root=root, now=now, manifest_binding=manifest_binding)
    terms = cash['terms']
    record_close = datetime.fromisoformat(terms['record_date'] + 'T15:00:00+08:00')
    lanes = []
    matched = [row for row in replay['results'] if row['symbol'] == symbol]
    if len(matched) != 1:
        raise ValueError('One retained execution security required')
    dates = {row['bar_label'][:10] for fold in matched[0]['strict']['folds']
        for row in fold['execution_observations']}
    if not {terms['record_date'], terms['ex_date']} <= dates:
        raise ValueError('Record and ex dates must be observed in retained execution window')
    for scenario in matched[0]['scenarios']:
        for fold in scenario['folds']:
            intentions = {row['id']: row for row in fold['generated_intentions']}
            fold_dates = {datetime.fromisoformat(bar['time']).astimezone(CHINA).date().isoformat()
                for bar in fold['simulator_inputs']['bars']}
            applicable = {terms['record_date'], terms['ex_date']} <= fold_dates
            quantity = 0
            for fill in fold['fills']:
                intent = intentions[fill['order_id']]
                executed = datetime.fromisoformat(intent['actual_execution_at']).astimezone(CHINA)
                if executed <= record_close:
                    quantity += fill['quantity'] * (1 if fill['side'] == 'BUY' else -1)
            if quantity < 0:
                raise ValueError('Retained execution inventory is negative')
            ex_decisions = []
            for row in fold['generated_intentions']:
                decision = datetime.fromisoformat(row['decision_at']).astimezone(CHINA)
                if decision.date().isoformat() != terms['ex_date']:
                    continue
                prefix = [bar for bar in fold['simulator_inputs']['bars']
                    if datetime.fromisoformat(bar['time']) <= decision][-6:]
                ex_decisions.append(dict(id=row['id'], decision_at=row['decision_at'],
                    execution_review=_execution_review(row, fold),
                    retained_lookback_bar_labels=[bar['time'] for bar in prefix],
                    six_bar_lookback_present=len(prefix) == 6,
                    raw_lookback_crosses_ex_date=bool(prefix) and
                        datetime.fromisoformat(prefix[0]['time']).astimezone(CHINA).date().isoformat() < terms['ex_date'],
                    cash_price_adjustment_applied=False))
            lanes.append(dict(cost_multiplier=scenario['cost_multiplier'], partition=fold['fold'],
                event_dates_within_partition=applicable,
                hypothetical_record_close_quantity=quantity if applicable else None,
                declared_gross_entitlement_if_eligible_cny=str(Decimal(quantity) * Decimal(terms['gross_cash_per_eligible_a_share']))
                    if applicable else None,
                ex_date_intentions=ex_decisions,
                cash_credited_to_replay=False, hypothetical_inventory_not_actual_holdings=True))
    bindings = [cash['source_binding'], *replay['source_bindings'],
        *(replay.get('statutory_fee_evidence') or {}).get('source_bindings', [])]
    for ref in bindings:
        if sha256_file(require_inside(root, root / ref['path'], 'cash exposure retained input')) != ref['sha256']:
            raise ValueError('Cash exposure source changed during read')
    result = dict(schema_version='hotspot-cash-execution-exposure-v1', symbol=symbol,
        evaluated_at=now.isoformat(), cash_proof=cash, lanes=lanes,
        source_bindings=bindings, implementation_bindings=replay['implementation_bindings'],
        replay_content_sha256=replay['content_sha256'], original_replay_summary=replay['summary'],
        execution_cost_assumptions=replay.get('costs'), execution_cost_fingerprint=replay.get('cost_fingerprint'),
        execution_parameters=replay.get('parameters'),
        source_available_at=max([cash['acquired_at'], *[row['source_available_at'] for row in replay['results']
            if row.get('source_available_at')]], key=datetime.fromisoformat), status='SINGLE_EVENT_EXPOSURE_RECOMPUTED',
        whole_action_history_verified=False, tax_or_cash_receipt_verified=False,
        price_comparability='UNKNOWN', original_protection_adjusted=False,
        adjusted_strategy_return=None, historical_availability_proven=False,
        strict_pit_admitted=False, strict_oos_admitted=False, performance_claim_allowed=False,
        strategy_validation='NOT_PROVEN', formal_eligibility=False, action='no_order')
    checkout = Path(__file__).resolve().parents[4]
    result['exposure_implementation_bindings'] = [dict(path=p.relative_to(checkout).as_posix(),
        sha256=sha256_file(p)) for p in [Path(__file__), *[Path(module.__file__) for module in (
            sse_cash_entitlement, cash_implementation, cash_implementation_v2, related_disclosure_identity)]]]
    result['content_sha256'] = fingerprint(result)
    return result
