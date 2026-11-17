"""Read-only dual-provider QUOTE bridge, independent of B1 close admission."""
from datetime import datetime, timedelta, timezone

from .intraday_conditions import CHINA, _session, _stamp
from ...quote_session_collection import resolve_session_reference
from ...quote_sessions import parse_quote


SCHEMA = "retained-intraday-quote-observation-v1"


def project_intraday_observation(bundle: dict, *, symbol: str, now: datetime,
                                 max_age: timedelta) -> dict:
    """Replay explicitly linked raw documents without collection or side effects.

    Returns status QUOTE_VERIFIED with observation, or STALE_OR_UNAVAILABLE
    with observation=None and a reason. Tencent is the primary source; Sina
    evidence and exact provider timestamps are retained separately. source_at
    is the older provider timestamp so downstream freshness is conservative.
    Received time is the later receipt. All timestamps are UTC ISO strings.
    Hash replay proves local integrity, not external timestamp attestation.
    """
    if (not isinstance(now, datetime) or now.utcoffset() is None
            or not isinstance(max_age, timedelta) or max_age <= timedelta(0)):
        raise ValueError("Aware now and explicit positive max_age required")
    if (not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii()
            or not symbol.isdigit()):
        raise ValueError("Exact six-digit symbol required")
    now = now.astimezone(timezone.utc)
    result = {"schema_version": SCHEMA, "symbol": symbol, "status": "STALE_OR_UNAVAILABLE",
        "reason": "RETAINED_BUNDLE_INVALID", "observation": None, "action": "no_order",
        "eligibility": False, "admitted": False, "b1_eligible": False}
    try:
        if bundle.get("version") != "quote-session-collection-v1":
            return result
        started, finished = _stamp(bundle["started_at"]), _stamp(bundle["finished_at"])
        if not started <= finished <= now:
            result["reason"] = "BUNDLE_CLOCK_CONFLICT"
            return result
        reference = bundle["references"][symbol]
        resolved = resolve_session_reference(reference, bundle["documents"])
        venue = "SSE" if symbol.startswith("6") else "SZSE" if symbol.startswith(("0", "3")) else None
        if resolved["symbol"] != symbol or resolved["calendar_exchange"] != venue or venue is None:
            result["reason"] = "SECURITY_IDENTITY_MISMATCH"
            return result
        if not _session(venue, now):
            result["reason"] = "OUTSIDE_EXCHANGE_SESSION"
            return result
        quotes, sources, received, refs = {}, {}, {}, {}
        for provider in ("tencent", "sina"):
            result["reason"] = "RAW_QUOTE_INVALID"
            document = resolved[provider]
            quote = parse_quote(document, provider, symbol, now)
            source, fetched = _stamp(quote["observed_trade_at"]), _stamp(document["fetched_at"])
            if not started <= fetched <= finished or not source <= fetched <= now:
                result["reason"] = "SOURCE_RECEIPT_CLOCK_CONFLICT"
                return result
            if now - source > max_age or now - fetched > max_age:
                result["reason"] = "STALE_QUOTE"
                return result
            if (source.astimezone(CHINA).date() != now.astimezone(CHINA).date()
                    or not _session(venue, source) or not _session(venue, fetched)):
                result["reason"] = "OUTSIDE_EXCHANGE_SESSION"
                return result
            if not quote["normal_with_volume"]:
                result["reason"] = "NOT_NORMAL_WITH_VOLUME"
                return result
            quotes[provider], sources[provider], received[provider] = quote, source, fetched
            refs[provider] = {"id": reference["document_refs"][provider], "provider": provider,
                "source_url": document["source_url"], "sha256": document["sha256"],
                "source_at": source.isoformat(), "received_at": fetched.isoformat()}
        if quotes["tencent"]["price"] != quotes["sina"]["price"]:
            result["reason"] = "CROSS_SOURCE_PRICE_CONFLICT"
            return result
        observation = {"symbol": symbol, "source_id": "tencent", "source_url": refs["tencent"]["source_url"],
            "source_at": min(sources.values()).isoformat(), "received_at": max(received.values()).isoformat(),
            "price": str(quotes["tencent"]["price"]), "quality": "VERIFIED", "suspended": False,
            "input_kind": "QUOTE", "period": "quote", "completed": False,
            "evidence_refs": [refs["tencent"]], "cross_check_evidence_refs": [refs["sina"]],
            "provider_source_at": {provider: stamp.isoformat() for provider, stamp in sources.items()},
            "verified_at": now.isoformat(), "action": "no_order", "eligibility": False,
            "admitted": False, "b1_eligible": False}
        result.update(status="QUOTE_VERIFIED", reason="DUAL_PROVIDER_EXACT_PRICE_MATCH", observation=observation)
        return result
    except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
        return result
