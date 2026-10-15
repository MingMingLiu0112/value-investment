"""Immutable current cases using the existing Sina parser and B1 contract."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import requests

from value_investment_agent.domain.hotspot.current_price import (
    CURRENT_BLOCKERS, aggregate_sessions, completed_session_bars, current_signal,
)
from value_investment_agent.domain.hotspot.price_action_plan import calculate_price_levels
from value_investment_agent.quote_sessions import (
    CHINA, evaluate_quote_session, latest_szse_session, next_sse_2026_session,
)
from .sina_price_case import ENDPOINT, PERIODS, _source_url_valid, daily_from_intraday, parse_klines
from .daily_market import bounded_get

DISPLAY_CLOSE_SCOPE = "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
STRICT_CLOSE_SCOPE = "SAME_SESSION_B1"


def _display_close(root, path, sha, symbol, as_of, price, now):
    """Newly acquired last-completed close, never same-session B1/PIT admission."""
    from value_investment_agent.quote_session_conversion import quote_snapshot_from_bundle_file
    path = _inside(root, path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("Display bundle hash mismatch")
    bundle = json.loads(raw)
    finished = datetime.fromisoformat(bundle["finished_at"])
    if finished.utcoffset() is None or finished > now:
        raise ValueError("Display bundle cutoff mismatch")
    snapshot = quote_snapshot_from_bundle_file(path, root, symbol=symbol,
        ref_id="completed-close-observation-" + sha, expected_sha256=sha, require_current_b1=False)
    if (snapshot.status != "verified_close" or snapshot.quote_date != as_of
            or Decimal(snapshot.current_price) != Decimal(price)):
        raise ValueError("Display dual-source close rejected")
    reference = bundle["references"][symbol]
    checked = evaluate_quote_session(symbol, price, reference, now, documents=bundle["documents"])
    if not checked["passed"] or checked["expected_session"] != as_of.isoformat():
        raise ValueError("Display close is not calendar-bound latest completed session: " + checked["status"])
    refs = reference["document_refs"]
    for key in [refs["tencent"], refs["sina"], *refs["calendar_documents"]]:
        fetched = datetime.fromisoformat(bundle["documents"][key]["fetched_at"])
        if fetched.utcoffset() is None or fetched > finished:
            raise ValueError("Display evidence cutoff mismatch")
    return dict(status="VERIFIED_LAST_COMPLETED_CLOSE_DISPLAY_ONLY", price=str(Decimal(price)),
        bundle_path=path.relative_to(root).as_posix(), bundle_sha256=sha,
        evidence_refs=checked["source_hashes"], provider_times=checked["provider_times"],
        next_session=None, observation_scope=DISPLAY_CLOSE_SCOPE,
        acquired_at=finished.isoformat(), latest_completed_session=as_of.isoformat(),
        current_pit=False, formal_eligibility=False, price_admitted=False)


def _inside(root, path):
    path = Path(path)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to((root / "runtime").resolve()):
        raise ValueError("Evidence must remain under runtime")
    return path


def _clock(now):
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware clock required")
    return now.astimezone(CHINA)


def _b1(root, path, sha, symbol, as_of, price, now):
    path = _inside(root, path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("B1 bundle hash mismatch")
    bundle = json.loads(raw)
    finished = datetime.fromisoformat(bundle["finished_at"])
    if (bundle.get("version") != "quote-session-collection-v1"
            or bundle.get("status") not in {"collected_not_verified", "partial_failure"}
            or finished.utcoffset() is None
            or finished > now):
        raise ValueError("B1 bundle contract mismatch")
    reference = bundle["references"][symbol]
    checked = evaluate_quote_session(symbol, price, reference, now,
                                     documents=bundle["documents"])
    if not checked["passed"] or checked["expected_session"] != as_of.isoformat():
        raise ValueError("B1 current close rejected: " + checked["status"])
    refs = reference["document_refs"]
    documents = [bundle["documents"][key] for key in
                 [refs["tencent"], refs["sina"], *refs["calendar_documents"]]]
    for document in documents:
        fetched = datetime.fromisoformat(document["fetched_at"])
        if fetched.utcoffset() is None or fetched > finished or document.get("http_status") != 200:
            raise ValueError("B1 evidence cutoff mismatch")
    for document in documents[:2]:
        fetched = datetime.fromisoformat(document["fetched_at"]).astimezone(CHINA)
        if fetched.date() != as_of or fetched.hour < 15:
            raise ValueError("B1 requires same-session post-close acquisition")
    calendars = documents[2:]
    if symbol.startswith("6"):
        next_session, _ = next_sse_2026_session(calendars, as_of, now)
    else:
        # Reuse the official monthly-calendar validator for each future close.
        next_session = None
        for offset in range(1, 33):
            candidate = datetime.combine(as_of + timedelta(days=offset),
                                         datetime.min.time(), CHINA).replace(hour=15, minute=5)
            try:
                session, _ = latest_szse_session(calendars, candidate)
            except ValueError:
                break
            if session > as_of.isoformat():
                next_session = session
                break
    return dict(status="VERIFIED_DUAL_SOURCE_CLOSE", price=str(Decimal(price)),
                bundle_path=path.relative_to(root).as_posix(), bundle_sha256=sha,
                evidence_refs=checked["source_hashes"],
                provider_times=checked["provider_times"], next_session=next_session)


def _build(root, symbol, as_of, sources, bundle_path, bundle_sha, now, *, observation_scope=STRICT_CLOSE_SCOPE):
    if observation_scope not in {STRICT_CLOSE_SCOPE, DISPLAY_CLOSE_SCOPE}:
        raise ValueError("Unsupported current-case observation scope")
    bars = {}
    for period, scale in PERIODS.items():
        source = sources[period]
        path = _inside(root, source["path"])
        raw = path.read_bytes()
        fetched = datetime.fromisoformat(source["fetched_at"])
        if (hashlib.sha256(raw).hexdigest() != source["sha256"]
                or source.get("adjustment") != "UNADJUSTED"
                or source.get("scope") != "SINGLE_PROVIDER_CURRENT_OBSERVATION"
                or not _source_url_valid(source["source_url"], symbol=symbol, scale=scale)
                or fetched.utcoffset() is None or fetched > now
                or fetched <= datetime.combine(as_of, datetime.min.time(), CHINA).replace(hour=15)):
            raise ValueError("Current source hash/identity/availability mismatch")
        bars[period] = completed_session_bars(parse_klines(raw, period=period, as_of=as_of),
                                               period=period)
    bars["daily"] = daily_from_intraday(bars["60m"])
    second_daily = {row["time"]: row for row in aggregate_sessions(bars["15m"])}
    for row in bars["daily"]:
        if row["time"] in second_daily and any(
                Decimal(row[field]) != Decimal(second_daily[row["time"]][field])
                for field in ("open", "high", "low", "close", "volume")):
            raise ValueError("Daily aggregate conflict")
        if (row["time"] in second_daily and
                abs(Decimal(row["amount"]) - Decimal(second_daily[row["time"]]["amount"])) > Decimal("0.01")):
            raise ValueError("Daily aggregate amount conflict exceeds one cent")
    if as_of.isoformat() not in second_daily:
        raise ValueError("Missing latest 15m daily aggregate")
    levels = {period: calculate_price_levels(rows, period=period) for period, rows in bars.items()}
    close = bars["daily"][-1]["close"]
    binding = (_display_close if observation_scope == DISPLAY_CLOSE_SCOPE else _b1)(
        root, bundle_path, bundle_sha, symbol, as_of, close, now)
    state, explanation = current_signal(levels)
    result = dict(schema_version="hotspot-current-price-case-v1", symbol=symbol,
                strategy="HOTSPOT_SATELLITE", market_trade_date=as_of.isoformat(),
                current_reference_price=close, current_reference_close=binding,
                levels=levels, bars=bars, source_bindings=sources,
                signal_state=state, explanation=explanation,
                blockers=list(CURRENT_BLOCKERS), action_eligibility=False, action="no_order",
                bar_timezone="Asia/Shanghai")
    if observation_scope == DISPLAY_CLOSE_SCOPE:
        result.update(observation_scope=DISPLAY_CLOSE_SCOPE, current_pit=False,
                      formal_eligibility=False, price_admitted=False)
    return result


def collect_current_price_case(*, root: Path, symbol: str, as_of: date,
                               quote_bundle_path: Path, quote_bundle_sha256: str,
                               fetch=None, now=None, observation_scope=STRICT_CLOSE_SCOPE) -> dict:
    root = Path(root).resolve()
    live_clock = now is None
    now = _clock(now)
    if len(symbol) != 6 or not symbol.isdigit() or not symbol.startswith(("0", "3", "6")):
        raise ValueError("Invalid symbol")
    if observation_scope not in {STRICT_CLOSE_SCOPE, DISPLAY_CLOSE_SCOPE}:
        raise ValueError("Unsupported current-case observation scope")
    # Reject incomplete, stale and unsupported sessions before network requests.
    bundle = json.loads(_inside(root, quote_bundle_path).read_bytes())
    from value_investment_agent.quote_sessions import parse_quote
    ref = bundle["references"][symbol]
    quote = parse_quote(bundle["documents"][ref["document_refs"]["tencent"]], "tencent", symbol, now)
    (_display_close if observation_scope == DISPLAY_CLOSE_SCOPE else _b1)(
        root, quote_bundle_path, quote_bundle_sha256, symbol, as_of, quote["price"], now)
    directory = root / "runtime" / "hotspot-current-price-cases" / f"{symbol}-{as_of}-{uuid4().hex}"
    directory.mkdir(parents=True)
    sources = {}
    with requests.Session() as session:
        session.trust_env = False
        fetch = fetch or session.get
        for period, scale in PERIODS.items():
            response = bounded_get(fetch, ENDPOINT, params=dict(symbol=("sh" if symbol.startswith("6") else "sz") + symbol,
                                                   scale=scale, ma="no", datalen="1970"), timeout=15)
            response.raise_for_status()
            raw = response.content
            if not raw or len(raw) > 5 * 1024 * 1024:
                raise ValueError("Provider response empty or oversized")
            path = directory / f"sina-{period}.jsonp"
            path.write_bytes(raw)
            sources[period] = dict(path=path.relative_to(root).as_posix(),
                                   sha256=hashlib.sha256(raw).hexdigest(), source_url=response.url,
                                   fetched_at=(_clock(None) if live_clock else now).isoformat(), adjustment="UNADJUSTED",
                                   scope="SINGLE_PROVIDER_CURRENT_OBSERVATION")
    sources["daily"] = {**sources["60m"], "scope": "DERIVED_FROM_SINA_60M_NOT_INDEPENDENT_DAILY_SOURCE"}
    now = _clock(None) if live_clock else now
    case = _build(root, symbol, as_of, sources, quote_bundle_path, quote_bundle_sha256, now,
                  observation_scope=observation_scope)
    path = directory / "case.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False, indent=2)
    return load_current_price_case(root=root, symbol=symbol, case_path=path, now=now)


def load_current_price_case(*, root: Path, symbol: str, as_of: date | None = None,
                            case_path: Path | None = None, expected_sha256: str | None = None,
                            now=None) -> dict:
    root = Path(root).resolve()
    now = _clock(now)
    if case_path is None:
        raise ValueError("Explicit immutable case_path required; Root owns registry")
    path = _inside(root, case_path)
    if not path.is_relative_to(root / "runtime/hotspot-current-price-cases") or path.name != "case.json":
        raise ValueError("Current case path outside immutable current results")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError("Current case hash mismatch")
    case = json.loads(raw)
    day = date.fromisoformat(case["market_trade_date"])
    if case["symbol"] != symbol or (as_of is not None and day != as_of):
        raise ValueError("Current case identity mismatch")
    for period in PERIODS:
        if case["source_bindings"][period]["path"] != (path.parent / f"sina-{period}.jsonp").relative_to(root).as_posix():
            raise ValueError("Current original path mismatch")
    binding = case["current_reference_close"]
    rebuilt = _build(root, symbol, day, case["source_bindings"], binding["bundle_path"],
                     binding["bundle_sha256"], now,
                     observation_scope=case.get("observation_scope", STRICT_CLOSE_SCOPE))
    if case != rebuilt or case["source_bindings"]["daily"] != {
            **case["source_bindings"]["60m"], "scope": "DERIVED_FROM_SINA_60M_NOT_INDEPENDENT_DAILY_SOURCE"}:
        raise ValueError("Current case calculation/contract mismatch")
    bundle = json.loads(_inside(root, binding["bundle_path"]).read_bytes())
    available = max(datetime.fromisoformat(value) for value in [
        bundle["finished_at"], *(source["fetched_at"] for source in case["source_bindings"].values())])
    return {**case, "case_path": path.relative_to(root).as_posix(), "case_sha256": sha,
            "verified_available_at": available.isoformat()}
