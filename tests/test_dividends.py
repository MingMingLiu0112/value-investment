from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from value_investment_agent.dividends import CninfoDividendAdapter, build_payout_ratio_records


class Row(dict):
    def to_dict(self):
        return dict(self)


class Frame:
    empty = False

    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


def test_cninfo_dividends_sum_paid_cash_dividends_in_trailing_year(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    recent = now.strftime("%Y-%m-%d")
    inside_window = (now - timedelta(days=180)).strftime("%Y-%m-%d")
    outside_window = (now - timedelta(days=800)).strftime("%Y-%m-%d")
    frame = Frame([
        Row({"派息日": recent, "派息比例": 5, "实施方案公告日期": recent}),
        Row({"派息日": inside_window, "派息比例": 3, "实施方案公告日期": inside_window}),
        Row({"派息日": outside_window, "派息比例": 99, "实施方案公告日期": outside_window}),
    ])
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(stock_dividend_cninfo=lambda symbol: frame))

    record = CninfoDividendAdapter().fetch(["600519"])[0]

    assert record.value == Decimal("0.8000")
    assert record.point_metadata["event_count"] == 2
    assert record.source_name == "CNINFO statutory dividend history"


def test_payout_ratio_uses_dps_and_eps_ttm() -> None:
    points = [
        {"symbol": "600519", "field_name": "dps_ttm", "value": Decimal("0.8"), "period_label": "2026-09-04", "source_id": "dps"},
        {"symbol": "600519", "field_name": "eps_ttm", "value": Decimal("4"), "period_label": "2026-06-30", "source_id": "eps"},
    ]
    record = build_payout_ratio_records(points, ["600519"])[0]

    assert record.value == Decimal("20.00")
    assert record.point_metadata["calculation"]["formula"] == "DPS_TTM / EPS_TTM * 100"
