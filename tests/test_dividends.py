from __future__ import annotations

import sys
from datetime import datetime, timezone
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
    today = datetime.now(timezone.utc).year
    frame = Frame([
        Row({"派息日": f"{today}-06-01", "派息比例": 5, "实施方案公告日期": f"{today}-05-20"}),
        Row({"派息日": f"{today - 1}-10-01", "派息比例": 3, "实施方案公告日期": f"{today - 1}-09-15"}),
        Row({"派息日": f"{today - 2}-01-01", "派息比例": 99, "实施方案公告日期": f"{today - 2}-01-01"}),
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
