"""Real issuer correction replay, retaining pre-correction historical facts."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path('D:/GPTProject/value-investment')
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
from value_investment_agent.historical_asof import select_asof, publication_date_upper_bound
from check_moutai_ttm_comparability import texts

BASE = ROOT/'runtime/company-research'
VERSIONS = BASE/'000858-comparative-versions-20260909T125609878982Z'
CORRECTION = BASE/'000858-accounting-correction-20260909T125822339983Z'
CURRENT = BASE/'000858-peer-interim-20260909T125304973619Z'
PINS = {
    VERSIONS/'1224596951.pdf': 'e460cfeaac9388f493dcafc14f4f5a6f83521f24a5ad3d3dd8a447cb437d755a',
    VERSIONS/'1225273126.pdf': '43763a06159d47b7ec2600a8c6c73fcc28799643849b5dd1f855ed29a9996f2a',
    CORRECTION/'1225273122.pdf': '466e1e18f25c1391fd160945b5977ce83732a40f223fc0dee7407bd90bb0e10d',
    CURRENT/'000858-1225531252.pdf': '15153679faee48d1b1b00c50557a88bdcbdf8cb4cbc49b8762e10f70210dfb5b',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_page(path, page, values):
    decoded = texts(path, page)
    for value in values:
        token = format(D(value), ',.2f')
        if any(token not in t for t in decoded):
            raise ValueError(f'Original page mismatch: {path.name} p{page} {token}')


def main():
    for path, digest in PINS.items():
        if sha(path) != digest:
            raise ValueError('Pinned source changed: '+str(path))
    manifest = json.loads((VERSIONS/'manifest.json').read_text(encoding='utf-8'))
    index = Path(manifest['official_index'])
    if sha(index) != manifest['index_sha256']:
        raise ValueError('Official announcement index changed')
    announcements = json.loads(index.read_text(encoding='utf-8'))['response']['announcements']
    versions = [
        ('1224596951', '2025-08-28', {'revenue':'52770984383.52', 'parent_net_income':'19491942398.53'}),
        ('1225273126', '2026-04-30', {'revenue':'23509972048.65', 'parent_net_income':'4623850715.13'}),
    ]
    points = []
    for identifier, published, values in versions:
        matches = [r for r in announcements if str(r['announcementId']) == identifier and r['secCode'] == '000858']
        if len(matches) != 1:
            raise ValueError('Official issuer/version identity mismatch')
        item = matches[0]
        day = datetime.fromtimestamp(item['announcementTime']/1000, timezone(timedelta(hours=8))).date().isoformat()
        if day != published or item['adjunctUrl'] != f'finalpage/{published}/{identifier}.PDF':
            raise ValueError('Official publication date mismatch')
        pdf = VERSIONS/(identifier+'.pdf')
        check_page(pdf, 6, values.values())
        for field, value in values.items():
            points.append(dict(symbol='000858', field_name=field, period_label='2025-06-30', value=value,
                unit='CNY', validation_status='verified', source_id=identifier, raw_file_hash=sha(pdf),
                source_url='https://static.cninfo.com.cn/'+item['adjunctUrl'], physical_page=6,
                timestamp_precision='date', publication_date_verified=True, availability_bound_verified=True,
                availability_method='china_publication_date_upper_bound', published_date=published,
                available_at=publication_date_upper_bound(published).isoformat(),
                verification_scope='Authenticated issuer table and revision chain; not independent external audit'))
    boundaries = [
        ('2025-08-28T23:59:59+08:00', None),
        ('2025-08-29T00:00:00+08:00', '1224596951'),
        ('2025-12-31T15:00:00+08:00', '1224596951'),
        ('2026-04-30T15:00:00+08:00', '1224596951'),
        ('2026-04-30T23:59:59+08:00', '1224596951'),
        ('2026-05-01T00:00:00+08:00', '1225273126'),
        ('2026-09-09T15:00:00+08:00', '1225273126'),
    ]
    runs = []
    for timestamp, expected in boundaries:
        for field in ['revenue', 'parent_net_income']:
            selected = select_asof(points, symbol='000858', field_name=field,
                                   period_label='2025-06-30', decision_at=timestamp)
            ids = [r['source_id'] for r in selected]
            if ids != ([] if expected is None else [expected]):
                raise ValueError('Real correction replay leaked or selected wrong version')
            runs.append(dict(decision_at=timestamp, field=field, expected=expected,
                             selected=ids, value=selected[0]['value'] if selected else None))
    old, adjustment, new = map(D, ['52770984383.52','-29261012334.87','23509972048.65'])
    check_page(CORRECTION/'1225273122.pdf', 3, [old, adjustment, new])
    if old+adjustment != new or F(old)+F(adjustment) != F(new):
        raise ValueError('Correction arithmetic failed')
    explanation = texts(CORRECTION/'1225273122.pdf', 1)
    for phrase in ['调整2025年部分业务收入确认相关核算', '不影响现金流量表列示']:
        if any(phrase not in t for t in explanation):
            raise ValueError('Correction explanation not located')
    revenue, profit = D('28416674541.77'), D('8752942991.31')
    check_page(CURRENT/'000858-1225531252.pdf', 6, [revenue, new, profit, '4623850715.13'])
    current_selling, prior_selling = D('6322231378.53'), D('3499723307.95')
    current_cfo, prior_cfo = D('-2153568792.32'), D('31136736628.58')
    check_page(CURRENT/'000858-1225531252.pdf', 11, [current_selling, prior_selling, current_cfo, prior_cfo])
    diagnostics = {
        'revenue_yoy_revised_comparable':str(revenue/new-1),
        'parent_profit_yoy_revised_comparable':str(profit/D('4623850715.13')-1),
        'revenue_change_vs_superseded_not_valid_yoy':str(revenue/old-1),
        'current_selling_to_revenue':str(current_selling/revenue),
        'prior_selling_to_revised_revenue':str(prior_selling/new),
        'selling_intensity_change_pp':str((current_selling/revenue-prior_selling/new)*100),
        'current_cfo':str(current_cfo), 'prior_cfo':str(prior_cfo),
    }
    out = BASE/('000858-revision-replay-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result = {'symbol':'000858', 'points':points, 'boundary_replays':runs, 'checks_passed':len(runs),
        'source_checks':'PDF hashes, official index dates/identity, two PDF decoders, correction arithmetic',
        'diagnostics':diagnostics, 'valuation_approved':False, 'strategy_approved':False,
        'historical_backtest_complete':False,
        'conclusion':'Peer reported growth uses revised base; higher selling intensity and negative CFO do not support assuming broad recovery. No direct inference that Moutai is impaired.',
        'limits':['Two decoders are not two independent sources.',
                  'Next-midnight bound is conservative publication-date availability, not an intraday publication timestamp.',
                  'Original figures remain the facts disclosed before correction, not currently endorsed economic truth.',
                  'This verifies financial input vintage selection, not executed strategy performance.',
                  'Revenue recognition adjustment does not itself establish fraud or its detailed economic cause.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    report = f'''# 同行反证及真实财报更正回放

五粮液2026H1收入284.17亿元，同比增长{D(diagnostics['revenue_yoy_revised_comparable']):.2%}；归母利润同比{D(diagnostics['parent_profit_yoy_revised_comparable']):.2%}。这些同比使用2026年4月30日更正后的2025H1基数。

2025H1原披露收入527.71亿元，更正为235.10亿元，调整额-292.61亿元；更正公告解释为梳理业务模式后调整部分业务收入确认核算，明确不影响现金流量表列示。不能臆测更正动机。

当前销售费用占收入{D(diagnostics['current_selling_to_revenue']):.2%}，可比期{D(diagnostics['prior_selling_to_revised_revenue']):.2%}，增加{D(diagnostics['selling_intensity_change_pp']):.2f}个百分点；经营现金流由311.37亿元降至-21.54亿元。收入/利润同比恢复不足以单独证明需求及回款全面恢复。

## 对茅台假设的处理

- 不用同行高同比升级茅台基准/乐观增长参数；现有增长率仍为研究情景，不是行业恢复预测。
- 下一次同行披露继续检查同口径收入、销售费用强度、实际回款及收入确认变化；不可单看同比数值。
- 两家公司产品及渠道并不相同，此反证不能单独证明茅台经营假设失效。

## 历史输入验收

真实原件两项指标、7个时间边界共14项通过。2025年末仍选原披露，2026年4月30日当天在未知具体发布时间时仍采用旧版，5月1日零点以后选修订版。当天保守延迟不冒充实际发布时间。

原PDF、公告日期、字段值、Hash与逐次回放见同目录evidence.json。此项仅证明真实更正链的时间选择，不是完整交易回测。
'''
    (out/'review.md').write_text(report,encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):h for p,h in PINS.items()},
        'official_index_sha256':sha(index), 'script_sha256':sha(Path(__file__)),
        'selector_sha256':sha(ROOT/'src/value_investment_agent/historical_asof.py'),
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'checks':len(runs),'diagnostics':diagnostics},ensure_ascii=False))


if __name__ == '__main__':
    main()
