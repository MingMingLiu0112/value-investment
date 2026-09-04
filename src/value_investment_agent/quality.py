from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import QualityGateResult


def automatically_verified(point: dict) -> bool:
    """Accept machine verification only when its cross-source evidence is retained."""
    metadata = point.get('metadata') or {}
    return bool(metadata.get('automatic_cross_source_verification'))


def accepted_verification(point: dict) -> bool:
    return point['validation_status'] == 'verified' and (
        point.get('human_reviewed', False) or automatically_verified(point)
    )


def evaluate(symbol: str, points: list[dict], max_age_hours: int, conflict_tolerance: Decimal) -> QualityGateResult:
    prices = [p for p in points if p['field_name'] == 'current_price']
    reasons: list[str] = []
    if not prices:
        return QualityGateResult(symbol, '缺失', ['缺少当前价格'], None, None, None, '待数据', Decimal('0'), {'reasons': ['缺少当前价格']})
    newest = max(prices, key=lambda p: p['created_at'])
    price = Decimal(newest['value'])
    if newest['validation_status'] not in {'verified', 'pending'}:
        reasons.append('价格校验失败')
    if newest['fetched_at'] < datetime.now(timezone.utc) - timedelta(hours=max_age_hours):
        reasons.append('价格数据已过期')
    unique_prices = {Decimal(p['value']) for p in prices}
    if len(unique_prices) > 1:
        spread = (max(unique_prices) - min(unique_prices)) / max(unique_prices)
        if spread > conflict_tolerance:
            reasons.append('双源价格差异超阈值')
    if reasons:
        return QualityGateResult(symbol, '异常', reasons, price, None, None, '等待数据', Decimal('0'), {'price': str(price), 'reasons': reasons})
    fair_values = [p for p in points if p['field_name'] == 'fair_value']
    if not fair_values:
        model_values = [p for p in points if p['field_name'] == 'model_fair_value']
        if not model_values:
            return QualityGateResult(symbol, '待估值', ['缺少已复核合理价值和模型参考价'], price, None, None, '待数据', Decimal('0'), {'price': str(price), 'reasons': ['缺少已复核合理价值和模型参考价']})
        model = max(model_values, key=lambda p: p['created_at'])
        fair_value = Decimal(model['value'])
        safety_margin = (fair_value - price) / fair_value if fair_value > 0 else Decimal('0')
        return QualityGateResult(
            symbol, '模型估值待复核', ['PE/PB 模型价尚未以一手财报复核'], price, fair_value,
            safety_margin, '等待复核', Decimal('0'), {
                'price': str(price), 'fair_value': str(fair_value),
                'safety_margin': str(safety_margin), 'formula': '(fair_value - current_price) / fair_value',
                'model_source_id': str(model.get('source_id', '')),
                'reasons': ['PE/PB 模型价尚未以一手财报复核'],
            },
        )
    fair = max(fair_values, key=lambda p: p['created_at'])
    fair_value = Decimal(fair['value'])
    if not accepted_verification(fair):
        reasons = ['合理价值尚未完成自动交叉验证']
        return QualityGateResult(symbol, '待核验', reasons, price, fair_value, None, '待数据', Decimal('0'), {'price': str(price), 'fair_value': str(fair_value), 'reasons': reasons})
    if not accepted_verification(newest):
        reasons = ['当前价格尚未完成自动交叉验证']
        return QualityGateResult(symbol, '待核验', reasons, price, fair_value, None, '待数据', Decimal('0'), {'price': str(price), 'fair_value': str(fair_value), 'reasons': reasons})
    safety_margin = (fair_value - price) / fair_value if fair_value > 0 else Decimal('0')
    if safety_margin >= Decimal('0.30'):
        status, signal, target_weight = '低估', '建仓候选', Decimal('0.10')
    elif safety_margin >= Decimal('0.15'):
        status, signal, target_weight = '合理', '观察', Decimal('0')
    else:
        status, signal, target_weight = '高估', '等待价格', Decimal('0')
    details = {
        'price': str(price),
        'fair_value': str(fair_value),
        'safety_margin': str(safety_margin),
        'formula': '(fair_value - current_price) / fair_value',
        'thresholds': {'build_candidate': '0.30', 'observe': '0.15'},
        'price_source_id': str(newest.get('source_id', '')),
        'fair_value_source_id': str(fair.get('source_id', '')),
    }
    return QualityGateResult(symbol, status, [], price, fair_value, safety_margin, signal, target_weight, details)


def as_valuation_row(result: QualityGateResult) -> dict:
    return {
        'symbol': result.symbol, 'current_price': result.current_price, 'fair_value': result.fair_value,
        'safety_margin': result.safety_margin, 'valuation_status': result.status,
        'build_signal': result.signal, 'target_weight': result.target_weight, 'data_status': result.status,
        'calculation_details': result.calculation_details,
    }
