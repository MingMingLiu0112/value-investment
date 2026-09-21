"""Research alerts with explicit evidence, freshness and position boundaries."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .financial_institutions import provisional_financial_type
from .financial_quality import GENERAL_FIELDS
from .quality import accepted_verification
from .quote_sessions import evaluate_quote_session


def _number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):
        return None


def _fresh(value, now, hours=30):
    try:
        date = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if date.tzinfo is None: return False
        return now-timedelta(hours=hours) <= date <= now+timedelta(minutes=5)
    except (ValueError,TypeError):
        return False


def build_reminders(payload, holdings=None, now=None):
    now=now or datetime.now(timezone.utc)
    holdings=holdings or {}
    qualities={r['symbol']:r for r in payload.get('financial_quality',[])}
    valuations={r['symbol']:r for r in payload.get('valuations',[])}
    tracking = {}
    duplicate_tracking = set()
    for row in payload.get('candidate_tracking', []) or []:
        symbol = row['symbol']
        if symbol in tracking:
            duplicate_tracking.add(symbol)
        tracking[symbol] = row
    points={}
    for p in payload.get('points',[]):
        key=(p['symbol'],p['field_name'])
        rank=(str(p.get('period_label','')),str(p.get('created_at','')))
        if key not in points or rank > points[key][0]: points[key]=(rank,p)
    rows=[]
    for c in payload.get('market_candidates',[]):
        symbol=c['symbol']; q=qualities.get(symbol,{}); v=valuations.get(symbol,{})
        price=points.get((symbol,'current_price'),(None,{}))[1]
        fair=points.get((symbol,'fair_value'),(None,{}))[1]
        reasons=[]
        checks=[]
        checkpoint=0
        def record_check(name):
            nonlocal checkpoint
            issues=reasons[checkpoint:]
            checks.append({'name':name,'passed':not issues,'reasons':list(issues)})
            checkpoint=len(reasons)
        if 'candidate_tracking' in payload:
            observation = tracking.get(symbol)
            if not observation or symbol in duplicate_tracking:
                reasons.append('每日跟踪缺失或重复，禁止沿用旧报价放行')
            else:
                if not _fresh(observation.get('quote_as_of'), now):
                    reasons.append('每日跟踪行情已过期或时间无效')
                if (observation.get('signal_blocked') is not False
                        or observation.get('quote_status') != 'matched'
                        or observation.get('risk_warning')
                        or observation.get('valuation_field_conflicts')):
                    reasons.append('每日跟踪存在报价、估值口径或风险异常')
                if (not observation.get('source_id')
                        or str(observation['source_id']) != str(price.get('source_id', ''))
                        or _number(observation.get('current_price')) is None
                        or _number(observation.get('current_price')) != _number(price.get('value'))):
                    reasons.append('每日跟踪与当前估值行情证据不一致')
        record_check('每日行情一致性')
        focus=(_number(c.get('initial_score')) or Decimal(0)) >= 55
        category='重点观察' if focus else '常规跟踪'
        action='先核验财务与估值，不交易'
        if not _fresh(payload.get('generated_at'),now,36): reasons.append('服务导出已过期')
        if not price or not accepted_verification(price): reasons.append('行情尚未逐项验证')
        elif (price.get('metadata') or {}).get('market_snapshot_source_id') and not (price.get('metadata') or {}).get('per_symbol_price_evidence'):
            reasons.append('旧行情缺少逐股票双源证据')
        if not _fresh(price.get('fetched_at'),now): reasons.append('行情时效不满足30小时门禁')
        quote_session = evaluate_quote_session(symbol, price.get('value'),
            (price.get('metadata') or {}).get('quote_session_evidence'), now,
            documents=payload.get('quote_session_documents'))
        if not quote_session['passed']:
            reasons.append(quote_session['reason'])
        record_check('行情验证与时效')
        if not fair or not accepted_verification(fair): reasons.append('合理价缺少自动验证依据')
        record_check('合理价证据')
        if q.get('quality_status') != '已验证' or q.get('total_score') is None:
            reasons.append('财务质量证据尚未完整')
        record_check('财务质量评分')
        latest_financials = {f: points.get((symbol,f),(None,{}))[1] for f in GENERAL_FIELDS}
        financial_period = max((str(p.get('period_label','')) for p in latest_financials.values()),default='')
        if any(not p or not accepted_verification(p) or str(p.get('period_label','')) != financial_period
               for p in latest_financials.values()):
            reasons.append('最新报告期财务指标缺证，年度评分不能替代中期跟踪')
        record_check('最新同报告期指标')
        if provisional_financial_type(c.get('name'),c.get('sector')):
            reasons.append('金融专用风险指标不能代替完整估值模型')
        record_check('行业模型适用性')
        if not _fresh(v.get('calculated_at'),now): reasons.append('估值计算未更新')
        details=v.get('calculation_details') or {}
        if str(details.get('price_source_id','')) != str(price.get('source_id','')) or str(details.get('fair_value_source_id','')) != str(fair.get('source_id','')):
            reasons.append('估值引用与当前证据不一致')
        record_check('估值计算与证据关联')
        price_value=_number(price.get('value')); fair_value=_number(fair.get('value'))
        margin=None
        if price_value is not None and price_value>0 and fair_value is not None and fair_value>0:
            margin=(fair_value-price_value)/fair_value
        else:
            if price_value is None or price_value <= 0:
                reasons.append('现价缺失或数值无效')
            if fair_value is None or fair_value <= 0:
                reasons.append('合理价缺失或数值无效')
        record_check('现价与合理价数值')
        if not reasons:
            if margin >= Decimal('0.30') and v.get('build_signal')=='建仓候选':
                category='买入研究候选'; action='安全边际达到30%，评估分批建仓；不自动下单'
            elif margin < 0:
                if (_number(holdings.get(symbol)) or Decimal(0)) > 0:
                    category='减仓研究候选'; action='现价高于已验证合理价，结合税费及投资逻辑评估减仓'
                else:
                    category='估值偏高'; action='没有已知实际持仓，不生成卖出指令'
            else:
                category='估值观察'; action='尚未达到建仓安全边际；继续跟踪'
        elif any('过期' in r or '时效' in r for r in reasons):
            category='数据过期'
        rows.append({**c,'category':category,'action':action,'reasons':reasons,
            'decision_checks':checks,'decision_price':str(price_value) if price_value is not None else None,
            'decision_fair_value':str(fair_value) if fair_value is not None else None,
            'known_holding':str(_number(holdings.get(symbol))) if _number(holdings.get(symbol)) is not None else None,
            'quote_session':quote_session,
            'upstream_build_signal':v.get('build_signal','尚无结果'),
            'priority':'重点观察' if focus else '常规跟踪',
            'signal_blocked':bool(reasons),'safety_margin':str(margin) if margin is not None else None,
            'quality_status':q.get('quality_status','尚无质量结果'),
            'price_source_id':str(price.get('source_id','')),'fair_value_source_id':str(fair.get('source_id','')),
            'as_of':price.get('fetched_at',c.get('screen_date'))})
    rank={'买入研究候选':0,'减仓研究候选':1,'数据过期':2,'重点观察':3,'估值偏高':4,'估值观察':5,'常规跟踪':6}
    return sorted(rows,key=lambda r:(rank[r['category']],-( _number(r.get('initial_score')) or Decimal(0)),r['symbol']))
