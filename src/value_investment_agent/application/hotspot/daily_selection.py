"""Daily candidate collection, bounded evidence and replayable ranking."""
from datetime import datetime, timezone
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from ...domain.hotspot.daily_selection import rank_daily_candidates
from ...infrastructure.hotspot.daily_market import collect_dated_market
from ...m2_market_data import fetch_sina_industry_quotes, parse_sina_industry
from ...quote_session_collection import collect_session_bundle
from ...quote_sessions import parse_quote, evaluate_quote_session


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def collect_daily_candidates(*, root: Path, limit=5, classification_collector=None,
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
    ranking = rank_daily_candidates(rows, trade_date=trade_date, limit=limit)
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
        observation_list=ranking["candidates"], hotspot_watch_queue=ranking["candidates"],
        source_bindings=bindings, failures=failures,
        coverage=dict(classified_securities=len(index), dated_quotes=len(quotes), ranked_securities=ranking["market"]["covered_securities"] if ranking["market"] else 0,
                      universe_scope="SINA_CLASSIFIED_A_SHARES_NOT_OFFICIAL_COMPLETE_UNIVERSE", missing_quotes=len(index)-len(quotes)),
        status="DATED_DAILY_OBSERVATIONS" if ranking["candidates"] else "BLOCKED",
        formal_eligibility=False, unknowns=["classification_effective_date", "persistence", "fund_flows", "catalyst", "market_regime_admission"])
    target = directory / "report.json"
    _write(target, report)
    return dict(path=target.relative_to(root).as_posix(), sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def verify_daily_selection(root: Path, report: dict) -> None:
    if report.get("action") != "no_order" or report.get("schema_version") != "hotspot-daily-selection-v1":
        raise ValueError("Invalid daily selection contract")
    if rank_daily_candidates(report["rows"], trade_date=report["trade_date"], limit=report["limit"]) != report["ranking"]:
        raise ValueError("Daily ranking replay mismatch")
    if report["hotspot_watch_queue"] != report["ranking"]["candidates"] or report["observation_list"] != report["ranking"]["candidates"]:
        raise ValueError("Daily watch membership mismatch")
    for binding in report["source_bindings"]:
        path = (root / binding["path"]).resolve()
        if not path.is_relative_to((root / "runtime").resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("Daily selection original changed")
    classification = json.loads((root / report["source_bindings"][0]["path"]).read_bytes())
    index = {r["symbol"]: r for r in parse_sina_industry(classification)}
    quote_bindings = {binding["sha256"]: binding for binding in report["source_bindings"][2:]}
    originals = {}
    for digest, binding in quote_bindings.items():
        text = (root / binding["path"]).read_bytes().decode("gb18030")
        originals[digest] = {match[1][2:]: match[2].split("~")
            for match in re.finditer(r'v_((?:sh|sz)\d{6})="([^"\r\n]*)";', text)}
    for row in report["rows"]:
        fields = originals[row["sha256"]][row["symbol"]]
        source = quote_bindings[row["sha256"]]
        close, previous = Decimal(fields[3]), Decimal(fields[4])
        trade_at = datetime.strptime(fields[30], "%Y%m%d%H%M%S")
        if (row["company_name"] != fields[1] or row["close"] != str(close)
                or row["change_percent"] != str((close / previous - 1) * 100)
                or row["amount_cny"] != str(Decimal(fields[37]) * 10000)
                or row["trade_date"] != trade_at.date().isoformat()
                or row["industry"] != index[row["symbol"]]["industry"]
                or row["available_at"] != source["available_at"]
                or row["source_url"] != source["source_url"]
                or row["classification_available_at"] != classification["fetched_at"]):
            raise ValueError("Daily facts differ from original evidence")
