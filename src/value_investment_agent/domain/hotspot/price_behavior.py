"""Transparent descriptive price behavior; no strategy or return optimization."""
from decimal import Decimal


def describe_bars(bars: list[dict]) -> dict:
    if len(bars) < 6:
        return {'status': 'UNKNOWN', 'reason': 'At least six completed bars required'}
    closes = [Decimal(b['close']) for b in bars]
    prior = bars[-6:-1]
    support = min(Decimal(b['low']) for b in prior)
    resistance = max(Decimal(b['high']) for b in prior)
    change = closes[-1] / closes[-6] - 1
    latest_volume = Decimal(bars[-1]['volume'])
    mean_volume = sum(Decimal(b['volume']) for b in prior) / 5
    return dict(status='OBSERVED_NOT_ADMITTED', first_date=bars[0]['date'],
        last_date=bars[-1]['date'], bars=len(bars), close=str(closes[-1]),
        five_bar_price_change=str(change), direction='UP' if change > 0 else 'DOWN' if change < 0 else 'FLAT',
        prior_five_bar_support=str(support), prior_five_bar_resistance=str(resistance),
        breakout=closes[-1] > resistance, below_support=closes[-1] < support,
        volume_ratio=str(latest_volume / mean_volume) if mean_volume > 0 else None,
        volume_unit='SOURCE_UNVERIFIED', volume_confirmation='UNKNOWN',
        invalidation_condition='Subsequent completed close below prior support requires renewed observation',
        adjustment='UNADJUSTED', corporate_action_review='UNKNOWN',
        execution_admitted=False, action='no_order')


def observation_gates() -> dict:
    return {name: {'status': 'NOT_PROVEN', 'passed': False} for name in (
        'issuer_identity', 'financial_sanity', 'value', 'risk', 'liquidity',
        'event_materiality', 'PIT', 'walk_forward_OOS', 'cost_validation', 'Shadow', 'production')}
