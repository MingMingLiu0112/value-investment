"""Real completed observation baselines; no scheduling or paper executions."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from copy import deepcopy

from .price_action_plan import RULE_VERSION, calculate_price_levels
from .current_price import SESSION_TIMES
from ..execution.exchange_calendar import next_exchange_session

PATH_RULE_VERSION = 'hotspot-frozen-completed-condition-path-v1'


def _frozen_condition(case):
    rows = deepcopy(case['bars']['60m'][-6:])
    level = calculate_price_levels(rows, period='60m')
    if rows[-1]['time'][:10] != case['market_trade_date']:
        raise ValueError('Frozen reference cutoff does not match its trade date')
    return dict(rule_version=RULE_VERSION, reference_bars=rows,
                entry_trigger_price=level['entry_trigger_price'],
                invalidation_price=level['invalidation_price'],
                mean_volume=str(sum(Decimal(row['volume']) for row in rows[:-1]) / 5),
                volume_multiplier='1.2', valid_after=rows[-1]['time'],
                expires_after_session=next_exchange_session(
                    'SSE', datetime.fromisoformat(case['market_trade_date']).date()).isoformat())


def make_shadow_baseline(case: dict, plan: dict, *, observed_at: datetime) -> dict:
    if observed_at.utcoffset() is None:
        raise ValueError("Timezone-aware observation required")
    if (case.get("action") != "no_order" or plan.get("action") != "no_order"
            or plan.get("action_eligibility") is not False
            or plan.get("model_or_rule_version") != RULE_VERSION
            or plan.get("symbol") != case.get("symbol")
            or plan.get("market_trade_date") != case.get("market_trade_date")
            or plan.get("signal_state") != case.get("signal_state")):
        raise ValueError("Shadow case/plan contract mismatch")
    latest = case["bars"]["60m"][-1]["time"]
    cutoff = datetime.fromisoformat(latest).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    if cutoff > observed_at:
        raise ValueError("Future bars cannot create Shadow observations")
    available = datetime.fromisoformat(case["data_available_at"])
    if available.utcoffset() is None or available > observed_at:
        raise ValueError("Shadow inputs not yet available")
    return {
        "schema_version": "hotspot-read-only-shadow-baseline-v1",
        "symbol": case["symbol"], "market_trade_date": case["market_trade_date"],
        "observed_at": observed_at.isoformat(), "cutoff": latest,
        "data_available_at": available.isoformat(),
        "rule_version": RULE_VERSION, "case_sha256": case["case_sha256"],
        "frozen_price_condition": _frozen_condition(case),
        "signal_state": plan["signal_state"],
        "current_reference_price": plan["current_reference_price"],
        "entry_trigger_price": plan["entry_trigger_price"],
        "invalidation_price": plan["invalidation_price"],
        "previous_judgment": None, "today_vs_previous_outcome": None,
        "trigger_observed": plan["signal_state"] == "TRIGGER_OBSERVED",
        "invalidation_observed": plan["signal_state"] == "TRIGGER_REJECTED",
        "execution_feasibility": "UNKNOWN", "potential_cost": None,
        "outside_rule_changes": "NOT_REVIEWED",
        "elapsed_real_shadow_sessions": 0, "real_trade": False,
        "formal_eligibility": False, "portfolio_eligibility": None, "action": "no_order",
    }


def evaluate_frozen_condition_path(prior: dict, current: dict, *, observed_at: datetime) -> dict:
    """Evaluate sealed levels in chronological completed bars, never fills/holdings.

    Frozen volume uses the same prior-five mean and 1.2 multiplier as the original
    price-level rule. A bar spanning both bounds cannot prove intrabar ordering.
    """
    condition = deepcopy(prior.get('frozen_price_condition'))
    result = dict(rule_version=PATH_RULE_VERSION, original_condition=condition,
        prior_case_sha256=prior.get('case_sha256'), current_case_sha256=current.get('case_sha256'),
        symbol=prior.get('symbol'), trade_date=current.get('market_trade_date'),
        status='NOT_ASSESSABLE', reason=None, first_valid_trigger=None,
        invalidation_at=None, ambiguous_at=None, trace=[], volume_confirmation='NOT_ASSESSED',
        evidence_refs=deepcopy(current.get('source_bindings', {})),
        observed_at=observed_at.isoformat(), scope='SEALED_CONDITION_OBSERVATION_NOT_POSITION_OR_EXECUTION',
        exit_scope='OBSERVATION_INVALIDATION_NOT_OWNED_POSITION_EXIT',
        formal_eligibility=False, personal_sell_permission=False, real_trade=False,
        hypothetical_fills=None, profit=None, action='no_order')
    def unavailable(reason):
        result.update(status='NOT_ASSESSABLE', reason=reason, first_valid_trigger=None,
                      invalidation_at=None, volume_confirmation='NOT_ASSESSED')
        return result
    if not condition:
        return unavailable('LEGACY_BASELINE_HAS_NO_FROZEN_VOLUME_BASIS')
    if observed_at.utcoffset() is None:
        raise ValueError('Timezone-aware observation required')
    if (prior.get('action') != 'no_order' or current.get('action') != 'no_order'
            or prior.get('symbol') != current.get('symbol')
            or prior.get('rule_version') != RULE_VERSION):
        raise ValueError('Frozen condition identity mismatch')
    basis = _frozen_condition(dict(bars={'60m': condition['reference_bars']},
                                   market_trade_date=prior['market_trade_date']))
    if (condition != basis or prior['entry_trigger_price'] != basis['entry_trigger_price']
            or prior['invalidation_price'] != basis['invalidation_price']):
        raise ValueError('Frozen price/volume basis changed')
    day = current['market_trade_date']
    prior_known = datetime.fromisoformat(prior['observed_at'])
    if (prior_known.utcoffset() is None or prior_known.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() >= day
            or prior_known > observed_at):
        return unavailable('PRIOR_CONDITION_NOT_KNOWN_BEFORE_TARGET_SESSION')
    if day != condition['expires_after_session']:
        return unavailable('TARGET_IS_NOT_THE_SEALED_NEXT_EXCHANGE_SESSION')
    available = [source['fetched_at'] for source in current.get('source_bindings', {}).values()
                 if 'fetched_at' in source]
    available += [current[key] for key in ('data_available_at', 'verified_available_at') if key in current]
    if any(datetime.fromisoformat(value).utcoffset() is None
           or datetime.fromisoformat(value) > observed_at for value in available):
        return unavailable('CURRENT_SOURCE_NOT_AVAILABLE_AT_OBSERVATION')
    rows = current['bars']['60m']
    times = [row['time'] for row in rows]
    today = [row for row in rows if row['time'][:10] == day]
    if times != sorted(set(times)) or tuple(row['time'][11:] for row in today) != SESSION_TIMES['60m']:
        return unavailable('INCOMPLETE_OR_UNORDERED_COMPLETED_60M_PATH')
    if any(datetime.fromisoformat(row['time']).replace(tzinfo=ZoneInfo('Asia/Shanghai')) > observed_at for row in today):
        return unavailable('SESSION_NOT_COMPLETED_AT_OBSERVATION')
    try:
        calculate_price_levels(condition['reference_bars'] + today, period='60m')
    except (ValueError, ArithmeticError, KeyError, TypeError):
        return unavailable('INVALID_OHLCV_OR_MISSING_VOLUME')
    trigger = Decimal(condition['entry_trigger_price'])
    protection = Decimal(condition['invalidation_price'])
    minimum_volume = Decimal(condition['mean_volume']) * Decimal(condition['volume_multiplier'])
    if trigger <= protection:
        return unavailable('DEGENERATE_FROZEN_PRICE_RANGE')
    result.update(status='NOT_TRIGGERED', reason='NO_COMPLETED_CLOSE_WITH_REQUIRED_VOLUME',
                  volume_confirmation='NO_QUALIFYING_TRIGGER')
    for row in today:
        close, volume = Decimal(row['close']), Decimal(row['volume'])
        qualified = close > trigger and volume >= minimum_volume
        invalid = close < protection
        ambiguous = Decimal(row['high']) > trigger and Decimal(row['low']) < protection
        event = dict(time=row['time'], close=row['close'], volume=row['volume'],
                     minimum_volume=str(minimum_volume), reason='WITHIN_FROZEN_RANGE')
        if ambiguous:
            result.update(status='NOT_ASSESSABLE', reason='SAME_BAR_BOUNDS_ORDER_UNKNOWN',
                          ambiguous_at=row['time'], volume_confirmation='ORDER_UNRESOLVED')
            event['reason'] = 'SAME_BAR_BOUNDS_ORDER_UNKNOWN'
            result['trace'].append(event)
            break
        if invalid:
            result.update(status='INVALIDATED_AFTER_TRIGGER' if result['first_valid_trigger'] else 'INVALIDATED_BEFORE_TRIGGER',
                          reason='COMPLETED_CLOSE_BELOW_ORIGINAL_PROTECTION', invalidation_at=row['time'])
            event['reason'] = result['reason']
            result['trace'].append(event)
            break
        if qualified:
            if result['first_valid_trigger'] is None:
                result['first_valid_trigger'] = dict(time=row['time'], close=row['close'],
                    volume=row['volume'], volume_ratio=str(volume / Decimal(condition['mean_volume'])))
            result.update(status='TRIGGER_OBSERVED', reason='COMPLETED_CLOSE_AND_FROZEN_VOLUME_CONFIRMED',
                          volume_confirmation='CONFIRMED_AGAINST_SEALED_PRIOR_FIVE_MEAN')
            event['reason'] = result['reason']
        elif close > trigger:
            event['reason'] = 'PRICE_ABOVE_TRIGGER_VOLUME_INSUFFICIENT'
        result['trace'].append(event)
    return result


def compare_archived_baseline(prior: dict, current: dict) -> dict:
    """Compare a genuine earlier baseline, not a retrospectively invented plan."""
    if (prior.get("schema_version") != "hotspot-read-only-shadow-baseline-v1"
            or current.get("schema_version") != prior["schema_version"]
            or prior.get("action") != "no_order" or current.get("action") != "no_order"
            or prior.get("symbol") != current.get("symbol")
            or prior.get("rule_version") != current.get("rule_version")
            or prior["market_trade_date"] >= current["market_trade_date"]
            or datetime.fromisoformat(prior["observed_at"]) >= datetime.fromisoformat(current["observed_at"])
            or datetime.fromisoformat(prior["observed_at"]).date().isoformat() >= current["market_trade_date"]):
        raise ValueError("Prior contemporaneous archived baseline required")
    close = Decimal(current["current_reference_price"])
    return {
        "prior_case_sha256": prior["case_sha256"], "current_case_sha256": current["case_sha256"],
        "close_above_prior_trigger": close > Decimal(prior["entry_trigger_price"]),
        "close_below_prior_invalidation": close < Decimal(prior["invalidation_price"]),
        "volume_confirmation": "NOT_REASSESSED_FOR_PRIOR_FROZEN_WINDOW",
        "real_trade": False, "profit": None, "action": "no_order",
    }
