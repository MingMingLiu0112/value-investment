"""Replay a bounded annual-report industry manufacturing cost schedule."""
from decimal import Decimal, ROUND_HALF_UP
import re

from .native_capital_observation_v1 import _compact


LABELS = ("直接材料", "直接人工", "制造费用", "装卸运输费")
HEADER = (
    "成本分析表单位:元币种:人民币分行业情况分行业成本构成项目本期金额"
    "本期占总成本比例(%)上年同期金额上年同期占总成本比例(%)"
    "本期金额较上年同期变动比例(%)情况说明"
)
MONEY = r"(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})"
PERCENT = r"(\d{1,3}\.\d{2})"
CHANGE = r"(-?\d+\.\d{2})"


def parse_industry_cost_composition(*, cover: str, page: str, symbol: str,
                                    issuer_name: str, fiscal_year: int, industry: str) -> dict:
    """Verify the reported mix without inferring a fixed/variable split."""
    title = _compact(cover)
    if (
        not re.fullmatch(r"[0-9]{6}", symbol)
        or not issuer_name
        or not industry
        or f"公司代码:{symbol}公司简称:" not in title
        or issuer_name + symbol + f"{fiscal_year}年年度报告" not in title
        or "摘要" in title
    ):
        raise ValueError("COST_COMPOSITION_REPORT_IDENTITY_INVALID")
    text = _compact(page)
    if len(text) > 30_000 or text.count(HEADER) != 1:
        raise ValueError("COST_COMPOSITION_UNIT_OR_COLUMNS_INVALID")
    body = text.split(HEADER, 1)[1].split("分产品情况", 1)
    parts = [re.escape(_compact(industry))]
    for label in LABELS:
        parts.extend((re.escape(label), MONEY, PERCENT, MONEY, PERCENT, CHANGE))
    match = re.fullmatch("".join(parts), body[0]) if len(body) == 2 else None
    if match is None:
        raise ValueError("COST_COMPOSITION_ROWS_OR_SCOPE_INVALID")
    rows = {}
    for i, label in enumerate(LABELS):
        current, current_share, prior, prior_share, change = (
            Decimal(v.replace(",", "")) for v in match.groups()[i * 5:(i + 1) * 5]
        )
        if min(current, prior) <= 0 or max(current_share, prior_share) > 100:
            raise ValueError("COST_COMPOSITION_VALUES_INVALID")
        cent = Decimal("0.01")
        if ((current / prior - 1) * 100).quantize(cent, rounding=ROUND_HALF_UP) != change:
            raise ValueError("COST_COMPOSITION_YEAR_CHANGE_MISMATCH")
        rows[label] = (current, current_share, prior, prior_share)
    totals = tuple(sum(row[column] for row in rows.values()) for column in (0, 2))
    discrepancies = []
    for label, row in rows.items():
        for offset, total, year in zip((0, 2), totals, (fiscal_year, fiscal_year - 1), strict=True):
            recalculated = (row[offset] * 100 / total).quantize(cent, rounding=ROUND_HALF_UP)
            if recalculated != row[offset + 1]:
                discrepancies.append({
                    "label": label, "year": year, "reported_pct": str(row[offset + 1]),
                    "recomputed_pct": str(recalculated),
                })
    return {
        "symbol": symbol,
        "issuer_name": issuer_name,
        "industry": industry,
        "periods": [f"{fiscal_year}-12-31", f"{fiscal_year - 1}-12-31"],
        "amount_unit": "CNY",
        "historical_rows": {label: [str(v) for v in row] for label, row in rows.items()},
        "labor_and_overhead_share_pct": [
            str(rows["直接人工"][column] + rows["制造费用"][column]) for column in (1, 3)
        ],
        "printed_share_discrepancies": discrepancies,
        "fixed_cogs_share": None,
        "action": "no_order",
    }
