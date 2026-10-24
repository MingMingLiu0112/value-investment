"""Recompute retained executions and locate a verified gross-cash entitlement exposure."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .strategy_execution_replay import build_strategy_execution_replay, fingerprint
from ...infrastructure.hotspot.sse_cash_entitlement import load_sse_cash_entitlement
from ...infrastructure.evidence.historical_price_correspondence import require_inside, sha256_file
from ...infrastructure.hotspot import sse_cash_entitlement, cash_implementation, cash_implementation_v2, related_disclosure_identity
from ...quote_sessions import CHINA


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
