"""Read numbered annual parent working-capital notes with ordered cumulative columns."""

from decimal import Decimal
import re
import unicodedata

from .parent_working_capital_cash import read_parent_working_capital_cash

_HEADING = re.compile(
    r"(?m)^[ \t]*[1-9][0-9]{0,2}\.[ \t]*母公司现金流量表补充资料[ \t]*\r?\n"
    r"[ \t]*项目[ \t]+本年累计数[ \t]+上年累计数[ \t]*(?=\r?$)"
)


def read_numbered_annual_parent_wc(pages, *, issuer_name, period_end, verified_parent_cfo_cny):
    """Parse the visible note and tie it to an independently verified parent CFO pair."""
    if (not re.fullmatch(r"20[0-9]{2}-12-31", period_end)
            or not issuer_name.strip()
            or len(verified_parent_cfo_cny) != 2
            or not all(isinstance(v, Decimal) and v.is_finite() for v in verified_parent_cfo_cny)):
        raise ValueError("NUMBERED_PARENT_WC_IDENTITY_OR_CFO_INVALID")
    candidates = []
    for index, raw in enumerate(pages):
        page = unicodedata.normalize("NFKC", raw)
        for match in _HEADING.finditer(page):
            candidates.append((index, page, match))
    if len(candidates) != 1:
        raise ValueError("NUMBERED_PARENT_WC_NOTE_MISSING_OR_AMBIGUOUS")
    index, page, match = candidates[0]
    lines = ["".join(line.split()) for line in page[:match.start()].splitlines()]
    issuer = "".join(unicodedata.normalize("NFKC", issuer_name).split())
    period = period_end[:4] + "年12月31日止年度"
    if (issuer not in lines or period not in lines
            or "(除特别注明外,金额单位为人民币元)" not in lines
            or not any(re.fullmatch(r"[一二三四五六七八九十]+、母公司财务报表主要项目附注(?:-续)?", line)
                       for line in lines)):
        raise ValueError("NUMBERED_PARENT_WC_ISSUER_PERIOD_CURRENCY_OR_SCOPE_INVALID")
    projected = list(pages)
    projected[index] = (page[:match.start()] + "母公司现金流量表补充资料\n补充资料 本期数 上年同期数"
                        + page[match.end():])
    result = read_parent_working_capital_cash(projected, verified_parent_cfo_cny=verified_parent_cfo_cny)
    return {**result, "layout_version": "numbered-annual-parent-wc-v1", "issuer_name": issuer_name,
            "period_end": period_end, "comparative_period_end": f"{int(period_end[:4]) - 1}-12-31"}
