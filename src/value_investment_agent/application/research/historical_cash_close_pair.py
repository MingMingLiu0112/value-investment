"""Replay the price effect of a single all-share SSE cash entitlement."""
from datetime import date, datetime, time
from decimal import Decimal
from urllib.parse import urlencode

from ...infrastructure.evidence.historical_price_correspondence import verify_price_correspondence
from ...quote_sessions import CHINA
from ..product.common import load_json_object


def replay_cash_close_pair(*, root, binding, symbol, distributions, end, now, read):
    """Historical only. The observed close includes the market move after ex-date."""
    stamp = datetime.fromisoformat(binding["acquired_at"])
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("HISTORICAL_PAIR_ACQUISITION_OUTSIDE_REPLAY_CLOCK")
    original = binding["original_binding"]
    read(original)
    matches = [row for row in distributions if row.get("native_terms") and
               any(anchor["binding"] == original for anchor in row["evidence"])]
    if len(matches) != 1:
        raise ValueError("HISTORICAL_PAIR_REQUIRES_UNIQUE_NATIVE_DISTRIBUTION")
    row, = matches
    terms = row["native_terms"]
    if (terms["symbol"] != symbol or terms.get("currency") != "CNY"
            or terms.get("parser_version") not in {
                "sse-explicit-cash-implementation-body-v1", "sse-full-share-cross-page-cash-scheme-v1"}
            or terms.get("body_terms_reconciled") is not True):
        raise ValueError("HISTORICAL_PAIR_REQUIRES_ALL_SHARE_CASH_SCHEME")
    record, ex = terms["record_date"], terms["ex_date"]
    if not (date.fromisoformat(record) < date.fromisoformat(ex) <= end):
        raise ValueError("HISTORICAL_PAIR_EX_DATE_OUTSIDE_COMPARISON")
    if stamp < datetime.combine(date.fromisoformat(ex), time(15), tzinfo=CHINA):
        raise ValueError("HISTORICAL_PAIR_ACQUIRED_BEFORE_EX_CLOSE")
    expected = f"sh{symbol},day,{record},{ex},2,"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + urlencode({"param": expected}, safe=",")
    if binding["url"] != url:
        raise ValueError("HISTORICAL_PAIR_SOURCE_OR_DATES_MISMATCH")
    ref = binding["price_binding"]
    payload = load_json_object(read(ref), "historical entitlement raw quotes")
    bars = payload.get("data", {}).get("sh" + symbol, {}).get("day", [])
    if [bar[0] for bar in bars] != [record, ex]:
        raise ValueError("HISTORICAL_PAIR_REQUIRES_TWO_EXACT_RAW_SESSIONS")
    sessions = [dict(date=bar[0], open=bar[1], close=bar[2]) for bar in bars if len(bar) >= 3]
    if len(sessions) != 2:
        raise ValueError("HISTORICAL_PAIR_INCOMPLETE_BARS")
    verified = verify_price_correspondence(root=root, symbol=symbol, sessions=sessions,
                                           references=[dict(**ref, kind="prices", url=url)])
    if verified["status"] != "MATCH":
        raise ValueError("HISTORICAL_PAIR_PRICE_CORRESPONDENCE_FAILED")
    before, after = (Decimal(item["close"]) for item in verified["rows"])
    cash = Decimal(terms["cash_per_share"])
    reference = before - cash
    if reference <= 0:
        raise ValueError("HISTORICAL_PAIR_INVALID_EX_REFERENCE")
    return dict(status="REPLAYED", scope="HISTORICAL_SINGLE_CASH_EVENT", symbol=symbol,
                record_date=record, ex_date=ex, record_close_cny=str(before),
                ex_close_cny=str(after), gross_per_share_cny=str(cash),
                theoretical_ex_reference_cny=str(reference), market_move_cny=str(after-reference),
                original_binding=original, price_binding=ref, source_url=url,
                acquired_at=binding["acquired_at"], model_inclusion=row["model_inclusion"],
                settlement_proven=False, current_price_comparison=False, action="no_order")
