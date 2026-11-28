"""Official FY/H1 parent statements with separately ruled note and period columns."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

from . import parent_direct_owner_cash_sources as parent
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from ...infrastructure.filings.parent_note_grid_v1 import compact, read_parent_grid

VERSION = "OFFICIAL_PARENT_NOTE_GRID_V1"
INCOME = {"revenue": "营业收入", "cost": "营业成本", "parent_net_profit_cny": "净利润（净亏损以“-”号填列）",
          "interest_expense_cny": "其中：利息费用"}
CASH = {**parent.cash_reader.LABELS, **parent.EXTRA_CASH, "customer_cash_cny": "销售商品、提供劳务收到的现金",
        "supplier_cash_cny": "购买商品、接受劳务支付的现金", "operating_inflow_cny": "经营活动现金流入小计",
        "operating_outflow_cny": "经营活动现金流出小计", "debt_repayments_paid_cny": "偿还债务支付的现金"}


def _rows(grid, labels, source, period, balance=False):
    rows = {}
    for field, label in labels.items():
        matches = [(p, cells) for p, cells in grid if
                   re.sub(r"^(?:[一二三四五六]、|[加减]：)", "", cells[0]).replace("－", "-") == label]
        if len(matches) != 1:
            raise ValueError("NOTE_GRID_ROW_MISSING_OR_AMBIGUOUS:" + field)
        page, cells = matches[0]
        values = []
        for cell in cells[-2:]:
            if cell in ("", "-", "—"):
                values.append(None)
            elif parent.MONEY.fullmatch(cell):
                values.append(str(Decimal(cell.replace(",", ""))))
            else:
                raise ValueError("NOTE_GRID_UNEXPECTED_AMOUNT:" + field)
        row = dict(current=values[0], comparative=values[1], physical_page=page,
                   excerpt=" | ".join(cells), printed_columns=cells[-2:])
        rows[field] = dict(**row, source_refs=parent._source_refs(source, field, row, period, balance),
                           classification="FACT" if any(v is not None for v in values) else "UNKNOWN",
                           currency="CNY", scope=parent.SCOPE)
    return rows


def _shares(pages, source, symbol, period, capital):
    year = period[:4]
    pattern = rf"截至{year}年12月31日，公司总股本为([0-9,]+)股"
    counts, refs = set(), []
    for i, page in enumerate(pages, 1):
        for match in re.finditer(pattern, compact(page)):
            counts.add(int(match[1].replace(",", "")))
            refs.append(dict(source, physical_page=i, excerpt=match[0]))
    for pattern in (rf"A股上海证券交易所[^\d\s]+{symbol}(?!\d)", "九、优先股相关情况□适用√不适用",
                    "报告期内，公司股份总数及股本结构未发生变化。"):
        matches = [(i, m[0]) for i, page in enumerate(pages, 1)
                   if (m := re.search(pattern, compact(page)))]
        if len(matches) != 1:
            raise ValueError("NOTE_GRID_ORDINARY_CLASS_UNVERIFIED")
        refs.append(dict(source, physical_page=matches[0][0], excerpt=matches[0][1]))
    if len(counts) != 1 or (count := counts.pop()) <= 0 or Decimal(capital["current"]) != count:
        raise ValueError("NOTE_GRID_DATED_SHARE_COUNT_UNVERIFIED")
    return dict(count=str(count), period_end=period, classification="DERIVED_FACT", unit="shares",
                scope="TOTAL_ISSUED_ORDINARY_SHARES", derivation="DATED_TOTAL_SHARES_A_SHARE_NO_PREFERRED",
                treasury_excluded=False, source_refs=[*refs, capital["source_refs"]])


def _reconcile(balance, cash):
    for column in ("current", "comparative"):
        def amount(rows, field):
            value = rows[field][column]
            if value is None:
                raise ValueError("NOTE_GRID_REQUIRED_AMOUNT_MISSING:" + field)
            return Decimal(value)
        if amount(balance, "assets_cny") != amount(balance, "liabilities_cny") + amount(balance, "book_equity_cny"):
            raise ValueError("NOTE_GRID_BALANCE_EQUATION_CHANGED")
        cfo = amount(cash, "cfo_cny")
        change = amount(cash, "reported_net_change_cny")
        fx = cash["fx_cny"][column]
        # A blank FX cell remains unknown. Separately check the printed change against
        # the three printed subtotals and any separately printed FX amount.
        subtotal = cfo + amount(cash, "cfi_cny") + amount(cash, "cff_cny")
        residual = change - subtotal
        if (cfo != amount(cash, "operating_inflow_cny") - amount(cash, "operating_outflow_cny")
                or (residual != 0 if fx is None else residual != Decimal(fx))
                or change != amount(cash, "closing_cash_and_equivalents_cny") - amount(cash, "opening_cash_and_equivalents_cny")):
            raise ValueError("NOTE_GRID_CASH_EQUATION_CHANGED")


def read_note_grid_parent_cash(*, root, symbol, issuer_name, sources, evaluated_at):
    if not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None:
        raise ValueError("NOTE_GRID_AWARE_CUTOFF_REQUIRED")
    root = Path(root).resolve()
    statements = []
    for entry in sources:
        period = entry["period_end"]
        if set(entry) != {"period_end", "receipt_binding"} or period[4:] not in ("-12-31", "-06-30"):
            raise ValueError("NOTE_GRID_FY_OR_H1_RECEIPT_REQUIRED")
        packet = load_retained_official_report(root=root, receipt_binding=entry["receipt_binding"],
            symbol=symbol, issuer_name=issuer_name, period=period)
        for stamp in (packet["completed_at"], packet["source"]["available_at"]):
            parent._clock(stamp, evaluated_at)
        source = {key: packet["source"][key] for key in ("path", "sha256", "available_at")}
        path, _ = parent._bound(root, source)
        pages = parent.extract_pages(path)
        if parent.labelled_security_codes(pages[:8], symbol=symbol) != {symbol}:
            raise ValueError("NOTE_GRID_SECURITY_IDENTITY_CHANGED")
        def read(title, labels):
            return _rows(read_parent_grid(path, pages, title, issuer_name, period), labels,
                         source, period, title == "母公司资产负债表")
        balance = read("母公司资产负债表", parent.BALANCE)
        income = read("母公司利润表", INCOME)
        cash = read("母公司现金流量表", CASH)
        _reconcile(balance, cash)
        annual = period.endswith("-12-31")
        shares = _shares(pages, source, symbol, period, balance["share_capital_cny"]) if annual else None
        for binding in (source, entry["receipt_binding"], *packet["index_bindings"]):
            parent._bound(root, binding)
        statements.append(dict(symbol=symbol, issuer_name=issuer_name, scope=parent.SCOPE,
            currency="CNY", period_start=period[:4]+"-01-01", period_end=period,
            period_basis="FY" if annual else "H1", source_binding=source,
            receipt_binding=entry["receipt_binding"], balance_sheet=balance, income=income,
            cash_flow=cash, ordinary_shares_evidence=shares, checks=dict(
                balance_equation_reconciled=True, cash_statement_reconciled=True, cfo_reconciled=True)))
    statements.sort(key=lambda s: s["period_end"])
    if not statements or len({s["period_end"] for s in statements}) != len(statements):
        raise ValueError("NOTE_GRID_UNIQUE_PERIODS_REQUIRED")
    for earlier, later in zip(statements, statements[1:]):
        if earlier["period_end"] != str(int(later["period_end"][:4])-1)+"-12-31":
            continue
        for key, old in earlier["balance_sheet"].items():
            current, comparative = old["current"], later["balance_sheet"][key]["comparative"]
            if None not in (current, comparative) and current != comparative:
                raise ValueError("NOTE_GRID_BALANCE_CONTINUITY_CHANGED:" + key)
        if earlier["cash_flow"]["closing_cash_and_equivalents_cny"]["current"] != later["cash_flow"]["opening_cash_and_equivalents_cny"]["current"]:
            raise ValueError("NOTE_GRID_CASH_CONTINUITY_CHANGED")
    return dict(source_adapter_version=VERSION, statements=statements, scope=parent.SCOPE,
                currency="CNY", action="no_order", formal_eligibility=False,
                status="SOURCE_BOUND_PARENT_BRIDGE_FACTS_NOT_OWNER_CASH")
