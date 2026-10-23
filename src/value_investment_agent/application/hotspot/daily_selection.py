"""Daily candidate collection, bounded evidence and replayable ranking."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from ...domain.hotspot.daily_selection import rank_daily_candidates, RULE_VERSION
from ...infrastructure.hotspot.daily_market import (
    collect_dated_market, parse_dated_market, requested_quote_symbols,
)
from ...m2_market_data import fetch_sina_industry_quotes, parse_sina_industry
from ...quote_session_collection import collect_session_bundle
from ...quote_sessions import parse_quote, evaluate_quote_session


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def collect_daily_candidates(*, root: Path, limit=5, candidate_pool_limit=None,
                             classification_collector=None,
                             market_collector=None, bundle_collector=None, now=None) -> dict:
    root = root.resolve()
    directory = root / "runtime" / "hotspot-daily-selection" / uuid4().hex
    directory.mkdir(parents=True)
    raw, classification = (classification_collector or fetch_sina_industry_quotes)()
    original = directory / "classification.json"
    with original.open("xb") as stream:
        stream.write(raw)
    if json.loads(raw) != classification:
        raise ValueError("Classification raw/payload mismatch")
    industry_rows = parse_sina_industry(classification)
    index = {r["symbol"]: r for r in industry_rows if r["symbol"].startswith(("0", "3", "6"))}
    if not index or len(index) != len([r for r in industry_rows if r["symbol"].startswith(("0", "3", "6"))]):
        raise ValueError("Empty or duplicate industry classification")
    # Two venues prove the completed session; acquisition date alone never does.
    anchors = [next(s for s in sorted(index) if s.startswith(("0", "3"))),
               next(s for s in sorted(index) if s.startswith("6"))]
    bundle = (bundle_collector or collect_session_bundle)(anchors)
    calendar_path = directory / "calendar-anchors.json"
    _write(calendar_path, bundle)
    now = now or datetime.now(timezone.utc)
    checks = []
    for symbol in anchors:
        ref = bundle["references"][symbol]
        quote = parse_quote(bundle["documents"][ref["document_refs"]["tencent"]], "tencent", symbol, now)
        result = evaluate_quote_session(symbol, quote["price"], ref, now, documents=bundle["documents"])
        if not result["passed"]:
            raise ValueError("Calendar anchor rejected: " + result["status"])
        checks.append(result)
    dates = {r["expected_session"] for r in checks}
    if len(dates) != 1:
        raise ValueError("Venue session conflict")
    trade_date = dates.pop()
    quotes, sources, failures = (market_collector or collect_dated_market)(sorted(index), directory=directory)
    rows = [{**q, "industry": index[q["symbol"]]["industry"],
             "classification_available_at": classification["fetched_at"],
             "classification_effective_date": None} for q in quotes]
    ranking = rank_daily_candidates(
        rows, trade_date=trade_date, limit=limit,
        candidate_pool_limit=candidate_pool_limit,
    )
    bindings = [dict(path=original.relative_to(root).as_posix(), sha256=hashlib.sha256(raw).hexdigest(),
                     available_at=classification["fetched_at"], source_url=classification["source_url"],
                     trade_date=None, status="ACQUIRED_CLASSIFICATION_EFFECTIVE_DATE_UNKNOWN"),
                dict(path=calendar_path.relative_to(root).as_posix(),
                     sha256=hashlib.sha256(calendar_path.read_bytes()).hexdigest(),
                     available_at=bundle["finished_at"], source_url="SZSE/SSE official calendar and dual-source anchors",
                     trade_date=trade_date, status="VERIFIED_COMPLETED_SESSION")]
    for source in sources:
        bindings.append({**source, "path": Path(source["path"]).relative_to(root).as_posix(), "trade_date": trade_date})
    report = dict(schema_version="hotspot-daily-selection-v1", action="no_order", trade_date=trade_date,
        available_at=max(datetime.fromisoformat(binding["available_at"]) for binding in bindings).isoformat(), limit=limit, rows=rows, ranking=ranking,
        observation_list=ranking["candidates"], candidate_pool=ranking["candidate_pool"],
        candidate_pool_limit=ranking["candidate_pool_limit"],
        candidate_pool_rule=ranking["candidate_pool_rule"],
        hotspot_watch_queue=ranking["candidate_pool"],
        source_bindings=bindings, failures=failures,
        coverage=dict(classified_securities=len(index), dated_quotes=len(quotes),
                      ranked_securities=ranking["market"]["covered_securities"] if ranking["market"] else 0,
                      activity_observation_count=len(ranking["candidates"]),
                      candidate_pool_count=len(ranking["candidate_pool"]),
                      candidate_pool_industry_count=len({row["industry"] for row in ranking["candidate_pool"]}),
                      universe_scope="SINA_CLASSIFIED_A_SHARES_NOT_OFFICIAL_COMPLETE_UNIVERSE", missing_quotes=len(index)-len(quotes)),
        status="DATED_DAILY_OBSERVATIONS" if ranking["candidates"] else "BLOCKED",
        formal_eligibility=False, unknowns=["classification_effective_date", "persistence", "fund_flows", "catalyst", "market_regime_admission"])
    target = directory / "report.json"
    _write(target, report)
    return dict(path=target.relative_to(root).as_posix(), sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def verify_daily_selection(root: Path, report: dict) -> None:
    if report.get("action") != "no_order" or report.get("schema_version") != "hotspot-daily-selection-v1":
        raise ValueError("Invalid daily selection contract")
    candidate_pool = report.get("candidate_pool")
    reported_version = report["ranking"].get("rule_version")
    legacy_versions = {"hotspot-dated-sector-liquidity-ranking-v1",
                       "hotspot-dated-sector-liquidity-ranking-v2"}
    if reported_version not in legacy_versions | {RULE_VERSION}:
        raise ValueError("Unsupported daily ranking rule version")
    if reported_version == RULE_VERSION:
        if not isinstance(candidate_pool, list):
            raise ValueError("Daily v3 candidate_pool is required")
        if type(report.get("candidate_pool_limit")) is not int:
            raise ValueError("Daily candidate-pool limit must be explicit for v3")
    replay = rank_daily_candidates(
        report["rows"], trade_date=report["trade_date"], limit=report["limit"],
        candidate_pool_limit=(
            report.get("candidate_pool_limit")
            if isinstance(candidate_pool, list)
            else None
        ),
    )
    if reported_version in legacy_versions:
        replay["rule_version"] = reported_version
        # Candidate-pool fields were introduced in v3. Legacy reports remain
        # replayable without rewriting their historical ranking object.
        for field in ("candidate_pool", "candidate_pool_rule", "candidate_pool_limit"):
            replay.pop(field, None)
    if reported_version == "hotspot-dated-sector-liquidity-ranking-v1":
        for candidate in replay["candidates"]:
            for field in ("activity_tier", "activity_reason", "structure_tier", "structure_reason"):
                candidate.pop(field)
    if replay != report["ranking"]:
        raise ValueError("Daily ranking replay mismatch")
    if report["observation_list"] != report["ranking"]["candidates"]:
        raise ValueError("Daily watch membership mismatch")
    if "candidate_pool" in report:
        if (report["candidate_pool"] != replay["candidate_pool"]
                or report["hotspot_watch_queue"] != replay["candidate_pool"]):
            raise ValueError("Daily pre-structure candidate pool mismatch")
    elif report["hotspot_watch_queue"] != report["ranking"]["candidates"]:
        raise ValueError("Legacy daily watch membership mismatch")
    for binding in report["source_bindings"]:
        path = (root / binding["path"]).resolve()
        if not path.is_relative_to((root / "runtime").resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("Daily selection original changed")
    classification = json.loads((root / report["source_bindings"][0]["path"]).read_bytes())
    index = {r["symbol"]: r for r in parse_sina_industry(classification)}
    originals = {}
    for binding in report["source_bindings"][2:]:
        symbols = requested_quote_symbols(binding["source_url"])
        if not set(symbols).issubset(index):
            raise ValueError("Daily quote request outside classification")
        available_at = datetime.fromisoformat(binding["available_at"])
        if available_at.utcoffset() is None:
            raise ValueError("Daily quote acquisition requires a timezone")
        raw = (root / binding["path"]).read_bytes()
        try:
            quotes, _ = parse_dated_market(raw, symbols=symbols,
                available_at=available_at, source_url=binding["source_url"])
        except ValueError:
            # The collector retains malformed batches as failures, without rows.
            quotes = []
        for quote in quotes:
            if quote["symbol"] in originals:
                raise ValueError("Duplicate daily quote original")
            originals[quote["symbol"]] = quote
    if {row["symbol"] for row in report["rows"]} != set(originals):
        raise ValueError("Daily rows omit or add valid original quotes")
    for row in report["rows"]:
        quote = originals[row["symbol"]]
        if (any(row[key] != quote[key] for key in (
                "company_name", "close", "change_percent", "amount_cny", "trade_date",
                "available_at", "source_url", "sha256", "status"))
                or ("quote_at" in row and row["quote_at"] != quote["quote_at"])
                or row["industry"] != index[row["symbol"]]["industry"]
                or row["classification_available_at"] != classification["fetched_at"]):
            raise ValueError("Daily facts differ from original evidence")
