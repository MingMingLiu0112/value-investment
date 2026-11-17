"""Extract reported revenue and operating cost from a paginated annual income table."""
from decimal import Decimal
import re

from .official_report_acquisition import _verify_cover

_AMOUNT = r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)\.[0-9]{2}"


def observe_annual_cost_pair(*, pages: list[str], symbol: str, issuer_name: str,
                             period: str) -> list[dict]:
    if re.fullmatch(r"[0-9]{4}-12-31", period) is None:
        raise ValueError("EXACT_ANNUAL_COST_PERIOD_REQUIRED")
    _verify_cover(pages[:12], symbol=symbol, issuer_name=issuer_name, period=period, kind="annual")
    year = int(period[:4])
    starts = [(n, index) for n, page in enumerate(pages) for index, line in enumerate(page.splitlines())
              if line.strip() == "合并利润表"]
    if len(starts) != 1:
        raise ValueError("CONSOLIDATED_INCOME_TABLE_MISSING_OR_DUPLICATE")
    page, start = starts[0]
    lines = [line.strip() for line in pages[page].splitlines()]
    compact = lambda line: "".join(line.split()).replace("：", ":").replace("—", "-")
    preceding = [compact(line) for line in lines[max(0, start-3):start]]
    if ("编制单位:" + compact(issuer_name) not in preceding
            or f"{year}年1-12月" not in preceding
            or [compact(line) for line in lines[start+1:start+3]] != [
                "单位:元币种:人民币", f"项目附注{year}年度{year-1}年度"]):
        raise ValueError("PAGINATED_COST_TABLE_SCOPE_OR_COLUMNS_NOT_PROVEN")
    rows = lines[start+3:]
    if any(line in {"母公司利润表", "合并现金流量表", "母公司现金流量表"} for line in rows):
        raise ValueError("PAGINATED_COST_TABLE_SCOPE_CHANGED")
    result = []
    for field, label in (("revenue", "营业收入"), ("cost", "营业成本")):
        pattern = re.compile(rf"^其中[：:]\s*{label}\s+[一二三四五六七八九十]+、[0-9]+\s+({_AMOUNT})\s+({_AMOUNT})$")
        matches = [(line, pattern.fullmatch(line)) for line in rows if re.match(rf"^其中[：:]\s*{label}(?![\u4e00-\u9fff])", line)]
        if len(matches) != 1 or matches[0][1] is None:
            raise ValueError("PAGINATED_COST_ROW_MISSING_OR_AMBIGUOUS:" + field)
        line, match = matches[0]
        for cohort, value in zip((year, year-1), match.groups()):
            result.append(dict(field=field, value=str(Decimal(value.replace(",", ""))),
                period=f"{cohort}-12-31", period_basis="FY", unit="CNY", scope="consolidated",
                physical_page=page+1, text=line))
    return result
