"""Read-only seven-row reported operating basis; no quality or valuation admission."""
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
from pathlib import Path, PureWindowsPath
import re

from .pdf_text import extract_pages
from .official_pdf import validate_pdf_original
from .official_report_acquisition import _verify_cover
from ..screening.value_evidence_enrichment_v1 import (
    _issuer_legal_owner, _statement_unit, _statement_lines, extract_income_comparatives,
    extract_debt_balance_candidates,
)

VERSION = "operating-statement-basis-v1"
LABELS = dict(revenue="营业收入", cost="营业成本", surcharges="税金及附加",
              selling="销售费用", admin="管理费用", research="研发费用", pre_tax_profit="利润总额")
# These two rows are deliberately outside the seven-row operating-driver basis.
# They are optional source-bound anchors for the downstream shareholder-income
# bridge: they must never be substituted for the operating rows or guessed when
# a report uses an unsupported presentation.
AUXILIARY_LABELS = dict(
    tax=("所得税费用",),
    parent_profit=("归属于母公司所有者的净利润", "归属于母公司股东的净利润"),
)
PARENT_CASH_LABELS = dict(
    parent_cfo=("经营活动产生的现金流量净额",),
    parent_investment_cash=("取得投资收益收到的现金",),
    parent_capex=("购建固定资产、无形资产和其他长期资产支付的现金",),
)
_TITLE = re.compile(r"^(?:[0-9]+、\s*)?((?:合并|母公司)?(?:利润表|资产负债表|现金流量表))$")
_NUMBER = r"-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}"
_NOTE = (r"(?:[1-9][0-9]{0,2}|[一二三四五六七八九十百]{1,6}\s*"
         r"(?:[（(]\s*[1-9][0-9]{0,2}\s*[）)]|[、-]\s*[1-9][0-9]{0,2}))")
_MAX_TABLE_PAGES = 6


def _same_h1_balance_group_owner(pages, income_page, owner, period):
    """Prove a missing H1 income preparer from its same-report primary balance.

    The balance heading must precede the income table within eight pages and
    print the exact legal owner, cutoff, comparative date and CNY scope. This
    verifies identity only; no balance amount enters operating facts.
    """
    headings = [(n, i) for n, page in enumerate(pages[:income_page+1])
                for i, line in enumerate(page.splitlines())
                if _TITLE.fullmatch(line.strip()) and
                _TITLE.fullmatch(line.strip())[1] == "合并资产负债表"]
    if len(headings) != 1:
        return None
    page_index, line_index = headings[0]
    if not 1 <= income_page - page_index <= 8:
        return None
    lines = pages[page_index].splitlines()[line_index:]
    next_table = next((i for i, line in enumerate(lines[1:], 1)
                       if _TITLE.fullmatch(line.strip())), len(lines))
    header = "".join("".join(line.split()) for line in lines[:min(next_table, 8)])
    year = int(period[:4])
    required = (f"{year}年6月30日", f"项目附注{year}年6月30日{year-1}年12月31日",
                "单位：元币种：人民币")
    preparers = re.findall(r"编制单位[：:]([^\r\n]+)", "\n".join(lines[:min(next_table, 8)]))
    if (any(item not in header for item in required) or len(preparers) != 1
            or "".join(preparers[0].split()) != owner["legal_name"]):
        return None
    return dict(method="SAME_H1_FINANCIAL_STATEMENT_GROUP",
                owner_evidence=owner, compiler_page=page_index+1,
                compiler_excerpt="\n".join(lines[:min(next_table, 8)]),
                table_context_id=f"{period}:consolidated-balance:{page_index+1}")


