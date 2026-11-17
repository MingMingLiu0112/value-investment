"""Source-bound parent cash observations for numbered CNINFO statements.

This version accepts a different printed layout from parent_cash_research v1.
It never changes v1 receipts or infers dividend capacity from cash balances.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re

from . import parent_cash_research as prior
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import require_inside, sha256_file


VERSION = "parent-cash-observations-v2"


def _compact(value: str) -> str:
    return prior._compact(value)


def extract_numbered_parent_cash_statement(*, pages: list[str], symbol: str,
        issuer_name: str, period: str) -> dict:
    """Extract printed two-column rows only after exact issuer/period/table checks."""
    periods = prior._period_pair(period)
    year = period[:4]
    report = f"{year}年{'年度' if period.endswith('12-31') else '半年度'}报告"
    header = "\n".join(line.strip() for page in pages[:8] for line in page.splitlines())
    owner = _compact(issuer_name)
    cover = re.compile(rf"^{re.escape(owner)}\s+{year}\s*年\s*{'年度' if period.endswith('12-31') else '半年度'}报告全文$", re.M)
    codes = set(re.findall(r"股票代码\s*([0-9]{6})(?!\d)", header))
    if not cover.search(header) or codes != {symbol}:
        raise ValueError("PARENT_CASH_V2_ISSUER_PERIOD_OR_CODE_MISMATCH")
    lines = [(number, line.strip()) for number, page in enumerate(pages, 1)
             for line in page.splitlines() if line.strip()]
    starts = [index for index, (_, line) in enumerate(lines)
              if _compact(line) == "6、母公司现金流量表"]
    if len(starts) != 1:
        raise ValueError("PARENT_CASH_V2_PARENT_TABLE_AMBIGUOUS")
    ends = [index for index in range(starts[0] + 1, len(lines))
            if _compact(lines[index][1]) == "7、合并所有者权益变动表"]
    if len(ends) != 1 or ends[0] <= starts[0]:
        raise ValueError("PARENT_CASH_V2_TABLE_END_MISSING")
    selected = lines[starts[0]:ends[0]]
    content = "\n".join(line for _, line in selected)
    compact = _compact(content).replace("：", ":")
    expected_columns = _compact("项目 " + " ".join(prior._column_labels(periods)))
    headings = [_compact(line) for _, line in selected if _compact(line).startswith("项目")]
    if (headings != [expected_columns] or compact.count("单位:元") != 1
            or any(token in compact for token in ("单位:万元", "币种:美元", "调整前", "调整后"))):
        raise ValueError("PARENT_CASH_V2_COLUMNS_OR_UNIT_INVALID")
    sections = ("一、经营活动产生的现金流量:", "二、投资活动产生的现金流量:",
                "三、筹资活动产生的现金流量:", "四、汇率变动对现金及现金等价物的影响")
    positions = [compact.find(section) for section in sections]
    if min(positions) < 0 or positions != sorted(positions) or any(compact.count(s) != 1 for s in sections):
        raise ValueError("PARENT_CASH_V2_SECTION_ORDER_INVALID")
    for _, line in selected[1:]:
        text = _compact(line)
        if (text.startswith("6、") or text.startswith("7、")
                or text.endswith("资产负债表") or text.endswith("利润表")):
            raise ValueError("PARENT_CASH_V2_TABLE_OWNERSHIP_CHANGED")
    rows = {}
    unquantified = []
    permitted = prior._partial_fields(periods)
    for key in prior.LABELS:
        if key not in permitted:
            continue
        label = prior.LABELS[key]
        if compact.count(label) != 1:
            raise ValueError("PARENT_CASH_V2_ROW_MISSING_OR_AMBIGUOUS:" + key)
        location = compact.index(label)
        section = (0 if key == "cfo_cny" else
                   1 if key in {"cfi_cny", "gross_capex_cny", "investment_income_cash_cny"} else
                   2 if key in {"cff_cny", "borrowings_received_cny", "debt_repaid_cny",
                                 "mixed_distribution_interest_paid_cny"} else 3)
        lower = positions[section]
        upper = positions[section + 1] if section < 3 else len(compact)
        if not lower < location < upper:
            raise ValueError("PARENT_CASH_V2_ROW_SECTION_MISMATCH:" + key)
        try:
            match = prior._printed_cash_row(text=content, key=key, label=label)
        except ValueError as error:
            if str(error) != "PARENT_CASH_TWO_PRINTED_VALUES_REQUIRED:" + key:
                raise
            # A single printed amount has no provable left/right column from
            # extracted text alone. Do not choose a year or synthesize zero.
            unquantified.append(key)
            continue
        page = selected[content[:match.start()].count("\n")][0]
        rows[key] = dict(label=label, physical_page=page,
                         statement_scope="listed_parent_only", unit="CNY", currency="CNY",
                         evidence_excerpt=match[0].strip(),
                         columns=[dict(period=p, value=str(Decimal(value.replace(",", ""))))
                                  for p, value in zip(periods, match.groups())])
    return dict(symbol=symbol, issuer=issuer_name, periods=list(periods),
                statement_scope="listed_parent_only", rows=rows,
                balances=[dict(period=p, **{key: row["columns"][index]["value"]
                                           for key, row in rows.items()})
                          for index, p in enumerate(periods)],
                whole_statement_reconciled=False,
                unknown_fields=sorted(set(prior.LABELS) - set(rows)),
                ambiguous_printed_columns=sorted(unquantified), report_title=report)


def replay_numbered_parent_cash_observations(*, root: Path, symbol: str,
        issuer_name: str, receipt_bindings: list[dict], now: datetime) -> dict:
    """Reverify each official index/PDF, then parse the numbered parent statement."""
    if now.utcoffset() is None or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("PARENT_CASH_V2_IDENTITY_OR_CLOCK_INVALID")
    root = root.resolve()
    if not receipt_bindings or len({item["period"] for item in receipt_bindings}) != len(receipt_bindings):
        raise ValueError("PARENT_CASH_V2_PERIODS_INVALID")
    statements, references = [], []
    for item in receipt_bindings:
        if set(item) != {"period", "receipt_binding"}:
            raise ValueError("PARENT_CASH_V2_RECEIPT_SCHEMA_INVALID")
        period, pin = item["period"], item["receipt_binding"]
        prior._period_pair(period)
        query = prior._receipt_issuer_query(root=root, receipt_binding=pin)
        packet = load_retained_official_report(root=root, receipt_binding=pin,
            symbol=symbol, issuer_name=query, period=period)
        published = date.fromisoformat(packet["published_date"])
        available = datetime.combine(published + timedelta(days=1), time(),
                                     timezone(timedelta(hours=8)))
        if available > now:
            raise ValueError("PARENT_CASH_V2_NOT_YET_AVAILABLE")
        source = packet["source"]
        original = require_inside(root, root / source["path"], "parent cash v2 original")
        if sha256_file(original) != source["sha256"]:
            raise ValueError("PARENT_CASH_V2_ORIGINAL_HASH_MISMATCH")
        statement = extract_numbered_parent_cash_statement(
            pages=extract_pages(original), symbol=symbol, issuer_name=issuer_name, period=period)
        if sha256_file(original) != source["sha256"]:
            raise ValueError("PARENT_CASH_V2_ORIGINAL_CHANGED")
        reference = dict(receipt_path=pin["path"], receipt_sha256=pin["sha256"],
            source_id=packet["source_id"], source_url=source["source_url"],
            source_path=source["path"], source_sha256=source["sha256"],
            published_date=packet["published_date"],
            date_only_available_at_conservative=available.isoformat())
        for row in statement["rows"].values():
            row.update(source_id=packet["source_id"], source_binding=dict(reference))
        statement["source_binding"] = reference
        statements.append(statement)
        references.append(reference)
    if len(statements) == 2 and {item["periods"][0] for item in statements} == {"FY2025", "H12026"}:
        annual = next(item for item in statements if item["periods"][0] == "FY2025")
        interim = next(item for item in statements if item["periods"][0] == "H12026")
        if Decimal(annual["balances"][0]["closing_cash_and_equivalents_cny"]) != Decimal(
                interim["balances"][0]["opening_cash_and_equivalents_cny"]):
            raise ValueError("PARENT_CASH_V2_PERIOD_CONTINUITY_FAILED")
    return dict(schema_version=VERSION, status="SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS",
        symbol=symbol, issuer_name=issuer_name, action="no_order", formal_eligibility=False,
        evaluated_at=now.isoformat(), historical_statements=statements,
        source_bindings=references, whole_statement_reconciled=False,
        limitation="Observed parent cash rows only; not distributable cash, forecast or approval.")
