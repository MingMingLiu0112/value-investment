"""Extract a standalone parent's selected trade balances and procurement cash."""

from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import re

from .pdf_text import extract_pages

TRADE_ASSETS = ("应收账款", "应收款项融资", "预付款项", "存货")
TRADE_LIABILITIES = ("应付票据", "应付账款", "合同负债")
PROCUREMENT = "购买商品、接受劳务支付的现金"
NUMBER = re.compile(r"-?[0-9][0-9,]*\.[0-9]{2}")


def read_parent_trade_balances(path: Path, *, expected_sha256: str, issuer_name: str,
                               balance_periods: tuple[str, str],
                               cash_periods: tuple[str, str]) -> dict:
    """Return two-column reported rows, plus a diagnostic balance bridge."""
    if sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("PARENT_TRADE_SOURCE_HASH_CHANGED")
    if not isinstance(issuer_name, str) or not issuer_name.strip():
        raise ValueError("PARENT_TRADE_ISSUER_REQUIRED")
    pages = extract_pages(path)

    def locate(title, periods):
        indices = [i for i, page in enumerate(pages) if title in {line.strip() for line in page.splitlines()}]
        if len(indices) != 1:
            raise ValueError("PARENT_TRADE_TABLE_NOT_UNIQUE")
        page = pages[indices[0]]
        if not any("".join(line.split()).startswith(issuer_name) for line in page.splitlines()[:3]):
            raise ValueError("PARENT_TRADE_ISSUER_CHANGED")
        if "单位：元币种：人民币" not in "".join(page.split()):
            raise ValueError("PARENT_TRADE_CNY_UNIT_REQUIRED")
        current, comparative = periods
        header = "项目附注" + "".join(current.split()) + "".join(comparative.split())
        if (not current.strip() or not comparative.strip() or current == comparative
                or header not in {"".join(line.split()) for line in page.splitlines()}):
            raise ValueError("PARENT_TRADE_PERIODS_CHANGED")
        return indices[0]

    def rows(indices, fields):
        result = {}
        for field in fields:
            matches = [(i, line) for i in indices for line in pages[i].splitlines()
                       if line.strip().split(maxsplit=1)[:1] == [field]]
            if len(matches) != 1:
                raise ValueError("PARENT_TRADE_ROW_NOT_UNIQUE:" + field)
            i, line = matches[0]
            values = [Decimal(v.replace(",", "")) for v in NUMBER.findall(line)]
            if field == "应收款项融资" and len(values) < 2:
                # Linearized PDF text cannot identify which column a lone value occupies.
                result[field] = dict(physical_page=i + 1, current=None, comparative=None)
                continue
            if len(values) != 2:
                raise ValueError("PARENT_TRADE_TWO_COLUMNS_REQUIRED:" + field)
            result[field] = dict(physical_page=i + 1, current=str(values[0]), comparative=str(values[1]))
        return result

    balance = locate("母公司资产负债表", balance_periods)
    cash = locate("母公司现金流量表", cash_periods)
    if balance + 1 >= cash:
        raise ValueError("PARENT_TRADE_TABLE_ORDER_INVALID")
    selected = rows((balance, balance + 1), TRADE_ASSETS + TRADE_LIABILITIES)
    supplier = rows((cash,), (PROCUREMENT,))[PROCUREMENT]
    missing = [name for name, row in selected.items() if row["current"] is None]
    proxy = None
    if not missing:
        changes = {name: Decimal(row["current"]) - Decimal(row["comparative"])
                   for name, row in selected.items()}
        proxy = sum(changes[name] for name in TRADE_LIABILITIES) - sum(changes[name] for name in TRADE_ASSETS)
    return dict(issuer_name=issuer_name, scope="PARENT_STANDALONE", currency="CNY",
                source_sha256=expected_sha256,
                balance_periods=list(balance_periods), cash_periods=list(cash_periods),
                trade_balances=selected, procurement_payments=supplier,
                missing_trade_balances=missing,
                selected_balance_movement_proxy_cny=str(proxy) if proxy is not None else None,
                classification="HISTORICAL_BALANCE_PROXY_NOT_CASH_OR_FORECAST",
                action="no_order")

def reconcile_parent_trade_intervals(first_half: dict, full_year: dict, next_first_half: dict,
                                     *, fiscal_year: int) -> dict:
    """Build three comparable intervals from replayed parent filings."""
    reports = (first_half, full_year, next_first_half)
    if len({report["issuer_name"] for report in reports}) != 1 or any(
        (report["scope"], report["currency"], report["action"]) != ("PARENT_STANDALONE", "CNY", "no_order")
        for report in reports
    ):
        raise ValueError("PARENT_TRADE_ISSUER_OR_SCOPE_CHANGED")
    previous_close = f"{fiscal_year-1}年12月31日"
    year_end = f"{fiscal_year}年12月31日"
    basis = (
        ([f"{fiscal_year}年6月30日", previous_close], [f"{fiscal_year}年半年度", f"{fiscal_year-1}年半年度"]),
        ([year_end, previous_close], [f"{fiscal_year}年度", f"{fiscal_year-1}年度"]),
        ([f"{fiscal_year+1}年6月30日", year_end], [f"{fiscal_year+1}年半年度", f"{fiscal_year}年半年度"]),
    )
    if any((report["balance_periods"], report["cash_periods"]) != periods
           for report, periods in zip(reports, basis, strict=True)):
        raise ValueError("PARENT_TRADE_NONCONTIGUOUS_PERIODS")
    if first_half["procurement_payments"]["current"] != next_first_half["procurement_payments"]["comparative"]:
        raise ValueError("PARENT_TRADE_PROCUREMENT_COMPARATIVE_CHANGED")
    fields = {"应收账款": -1, "存货": -1, "应付账款": 1}
    totals = [Decimal(0)] * 3
    movements = {}
    for field, sign in fields.items():
        first, annual, following = (report["trade_balances"][field] for report in reports)
        if first["comparative"] != annual["comparative"] or annual["current"] != following["comparative"]:
            raise ValueError("PARENT_TRADE_OPENING_BALANCE_CHANGED:" + field)
        values = tuple(Decimal(value) for value in (
            first["comparative"], first["current"], annual["current"], following["current"]))
        if any(not value.is_finite() or value < 0 for value in values):
            raise ValueError("PARENT_TRADE_BALANCE_INVALID:" + field)
        changes = [end - start for start, end in zip(values[:-1], values[1:], strict=True)]
        totals = [total + sign * change for total, change in zip(totals, changes, strict=True)]
        movements[field] = [str(value) for value in changes]
    second_half_paid = Decimal(full_year["procurement_payments"]["current"]) - Decimal(
        first_half["procurement_payments"]["current"])
    if not second_half_paid.is_finite() or second_half_paid < 0:
        raise ValueError("PARENT_TRADE_PROCUREMENT_CUMULATIVE_INVALID")
    return dict(issuer_name=first_half["issuer_name"], scope="PARENT_STANDALONE", currency="CNY",
                periods=[f"{fiscal_year}H1", f"{fiscal_year}H2", f"{fiscal_year+1}H1"],
                source_sha256=[report["source_sha256"] for report in reports],
                balance_movements_cny=movements, cash_direction_balance_proxy_cny=list(map(str, totals)),
                second_half_procurement_paid_cny=str(second_half_paid),
                operating_wc_cash_cny=None, action="no_order",
                classification="HISTORICAL_BALANCE_PROXY_NOT_CASH_OR_FORECAST")
