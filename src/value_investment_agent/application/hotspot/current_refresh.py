"""Bounded current price refresh from an explicitly hash-bound watch report."""

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from value_investment_agent.infrastructure.hotspot.current_price_case import collect_current_price_case
from value_investment_agent.quote_session_collection import collect_session_bundle
from value_investment_agent.quote_sessions import evaluate_quote_session, parse_quote
from value_investment_agent.application.product.publication_chain import bound_object, load_current_chain
from .daily_selection import verify_daily_selection


def current_watch_binding(root: Path) -> dict:
    chain = load_current_chain(root)
    binding = chain["model"]["product_extensions"]["hotspot_report"]
    report = bound_object(root, binding)
    if report.get("schema_version") != "hotspot-observation-report-v1" or report.get("action") != "no_order":
        raise ValueError("Published extension is not a hotspot observation report")
    return binding


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def select_watch_candidates(report: dict, *, limit: int = 5) -> tuple[list[dict], str]:
    maximum = 10 if report.get("schema_version") == "hotspot-daily-selection-v1" else 5
    if isinstance(limit, bool) or not 1 <= limit <= maximum:
        raise ValueError("At most five candidates allowed")
    queue = report.get("hotspot_watch_queue") or report.get("watch_queue") or []
    scope = ("DATED_DAILY_SECTOR_RANKING_OBSERVATION" if report.get("schema_version") == "hotspot-daily-selection-v1"
             else "HOTSPOT_WATCH_QUEUE")
    if not queue:
        queue = [row for row in report.get("dated_quote_observations", [])
                 if row.get("status") == "DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION"]
        scope = "DATED_SECURITIES_WATCH_FALLBACK_NOT_INDUSTRY_CERTIFIED"
    names = {}

    def visit(value):
        if isinstance(value, dict):
            if value.get("symbol") and (value.get("company_name") or value.get("name")):
                names[value["symbol"]] = value.get("company_name") or value["name"]
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(report)
    selected, seen = [], set()
    for row in queue:
        symbol = row.get("symbol", "")
        if len(symbol) != 6 or not symbol.isdigit() or not symbol.startswith(("0", "3", "6")):
            raise ValueError("Invalid watch symbol")
        if symbol not in seen:
            selected.append(dict(symbol=symbol, company_name=names.get(symbol, symbol)))
            seen.add(symbol)
        if len(selected) == limit:
            break
    return selected, scope


def refresh_current_price_conditions(*, root: Path, watch_source_path: Path,
                                     watch_source_sha256: str, limit: int = 5,
                                     bundle_collector=None, case_collector=None, now=None) -> dict:
    root = Path(root).resolve()
    source = Path(watch_source_path)
    source = (source if source.is_absolute() else root / source).resolve()
    if not source.is_relative_to((root / "runtime").resolve()):
        raise ValueError("Watch evidence must remain under runtime")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != watch_source_sha256:
        raise ValueError("Watch source hash mismatch")
    report = json.loads(raw)
    if report.get("schema_version") == "hotspot-daily-selection-v1":
        verify_daily_selection(root, report)
    selected, scope = select_watch_candidates(report, limit=limit)
    empty_daily = (not selected and report.get("schema_version") == "hotspot-daily-selection-v1"
                   and bool(report.get("rows")) and not report.get("failures"))
    if not selected and not empty_daily:
        return dict(status="BLOCKED", items=[], failures=[dict(reason="NO_BOUND_WATCH_CANDIDATES")], action="no_order")
    bundle = (dict(status="NO_CANDIDATES", finished_at=report["available_at"])
              if empty_daily else
              (bundle_collector or collect_session_bundle)([row["symbol"] for row in selected]))
    archive = root / "runtime" / "hotspot-current-refresh" / uuid4().hex
    archive.mkdir(parents=True)
    bundle_path = archive / "bundle.json"
    _write(bundle_path, bundle)
    bundle_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    now = now or datetime.now(timezone.utc)
    observations, items, failures = [], [], []
    for row in selected:
        symbol = row["symbol"]
        try:
            ref = bundle["references"][symbol]
            quote = parse_quote(bundle["documents"][ref["document_refs"]["tencent"]], "tencent", symbol, now)
            checked = evaluate_quote_session(symbol, quote["price"], ref, now, documents=bundle["documents"])
            observations.append(dict(symbol=symbol, observed_price=str(quote["price"]), result=checked))
            if not checked["passed"]:
                raise ValueError("B1 rejected: " + checked["status"] + ":" + checked.get("detail", ""))
            if report.get("schema_version") == "hotspot-daily-selection-v1" and checked["expected_session"] != report["trade_date"]:
                raise ValueError("Selection session and price session differ")
            case = (case_collector or collect_current_price_case)(
                root=root, symbol=symbol, as_of=date.fromisoformat(checked["expected_session"]),
                quote_bundle_path=bundle_path, quote_bundle_sha256=bundle_sha)
            items.append({**row, "case_path": case["case_path"], "case_sha256": case["case_sha256"]})
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
            failures.append({**row, "reason": str(error)})
        except Exception as error:
            # A source failure must not replace a previously verified registry.
            failures.append({**row, "reason": type(error).__name__ + ":" + str(error)})
    _write(archive / "report.json", dict(bundle_sha256=bundle_sha,
           bundle_bytes=bundle_path.stat().st_size, status=bundle["status"], observations=observations,
           production_database_changed=False, financial_or_strategy_approval=False))
    registry = dict(schema_version="current-price-conditions-v1", action="no_order",
                    watch_source_binding=dict(path=source.relative_to(root).as_posix(), sha256=watch_source_sha256),
                    watch_source_scope=scope, items=items, failures=failures,
                    selected_symbols=[row["symbol"] for row in selected],
                    completed_at=bundle["finished_at"])
    target = root / "config" / "current-price-conditions.json"
    if target.is_file():
        try:
            previous_raw = target.read_bytes()
            previous = json.loads(previous_raw)
            _write(archive / "previous-registry.json", previous)
            candidates = [{**item, "watch_source_binding": previous["watch_source_binding"],
                           "watch_source_scope": previous["watch_source_scope"]}
                          for item in previous["items"]] + previous.get("previous_items", [])
            selected_symbols = {item["symbol"] for item in items}
            retained = {}
            for item in candidates:
                if item["symbol"] not in selected_symbols:
                    retained.setdefault(item["symbol"], item)
            registry["previous_items"] = list(retained.values())[:10]
        except (ValueError, OSError, KeyError, TypeError):
            # An invalid previous pointer is not evidence and is never imported.
            pass
    result = dict(status="WRITTEN" if items or empty_daily else "BLOCKED", items=items, failures=failures,
                  bundle_path=bundle_path.relative_to(root).as_posix(), bundle_sha256=bundle_sha,
                  watch_source_scope=scope, action="no_order")
    _write(archive / "refresh.json", result)
    if items or empty_daily:
        if hashlib.sha256(source.read_bytes()).hexdigest() != watch_source_sha256:
            raise ValueError("Watch source changed during refresh")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(".current-price-conditions-" + uuid4().hex + ".json")
        try:
            _write(temporary, registry)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return result