def _parse(pages, source):
    period = source["period"]
    year = int(period[:4])
    basis = "FY" if period.endswith("-12-31") else "H1"
    prior = str(year-1)+period[4:]
    result = dict(schema_version=VERSION, symbol=source["symbol"], source_binding=dict(source),
        evidence=[], gaps=[], complete_periods=[], action="no_order",
        formal_eligibility=False, financial_quality_granted=False,
        assurance="SOURCE_BOUND_REPORTED_ROWS_NOT_FINANCIAL_QUALITY_ADMISSION")
    def gap(reason, field=None, page=None):
        result["gaps"].append(dict(reason=reason, field=field, physical_page=page))
    def finish():
        result["status"] = "COMPLETE_SOURCE_BOUND_STATEMENT" if not result["gaps"] else "PARTIAL"
        if not result["gaps"]:
            result["complete_periods"] = [period, prior]
        return result
    owner = _issuer_legal_owner(pages)
    if not owner or owner["security_code"] != source["symbol"]:
        gap("ISSUER_IDENTITY_MISSING_OR_CONFLICT")
        return finish()
    result["issuer_name"] = owner["legal_name"]
    try:
        _verify_cover(pages[:12], symbol=source["symbol"], issuer_name=owner["legal_name"],
                      period=period, kind="annual" if basis == "FY" else "interim")
    except ValueError:
        gap("REPORT_IDENTITY_OR_PERIOD_NOT_PROVEN")
        return finish()
    starts = [(i,j) for i,p in enumerate(pages) for j,line in enumerate(p.splitlines())
              if _TITLE.fullmatch(line.strip()) and _TITLE.fullmatch(line.strip())[1] == "合并利润表"]
    if len(starts) != 1:
        gap("CONSOLIDATED_INCOME_TABLE_MISSING_OR_DUPLICATE")
        return finish()
    first, start = starts[0]
    if "合并利润表" not in _statement_lines(pages[first]):
        gap("CONSOLIDATED_INCOME_HEADING_NOT_PROVEN")
        return finish()
    pieces = []
    ended = False
    for i in range(first, min(len(pages), first+_MAX_TABLE_PAGES)):
        lines = pages[i].splitlines()
        if i == first:
            lines = lines[start+1:]
        selected = []
        for line in lines:
            if _TITLE.fullmatch(line.strip()):
                ended = True
                break
            selected.append(line)
        pieces.append((i+1, selected))
        if ended:
            break
    if not ended:
        gap("CONSOLIDATED_TABLE_END_NOT_LOCATED")
        return finish()
    header_lines = []
    for line in pieces[0][1]:
        header_lines.append(line)
        if "".join(line.split()).startswith("项目"):
            break
    header = "\n".join(header_lines)
    header_compact = "".join(header.split())
    preparers = re.findall(r"编制单位[：:]([^\r\n]+)", header)
    preparers = [re.split(r"\s*(?:单位|币种)[：:]", name)[0] for name in preparers]
    owner_proof = None
    if re.search(r"编制单位[：:]", header):
        if len(preparers) == 1 and "".join(preparers[0].split()) == owner["legal_name"]:
            owner_proof = dict(method="DIRECT_STATEMENT_PREPARER", owner_evidence=owner,
                               compiler_page=first+1, compiler_excerpt=header)
    elif basis == "H1":
        owner_proof = _same_h1_balance_group_owner(pages, first, owner, period)
    elif basis == "FY":
        # Identity only: reuse native annual balance evidence, never its financial amounts.
        candidates = extract_debt_balance_candidates(
            pages, period, balance_totals=True, include_equity=True)
        proofs = {}
        for row in candidates:
            native = row.get("owner_evidence", {})
            page = row.get("statement_evidence_page", 0)
            if (row.get("statement_title") == "合并资产负债表"
                    and row.get("statement_scope") == "consolidated"
                    and row.get("period_label") == period
                    and row.get("prior_period_label") == prior
                    and row.get("prior_period_basis") == "EXPLICIT_DATES"
                    and 1 <= first+1-page <= 8
                    and native.get("compiler_page") == page
                    and row.get("period_evidence_page") == page
                    and native.get("legal_name") == owner["legal_name"]
                    and native.get("compiler_name") == owner["legal_name"]
                    and native.get("security_code") == source["symbol"]
                    and row.get("table_context_id")):
                proofs[row["table_context_id"]] = dict(
                    method="SAME_ANNUAL_FINANCIAL_STATEMENT_GROUP",
                    owner_evidence=native, compiler_page=page,
                    compiler_excerpt=native["compiler_excerpt"],
                    period_evidence_page=row["period_evidence_page"],
                    period_evidence_excerpt=row["period_evidence_excerpt"],
                    table_context_id=row["table_context_id"])
        if len(proofs) == 1:
            owner_proof = next(iter(proofs.values()))
    if owner_proof is None:
        gap("STATEMENT_PREPARER_NOT_EXACT_LEGAL_OWNER", page=first+1)
    else:
        owner_proof["source_binding"] = dict(source)
        result["owner_proof"] = owner_proof
    column = "".join(header_lines[-1].split()) if header_lines else ""
    if basis == "FY":
        expected = [f"项目附注{year}年度{year-1}年度", f"项目{year}年度{year-1}年度"]
    else:
        expected = [f"项目{note}{year}{suffix}{year-1}{suffix}"
                    for note in ("", "附注") for suffix in ("年半年度", "年1—6月", "年1-6月", "年1至6月")]
    if column not in expected:
        gap("EXPLICIT_ORDERED_PERIOD_COLUMNS_REQUIRED", page=first+1)
    ranges = re.findall(r"([0-9]{4})年1[—至-]([0-9]{1,2})月", header_compact.split("项目",1)[0])
    if ranges and any(y != str(year) or int(month) != (12 if basis == "FY" else 6) for y,month in ranges):
        gap("REPORTING_RANGE_CONFLICT", page=first+1)
    # This contract admits yuan only; no guessed or implicit monetary multiplier.
    multiplier, unit_evidence = _statement_unit(header, first+1, [])
    if multiplier != 1 or not re.search(r"单位[：:]元(?:币种|$)", header_compact.split("项目",1)[0]):
        gap("EXPLICIT_YUAN_RENMINBI_REQUIRED", page=first+1)
    for page_no, lines in pieces:
        text = "\n".join(lines)
        if any(w in "".join(text.split()) for w in ("调整前", "调整后", "重述")):
            gap("ADJUSTED_OR_RESTATED_COLUMNS_UNSUPPORTED", page=page_no)
        if page_no != first+1:
            declarations = [l for l in lines if re.search(r"(?:单位|币种)\s*[：:]", l)]
            if declarations and _statement_unit("\n".join(declarations), page_no, [])[0] != 1:
                gap("CONTINUATION_UNIT_CURRENCY_CONFLICT", page=page_no)
            for line in lines:
                if "".join(line.split()).startswith("项目") and "".join(line.split()) not in expected:
                    gap("CONTINUATION_PERIOD_COLUMNS_CONFLICT", page=page_no)
    if result["gaps"]:
        return finish()
    # Same FY context as the established income comparative reader; no new income formula.
    income_rows = extract_income_comparatives(pages, period) if basis == "FY" else []
    for field,label in LABELS.items():
        label_re = r"\s*".join(map(re.escape,label))
        prefix = r"(?:(?:其中|加|减)[：:]|[0-9]+[、.．]|[一二三四五六七八九十]+[、.．])?\s*"
        head = re.compile(r"^[ \t]*"+prefix+label_re+r"(?=\s|[（(]|$)")
        loss = r"(?:\s*[（(]\s*亏\s*损\s*总\s*额\s*以[^）)]{0,50}[）)])?" if field == "pre_tax_profit" else ""
        pattern = re.compile(r"^[ \t]*"+prefix+label_re+loss+r"\s+(?:"+_NOTE+r"\s+)?"
                             +r"("+_NUMBER+r")[ \t]+("+_NUMBER+r")[ \t\r\n]*$")
        occurrences = [(n,lines,j) for n,lines in pieces for j,line in enumerate(lines) if head.match(line)]
        if len(occurrences) != 1:
            gap("MISSING_FIELD" if not occurrences else "DUPLICATE_FIELD", field)
            continue
        n,lines,j = occurrences[0]
        # Up to four nonempty printed lines allow only a wrapped label/note, not another table.
        tail = [line for line in lines[j:] if line.strip()]
        match = None
        for count in range(1,min(4,len(tail))+1):
            excerpt = "\n".join(tail[:count])
            match = pattern.fullmatch(excerpt)
            if match:
                if count < len(tail) and re.fullmatch(r"\s*"+_NUMBER+r"\s*",tail[count]):
                    match = None
                break
        if match is None:
            gap("MISSING_OR_AMBIGUOUS_TWO_PERIOD_AMOUNTS",field,n)
            continue
        values = [str(Decimal(match[k].replace(",",""))) for k in (1,2)]
        if field == "revenue" and basis == "FY":
            comparable = [r for r in income_rows if r["field_name"] == "revenue"]
            if len(comparable) != 1 or (comparable[0]["value"],comparable[0]["prior_value"]) != tuple(values):
                gap("EXISTING_INCOME_CONTEXT_DISAGREEMENT",field,n)
                continue
        for index,(closing,value) in enumerate(zip((period,prior),values)):
            identity = "|".join((VERSION,source["sha256"],source["symbol"],closing,field,str(n),str(index),value))
            result["evidence"].append(dict(
                id="operating-statement:"+hashlib.sha256(identity.encode()).hexdigest(),
                source_id="official:"+source["sha256"], source_binding=dict(source),
                symbol=source["symbol"], pdf_sha256=source["sha256"], available_at=source["available_at"],
                period=closing, period_start=closing[:4]+"-01-01", period_basis=basis,
                scope="consolidated", unit="CNY", currency="CNY", field=field, value=value,
                physical_page=n, text=excerpt, excerpt=excerpt, column_index=index,
                column_periods=[period,prior], column_header=header_lines[-1],
                header_page=first+1, header_excerpt=header, owner_proof=owner_proof, **unit_evidence,
                kind="SOURCE_BOUND_REPORTED_STATEMENT_ROW", action="no_order",
                financial_quality_granted=False, formal_eligibility=False))
    # Keep tax and attributable-profit anchors separate from the driver contract:
    # E2 may consume them only when this exact consolidated statement prints both
    # ordered values.  Missing/ambiguous auxiliary rows do not downgrade a valid
    # seven-row D2 operating basis; they remain an explicit E2 evidence gap.
    for field, labels in AUXILIARY_LABELS.items():
        label_re = "(?:" + "|".join(r"\s*".join(map(re.escape, label)) for label in labels) + ")"
        prefix = r"(?:(?:其中|加|减)[：:]|[0-9]+[、.．]|[一二三四五六七八九十]+[、.．])?\s*"
        head = re.compile(r"^[ \t]*" + prefix + label_re + r"(?=\s|[（(]|$)")
        pattern = re.compile(r"^[ \t]*" + prefix + label_re
                             + r"(?:\s*[（(][^）)]{0,80}[）)])?\s+(?:" + _NOTE + r"\s+)?"
                             + r"(" + _NUMBER + r")[ \t]+(" + _NUMBER + r")[ \t\r\n]*$")
        occurrences = [(n, lines, j) for n, lines in pieces for j, line in enumerate(lines) if head.match(line)]
        if len(occurrences) != 1:
            continue
        n, lines, j = occurrences[0]
        tail = [line for line in lines[j:] if line.strip()]
        match = None
        for count in range(1, min(4, len(tail)) + 1):
            excerpt = "\n".join(tail[:count])
            match = pattern.fullmatch(excerpt)
            if match:
                if count < len(tail) and re.fullmatch(r"\s*" + _NUMBER + r"\s*", tail[count]):
                    match = None
                break
        if match is None:
            continue
        for index, (closing, value) in enumerate(zip((period, prior),
                                                      [str(Decimal(match[k].replace(",", ""))) for k in (1, 2)])):
            identity = "|".join((VERSION, source["sha256"], source["symbol"], closing, field,
                                 str(n), str(index), value, "auxiliary"))
            result["evidence"].append(dict(
                id="operating-statement:" + hashlib.sha256(identity.encode()).hexdigest(),
                source_id="official:" + source["sha256"], source_binding=dict(source),
                symbol=source["symbol"], pdf_sha256=source["sha256"], available_at=source["available_at"],
                period=closing, period_start=closing[:4] + "-01-01", period_basis=basis,
                scope="consolidated" if field == "tax" else "consolidated_parent",
                unit="CNY", currency="CNY", field=field, value=value, physical_page=n,
                text=excerpt, excerpt=excerpt, column_index=index, column_periods=[period, prior],
                column_header=header_lines[-1], header_page=first+1, header_excerpt=header,
                owner_proof=owner_proof, auxiliary_anchor=True, **unit_evidence,
                kind="SOURCE_BOUND_REPORTED_STATEMENT_ROW", action="no_order",
                financial_quality_granted=False, formal_eligibility=False))
    result["evidence"].extend(_parent_cash_rows(pages, source, owner, period, prior, basis))
    return finish()


