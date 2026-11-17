"""Read the signed operating adjustments from an explicit parent cash-flow note."""
from decimal import Decimal
import re
import unicodedata

_HEADING = "母公司现金流量表补充资料"
_CASH_TOTAL = "经营活动产生的现金流量净额"
_ADJUSTMENTS = {
    "inventory": "存货的减少",
    "operating_receivables": "经营性应收项目的减少",
    "operating_payables": "经营性应付项目的增加",
}
_AMOUNT = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}"


def _pair(pattern, text):
    matches = re.findall(pattern + r"\s+(" + _AMOUNT + r")\s+(" + _AMOUNT + r")(?=\s|$)", text)
    if len(matches) != 1:
        raise ValueError("PARENT_WC_CASH_ROW_MISSING_OR_AMBIGUOUS")
    return tuple(Decimal(value.replace(",", "")) for value in matches[0])


def _parent_note_pages(pages):
    for number, raw in enumerate(pages, 1):
        for line in unicodedata.normalize("NFKC", raw).splitlines():
            heading = re.sub(r"\s+", "", line)
            if re.fullmatch(r"(?:\([一二三四五六七八九十]+\))?" + _HEADING, heading):
                yield number, raw, line


def has_explicit_parent_note(pages):
    return next(_parent_note_pages(pages), None) is not None


def read_parent_working_capital_cash(pages, *, verified_parent_cfo_cny):
    """Require both periods to match an independently verified CNY parent cash statement.

    A caller must bind the statement and note to the same issuer, report, currency
    and ordered periods before admission. Values here use the printed cash-impact
    sign. They are historical reconciliation adjustments, not model outflows.
    """
    notes = list(_parent_note_pages(pages))
    if len(notes) != 1:
        raise ValueError("PARENT_WC_CASH_EXPLICIT_NOTE_REQUIRED")
    page, raw, heading = notes[0]
    document = unicodedata.normalize("NFKC", raw).replace("−", "-")
    text = document.split(heading, 1)[1]
    table = re.match(r"\s*补充资料\s+本期数\s+上年同期数\s+1[.、]\s*将净利润调节为经营活动现金流量[:：]", text)
    if table is None or text.count(_CASH_TOTAL) != 1:
        raise ValueError("PARENT_WC_CASH_COLUMNS_OR_SCOPE_UNVERIFIED")
    total = _pair(_CASH_TOTAL, text[table.end():])
    if tuple(verified_parent_cfo_cny) != total:
        raise ValueError("PARENT_WC_CASH_PARENT_CFO_MISMATCH")
    block = text[table.end():text.index(_CASH_TOTAL)]
    values = {
        key: _pair(label + r"\s*\([^)]{1,40}\)", block)
        for key, label in _ADJUSTMENTS.items()
    }
    return dict(physical_page=page, unit="CNY", scope="ISSUER_PARENT_STANDALONE",
                field="working_capital_cash_component",
                row_amounts_cny={key: [str(amount) for amount in pair] for key, pair in values.items()},
                cash_impact_cny=[str(sum(amounts)) for amounts in zip(*values.values())],
                parent_cfo_cny=[str(amount) for amount in total], action="no_order")
