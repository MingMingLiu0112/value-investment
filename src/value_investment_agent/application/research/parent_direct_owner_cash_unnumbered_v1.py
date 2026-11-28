"""Replay official unnumbered parent statements without changing numbered receipts."""
from datetime import datetime
from decimal import Decimal
import json
import re
from pathlib import Path
from functools import partial

from .parent_cash_research import _receipt_issuer_query
from . import parent_direct_owner_cash_sources as parent
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report

VERSION = "UNNUMBERED_OFFICIAL_CNINFO_V1"
FINANCING_VERSION = "UNNUMBERED_OFFICIAL_CNINFO_V2"
UNNUMBERED_VERSIONS = {VERSION, FINANCING_VERSION}


def _annual_share_anchor(pages, statement):
    if statement["period_basis"] != "FY":
        return None
    headings = [
        (index, text) for index, text in enumerate(pages, 1)
        if all(key in parent._compact(text) for key in (
            "第六节股份变动及股东情况", "股份变动情况表", "单位:股",
            "本次变动前", "本次变动后",
        ))
    ]
    preferred = [
        index for index, text in enumerate(pages, 1)
        if "九、优先股相关情况□适用√不适用" in parent._compact(text)
    ]
    if len(headings) != 1 or len(preferred) != 1:
        return None
    page, text = headings[0]
    if not page <= preferred[0] <= page + 8:
        return None
    amounts = r"([0-9][0-9,]*)"
    ratio = r"[0-9]+(?:\.[0-9]+)?"
    movement = r"(-?[0-9][0-9,]*)"
    patterns = {
        "restricted": rf"(?:.*比例\(%\)\s+)?一、有限售条件股份\s+{amounts}\s+{ratio}\s+{amounts}\s+{ratio}",
        "unrestricted": rf"二、无限售条件流通股份\s+{amounts}\s+{ratio}\s+{movement}\s+{movement}\s+{amounts}\s+{ratio}",
        "ordinary": rf"1、人民币普通股\s+{amounts}\s+{ratio}\s+{movement}\s+{movement}\s+{amounts}\s+{ratio}",
        "total": rf"三、股份总数\s+{amounts}\s+100\s+{movement}\s+{movement}\s+{amounts}\s+100",
    }
    rows = {}
    refs = []
    source = statement["source_binding"]
    for key, pattern in patterns.items():
        matches = [(line, match) for line in text.splitlines()
                   if (match := re.fullmatch(pattern, line.strip()))]
        if len(matches) != 1:
            return None
        line, match = matches[0]
        rows[key] = [int(value.replace(",", "")) for value in match.groups()]
        refs.append(dict(source, physical_page=page, excerpt=line.strip()))
    start, change, subtotal, closing = rows["total"]
    restricted_start, restricted_end = rows["restricted"]
    unrestricted_start, unrestricted_change, unrestricted_subtotal, unrestricted_end = rows["unrestricted"]
    capital = statement["balance_sheet"].get("share_capital_cny")
    if (rows["ordinary"] != rows["unrestricted"] or change != subtotal
            or unrestricted_change != unrestricted_subtotal
            or unrestricted_start + unrestricted_subtotal != unrestricted_end
            or restricted_start + unrestricted_start != start or start + subtotal != closing
            or restricted_end + unrestricted_end != closing or closing <= 0
            or capital is None or Decimal(capital["current"]) != Decimal(closing)):
        raise ValueError("UNNUMBERED_PARENT_ANNUAL_SHARE_RECONCILIATION_CHANGED")
    refs.append(dict(source, physical_page=preferred[0], excerpt="九、优先股相关情况：不适用"))
    refs.append(capital["source_refs"])
    return dict(classification="DERIVED_FACT", period_end=statement["period_end"],
                unit="shares", scope="TOTAL_ISSUED_ORDINARY_SHARES", count=str(closing),
                derivation="ANNUAL_SHARE_TABLE_AND_NO_PREFERRED",
                treasury_excluded=False, source_refs=refs)