def _parent_cash_rows(pages, source, owner, period, prior, basis):
    """Read three optional parent-CF rows, never substitute consolidated cash.

    The operating seven-row income basis remains independently complete.  This
    optional extraction exists only for E2's historical parent-cash proxy and
    requires a named parent-company cash-flow statement with the same explicit
    comparative periods and yuan/RMB declaration.
    """
    starts = [(i, j) for i, page in enumerate(pages) for j, line in enumerate(page.splitlines())
              if _TITLE.fullmatch(line.strip()) and _TITLE.fullmatch(line.strip())[1] == "母公司现金流量表"]
    if len(starts) != 1:
        return []
    first, start = starts[0]
    pieces, ended = [], False
    for i in range(first, min(len(pages), first + _MAX_TABLE_PAGES)):
        lines = pages[i].splitlines()
        if i == first:
            lines = lines[start + 1:]
        selected = []
        for line in lines:
            if _TITLE.fullmatch(line.strip()):
                ended = True
                break
            selected.append(line)
        pieces.append((i + 1, selected))
        if ended:
            break
    if not pieces:
        return []
    joined = "\n".join(line for _, lines in pieces for line in lines)
    compact = "".join(joined.split())
    if basis == "FY":
        expected = (f"项目附注{period[:4]}年度{prior[:4]}年度", f"项目{period[:4]}年度{prior[:4]}年度")
    else:
        expected = tuple(f"项目{note}{period[:4]}{suffix}{prior[:4]}{suffix}"
                         for note in ("", "附注") for suffix in ("年半年度", "年1—6月", "年1-6月", "年1至6月"))
    header_lines = [line for _, lines in pieces for line in lines if "".join(line.split()) in expected]
    if len(header_lines) != 1 or "单位：元币种：人民币" not in compact:
        return []
    header = header_lines[0]
    prefix = r"(?:(?:其中|加|减)[：:]|[0-9]+[、.．]|[一二三四五六七八九十]+[、.．])?\s*"
    rows = []
    for field, labels in PARENT_CASH_LABELS.items():
        label_re = "(?:" + "|".join(r"\s*".join(map(re.escape, label)) for label in labels) + ")"
        pattern = re.compile(r"^[ \t]*" + prefix + label_re + r"\s+(?:" + _NOTE + r"\s+)?"
                             + r"(" + _NUMBER + r")[ \t]+(" + _NUMBER + r")[ \t\r\n]*$")
        matches = []
        for page_number, lines in pieces:
            for index in range(len(lines)):
                tail = [line for line in lines[index:] if line.strip()]
                for count in range(1, min(4, len(tail)) + 1):
                    excerpt = "\n".join(tail[:count])
                    match = pattern.fullmatch(excerpt)
                    if match:
                        if count < len(tail) and re.fullmatch(r"\s*" + _NUMBER + r"\s*", tail[count]):
                            match = None
                        else:
                            matches.append((page_number, excerpt, match))
                        break
        if len(matches) != 1:
            continue
        page_number, excerpt, match = matches[0]
        for column_index, (closing, value) in enumerate(zip((period, prior),
                                                             [str(Decimal(match[k].replace(",", ""))) for k in (1, 2)])):
            identity = "|".join((VERSION, source["sha256"], source["symbol"], closing, field,
                                 str(page_number), str(column_index), value, "parent-cash"))
            rows.append(dict(
                id="operating-statement:" + hashlib.sha256(identity.encode()).hexdigest(),
                source_id="official:" + source["sha256"], source_binding=dict(source),
                symbol=source["symbol"], pdf_sha256=source["sha256"], available_at=source["available_at"],
                period=closing, period_start=closing[:4] + "-01-01", period_basis=basis,
                scope="parent", unit="CNY", currency="CNY", field=field, value=value,
                physical_page=page_number, text=excerpt, excerpt=excerpt,
                column_index=column_index, column_periods=[period, prior], column_header=header,
                header_page=next(number for number, lines in pieces if header in lines),
                header_excerpt=header, owner_proof=dict(method="PARENT_CASH_FLOW_TITLE_WITH_BOUND_ISSUER",
                                                         owner_evidence=owner),
                parent_cash_anchor=True,
                kind="SOURCE_BOUND_REPORTED_STATEMENT_ROW", action="no_order",
                financial_quality_granted=False, formal_eligibility=False))
    return rows


