"""User-readable report text without changing observation semantics."""
from decimal import Decimal


def render_hotspot_markdown(report):
    lines = ['# 热点研究观察', '', '仅供研究，未获交易准入，不产生订单。',
             f"市场原文采集时间：{report['market_snapshot_acquired_at']}（不是交易日期）。",
             '行业快照交易日期未知；以下报价只证明各证券所列日期，不代表全市场日期。',
             '', '## 带日期报价', '', '| 证券代码 | 报价日期 | 价格（元） | 核验状态 |',
             '| --- | --- | ---: | --- |']
    for quote in report['dated_quote_observations']:
        valid = quote['status'] == 'DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION'
        lines.append(f"| {quote['symbol']} | {quote.get('quote_date') or '未知'} | {quote.get('price') if valid else '未知'} | {'双源日期与价格一致，未获价格准入' if valid else '未知，未获价格准入'} |")
    if not report['dated_quote_observations']:
        lines.append('| — | 未知 | 未知 | 无已核验带日期报价 |')
    behavior = report['price_behavior']
    daily = behavior['periods']['daily']
    lines += ['', '## 历史日线关键价位', '', f"证券：{behavior['symbol']}。"]
    if daily['status'] == 'OBSERVED_NOT_ADMITTED':
        change = Decimal(daily['five_bar_price_change']) * 100
        lines += [f"历史范围：{daily['first_date']}至{daily['last_date']}，共{daily['bars']}根日线。",
                  f"历史末日收盘：{daily['close']}元；此前五根日线支撑：{daily['prior_five_bar_support']}元；阻力：{daily['prior_five_bar_resistance']}元。",
                  f"五根日线价格变化：{change:.2f}%；历史末日突破阻力：{'是' if daily['breakout'] else '否'}；跌破支撑：{'是' if daily['below_support'] else '否'}。",
                  '上述价位仅适用于历史窗口；后续报价不能据此证明当前突破。价格未复权，公司行动与成交量口径未核验。',
                  '失效观察：后续完整收盘跌破历史支撑时需重新研究；这不是卖出指令。']
    else:
        lines.append('历史日线不足，关键价位未知。')
    lines += ['60分钟与15分钟：未知，无对应原件；不合成周期。', '', '## 行业快照', '',
              '交易日期未知，不是今日热点。百分比为覆盖证券等权变化，非行业指数收益。', '',
              '| 行业 | 等权变化 | 持续性／催化剂 |', '| --- | ---: | --- |']
    for sector in report['themes'][:10]:
        change = Decimal(sector['equal_weight_change_percent'])
        lines.append(f"| {sector['theme']} | {change:.2f}% | 未知 |")
    lines += ['', '价值、风险、事件、PIT、样本外与Shadow等门禁仍未证明；观察状态不构成买卖建议。']
    return '\n'.join(lines) + '\n'
