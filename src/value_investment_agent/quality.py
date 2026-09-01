from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import QualityGateResult


def evaluate(symbol: str, points: list[dict], max_age_hours: int, conflict_tolerance: Decimal) -> QualityGateResult:
    prices = [p for p in points if p['field_name'] == 'current_price']
    reasons: list[str] = []
    if not prices:
        return QualityGateResult(symbol, '缺失', ['缺少当前价格'], None, None, None, '待数据', Decimal('0'))
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
        return QualityGateResult(symbol, '异常', reasons, price, None, None, '等待数据', Decimal('0'))
    # Fair value is intentionally absent until an auditable valuation model is imported.
    return QualityGateResult(symbol, '待估值', ['缺少已复核合理价值'], price, None, None, '待数据', Decimal('0'))


def as_valuation_row(result: QualityGateResult) -> dict:
    return {
        'symbol': result.symbol, 'current_price': result.current_price, 'fair_value': result.fair_value,
        'safety_margin': result.safety_margin, 'valuation_status': result.status,
        'build_signal': result.signal, 'target_weight': result.target_weight, 'data_status': result.status,
    }
