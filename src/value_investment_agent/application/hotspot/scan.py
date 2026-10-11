"""Compose source-bound observations without admitting tactical signals."""
from datetime import datetime
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from value_investment_agent.application.product.common import sha256_file, write_new_json, require_inside
from value_investment_agent.domain.hotspot.price_behavior import describe_bars, observation_gates
from value_investment_agent.infrastructure.hotspot.sources import read_bound, aware, load_quote_history
from value_investment_agent.m2_market_data import parse_sina_industry, parse_tencent_board
from value_investment_agent.infrastructure.hotspot.dated_quotes import load_dated_quotes


def scan_market_hotspots(*, root: Path, config_path: Path, output: Path, cutoff: datetime, prepared_output: bool = False, collection: dict | None = None) -> dict:
    if cutoff.utcoffset() is None:
        raise ValueError('Observation cutoff requires timezone')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config.get('schema_version') != 'hotspot-manual-scan-config-v1' or config.get('action') != 'no_order':
        raise ValueError('Unsupported observation config')
    if set(config) - {'schema_version','action','industry','market','history','limit','dated_quotes'}:
        raise ValueError('Config cannot introduce admission or strategy overrides')
    if type(config['limit']) is not int or not 1 <= config['limit'] <= 30:
        raise ValueError('Observation output limit must be 1..30')
    sources = []
    payloads = {}
    for role in ('industry','market'):
        raw, source = read_bound(root, config[role], cutoff)
        payload = json.loads(raw)
        if aware(payload['fetched_at']) != aware(source['available_at']):
            raise ValueError('Bound availability differs from provider acquisition')
        sources.append(dict(source, role=role))
        payloads[role] = payload
    industries = parse_sina_industry(payloads['industry'])
    market = parse_tencent_board(payloads['market'])
    index = {row['symbol']:row for row in industries}
    if len(index) != len(industries) or len({r['symbol'] for r in market}) != len(market):
        raise ValueError('Duplicate securities in source snapshot')
    grouped = {}
    valid = []
    for raw, normalized in zip(payloads['industry']['rows'], industries):
        try:
            change = Decimal(str(raw['changepercent']))
            amount = Decimal(str(raw['amount']))
            if not change.is_finite() or not amount.is_finite() or amount < 0:
                continue
        except (ValueError, KeyError, ArithmeticError):
            continue
        industry = normalized['industry']
        if industry:
            grouped.setdefault(industry, []).append(change)
        valid.append((normalized, change, amount))
    market_mean = sum(c for _,c,_ in valid)/len(valid) if valid else None
    sectors = [dict(theme=name, classification='SINA_SHENWAN', securities=len(changes),
        equal_weight_change_percent=str(sum(changes)/len(changes)),
        relative_to_covered_universe_percent=str(sum(changes)/len(changes)-market_mean),
        status='HISTORICAL_SNAPSHOT_OBSERVATION', persistence='UNKNOWN', catalyst='UNKNOWN')
        for name, changes in grouped.items()]
    sectors.sort(key=lambda s:Decimal(s['equal_weight_change_percent']), reverse=True)
    # Output ordering is descriptive turnover ordering, never an entry score.
    valid.sort(key=lambda item:item[2], reverse=True)
    observations = [dict(symbol=row['symbol'], name=row['name'], industry=row['industry'],
        snapshot_change_percent=str(change), snapshot_amount_cny=str(amount),
        status='HOT_WATCH' if change>0 else 'NO_SIGNAL', status_scope='RESEARCH_OBSERVATION_ONLY',
        confirmed_market_date=None, source_refs=[config['industry']['sha256']],
        risk_flags=['ST_NAME_MARKER'] if 'ST' in row['name'].upper() else ['ST_AND_SUSPENSION_NOT_VERIFIED'],
        periods={period:dict(status='UNKNOWN',reason='No time-bound bars supplied for this security') for period in ('daily','60m','15m')},
        gates=observation_gates(), entry_review_eligible=False, next_observation='Obtain dated bars, source catalyst and independent risk/value review',
        invalidation='Source date/hash conflict or unsupported theme catalyst',action='no_order')
        for row,change,amount in valid[:config['limit']]]
    bars, history_sources = load_quote_history(root, config['history'], cutoff)
    sources.extend(dict(s,role='history') for s in history_sources)
    history_symbol = json.loads((root/config['history']['path']).read_text(encoding='utf-8'))['symbol']
    price_behavior = dict(symbol=history_symbol, periods={'daily':describe_bars(bars),
        '60m':dict(status='UNKNOWN',reason='No retained 60m original'),
        '15m':dict(status='UNKNOWN',reason='No retained 15m original')},
        contemporaneous_with_market_snapshot=False, gates=observation_gates(), action='no_order')
    fingerprint = hashlib.sha256(json.dumps(price_behavior,sort_keys=True).encode()).hexdigest()
    dated=[]
    if config.get('dated_quotes'):
        dated,dated_source=load_dated_quotes(root,config['dated_quotes'],cutoff)
        sources.append(dict(dated_source,role='dated_quotes'))
    dated_days={q['quote_date'] for q in dated if q['quote_date'] is not None}
    confirmed_date=next(iter(dated_days)) if len(dated_days)==1 else None
    output = require_inside(root/'runtime', output, 'hotspot output')
    if not prepared_output:
        output.mkdir(parents=True,exist_ok=False)
    elif (output/'report.json').exists():
        raise FileExistsError('Hotspot report already exists')
    result = dict(schema_version='hotspot-observation-report-v1',status='HOTSPOT_RESEARCH_MVP_USABLE',
        scope='MANUAL_CACHED_RESEARCH_NOT_CURRENT_HOTSPOT_OR_TRADE_ADMISSION',
        observed_at=cutoff.isoformat(),generated_at=datetime.now().astimezone().isoformat(),
        market_snapshot_acquired_at=config['market']['available_at'],confirmed_market_date=confirmed_date,
        confirmed_market_date_scope='DATED_QUOTE_SUBSET_ONLY_NOT_INDUSTRY_SNAPSHOT',dated_quote_observations=dated,
        confirmed_price_behavior_date=bars[-1]['date'],classification_as_of='UNKNOWN',
        coverage=dict(industry_rows=len(industries),market_rows=len(market),valid_quote_rows=len(valid),
            themes=len(sectors),universe_survivorship='UNKNOWN'),themes=sectors,
        observation_list=observations,price_behavior=price_behavior,sources=sources,
        config_binding=dict(path=config_path.relative_to(root).as_posix(),sha256=sha256_file(config_path)),
        deterministic_explanation=dict(status='RULE_EXPLANATION_ONLY',input_sha256=fingerprint,
            text='Catalyst and persistence are unknown. Unadjusted prices and missing intraday data cannot establish an entry.',
            cannot_override_rules=True),
        missing_features=['60m','15m','official_catalyst','theme_persistence','verified_fund_flows'],
        gates=observation_gates(),entry_review_eligible=False,collection=collection or {'mode':'OFFLINE_VERIFIED_REPLAY','network_attempted':False,'fallback':False},action='no_order')
    result['semantic_content'] = dict(
        scope=result['scope'], confirmed_market_date=confirmed_date, dated_quote_observations=dated,
        snapshot_acquisition_date=config['market']['available_at'][:10],
        themes=sectors, observations=deepcopy(observations), price_behavior=price_behavior,
        events={'status':'UNKNOWN','items':[]}, gates=result['gates'], action='no_order')
    # Provider payload content, without collector wall-clock metadata.
    result['semantic_content']['market_content_sha256'] = {
        role:hashlib.sha256(json.dumps(payloads[role]['rows'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        for role in ('market','industry')}
    for observation in result['semantic_content']['observations']:
        observation.pop('source_refs',None)
    result['semantic_content_sha256']=hashlib.sha256(json.dumps(result['semantic_content'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    write_new_json(output/'report.json',result)
    from .report_text import render_hotspot_markdown
    (output/'report.md').write_text(render_hotspot_markdown(result),encoding='utf-8')
    return result
