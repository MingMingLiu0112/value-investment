"""Report which workbook-facing data is present in the central database.

This is intentionally read-only. It distinguishes public-source gaps from fields
that the system must not calculate before official evidence and human review.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from value_investment_agent.db import connect, latest_points  # noqa: E402
from value_investment_agent.settings import get_settings  # noqa: E402
from value_investment_agent.universe import UNIVERSE  # noqa: E402


FINANCIAL_FIELDS = (
    "revenue", "net_income", "operating_cash_flow", "fcf_per_share", "roic",
    "roe", "gross_margin", "net_margin", "revenue_yoy", "net_income_yoy",
    "debt_ratio", "cash", "interest_bearing_debt", "eps_ttm", "bvps", "dps_ttm",
)
RESEARCH_FIELDS = ("fair_value",)


def main() -> None:
    settings = get_settings()
    names = {symbol: name for symbol, name, *_ in UNIVERSE}
    with connect(settings.database_url) as connection:
        points_by_symbol: dict[str, dict[str, dict]] = {symbol: {} for symbol in names}
        for point in latest_points(connection):
            points_by_symbol[point["symbol"]][point["field_name"]] = point
        valuations = {
            row["symbol"]: row
            for row in connection.execute(
                "SELECT symbol, fair_value, safety_margin, build_signal, data_status "
                "FROM valuation_results ORDER BY symbol"
            ).fetchall()
        }

    for symbol, name in names.items():
        points = points_by_symbol[symbol]
        missing = [field for field in FINANCIAL_FIELDS if field not in points]
        supplied = [field for field in FINANCIAL_FIELDS if field in points]
        valuation = valuations.get(symbol, {})
        print(f"{symbol} {name}")
        print(f"  Public data present: {', '.join(supplied) or 'none'}")
        print(f"  Public source missing: {', '.join(missing) or 'none'}")
        if "roic" in missing or "fcf_per_share" in missing:
            print("  Note: ROIC and FCF/share are intentionally blank when the source does not publish an applicable value.")
        if "fair_value" not in points:
            print("  Research data pending: fair_value, safety_margin, build_signal (official evidence + human review required)")
        else:
            print(
                "  Research data: "
                f"fair_value={valuation.get('fair_value')}, safety_margin={valuation.get('safety_margin')}, "
                f"build_signal={valuation.get('build_signal')}"
            )


if __name__ == "__main__":
    main()
