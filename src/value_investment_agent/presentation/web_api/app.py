"""Hash-bound, read-only projections of the current published product."""
from __future__ import annotations

import json
import hashlib
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Depends, Query
from typing import Literal
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from ...application.product.daily_public_packet import (
    SCHEMA_VERSION as PACKET_SCHEMA,
    build_daily_public_packet,
    count_formal_admissions,
    publication_block,
    publication_block_unavailable,
    unavailable_packet,
)
from ...application.product.daily_research_status import build_daily_research_status
from ...application.product.dual_sleeve_risk import run_dual_sleeve_review
from ...application.product.publication_chain import (
    STRUCTURE_ERRORS as _STRUCTURE_ERRORS,
    bound_object as _bound,
    load_current_chain as _current,
)
from ...application.product.public_snapshot import (
    load_current_packet as _load_snapshot,
)
from ...application.product.public_snapshot import (
    snapshot_metadata as _snapshot_metadata,
)
from ...application.product.public_snapshot import (
    workbook_version_report as _workbook_report,
)
from ...application.product.quote_bridge import execute_quote_bridge_for_symbol
from ...application.product.research_draft import load_current_research_draft
from ...application.product.research_funnel_status import research_funnel_status
from ...application.hotspot.price_action_case import project_price_action_plan
from ...application.hotspot.independent_price_conditions import (
    load_independent_price_conditions,
    project_independent_price_condition,
    project_independent_price_conditions,
)
from ...application.decision.current_value_plan import revalidate_current_value_plan
from ...application.decision.value_action_plan import CoreValuePublicReviews
from ...application.decision.strategy_readiness import attach_strategy_readiness
from ...infrastructure.hotspot.sina_price_case import load_historical_case
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from ..read_models.dual_sleeve_surface import (
    BLOCKER_SURFACE_INVALID,
    build_dual_sleeve_surface,
    unavailable as dual_sleeve_unavailable,
)
from ..read_models.research_history import build_research_history
from ..read_models.value_decision_detail import project_value_decision_detail
from ...application.decision.public_strategy_assessment import project_strategy_decision, summarize_actionable_evaluations, project_actionable_evaluation
from .local_auth import (
    BOOTSTRAP_ENV,
    SESSION_HEADER,
    SESSION_TTL_SECONDS,
    LocalAuthorizationError,
    LocalOperatorSession,
    authorize,
)
from .private_routes import portfolio_connection, register_private_routes
from .condition_alert_routes import register_condition_alert_routes
from .agent_research_routes import register_agent_research_routes
from .simulated_journey_routes import register_simulated_journey_routes
from .dual_simulated_journey_routes import register_dual_simulated_journey_routes
from .simulated_portfolio_routes import register_simulated_portfolio_routes
from .source_native_economic_routes import register_source_native_economic_routes
from .runtime_identity import data_freshness, git_head, publication_registry_status, runtime_identity, sha256
from .value_policy_routes import register_value_policy_routes
from ...application.decision.value_policy_interaction import (
    ValuePolicyInteractionService, PolicyPrincipal, PERMISSION,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PORT = 8001
_ID = re.compile(r"[0-9]{6}\Z")
_UNAVAILABLE_RESEARCH = {"schema_version": "daily-research-status-v1", "action": "no_order",
                         "status": "UNAVAILABLE", "registered_count": 0, "rows": [],
                         "blockers": ["RESEARCH_STATUS_UNAVAILABLE"]}


def _public(root: Path) -> dict | None:
    try:
        return _current(root)
    except _STRUCTURE_ERRORS:
        return None


def _publication_block(root: Path, current: dict | None) -> dict:
    """The compact identity block every public endpoint must share (TL9 MVP-1)."""
    if current is None:
        return publication_block_unavailable()
    try:
        return publication_block(root, current)
    except _STRUCTURE_ERRORS:
        return publication_block_unavailable()


def _binding_path(model: dict, role: str) -> str | None:
    """Name the artifact a failure came from, without reading it again."""
    binding = (model.get("product_extensions") or {}).get(role)
    if isinstance(binding, dict) and isinstance(binding.get("path"), str):
        return binding["path"]
    return None


def _unavailable(code: str, reason: str, *, source: str | None = None) -> dict:
    """Fail closed on a broken publication chain without inventing any count."""
    body = {"action": "no_order", "status": "UNAVAILABLE", "as_of": None,
            "market": {"status": "UNKNOWN", "reason": reason},
            "summary": {"universe_count": None, "formal_count": 0, "watch_count": None},
            "sections": {"holdings": [], "value": [], "hotspot": []},
            "research": dict(_UNAVAILABLE_RESEARCH),
            "dual_sleeve": dual_sleeve_unavailable(),
            "publication": publication_block_unavailable(),
            "blockers": [code], "gate_code": code, "reason": reason}
    if source is not None:
        body["publication_source"] = source
    return body


def _pick(value: dict, *keys: str) -> dict:
    return {key: value[key] for key in keys if key in value}


def _quote_bridge_execution(root: Path, symbol: str) -> dict | None:
    """Execute the registered price bridge; a broken registration degrades, never raises."""
    try:
        return execute_quote_bridge_for_symbol(root, symbol, today=datetime.now(timezone.utc))
    except _STRUCTURE_ERRORS:
        return None


def _daily_research(root: Path, names: dict[str, str]) -> dict:
    """Compose the registered research/close status; a broken chain degrades, never raises."""
    try:
        return build_daily_research_status(root, today=datetime.now(timezone.utc), names=names)
    except _STRUCTURE_ERRORS:
        return dict(_UNAVAILABLE_RESEARCH)


def _item(row: dict, as_of: str, status: str = "RESEARCH_ONLY") -> dict:
    symbol = row["symbol"]
    return {"id": symbol, "symbol": symbol, "name": row.get("company_name", symbol),
            "strategy": "value", "status": status, "candidate_action": "no_order",
            "reason": row.get("why_now") or row.get("next_trigger") or "研究证据仍待复核",
            "as_of": as_of}


def _queue_item(row: dict, as_of: str) -> dict:
    reasons = row.get("screening_reasons", [])
    item = _item(row, as_of)
    item["reason"] = reasons[0] if isinstance(reasons, list) and reasons and isinstance(reasons[0], str) else "待完成数据核验"
    item["why_selected"] = item["reason"]
    item["channels"] = [part for part in row.get("channels", []) if isinstance(part, str)]
    item["blockers"] = [part for part in row.get("gaps", []) if isinstance(part, str)]
    return item


_EXPLANATION_FIELDS = ("support", "counter_evidence", "thesis_breakers", "blockers",
                       "price_context", "next_events")


def _attach_value_explanations(root: Path, model: dict, items: list[dict]) -> list[dict]:
    """Copy bound value explanations onto list rows without hiding a broken binding."""
    explanations: dict[str, dict] = {}
    unreadable: set[str] = set()
    for binding in model.get("additional_evidence_bindings", []):
        if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
            continue
        if not binding["path"].endswith("-value-decision-explanation.json"):
            continue
        symbol = Path(binding["path"]).name.partition("-")[0]
        if not _ID.fullmatch(symbol):
            continue
        try:
            explanation = _bound(root, binding)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
            unreadable.add(symbol)
            continue
        if (explanation.get("schema_version") == "public-value-decision-explanation-v1"
                and explanation.get("symbol") == symbol and explanation.get("action") == "no_order"):
            explanations[symbol] = explanation
        else:
            unreadable.add(symbol)
    for item in items:
        symbol = str(item.get("id", ""))
        explanation = explanations.get(symbol)
        if explanation is not None:
            item.update(_pick(explanation, *_EXPLANATION_FIELDS))
        if symbol in unreadable:
            item["blockers"] = [*(item.get("blockers") or []), "VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
    return items


def _default_port() -> int:
    raw = os.environ.get("VALUE_INVESTMENT_WEB_PORT", "")
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_PORT


def create_app(
    root: Path | None = None,
    *,
    port: int | None = None,
    session_ttl_seconds: float = SESSION_TTL_SECONDS,
    bootstrap_secret: str | None = None,
    value_policy_service: ValuePolicyInteractionService | None = None,
) -> FastAPI:
    # Root injection is for in-process tests; no HTTP parameter or environment override exists.
    project = (root or ROOT).resolve()
    backend_module = Path(__file__).resolve()
    backend_head = git_head(project)
    backend_module_sha = sha256(backend_module)
    bound_port = port if port is not None else _default_port()
    # The launcher exports a per-run secret; without one the workbench stays
    # locked, so an accidentally exposed process never serves the private API.
    secret = bootstrap_secret if bootstrap_secret is not None else os.environ.get(BOOTSTRAP_ENV)
    sessions = LocalOperatorSession(bootstrap_secret=secret, ttl_seconds=session_ttl_seconds)
    api = FastAPI(title="Value Investment Read API")

    def current_items(packet, *, active_only=False):
        rows = (packet or {}).get("price_conditions", {}).get("items", [])
        registry = (packet or {}).get("identity_inputs", {}).get("current_price_conditions")
        registry_matches = True
        if registry is not None:
            try:
                observed = hashlib.sha256((project / "config/current-price-conditions.json").read_bytes()).hexdigest()
                registry_matches = observed == registry["observed_sha256"]
            except (OSError, KeyError, TypeError):
                registry_matches = False
        checked = []
        for row in rows:
            plan = row["price_action_plan"]
            if active_only and plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY":
                continue
            try:
                if not registry_matches:
                    raise ValueError("Current price registry differs from frozen publication")
                load_current_price_case(root=project, symbol=row["symbol"],
                    case_path=Path(plan["case_path"]), expected_sha256=plan["case_sha256"])
                if plan.get("daily_selection_binding"):
                    from ...application.hotspot.daily_selection import verify_daily_selection
                    binding = plan["daily_selection_binding"]
                    target = (project / binding["path"]).resolve()
                    if not target.is_relative_to(project / "runtime") or hashlib.sha256(target.read_bytes()).hexdigest() != binding["sha256"]:
                        raise ValueError("Daily selection changed")
                    selection = json.loads(target.read_bytes())
                    verify_daily_selection(project, selection)
                    members = selection.get("candidate_pool", []) + selection["observation_list"]
                    selected = next(r for r in members if r["symbol"] == row["symbol"])
                    if selected != plan["daily_selection"]:
                        raise ValueError("Frozen selection differs from original")
                checked.append(row)
            except (ValueError, OSError, KeyError, TypeError, StopIteration, ArithmeticError) as error:
                stale = "B1 current close rejected" in str(error)
                checked.append({**row, "price_action_plan": {**plan,
                    "signal_state": "STALE" if stale else "BLOCKED",
                    "action_eligibility": False, "formal_eligibility": False,
                    "portfolio_eligibility": None, "action_intent": "WATCH", "entry_trigger_price": None,
                    "invalidation_price": None, "current_reference_price": None,
                    "entry_condition": None, "exit_condition": None, "invalidation_condition": None,
                    "price_behavior": None, "risk_reward_ratio": None,
                    "levels": {}, "current_reference_close": None,
                    "blockers": [*plan["blockers"], "CURRENT_CASE_CHANGED_OR_STALE"],
                    "explanation": "本次读取无法验证价格条件的新鲜度或原始证据；旧价位不作为当前条件。"}})
        return checked

    def core_public_reviews():
        with CoreValuePublicReviews(project, now=datetime.now(timezone.utc)) as reviews:
            yield reviews

    def value_plan(symbol, packet, public_reviews=None):
        frozen = (packet or {}).get("value_price_conditions", {}).get(symbol)
        options = {'public_reviews': public_reviews} if public_reviews is not None else {}
        now = public_reviews.now if public_reviews is not None else datetime.now(timezone.utc)
        return revalidate_current_value_plan(project, frozen, now=now, **options) if frozen else None

    def value_plan_matches_research(plan, analysis=None):
        """A displayed price plan must bind its own current research version."""
        current_analysis = analysis if isinstance(analysis, dict) else plan.get(
            "research_analysis")
        if not isinstance(current_analysis, dict):
            return True
        return (plan.get("valuation_input_version") ==
                    current_analysis.get("input_descriptor_sha256")
                and plan.get("research_version") ==
                    current_analysis.get("research_version"))

    def pinned_publication(packet, current):
        if packet is None:
            return _publication_block(project, current)
        return {"action": "no_order", "packet_status": "CURRENT", "snapshot_status": "VERIFIED",
                "publication_id": packet["publication_id"],
                "research_version": packet.get("research_version"),
                "generated_at": packet.get("generated_at"),
                "engine_version": packet.get("engine_version")}

    def chain_matches_packet(packet, current):
        bindings = (packet or {}).get("identity_inputs", {}).get("chain")
        if bindings is None:
            return True
        observed = [{"role": row["role"], "path": row["path"], "sha256": row["sha256"]}
                    for row in sorted(current["bindings"], key=lambda row: str(row["role"]))]
        return bindings == observed

    def current_item(row):
        plan = row["price_action_plan"]
        return {"id": plan["decision_id"], "symbol": row["symbol"],
                "name": row["company_name"], "company_name": row["company_name"],
                "strategy": "hotspot", "status": plan["signal_state"],
                "action": "no_order", "as_of": plan["market_trade_date"],
                "reason": plan["explanation"], "blockers": plan["blockers"],
                "why_selected": plan.get("watch_reason"),
                "price_action_plan": plan}

    @api.get("/api/v1/current-price-case/{symbol}")
    def current_price_case(symbol: str):
        packet, _ = _load_snapshot(project)
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "PUBLICATION_VERSION_MISMATCH"}
        row = next((row for row in current_items(packet) if row["symbol"] == symbol), None)
        if row is None:
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "CURRENT_CASE_NOT_PUBLISHED"}
        plan = row["price_action_plan"]
        if plan["signal_state"] in ("BLOCKED", "STALE"):
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "CURRENT_CASE_CHANGED_OR_STALE"}
        try:
            case = load_current_price_case(root=project, symbol=symbol,
                case_path=Path(plan["case_path"]), expected_sha256=plan["case_sha256"])
            return {**case, "price_action_plan": plan}
        except (ValueError, OSError, KeyError, TypeError):
            return {"action": "no_order", "status": "UNAVAILABLE", "reason": "CURRENT_CASE_CHANGED_OR_STALE"}

    @api.get("/api/v1/historical-price-case/{symbol}/{trade_date}")
    def historical_price_case(symbol: str, trade_date: str):
        if not _ID.fullmatch(symbol):
            return {"action": "no_order", "status": "UNAVAILABLE",
                    "reason": "INVALID_SYMBOL"}
        try:
            requested_date = date.fromisoformat(trade_date)
            case = load_historical_case(root=project, symbol=symbol,
                                        as_of=requested_date)
            return {**case, "price_action_plan": project_price_action_plan(case)}
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
            return {"action": "no_order", "status": "UNAVAILABLE",
                    "reason": "HISTORICAL_SOURCE_OR_CALCULATION_UNAVAILABLE"}

    @api.get("/api/v1/historical-price-cases")
    def historical_price_cases():
        base = project / "runtime" / "hotspot-price-cases"
        items = []
        if base.is_dir():
            for folder in sorted(base.iterdir(), reverse=True):
                if len(items) >= 10:
                    break
                match = re.fullmatch(r"([0-9]{6})-([0-9]{4}-[0-9]{2}-[0-9]{2})", folder.name)
                if not match or not folder.is_dir():
                    continue
                try:
                    case = load_historical_case(root=project, symbol=match[1],
                                                as_of=date.fromisoformat(match[2]))
                except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
                    continue
                items.append({"symbol": case["symbol"], "market_trade_date": case["market_trade_date"],
                              "reference_price": case["current_reference_price"],
                              "levels": case["levels"], "signal_state": case["signal_state"],
                              "blockers": case["blockers"]})
        return {"action": "no_order", "status": "HISTORICAL_NOT_CURRENT", "items": items}

    @api.get("/api/v1/independent-hotspot-conditions")
    def independent_hotspot_conditions():
        packet, _ = _load_snapshot(project)
        current = _public(project)
        return independent_hotspot_for_publication(packet, current)

    def independent_hotspot_for_publication(packet, current):
        if packet is None or current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "items": [],
                    "reason": "PUBLICATION_VERSION_MISMATCH"}
        try:
            output = load_independent_price_conditions(project, now=datetime.now(timezone.utc),
                research_version=packet.get("research_version"))
            # Retired observations remain in historical/detail views, never in
            # today's independent opportunity list.
            output["items"] = [row for row in output.get("items", [])
                if row["price_action_plan"].get("candidate_lifecycle")
                != "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"]
            published = {row["symbol"]: row["price_action_plan"]
                         for row in current_items(packet, active_only=True)}
            accepted, gaps = [], list(output.get("blockers", []))
            if output.get("status") in {"BLOCKED", "NOT_CONNECTED"} and not gaps:
                gaps.append("INDEPENDENT_HOTSPOT_EVIDENCE_UNAVAILABLE")
            for row in output.get("items", []):
                old = published.get(row["symbol"], {})
                plan = row["price_action_plan"]
                if (old.get("signal_state") in {"STALE", "BLOCKED"} or not old
                        or any(old.get(key) != plan.get(key) for key in ("case_path", "case_sha256"))):
                    gaps.append("CURRENT_HOTSPOT_PLAN_UNAVAILABLE:" + row["symbol"])
                    continue
                accepted.append(row)
            output["items"] = accepted
            if gaps:
                output["blockers"] = list(dict.fromkeys(gaps))
                output["status"] = "PARTIAL" if accepted else "UNAVAILABLE"
                output["reason"] = "INDEPENDENT_HOTSPOT_EVIDENCE_UNAVAILABLE"
            output["publication"] = pinned_publication(packet, current)
            output["decision_views"] = [project_strategy_decision(row["price_action_plan"],
                symbol=row["symbol"]) for row in output.get("items", [])]
            return output
        except (ValueError, OSError, KeyError, TypeError):
            return {"action": "no_order", "status": "UNAVAILABLE", "items": [],
                    "reason": "INDEPENDENT_HOTSPOT_EVIDENCE_UNAVAILABLE"}

    @api.get("/api/v1/strategy-decisions")
    def strategy_decisions():
        packet, _ = _load_snapshot(project)
        current = _public(project)
        if packet is None or current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "items": []}
        # Both sleeves consume one verified publication. Failure of a sibling
        # branch cannot suppress the independently verified value plans.
        hotspot = independent_hotspot_for_publication(packet, current)
        values, gaps = [], []
        if hotspot.get("status") in {"UNAVAILABLE", "PARTIAL"}:
            gaps.extend(hotspot.get("blockers") or ["INDEPENDENT_HOTSPOT_EVIDENCE_UNAVAILABLE"])
        for symbol in (packet or {}).get("value_price_conditions", {}):
            try:
                plan = value_plan(symbol, packet)
                values.append(project_strategy_decision(plan, symbol=symbol))
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
                gaps.append("VALUE_PLAN_UNAVAILABLE:" + symbol)
        items = [*values, *hotspot.get("decision_views", [])]
        status = ("PARTIAL" if items else "UNAVAILABLE") if gaps else "CONDITIONAL_REVIEW_ONLY"
        return {"action": "no_order", "status": status,
            "publication": pinned_publication(packet, current),
            "items": items, "blockers": gaps}

    @api.get("/api/v1/daily-decisions")
    def daily_decisions(core_reviews: CoreValuePublicReviews = Depends(core_public_reviews)):
        packet, _ = _load_snapshot(project)
        empty = {"action": "no_order", "status": "UNAVAILABLE", "as_of": None,
                 "market": {"status": "UNKNOWN", "reason": "PUBLICATION_UNAVAILABLE"},
                 "summary": {"universe_count": None, "formal_count": 0, "watch_count": None},
                 "sections": {"holdings": [], "value": [], "hotspot": []},
                 "research": dict(_UNAVAILABLE_RESEARCH),
                 "dual_sleeve": dual_sleeve_unavailable(),
                 "publication": publication_block_unavailable(),
                 "blockers": ["PUBLICATION_UNAVAILABLE"],
                 "gate_code": "PUBLICATION_UNAVAILABLE", "reason": "PUBLICATION_UNAVAILABLE"}
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return empty
        state, model = current["state"], current["model"]
        extensions = state["content"].get("extensions", {})
        snapshot = model.get("snapshot", {})
        if not isinstance(extensions, dict) or not isinstance(snapshot, dict) or snapshot.get("action") != "no_order":
            return empty
        discovery = extensions.get("value_discovery_report", {})
        quality = extensions.get("m2_quality_diagnostic", {})
        market = extensions.get("market_regime_observation", {})
        hotspot = extensions.get("hotspot_watch_queue", {})
        queue = extensions.get("value_research_queue", {})
        if (discovery.get("status") != "RESEARCH_LEADS_ONLY" or
                quality.get("schema_version") != "m2-quality-diagnostic-v1" or
                market.get("schema_version") != "market-regime-observation-v1" or
                hotspot.get("schema_version") != "hotspot-watch-queue-v1" or
                queue.get("schema_version") != "value-research-queue-v1" or
                queue.get("admission") != "RESEARCH_QUEUE_ONLY"):
            return empty
        # The dual-sleeve section restates only a formally bound review. An
        # older publication without the binding gets the shared not-connected
        # result instead of an invented portfolio, and a malformed report
        # fails closed alone so the research page keeps answering.
        dual_report = extensions.get("dual_sleeve_report")
        try:
            if dual_report is None:
                dual_report = run_dual_sleeve_review(
                    root=project, generated_at=datetime.now(timezone.utc))
                dual_sleeve = build_dual_sleeve_surface(dual_report)
            else:
                dual_sleeve = build_dual_sleeve_surface(
                    dual_report, source=_binding_path(model, "dual_sleeve_report"))
        except _STRUCTURE_ERRORS:
            dual_sleeve = dual_sleeve_unavailable(BLOCKER_SURFACE_INVALID)
        leads = discovery.get("lead_symbols", [])
        if not isinstance(leads, list):
            return empty
        report_source = _binding_path(model, "value_discovery_report")
        try:
            report = _bound(project, model["product_extensions"]["value_discovery_report"])
        except _STRUCTURE_ERRORS:
            return _unavailable("VALUE_DISCOVERY_REPORT_BINDING_UNAVAILABLE",
                                "VALUE_DISCOVERY_REPORT_UNAVAILABLE", source=report_source)
        try:
            receipt = _bound(project, report["receipt_binding"])
        except _STRUCTURE_ERRORS:
            binding = report.get("receipt_binding")
            source = binding.get("path") if isinstance(binding, dict) else None
            return _unavailable("VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE",
                                "VALUE_DISCOVERY_RECEIPT_UNAVAILABLE",
                                source=source if isinstance(source, str) else report_source)
        universe = receipt.get("universe")
        records = universe.get("records") if isinstance(universe, dict) else None
        if (receipt.get("schema_version") != "m2-opportunity-discovery-v2"
                or not isinstance(records, list)):
            return _unavailable("VALUE_DISCOVERY_UNIVERSE_UNAVAILABLE",
                                "VALUE_DISCOVERY_UNIVERSE_UNREADABLE", source=report_source)
        # Counts are published beside the rows they describe; a mismatch means the
        # chain is only half-wired and no number here would be fully true.
        health = report.get("data_health")
        if isinstance(health, dict) and health.get("universe_count") != len(records):
            return _unavailable("VALUE_DISCOVERY_UNIVERSE_INCONSISTENT",
                                "VALUE_DISCOVERY_UNIVERSE_COUNT_MISMATCH", source=report_source)
        if ("deduplicated_lead_count" in report
                and report["deduplicated_lead_count"] != len(leads)):
            return _unavailable("VALUE_DISCOVERY_LEAD_COUNT_INCONSISTENT",
                                "VALUE_DISCOVERY_LEAD_COUNT_MISMATCH", source=report_source)
        symbols = {row["symbol"] for row in records
                   if isinstance(row, dict) and isinstance(row.get("symbol"), str)}
        if symbols and any(lead not in symbols for lead in leads if isinstance(lead, str)):
            return _unavailable("VALUE_DISCOVERY_LEAD_NOT_IN_UNIVERSE",
                                "VALUE_DISCOVERY_LEAD_UNIVERSE_MISMATCH", source=report_source)
        companies = snapshot.get("companies", [])
        as_of = queue.get("as_of") or snapshot.get("as_of")
        pending_symbols = {c.get("symbol") for c in snapshot.get("opportunities", [])
                           if isinstance(c, dict) and c.get("valuation_status", {}).get("code") == "NOT_READY"}
        value = [_item(c, as_of, "PENDING_RESEARCH" if c.get("symbol") in pending_symbols else "RESEARCH_ONLY")
                 for c in companies if isinstance(c, dict)
                 and c.get("action") == "no_order" and _ID.fullmatch(str(c.get("symbol", "")))]
        known = {c.get("symbol") for c in value}
        value.extend(_item(c, as_of, "PENDING_RESEARCH") for c in snapshot.get("opportunities", [])
                     if isinstance(c, dict) and c.get("action") == "no_order"
                     and _ID.fullmatch(str(c.get("symbol", ""))) and c["symbol"] not in known)
        value = _attach_value_explanations(project, model, value)
        for item in value:
            plan = value_plan(item["symbol"], packet, core_reviews)
            if plan is not None and value_plan_matches_research(plan):
                item["price_action_plan"] = plan
            elif plan is not None:
                item["blockers"] = [*(item.get("blockers") or []),
                    "CURRENT_VALUE_PLAN_NOT_BOUND_TO_LATEST_RESEARCH"]
        known = {c["symbol"] for c in value}
        value.extend(_queue_item(c, as_of) for c in queue.get("entries", [])
                     if isinstance(c, dict) and c.get("queue_status") == "SELECTED_FOR_DATA_CHECK"
                     and _ID.fullmatch(str(c.get("symbol", ""))) and c["symbol"] not in known)
        named = [*(companies if isinstance(companies, list) else []),
                 *snapshot.get("opportunities", []),
                 *queue.get("entries", [])]
        names = {row["symbol"]: str(row.get("company_name")) for row in named
                 if isinstance(row, dict) and isinstance(row.get("symbol"), str)
                 and isinstance(row.get("company_name"), str)}
        # Formal admissions are counted from the published rows themselves; no row
        # carries an admitted valuation status yet, so the count stays derived, not fixed.
        formal_count = count_formal_admissions(named)
        hotspot_rows = project_independent_price_conditions(project,
            items=current_items(packet, active_only=True), now=datetime.now(timezone.utc))["items"]
        hotspot_items = [current_item(row) for row in hotspot_rows]
        if "price_conditions" not in (packet or {}):
            hotspot_items = [
            dict(_item(c, as_of, "UNKNOWN"), strategy="hotspot")
            for c in hotspot.get("items", []) if isinstance(c, dict)
            and c.get("action") == "no_order" and _ID.fullmatch(str(c.get("symbol", "")))]
        return {"action": "no_order", "status": "RESEARCH_OBSERVATION",
                "actionable_evaluation": attach_strategy_readiness(
                    summarize_actionable_evaluations([*value, *hotspot_items],
                        core_reviews=core_reviews, now=core_reviews.now),
                    [*value, *hotspot_items], packet),
                "as_of": as_of,
                "market": _pick(market, "status", "reason"),
                "summary": {"universe_count": len(records),
                            "formal_count": formal_count,
                            "watch_count": len(leads)},
                "research": _daily_research(project, names),
                "dual_sleeve": dual_sleeve,
                "publication": pinned_publication(packet, current),
                "sections": {"holdings": [], "value": value,
                             "hotspot": hotspot_items},
                # The public packet never claims anything about the private ledger;
                # private connection state is owned by the authorized private routes.
                "blockers": ["NO_FORMAL_ADMISSION"]}

    @api.get("/api/v1/decisions/{decision_id}")
    def decision(decision_id: str, independent_hotspot: bool = False,
                 strategy: Literal['value', 'hotspot'] | None = None,
                 core_reviews: CoreValuePublicReviews = Depends(core_public_reviews)):
        def new_candidate_detail():
            if not _ID.fullmatch(decision_id):
                return None
            from ...application.research.value_research_analysis import (
                load_current_value_research_analysis,
            )
            try:
                analysis = load_current_value_research_analysis(
                    root=project, symbol=decision_id, now=datetime.now(timezone.utc)
                )
            except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
                # The loader returns None when no candidate/replay registration
                # exists.  Any exception therefore means one of its supported
                # current registries or bound artifacts is invalid.  Never
                # reimplement only one registry here or fall through to an old
                # publication after a workflow/replay registration breaks.
                return {
                    "action": "no_order",
                    "status": "UNAVAILABLE",
                    "decision": None,
                    "publication": publication_block_unavailable(),
                    "reason": "CURRENT_RESEARCH_CANDIDATE_UNAVAILABLE",
                    "formal_eligibility": False,
                }
            if analysis is not None:
                decision = {
                    "id": decision_id,
                    "symbol": decision_id,
                    "name": analysis.get("company_name") or decision_id,
                    "company_name": analysis.get("company_name") or decision_id,
                    "strategy": "CORE_VALUE",
                    "status": "RESEARCH_ONLY",
                    "action": "no_order",
                    "as_of": analysis.get("research_as_of"),
                    "reason": analysis.get("thesis") or "已形成未批准的条件研究估值。",
                    "blockers": analysis.get("blockers", []),
                    "research_analysis": analysis,
                }
                return {
                    "action": "no_order",
                    "status": "RESEARCH_ONLY",
                    "decision": decision,
                    "review_replay": {
                        "status": "VERIFIED_NEW_INPUT_CANDIDATE",
                        "symbol": decision_id,
                        "action": "no_order",
                        "formal_eligibility": False,
                        "approval_changed": False,
                        "research_admitted": False,
                        "price_admitted": False,
                        "research_as_of": analysis.get("research_as_of"),
                        "prepared_at": analysis.get("computed_at"),
                        "scope": "UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY",
                        "next_url": "#conditional-research-analysis",
                    },
                    "publication": publication_block_unavailable(),
                    "formal_eligibility": False,
                }
            from ...application.discovery.value_candidate_selection import load_current_public_candidate_research
            detail = load_current_public_candidate_research(root=project, symbol=decision_id,
                now=datetime.now(timezone.utc))
            if detail is None:
                return None
            row = detail['candidate']
            item = _queue_item(dict(row, gaps=row['blockers'], screening_reasons=[
                '已自动取得官方原件并核验财务事实；企业质量、估值和投资资格仍待完成。']), detail['as_of'])
            return dict(action='no_order', status='RESEARCH_ONLY', decision=item,
                financial_progress=detail['financial_progress'], public_candidate_research=detail,
                publication=publication_block_unavailable(), formal_eligibility=False)

        if strategy is not None:
            if strategy == 'value':
                researched = new_candidate_detail()
                if researched is not None:
                    return researched
                draft = load_current_research_draft(project, decision_id)
                if draft is not None:
                    return dict(action='no_order', status='RESEARCH_ONLY',
                        decision=dict(id=decision_id, symbol=decision_id,
                            name=draft.get('company_name') or decision_id, strategy='CORE_VALUE',
                            status='RESEARCH_ONLY', action='no_order'), research_draft=draft,
                        publication=publication_block_unavailable(), formal_eligibility=False)
            from ...application.discovery.dual_strategy_selection import build_dual_strategy_selection
            lanes = build_dual_strategy_selection(root=project, now=datetime.now(timezone.utc),
                limit=50, q_value=decision_id if strategy == 'value' else '',
                q_hotspot=decision_id if strategy == 'hotspot' else '',
                **({'value_selector': lambda **kw: dict(action='no_order', items=[])}
                   if strategy == 'hotspot' else
                   {'hotspot_selector': lambda **kw: dict(action='no_order', items=[])}))
            lane = lanes[strategy]
            row = next((r for r in lane['items'] if r.get('symbol') == decision_id), None)
            if row is None:
                return dict(action='no_order', status='UNAVAILABLE', decision=None,
                    reason='SELECTION_CANDIDATE_UNAVAILABLE', formal_eligibility=False)
            candidate = dict(row)
            for key in ('quote_date', 'trade_date'):
                candidate.setdefault(key, lane.get(key))
            item = dict(id=decision_id, symbol=decision_id,
                name=row.get('name') or row.get('company_name') or decision_id,
                strategy='CORE_VALUE' if strategy == 'value' else 'HOTSPOT_SATELLITE',
                status='RESEARCH_ONLY', action='no_order',
                as_of=candidate.get('quote_date') or candidate.get('trade_date'),
                blockers=row.get('blockers', []), selection_candidate=candidate,
                formal_eligibility=False, trade_eligible=False)
            sample = {}
            if strategy == 'hotspot':
                from ...application.hotspot.replay_read_model import load_symbol_retained_replay
                sample['hotspot_sample_review'] = load_symbol_retained_replay(
                    root=project, symbol=decision_id, now=datetime.now(timezone.utc))
            return dict(action='no_order', status='RESEARCH_ONLY', decision=item,
                selection_candidate=candidate, formal_eligibility=False, trade_eligible=False,
                publication=publication_block_unavailable(), **sample)

        packet, _ = _load_snapshot(project)
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            independent = new_candidate_detail()
            if independent is not None:
                return independent
            return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                    "publication": publication_block_unavailable(),
                    "reason": "PUBLICATION_VERSION_MISMATCH"}
        if decision_id.startswith("hotspot-"):
            row = next((row for row in current_items(packet)
                        if row["price_action_plan"]["decision_id"] == decision_id), None)
            if row is not None and independent_hotspot:
                row = {**row, "price_action_plan": project_independent_price_condition(
                    project, symbol=row["symbol"], plan=row["price_action_plan"],
                    now=datetime.now(timezone.utc))}
            from ...application.product.hotspot_lifecycle_surface import current_hotspot_lifecycle
            lifecycle = current_hotspot_lifecycle(root=project, symbol=row["symbol"],
                plan=row["price_action_plan"], now=datetime.now(timezone.utc)) if row else None
            return {"action": "no_order", "status": "CURRENT_OBSERVATION" if row else "NOT_FOUND",
                    "publication": pinned_publication(packet, current),
                    "hotspot_lifecycle_review": lifecycle,
                    "decision": current_item(row) if row else None}
        if not _ID.fullmatch(decision_id):
            return {"action": "no_order", "status": "NOT_FOUND", "decision": None, "reason": "UNKNOWN_DECISION"}
        current = _public(project)
        if current is None or not chain_matches_packet(packet, current):
            return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                    "publication": _publication_block(project, current),
                    "reason": "PUBLICATION_UNAVAILABLE"}
        model = current["model"]
        published = model.get("snapshot") if isinstance(model.get("snapshot"), dict) else {}

        def with_research_draft(payload: dict) -> dict:
            if isinstance(payload.get('decision'), dict):
                payload['strategy_evaluation'] = project_actionable_evaluation(
                    payload['decision'], core_reviews=core_reviews, now=core_reviews.now)
            draft = load_current_research_draft(project, decision_id)
            if draft is not None:
                payload["research_draft"] = draft
            from ...application.research.value_enrichment_batch import read_verified_enrichment_progress
            payload["financial_progress"] = read_verified_enrichment_progress(
                root=project, symbol=decision_id, evaluation_at=datetime.now(timezone.utc))
            from ...application.product.pending_candidate_supplement import load_current_pending_candidate_supplement
            try:
                supplement = load_current_pending_candidate_supplement(root=project, symbol=decision_id)
                if supplement is not None:
                    candidate = supplement["candidate"]
                    from ...application.product.economic_review_materials import project_product_continuation_review
                    continuation = project_product_continuation_review(
                        root=project, supplement=supplement, now=datetime.now(timezone.utc))
                    if continuation is not None:
                        payload['product_continuation_candidate'] = continuation
                    payload["review_replay"] = dict(status="VERIFIED_NEW_INPUT_CANDIDATE",
                        symbol=decision_id, action="no_order", formal_eligibility=False,
                        approval_changed=False, research_admitted=False, price_admitted=False,
                        research_as_of=candidate["candidate_research_as_of"],
                        prepared_at=candidate["generated_at"],
                        candidate_binding=supplement["candidate_binding"],
                        scope=supplement["scope"], next_url="#value-review-handoff")
                    if candidate.get("valuation_basis_scope") == "EX_POST_PRIOR_COMPLETED_SESSION":
                        payload["review_replay"].update(
                            valuation_basis_scope=candidate["valuation_basis_scope"],
                            valuation_basis_date=candidate["valuation_basis_date"])
                    return payload
            except (ValueError, OSError, KeyError, TypeError):
                payload["review_replay"] = dict(status="SOURCE_UNAVAILABLE", symbol=decision_id,
                    action="no_order", formal_eligibility=False)
                return payload
            from ...application.product.pending_replay_publication import load_current_pending_replay
            try:
                replay = load_current_pending_replay(root=project, symbol=decision_id)
                if replay is not None:
                    candidate = replay["candidate"]
                    payload["review_replay"] = dict(status="VERIFIED_EXACT_INPUT_REPLAY",
                        symbol=decision_id, action="no_order", formal_eligibility=False,
                        approval_changed=False, research_admitted=False, price_admitted=False,
                        research_as_of=candidate["candidate_research_as_of"],
                        replayed_at=candidate["generated_at"],
                        publication_binding=replay["publication_binding"],
                        scope=replay["scope"], next_url="#value-review-handoff")
            except (ValueError, OSError, KeyError, TypeError):
                payload["review_replay"] = dict(status="SOURCE_UNAVAILABLE", symbol=decision_id,
                    action="no_order", formal_eligibility=False)
            return payload

        current_candidate = new_candidate_detail()
        if (current_candidate is not None
                and current_candidate.get("status") == "UNAVAILABLE"):
            # A registered current candidate is authoritative for the current
            # research slot.  Corruption must not fall through to an older
            # published card or frozen price plan.
            return current_candidate
        current_analysis = None
        if (current_candidate is not None
                and current_candidate.get("review_replay", {}).get("status")
                    == "VERIFIED_NEW_INPUT_CANDIDATE"):
            current_analysis = current_candidate["decision"]["research_analysis"]

        for company in published.get("companies", []):
            if isinstance(company, dict) and company.get("symbol") == decision_id and company.get("action") == "no_order":
                pending = any(isinstance(c, dict) and c.get("symbol") == decision_id
                              and c.get("valuation_status", {}).get("code") == "NOT_READY"
                              for c in published.get("opportunities", []))
                status = "PENDING_RESEARCH" if pending else "RESEARCH_ONLY"
                item = _item(company, published.get("as_of"), status)
                binding = next((b for b in model.get("additional_evidence_bindings", [])
                                if isinstance(b, dict) and isinstance(b.get("path"), str)
                                and b["path"].endswith(f"/{decision_id}-value-decision-explanation.json")), None)
                explanation = None
                binding_status = "NOT_BOUND"
                if binding:
                    try:
                        candidate = _bound(project, binding)
                    except _STRUCTURE_ERRORS:
                        binding_status = "UNAVAILABLE"
                    else:
                        if (candidate.get("schema_version") == "public-value-decision-explanation-v1"
                                and candidate.get("symbol") == decision_id
                                and candidate.get("action") == "no_order"):
                            explanation, binding_status = candidate, "VERIFIED"
                        else:
                            binding_status = "UNAVAILABLE"
                if explanation is not None:
                    item.update(_pick(explanation, "candidate_explanation", "support",
                                      "counter_evidence", "thesis_breakers", "blockers",
                                      "price_context", "next_events"))
                    item["reason"] = explanation.get("candidate_explanation") or item["reason"]
                elif binding_status == "UNAVAILABLE":
                    # Keep the verified company card readable, but never present it
                    # as if the bound decision explanation had been read.
                    item["blockers"] = [*(item.get("blockers") or []),
                                        "VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
                item["research"] = project_value_decision_detail(
                    symbol=decision_id, company=company, explanation=explanation,
                    binding_status=binding_status, binding=binding,
                    price_bridge_execution=_quote_bridge_execution(project, decision_id),
                    binding_blockers=(["VALUE_EXPLANATION_BINDING_UNAVAILABLE"]
                                      if binding_status == "UNAVAILABLE" else []))
                plan = value_plan(decision_id, packet, core_reviews)
                if plan is not None:
                    if value_plan_matches_research(plan, current_analysis):
                        item["price_action_plan"] = plan
                    else:
                        item["blockers"] = [*(item.get("blockers") or []),
                            "CURRENT_VALUE_PLAN_NOT_BOUND_TO_LATEST_RESEARCH"]
                if current_analysis is not None:
                    item["research_analysis"] = current_analysis
                response = with_research_draft({"action": "no_order", "status": status,
                                                "publication": pinned_publication(packet, current),
                                                "decision": item})
                if current_analysis is not None:
                    response["review_replay"] = current_candidate["review_replay"]
                    response["formal_eligibility"] = False
                return response
        if current_analysis is not None:
            # A verified current research candidate also outranks an older
            # opportunity/queue row when the symbol has not yet been promoted
            # into the published company list.  Keep the live publication
            # identity, but do not inherit any older price action plan.
            response = with_research_draft(current_candidate)
            response["publication"] = pinned_publication(packet, current)
            response["review_replay"] = current_candidate["review_replay"]
            response["formal_eligibility"] = False
            return response
        for opportunity in published.get("opportunities", []):
            if isinstance(opportunity, dict) and opportunity.get("symbol") == decision_id and opportunity.get("action") == "no_order":
                return with_research_draft({
                    "action": "no_order", "status": "PENDING_RESEARCH",
                    "publication": _publication_block(project, current),
                    "decision": _item(opportunity, published.get("as_of"), "PENDING_RESEARCH")})
        queue_binding = model.get("product_extensions", {}).get("value_research_queue")
        if queue_binding:
            try:
                queue = _bound(project, queue_binding)
            except (OSError, ValueError, KeyError, TypeError):
                return {"action": "no_order", "status": "UNAVAILABLE", "decision": None,
                        "reason": "PUBLICATION_UNAVAILABLE"}
            for entry in queue.get("entries", []):
                if (isinstance(entry, dict) and entry.get("symbol") == decision_id
                        and entry.get("queue_status") == "SELECTED_FOR_DATA_CHECK"):
                    return with_research_draft({
                        "action": "no_order", "status": "RESEARCH_ONLY",
                        "publication": _publication_block(project, current),
                        "decision": _queue_item(entry, queue.get("as_of"))})
        independent = new_candidate_detail()
        if independent is not None:
            return independent
        return {"action": "no_order", "status": "NOT_FOUND", "decision": None,
                "publication": _publication_block(project, current),
                "reason": "UNKNOWN_DECISION"}

    def bound_decisions() -> dict[str, dict]:
        """Every research decision the current publication really binds."""
        current = _public(project)
        decisions: dict[str, dict] = {}
        if current is None:
            return decisions
        model = current["model"]
        for binding in model.get("additional_evidence_bindings", []):
            if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
                continue
            if not binding["path"].endswith("-value-decision-explanation.json"):
                continue
            try:
                explanation = _bound(project, binding)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if (explanation.get("schema_version") == "public-value-decision-explanation-v1"
                    and explanation.get("action") == "no_order"
                    and isinstance(explanation.get("symbol"), str)
                    and isinstance(explanation.get("research_version"), str)):
                decisions[explanation["symbol"]] = {
                    "research_version": explanation["research_version"],
                    "candidate_action": explanation.get("candidate_action"),
                    "decision_cutoff": explanation.get("decision_as_of"),
                    "artifact": binding["path"], "sha256": binding["sha256"]}
        return decisions

    @api.get("/api/v1/daily-update-status")
    def daily_update_status():
        from ...application.product.daily_refresh import read_latest_run
        result = read_latest_run(project)
        return {"action": "no_order", "status": "RECORDED" if result else "NOT_RECORDED", "last_run": result}

    @api.get("/api/v1/strategy-selection")
    def strategy_selection(value_offset: int = Query(0, ge=0),
                           hotspot_offset: int = Query(0, ge=0),
                           limit: int = Query(30, ge=1, le=50),
                           q_value: str = '', q_hotspot: str = ''):
        from ...application.discovery.dual_strategy_selection import build_dual_strategy_selection
        return JSONResponse(build_dual_strategy_selection(root=project,
            now=datetime.now(timezone.utc), limit=limit, value_offset=value_offset,
            hotspot_offset=hotspot_offset, q_value=q_value, q_hotspot=q_hotspot),
            headers={"Cache-Control": "no-store"})

    @api.get("/api/v1/hotspot-replay-review")
    def hotspot_replay_review(symbol: str | None = None):
        if symbol is not None:
            if not re.fullmatch(r"[0-9]{6}", symbol):
                return JSONResponse(status_code=422, content={
                    "action": "no_order", "status": "INVALID_SYMBOL"})
            from ...application.hotspot.replay_read_model import load_symbol_retained_replay
            return JSONResponse(content=load_symbol_retained_replay(
                root=project, symbol=symbol, now=datetime.now(timezone.utc)),
                headers={"Cache-Control": "no-store"})
        from ...application.hotspot.replay_read_model import load_replay_summary
        try:
            pins = json.loads((project / "config/hotspot-replay-review-v1.json").read_bytes())
            if pins.get("action") != "no_order":
                raise ValueError("Invalid review pins")
            result = load_replay_summary(root=project, manifest_sha256=pins["manifest_sha256"],
                                         structure_manifest_sha256=pins["structure_manifest_sha256"])
            if "retained_manifest_binding" in pins:
                from ...application.hotspot.retained_source_replay import load_retained_replay_summary
                retained = load_retained_replay_summary(root=project,
                    manifest_binding=pins["retained_manifest_binding"], now=datetime.now(timezone.utc))
                if (retained.get("namespace") != "ACTUAL" or retained.get("scope") != "DESCRIPTIVE"
                        or retained.get("action") != "no_order" or retained.get("formal_eligibility") is not False
                        or retained.get("trade_count") is not None):
                    raise ValueError("Retained review scope mismatch")
                result["retained_validation"] = retained
                from ...application.hotspot.strategy_execution_replay import build_strategy_execution_replay
                execution = build_strategy_execution_replay(root=project, now=datetime.now(timezone.utc))
                if (execution.get("action") != "no_order" or execution.get("formal_eligibility") is not False
                        or execution.get("strategy_validation") != "NOT_PROVEN"):
                    raise ValueError("Execution experiment cannot grant admission")
                result["execution_validation"] = {
                    key: execution[key] for key in ("schema_version", "evaluated_at", "status",
                        "metrics_scope", "summary", "gaps", "costs", "parameter_fingerprint",
                        "source_fingerprint", "strategy_validation", "formal_eligibility", "action")}
                result["execution_validation"]["case_results"] = [
                    {"symbol": row["symbol"], "cost_multiplier": scenario["cost_multiplier"],
                     "folds": [{key: fold[key] for key in ("fold", "trade_count",
                         "net_pnl_cny", "ending_equity_cny", "maximum_drawdown", "same_fills_gross_return",
                         "total_fees_cny", "total_slippage_cny")} for fold in scenario["folds"]]}
                    for row in execution["results"] for scenario in row["scenarios"]]
            if "historical_action_observation_binding" in pins:
                from ...application.product.historical_action_lineage import load_historical_action_lineage
                try:
                    result['historical_action_lineage'] = load_historical_action_lineage(root=project,
                        observation_binding=pins['historical_action_observation_binding'], now=datetime.now(timezone.utc))
                except (ValueError, OSError, KeyError, TypeError):
                    result['historical_action_lineage'] = dict(action='no_order', status='UNAVAILABLE',
                        reason='OFFICIAL_LINEAGE_SOURCES_NOT_VERIFIED', formal_eligibility=False)
            if "simulated_hotspot_lifecycle_receipt_binding" in pins:
                from ...application.hotspot.simulated_lifecycle import load_simulated_hotspot_lifecycle
                try:
                    result['simulated_hotspot_lifecycle'] = load_simulated_hotspot_lifecycle(project,
                        pins['simulated_hotspot_lifecycle_receipt_binding'], datetime.now(timezone.utc))
                except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
                    result['simulated_hotspot_lifecycle'] = dict(action='no_order', status='UNAVAILABLE',
                        reason='SIMULATED_LIFECYCLE_SOURCES_NOT_VERIFIED', formal_eligibility=False)
            return result
        except (ValueError, OSError, KeyError, TypeError):
            return JSONResponse(status_code=409, content={
                "action": "no_order", "status": "REPLAY_UNAVAILABLE"})

    @api.get("/api/v1/value-policy-review/{symbol}")
    def value_policy_review(symbol: str):
        from ...application.decision.value_price_policy import load_value_policy_review
        try:
            review = load_value_policy_review(project, symbol, datetime.now(timezone.utc))
            return {"action": "no_order", "status": "RESEARCH_ONLY", **review}
        except (ValueError, OSError):
            return JSONResponse(status_code=409, content={
                "action": "no_order", "status": "REVIEW_UNAVAILABLE",
                "detail": "Review sources or current research basis are unavailable or changed."})

    @api.get("/api/v1/decision-history")
    def decision_history():
        from ...application.product.daily_refresh import read_observation_changes
        decisions = bound_decisions()
        history = build_research_history(
            project,
            published_versions={symbol: row["research_version"]
                                for symbol, row in decisions.items()},
            published_decisions=decisions)
        current = _public(project)
        history["publication"] = _publication_block(project, current)
        snapshot, _ = _load_snapshot(project)
        expected = ((snapshot or {}).get("identity_inputs") or {}).get("current_price_conditions") or {}
        history["observation_changes"] = (
            {**read_observation_changes(project, now=datetime.now(timezone.utc),
                expected_registry_sha256=expected["observed_sha256"]),
             "publication_id": snapshot["publication_id"]}
            if expected.get("observed_sha256") else
            dict(status="UNAVAILABLE", scope="OBSERVATION_ONLY", items=[],
                 action="no_order", formal_eligibility=False))
        return history

    @api.get("/api/v1/daily-public-packet")
    def daily_public_packet():
        """The one frozen public daily decision packet (TL10-RC).

        Every surface serves the same verified snapshot: the bytes the daily
        entry wrote, re-checked against the recorded SHA-256. Only when no
        snapshot has ever been published (a fresh checkout or a test fixture)
        does this fall back to a live composition, and then the response says
        so instead of presenting itself as a frozen version.
        """
        packet, error = _load_snapshot(project)
        if packet is not None:
            return packet
        try:
            live = build_daily_public_packet(project)
        except _STRUCTURE_ERRORS:
            return unavailable_packet(chain_error="PACKET_BUILD_FAILED")
        if live.get("packet_status") == "CURRENT":
            live = dict(live)
            live["snapshot_status"] = "NO_VERIFIED_SNAPSHOT"
            live["snapshot_reason"] = error
            live["blockers"] = list(dict.fromkeys(
                ["PUBLIC_SNAPSHOT_UNAVAILABLE", *(live.get("blockers") or [])]))
        return live

    @api.get("/api/v1/daily-public-snapshot")
    def daily_public_snapshot():
        """Version metadata for the frozen snapshot plus the read-only Excel check."""
        metadata = _snapshot_metadata(project)
        metadata["excel_live"] = _workbook_report(project)
        return metadata

    @api.get("/api/v1/runtime-identity")
    def runtime_version():
        identity = runtime_identity(project, backend_head=backend_head,
                                    backend_module=backend_module,
                                    backend_module_sha=backend_module_sha)
        snapshot = _snapshot_metadata(project)
        identity["publication"] = {
            "status": snapshot["status"],
            "publication_id": snapshot["publication_id"],
            "packet_sha256": snapshot["packet_sha256"],
            "published_at": snapshot["published_at"],
            "dates": snapshot["dates"],
        }
        identity["data_freshness"] = data_freshness(snapshot.get("dates"))
        packet, _ = _load_snapshot(project)
        registry = publication_registry_status(project, packet)
        identity["publication_registry"] = registry
        if registry["status"] != "MATCHED":
            identity["status"] = "MISMATCH"
            identity["reasons"].append("PUBLICATION_REGISTRY_" + registry["status"])
        return identity

    @api.get("/api/v1/research-funnel-status")
    def research_funnel_audit_status():
        """Serve only the hash-verified, read-only W6 audit projection."""
        return research_funnel_status(project)

    @api.get("/api/v1/system/status")
    def system_status(request: Request):
        try:
            authorize(request, session=sessions, port=bound_port)
            portfolio = portfolio_connection(project)
        except LocalAuthorizationError:
            # Whether a private ledger exists is itself private information.
            portfolio = "LOCKED"
        current = _public(project)
        if current is None:
            return {"action": "no_order", "status": "UNAVAILABLE", "publication": "UNAVAILABLE",
                    "portfolio": portfolio}
        return {"action": "no_order", "status": "READ_ONLY",
                "publication": current["pointer"]["current_publication"]["status"],
                "portfolio": portfolio}

    @api.exception_handler(RequestValidationError)
    def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "action": "no_order", "status": "VALIDATION_FAILED",
            "detail": [{"field": ".".join(str(part) for part in item.get("loc", ())),
                        "message": item.get("msg", "invalid")} for item in error.errors()]})

    register_private_routes(
        api, project, sessions=sessions, port=bound_port)
    register_condition_alert_routes(api, project=project, sessions=sessions, port=bound_port)
    register_agent_research_routes(api, project=project, sessions=sessions, port=bound_port)
    register_simulated_journey_routes(api, project=project)
    register_dual_simulated_journey_routes(api, project=project)
    register_simulated_portfolio_routes(api, project=project, port=bound_port)
    def economic_replacement_bindings():
        # Reuse the research-only publication pointer, never the approval registry.
        pointer = project / "config/current-research-drafts.json"
        if not pointer.exists():
            return {}
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        if (not isinstance(payload, dict)
                or payload.get("schema_version") != "current-research-drafts-v1"
                or payload.get("action") != "no_order"
                or not isinstance(payload.get("economic_comparisons", {}), dict)):
            raise ValueError("Invalid research-only comparison pointer")
        return payload.get("economic_comparisons", {})

    register_source_native_economic_routes(
        api, project=project, replacement_bindings=economic_replacement_bindings)
    register_value_policy_routes(api, sessions=sessions, port=bound_port,
        principal_resolver=lambda request: PolicyPrincipal("local-account-owner", frozenset({PERMISSION})),
        get_service=lambda: value_policy_service or ValuePolicyInteractionService(
            project, storage_relative="runtime/value-policy-review/local-account-owner"))

    dist = project / "web" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        bundle = dist.resolve()

        @api.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return {"detail": "Not Found"}
            # The bundler emits flat bundles beside index.html, so every real file
            # is served as-is and only client-side routes fall back to the shell.
            if path and not path.endswith("/"):
                candidate = (bundle / path).resolve()
                if candidate.is_relative_to(bundle) and candidate.is_file():
                    return FileResponse(candidate, headers={"Cache-Control": "no-store"})
            return FileResponse(bundle / "index.html", headers={"Cache-Control": "no-store"})

    return api


app = create_app()
