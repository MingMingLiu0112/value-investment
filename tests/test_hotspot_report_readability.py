"""Verify readable presentation and unchanged research boundaries."""
import copy
import json
from pathlib import Path
import pytest
from value_investment_agent.application.hotspot.report_text import render_hotspot_markdown


def _prepared():
    root = Path(__file__).resolve().parents[1]
    return root, render_hotspot_markdown


def test_prepared_real_report_dates_levels_and_no_mutation():
    root, render = _prepared()
    path = root / 'runtime/daily-trade-assistant/20261012-productization-canonical-publish-v4/hotspot-observation/report.json'
    if not path.is_file():
        pytest.skip('local real report evidence is unavailable in a clean checkout')
    report = json.loads(path.read_text(encoding='utf-8'))
    before = copy.deepcopy(report)
    text = render(report)
    assert '| 000651 | 2026-10-09 | 38.83 |' in text
    assert '2026-09-22' in text and '38.18元' in text
    assert '支撑：37.83元' in text and '阻力：38.79元' in text
    assert '5.53%' in text and '-0.31%' in text
    assert '不是交易日期' in text and '后续报价不能据此证明当前突破' in text
    assert '不合成周期' in text and '不产生订单' in text
    assert report == before


def test_isolated_dates_prices_and_missing_periods_are_kept_separate():
    report = dict(market_snapshot_acquired_at='2026-10-12T00:00:00+08:00',
        dated_quote_observations=[dict(symbol='123456', quote_date='2026-10-09',
            price='100.00', status='DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION')],
        price_behavior=dict(symbol='123456', periods=dict(daily=dict(
            status='OBSERVED_NOT_ADMITTED', first_date='2026-01-01', last_date='2026-09-22',
            bars=100, close='90.00', prior_five_bar_support='88.00',
            prior_five_bar_resistance='92.00', five_bar_price_change='0.0553',
            breakout=False, below_support=False))),
        themes=[dict(theme='Synthetic sector', equal_weight_change_percent='-0.312345')])
    before = copy.deepcopy(report)
    text = render_hotspot_markdown(report)
    assert '| 123456 | 2026-10-09 | 100.00 |' in text
    assert '2026-09-22' in text and '90.00元' in text
    assert '支撑：88.00元' in text and '阻力：92.00元' in text
    assert '5.53%' in text and '-0.31%' in text
    assert '不是交易日期' in text and '后续报价不能据此证明当前突破' in text
    assert '不合成周期' in text and '不产生订单' in text
    assert report == before


def test_prepared_unknown_quote_and_insufficient_history():
    _, render = _prepared()
    report = dict(market_snapshot_acquired_at='2026-10-12T00:00:00+08:00',
                  dated_quote_observations=[dict(symbol='123456',status='UNKNOWN',quote_date=None)],
                  price_behavior=dict(symbol='123456',periods=dict(daily=dict(status='UNKNOWN'))), themes=[])
    text = render(report)
    assert '| 123456 | 未知 | 未知 |' in text
    assert '关键价位未知' in text
    report['dated_quote_observations'] = []
    assert '无已核验带日期报价' in render(report)