def load_operating_statement_basis(*, root, source, evaluation_at) -> dict:
    """Read an existing six-field RetainedAnnualSource/dict; never fetch or cache."""
    source = asdict(source) if is_dataclass(source) else dict(source)
    if set(source) != {"symbol","period","path","sha256","source_url","available_at"}:
        raise ValueError("EXACT_RETAINED_SOURCE_REQUIRED")
    if not isinstance(evaluation_at,datetime) or evaluation_at.utcoffset() is None:
        raise ValueError("AWARE_CUTOFF_REQUIRED")
    available = datetime.fromisoformat(source["available_at"])
    if available.utcoffset() is None or available > evaluation_at:
        raise ValueError("SOURCE_NOT_AVAILABLE")
    if not re.fullmatch(r"[0-9]{6}",source["symbol"]) or not re.fullmatch(r"[0-9]{4}-(?:12-31|06-30)",source["period"]):
        raise ValueError("EXPLICIT_FY_H1_IDENTITY_REQUIRED")
    url = re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/([0-9]{4}-[0-9]{2}-[0-9]{2})/[0-9]+\.PDF",source["source_url"])
    if not url or not date.fromisoformat(source["period"]) <= date.fromisoformat(url[1]) <= available.date():
        raise ValueError("OFFICIAL_URL_OR_PUBLICATION_CONFLICT")
    relative = source["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or PureWindowsPath(relative).drive or PureWindowsPath(relative).root or ".." in PureWindowsPath(relative).parts:
        raise ValueError("PROJECT_RELATIVE_SOURCE_PATH_REQUIRED")
    root = Path(root).resolve()
    path = (root/source["path"]).resolve()
    if not path.is_relative_to(root) or path.stat().st_size > 32_000_000:
        raise ValueError("ORIGINAL_PATH_OR_SIZE_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}",source["sha256"]) or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("ORIGINAL_HASH_MISMATCH")
    validate_pdf_original(path)
    pages = extract_pages(path,limit=601)
    if len(pages)>600:
        raise ValueError("ORIGINAL_PAGE_BUDGET")
    result = _parse(pages,source)
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("ORIGINAL_CHANGED_DURING_EXTRACTION")
    result["implementation_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result
