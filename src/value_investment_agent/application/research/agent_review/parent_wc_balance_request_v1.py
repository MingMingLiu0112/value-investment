"""Opt-in D2 request adapter for verified parent balance risk anchors.

The caller supplies a source-verified history. This module never reads PDFs,
calls a provider, or turns balance movements into working-capital cash flow.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from . import operating_horizon_draft_v3 as draft

VERSION = "parent-wc-balance-request-v1"
FIELDS = ("accounts_receivable", "inventory", "accounts_payable")
HASH = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("PARENT_WC_PERIOD_INVALID")
    return date.fromisoformat(value)


def _source(row, *, as_of):
    digest, url, raw_time = (row.get(key) for key in
                             ("original_sha256", "source_url", "available_at"))
    if not isinstance(digest, str) or not HASH.fullmatch(digest) or not isinstance(url, str):
        raise ValueError("PARENT_WC_SOURCE_BINDING_INVALID")
    parsed = urlparse(url)
    match = re.fullmatch(r"/finalpage/(\d{4}-\d{2}-\d{2})/\d{10}\.PDF", parsed.path)
    if (parsed.scheme != "https" or parsed.netloc != "static.cninfo.com.cn"
            or parsed.query or parsed.fragment or not match):
        raise ValueError("PARENT_WC_SOURCE_BINDING_INVALID")
    try:
        available = datetime.fromisoformat(raw_time)
        published = _date(match[1])
    except (TypeError, ValueError) as error:
        raise ValueError("PARENT_WC_SOURCE_TIME_INVALID") from error
    if (available.utcoffset() is None or available > as_of
            or published > available.astimezone(ZoneInfo("Asia/Shanghai")).date()):
        raise ValueError("PARENT_WC_SOURCE_NOT_AVAILABLE_AS_OF")
    return digest


def attach_parent_wc_balance_anchor(context: dict, *, history: dict,
                                    as_of: datetime) -> tuple[dict, dict]:
    """Attach at least two compatible historical parent balance intervals."""
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("PARENT_WC_REQUEST_AS_OF_INVALID")
    if (not isinstance(context, dict) or not isinstance(context.get("symbol"), str)
            or not re.fullmatch(r"\d{6}", context["symbol"])
            or not isinstance(context.get("issuer_name"), str) or not context["issuer_name"]
            or context.get("as_of") != as_of.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            or not isinstance(context.get("evidence"), list)):
        raise ValueError("PARENT_WC_REQUEST_IDENTITY_OR_AS_OF_INVALID")
    if (not isinstance(history, dict)
            or history.get("status") != "PARENT_BALANCE_MOVEMENTS_ONLY"
            or history.get("symbol") != context["symbol"]
            or ("issuer_name" in history and history["issuer_name"] != context["issuer_name"])
            or history.get("operating_wc_cash_cny") != "UNKNOWN"
            or history.get("formal_eligibility") is not False
            or history.get("action") != "no_order"
            or not isinstance(history.get("registry_sha256"), str)
            or not HASH.fullmatch(history["registry_sha256"])):
        raise ValueError("PARENT_WC_HISTORY_NOT_VERIFIED_OR_CROSS_ISSUER")
    periods = history.get("observations")
    if not isinstance(periods, list) or len(periods) < 2 or len(periods) > 12:
        raise ValueError("PARENT_WC_HISTORY_PERIODS_INVALID")
    enriched = deepcopy(context)
    anchors = []
    existing_ids = {row.get("id") for row in enriched["evidence"] if isinstance(row, dict)}
    prior_end, prior_balances = None, None
    for row in periods:
        if not isinstance(row, dict) or row.get("unit") != "CNY":
            raise ValueError("PARENT_WC_SCOPE_OR_UNIT_INVALID")
        columns = row.get("columns")
        if not isinstance(columns, list) or len(columns) != 2 or columns[0] != row.get("period"):
            raise ValueError("PARENT_WC_HISTORY_PERIODS_INVALID")
        end_date, start_date = _date(columns[0]), _date(columns[1])
        if start_date >= end_date or end_date > as_of.astimezone(ZoneInfo("Asia/Shanghai")).date():
            raise ValueError("PARENT_WC_HISTORY_PERIODS_INVALID")
        if prior_end is not None and (start_date != prior_end or end_date <= prior_end):
            raise ValueError("PARENT_WC_HISTORY_PERIODS_NOT_CONTIGUOUS")
        digest = _source(row, as_of=as_of)
        if (row.get("parent_cfo_cny") == row.get("excluded_group_note_cfo_cny")
                or not isinstance(row.get("parent_balance_pages"), list)
                or not row["parent_balance_pages"]
                or any(type(page) is not int or page < 1 for page in row["parent_balance_pages"])):
            raise ValueError("PARENT_WC_SCOPE_OR_UNIT_INVALID")
        balances, changes = {}, {}
        try:
            for field in FIELDS:
                entry = row["balance_rows"][field]
                end = Decimal(entry["period_end_balance_cny"])
                begin = Decimal(entry["period_start_balance_cny"])
                delta = Decimal(entry["balance_change_cny"])
                if (not all(value.is_finite() for value in (end, begin, delta))
                        or end - begin != delta or end < 0 or begin < 0):
                    raise ValueError("PARENT_WC_BALANCE_RECONCILIATION_FAILED")
                balances[field] = (begin, end)
                changes[field] = delta
        except (KeyError, TypeError, InvalidOperation) as error:
            raise ValueError("PARENT_WC_BALANCE_RECONCILIATION_FAILED") from error
        if prior_balances is not None and any(
                balances[field][0] != prior_balances[field] for field in FIELDS):
            raise ValueError("PARENT_WC_OPENING_BALANCES_CHANGED")
        proxy = changes["accounts_receivable"] + changes["inventory"] - changes["accounts_payable"]
        evidence_id = f"official:parent-three-line-wc-balance:{context['symbol']}:{row['period']}"
        if evidence_id in existing_ids:
            raise ValueError("PARENT_WC_DUPLICATE_EVIDENCE_ID")
        existing_ids.add(evidence_id)
        text = (f"母公司{columns[1]}至{columns[0]}余额变化：应收账款{changes['accounts_receivable']}元、"
                f"存货{changes['inventory']}元、应付账款{changes['accounts_payable']}元；"
                f"三项窄口径余额代理变化{proxy}元。非现金流分解、非未来预测，不能按不同期间年化或直接套用。")
        enriched["evidence"].append(dict(id=evidence_id,
            source_id="official:" + digest, pdf_sha256=digest,
            available_at=row["available_at"], period=row["period"],
            period_basis="BALANCE_INTERVAL", scope="ISSUER_PARENT_STANDALONE_BALANCE_PROXY",
            unit="CNY", field="parent_three_line_wc_balance_change",
            value=str(proxy), text=text))
        anchors.append(dict(period_start=columns[1], period_end=columns[0],
            proxy_balance_change_cny=str(proxy), evidence_id=evidence_id,
            source_url=row["source_url"], pdf_sha256=digest,
            available_at=row["available_at"], parent_balance_pages=row["parent_balance_pages"],
            formula="change(accounts_receivable)+change(inventory)-change(accounts_payable)"))
        prior_end = end_date
        prior_balances = {field: balances[field][1] for field in FIELDS}
    enriched["snapshot_fingerprint"] = hashlib.sha256(_canonical({
        key: value for key, value in enriched.items() if key != "snapshot_fingerprint"})).hexdigest()
    return enriched, dict(schema_version=VERSION, action="no_order",
        symbol=context["symbol"], issuer_name=context["issuer_name"],
        historical_balance_anchors=anchors, operating_wc_cash_cny="UNKNOWN",
        formal_eligibility=False,
        limitation="Different interval lengths remain separate risk references; no pooled forecast range or parent WC cash decomposition.")


def build_request_with_parent_wc_balance(context: dict, years, *, history: dict,
                                         as_of: datetime, max_completion_tokens=4096):
    """Build the existing D2 request without dispatching a provider."""
    enriched, anchor = attach_parent_wc_balance_anchor(context, history=history, as_of=as_of)
    request = draft.build_request(enriched, years, max_completion_tokens)
    system = request.system + (" " + VERSION + ": Historical standalone-parent three-line "
        "working-capital BALANCE movements are risk anchors only. Intervals may differ in "
        "duration. Do not annualize, treat a balance delta as cash flow, set future "
        "operating_wc_cash_cny to zero, or copy a historical delta into a scenario. "
        "A numeric conditional WC assumption needs an explicit economic mechanism, scope, "
        "time horizon, counterevidence, and cited original IDs; otherwise UNKNOWN with null value.")
    user = request.user + "\nSOURCE_BOUND_PARENT_WC_BALANCE_RISK_ANCHOR=" + _canonical(anchor).decode("utf-8")
    if len(user) > 64000:
        raise ValueError("PARENT_WC_REQUEST_OVER_BUDGET")
    return enriched, replace(request, system=system, user=user), anchor