def read_unnumbered_parent_cash(*, root, symbol, issuer_name, sources, evaluated_at,
                                constraint_binding=None, fund_selection=None,
                                source_adapter_version=VERSION):
    if source_adapter_version not in UNNUMBERED_VERSIONS:
        raise ValueError("UNNUMBERED_PARENT_SOURCE_VERSION_INVALID")
    if not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None or not sources:
        raise ValueError("UNNUMBERED_PARENT_AWARE_CLOCK_AND_RECEIPTS_REQUIRED")
    root = Path(root).resolve()
    originals = []
    for row in sources:
        if (not isinstance(row, dict) or set(row) != {"period_end", "receipt_binding"}
                or not isinstance(row["period_end"], str)
                or row["period_end"][4:] not in {"-12-31", "-06-30"}):
            raise ValueError("UNNUMBERED_PARENT_SOURCE_CONTRACT_INVALID")
        pin = row["receipt_binding"]
        packet = load_retained_official_report(
            root=root, receipt_binding=pin, symbol=symbol,
            issuer_name=_receipt_issuer_query(root=root, receipt_binding=pin),
            period=row["period_end"],
        )
        if datetime.fromisoformat(packet["completed_at"]) > evaluated_at:
            raise ValueError("UNNUMBERED_PARENT_ACQUISITION_AFTER_CUTOFF")
        source = packet["source"]
        originals.append({**{key: source[key] for key in ("path", "sha256", "available_at")},
                          "period_end": row["period_end"]})
    result = parent.read_parent_direct_owner_cash_sources(
        root=root, symbol=symbol, issuer_name=issuer_name, sources=originals,
        evaluated_at=evaluated_at, constraint_binding=constraint_binding, fund_selection=fund_selection,
    )
    if constraint_binding is not None:
        _, raw = parent._bound(root, constraint_binding)
        packet = json.loads(raw, object_pairs_hook=parent._unique)
        financing = result["constraints"]["issued_financing"]
        if "supplemental_financing_sources_v1" in packet:
            from ...infrastructure.filings.operating_event_terms import parse_operating_event_terms

            sources = packet["supplemental_financing_sources_v1"]
            if not isinstance(sources, list) or not sources:
                raise ValueError("SUPPLEMENTAL_FINANCING_SOURCES_INVALID")
            primary_path, _ = parent._bound(root, packet["financing_source"])
            primary = parse_operating_event_terms(extract_pages(primary_path), symbol=symbol)
            if (primary["event_type"] != "REPORTED_ISSUER_FINANCING_ISSUANCE"
                    or primary["published_date"] > packet["financing_source"]["available_at"][:10]):
                raise ValueError("PRIMARY_FINANCING_DISCLOSURE_INVALID")
            primary_terms = {item["code"]: item for item in primary["financing_issues"]}
            if primary_terms.keys() != {item["code"] for item in financing}:
                raise ValueError("PRIMARY_FINANCING_CODES_CHANGED")
            for item in financing:
                terms = primary_terms[item["code"]]
                principal = Decimal(terms["face_value_cny"])
                if (principal != Decimal(item["principal_cny"])
                        or terms["interest_start"] != item["issue_date"]
                        or terms["maturity"] != item["maturity"]):
                    raise ValueError("PRIMARY_FINANCING_TERMS_CHANGED")
                gross = principal * Decimal(terms["issue_price_per_100_face_cny"]) / 100
                item["gross_issue_price_amount_cny"] = str(gross)
            seen = set(primary_terms)
            for source in sources:
                parent._clock(source["available_at"], evaluated_at)
                path, _ = parent._bound(root, source)
                parsed = parse_operating_event_terms(extract_pages(path), symbol=symbol)
                parent._bound(root, source)
                if (parsed["event_type"] != "REPORTED_ISSUER_FINANCING_ISSUANCE"
                        or parent._compact(parsed["issuer_name"]) != parent._compact(issuer_name)
                        or parsed["published_date"] > source["available_at"][:10]):
                    raise ValueError("SUPPLEMENTAL_FINANCING_DISCLOSURE_INVALID")
                for item in parsed["financing_issues"]:
                    code = item["code"]
                    if code in seen:
                        raise ValueError("SUPPLEMENTAL_FINANCING_DUPLICATE_CODE")
                    seen.add(code)
                    principal = Decimal(item["face_value_cny"])
                    gross = principal * Decimal(item["issue_price_per_100_face_cny"]) / 100
                    financing.append(dict(
                        code=code, issue_date=item["interest_start"], maturity=item["maturity"],
                        principal_cny=str(principal), gross_issue_price_amount_cny=str(gross),
                        classification="FACT", scope="ISSUER_FINANCING_DISCLOSURE", currency="CNY",
                        source_refs=dict(source), actual_settlement_verified=False,
                        unrestricted_cash_receipt_verified=False, refinancing_verified=False,
                        outstanding_at_evaluation_cny=None))
    for statement in result["statements"]:
        if not all(statement["checks"].values()):
            raise ValueError("UNNUMBERED_PARENT_STATEMENT_NOT_RECONCILED")
        for field in ("opening_cash_and_equivalents_cny", "closing_cash_and_equivalents_cny", "cfo_cny"):
            if field not in statement["cash_flow"]:
                raise ValueError("UNNUMBERED_PARENT_REQUIRED_CASH_FACT_MISSING:" + field)
        source = statement["source_binding"]
        path, _ = parent._bound(root, source)
        pages = extract_pages(path)
        table = parent._statement(
            pages, "母公司现金流量表", issuer_name, statement["period_end"])
        parent._bound(root, source)
        if statement.get("ordinary_shares_evidence") is None:
            statement["ordinary_shares_evidence"] = _annual_share_anchor(pages, statement)
        required_rows = (
            ("customer_cash_cny", "销售商品、提供劳务收到的现金"),
            ("supplier_cash_cny", "购买商品、接受劳务支付的现金"),
        )
        financing_rows = (
            ("borrowings_received_cny", "取得借款收到的现金"),
            ("debt_repayments_paid_cny", "偿还债务支付的现金"),
        ) if source_adapter_version == FINANCING_VERSION else ()
        for field, label in required_rows + financing_rows:
            row, _ = parent._row(table, label)
            if row is None:
                raise ValueError("UNNUMBERED_PARENT_REQUIRED_CASH_FACT_MISSING:" + field)
            statement["cash_flow"][field] = {
                **row, "classification": "FACT", "scope": parent.SCOPE, "currency": "CNY",
                "source_refs": parent._source_refs(source, field, row, statement["period_end"]),
            }
    return {**result, "source_adapter_version": source_adapter_version}


read_unnumbered_parent_financing = partial(
    read_unnumbered_parent_cash, source_adapter_version=FINANCING_VERSION,
)
