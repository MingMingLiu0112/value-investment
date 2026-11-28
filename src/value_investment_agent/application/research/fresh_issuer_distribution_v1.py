"""Immutable aggregate distribution evidence for a first issuer research task."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from ..product.common import require_inside, write_new_bytes
from ..product.daily_event_observation import verify_retained_event_coverage
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from ...infrastructure.filings.pdf_text import extract_pages

VERSION = "fresh-issuer-distribution-v1"
_MONEY = r"(\d[\d,]*\.\d{2})"
_DATE = r"(\d{4}/\d{1,2}/\d{1,2})"


def _bound(root, pin):
    if (not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
            or not isinstance(pin["path"], str) or Path(pin["path"]).is_absolute()
            or ".." in Path(pin["path"]).parts):
        raise ValueError("FRESH_DISTRIBUTION_BINDING_INVALID")
    path = require_inside(root / "runtime", root / pin["path"], "fresh issuer distribution")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("FRESH_DISTRIBUTION_HASH_CHANGED")
    return path, raw


def _compact(text):
    return re.sub(r"\s+", "", text).replace("Ａ", "A").replace("－", "-")


def _unique(pattern, text, error):
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError(error)
    return matches[0]


def _terms(pages, symbol, issuer):
    first, second = map(_compact, pages[:2])
    if (issuer not in first or f"证券代码：{symbol}" not in first
            or "差异化分红送转：否" not in first or "中国结算上海分公司" not in second
            or "自行发放对象" not in second):
        raise ValueError("FRESH_DISTRIBUTION_ISSUER_OR_SCOPE_INVALID")
    fiscal = int(_unique(r"(\d{4})年年度权益分派实施公告", first,
                         "FRESH_DISTRIBUTION_REPORT_YEAR_REQUIRED"))
    headline = _unique(r"A股每股现金红利" + _MONEY + "元", first,
                       "FRESH_DISTRIBUTION_HEADLINE_REQUIRED")
    shares, per_share, total = _unique(
        r"本次利润分配以方案实施前的公司总股本([\d,]+)股为基数，每股派发现金红利"
        + _MONEY + r"元（含税），共计派发现金红利" + _MONEY + "元",
        first + second, "FRESH_DISTRIBUTION_TERMS_REQUIRED")
    date_pattern = r"A股" + _DATE + "-" + _DATE + _DATE
    dates = _unique(date_pattern, first, "FRESH_DISTRIBUTION_DATES_REQUIRED")
    if dates != _unique(date_pattern, second, "FRESH_DISTRIBUTION_DATES_REQUIRED"):
        raise ValueError("FRESH_DISTRIBUTION_DATES_CONFLICT")
    record, ex_date, payment = (datetime.strptime(value, "%Y/%m/%d").date() for value in dates)
    count = int(shares.replace(",", ""))
    rate = Decimal(per_share)
    amount = Decimal(total.replace(",", ""))
    if (rate != Decimal(headline) or rate <= 0 or count <= 0 or amount != count * rate
            or not record < ex_date <= payment or payment.year != fiscal + 1):
        raise ValueError("FRESH_DISTRIBUTION_ARITHMETIC_OR_DATE_CONFLICT")
    return dict(fiscal_year=fiscal, entitled_shares=count, per_share_cny=str(rate),
                total_cny=str(amount), record_date=record.isoformat(),
                ex_date=ex_date.isoformat(), paid_date=payment.isoformat(),
                payment_date_basis="IMPLEMENTATION_NOTICE_SCHEDULE")


def _confirm(pages, terms):
    fiscal = terms["fiscal_year"]
    pattern = (fr"{fiscal}年度，以权益分派股权登记日总股本为基数，向全体股东每10股派发现金股利"
               + _MONEY + r"元（含税），累计派发现金股利" + _MONEY + "元")
    hits = [(p, rate, total) for p, text in enumerate(pages, 1)
            for rate, total in re.findall(pattern, _compact(text))]
    if (len(hits) != 1 or Decimal(hits[0][1]) != 10 * Decimal(terms["per_share_cny"])
            or Decimal(hits[0][2].replace(",", "")) != Decimal(terms["total_cny"])):
        raise ValueError("FRESH_DISTRIBUTION_AGGREGATE_CONFIRMATION_REQUIRED")
    return hits[0][0]


def _derive(root, source, now):
    if now.utcoffset() is None:
        raise ValueError("FRESH_DISTRIBUTION_AWARE_CLOCK_REQUIRED")
    symbol, issuer = source["symbol"], source["issuer_name"]
    day = date.fromisoformat(source["notice_date"])
    if not re.fullmatch(r"[0-9]{10}", source["notice_id"]):
        raise ValueError("FRESH_DISTRIBUTION_NOTICE_ID_INVALID")
    _, raw = _bound(root, source["observation_binding"])
    obs = json.loads(raw)
    verify_retained_event_coverage(
        root, obs, symbol=symbol, required_from=day, required_to=day, now=now)
    url = f"https://static.cninfo.com.cn/finalpage/{day}/{source['notice_id']}.PDF"
    originals = [row for row in obs["source_bindings"] if row["source_url"] == url]
    if len(originals) != 1:
        raise ValueError("FRESH_DISTRIBUTION_OFFICIAL_ORIGINAL_REQUIRED")
    pin = {key: originals[0][key] for key in ("path", "sha256")}
    path, _ = _bound(root, pin)
    terms = _terms(extract_pages(path, limit=2), symbol, issuer)
    record, paid = (date.fromisoformat(terms[key]) for key in ("record_date", "paid_date"))
    if not day < record < paid <= now.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("FRESH_DISTRIBUTION_EVENT_OUTSIDE_CLOCK")
    confirmation = load_retained_official_report(
        root=root, receipt_binding=source["confirmation_binding"], symbol=symbol,
        issuer_name=issuer, period=f"{paid.year}-06-30")
    report = confirmation["source"]
    if (datetime.fromisoformat(confirmation["completed_at"]) > now
            or datetime.fromisoformat(report["available_at"]) > now
            or date.fromisoformat(report["source_url"].split("/")[-2]) <= paid):
        raise ValueError("FRESH_DISTRIBUTION_CONFIRMATION_CLOCK_INVALID")
    path, _ = _bound(root, {key: report[key] for key in ("path", "sha256")})
    page = _confirm(extract_pages(path), terms)
    return dict(symbol=symbol, issuer_name=issuer, notice_id=source["notice_id"],
                notice_original=pin, confirmation_original_sha256=report["sha256"],
                confirmation_page=page, distribution=terms,
                event_id=f"{symbol}:cninfo:{source['notice_id']}", action="no_order",
                formal_eligibility=False, aggregate_status="ISSUER_CONFIRMED_DISTRIBUTED_TOTAL",
                settlement_status="ROUTE_ACTUALS_UNVERIFIED",
                route_settlement_cny={"issuer_direct": None, "china_clear_shanghai": None})


def seal_fresh_issuer_distribution(*, root, receipt_path, symbol, issuer_name,
                                  notice_date, notice_id, observation_binding,
                                  confirmation_binding, now):
    """Create a receipt from retained originals, without a predecessor valuation."""
    root = Path(root).resolve()
    receipt_path = require_inside(root / "runtime", Path(receipt_path).resolve(),
                                  "fresh issuer distribution receipt")
    source = dict(symbol=symbol, issuer_name=issuer_name, notice_date=notice_date,
                  notice_id=notice_id, observation_binding=observation_binding,
                  confirmation_binding=confirmation_binding)
    result = _derive(root, source, now)
    content = dict(schema_version=VERSION, source=source, result=result)
    raw = (json.dumps(content, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    write_new_bytes(receipt_path, raw)
    pin = dict(path=receipt_path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())
    replay_fresh_issuer_distribution(root=root, receipt_binding=pin, symbol=symbol, now=now)
    return pin


def replay_fresh_issuer_distribution(*, root, receipt_binding, symbol, now):
    """Recover the exact aggregate event for the named issuer."""
    root = Path(root).resolve()
    _, raw = _bound(root, receipt_binding)
    receipt = json.loads(raw)
    if (set(receipt) != {"schema_version", "source", "result"} or receipt["schema_version"] != VERSION
            or receipt["source"]["symbol"] != symbol):
        raise ValueError("FRESH_DISTRIBUTION_RECEIPT_IDENTITY_MISMATCH")
    result = _derive(root, receipt["source"], now)
    if result != receipt["result"]:
        raise ValueError("FRESH_DISTRIBUTION_REPLAY_MISMATCH")
    return result


def apply_fresh_issuer_distribution(*, scenarios, event, symbol, valuation_date):
    """Set one first-year schedule entry per scenario on pristine model rows."""
    terms = event["distribution"]
    basis = date.fromisoformat(valuation_date)
    payment_year = date.fromisoformat(terms["paid_date"]).year
    if (event["symbol"] != symbol or event["aggregate_status"] != "ISSUER_CONFIRMED_DISTRIBUTED_TOTAL"
            or basis != date(terms["fiscal_year"], 12, 31) or payment_year != basis.year + 1
            or set(scenarios) != {"bear", "base", "bull"}):
        raise ValueError("FRESH_DISTRIBUTION_MODEL_IDENTITY_MISMATCH")
    result = deepcopy(scenarios)
    for scenario in result.values():
        rows = scenario["years"]
        if (not rows or rows[0]["year"] != payment_year
                or [row["year"] for row in rows] != list(range(payment_year, payment_year + len(rows)))
                or any(Decimal(row.get("scheduled_owner_distribution_cny", "0")) != 0 for row in rows)):
            raise ValueError("FRESH_DISTRIBUTION_MODEL_SCHEDULE_NOT_PRISTINE")
        for index, row in enumerate(rows):
            row["scheduled_owner_distribution_cny"] = terms["total_cny"] if index == 0 else "0"
    return result
